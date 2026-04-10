# -*- coding: utf-8 -*-
"""
FastAPI 后端服务 - AI 视频生成系统
====================================
提供 REST API 访问核心功能：AI分析、配音生成、视频素材搜索、云端视频生成
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import asyncio
import uuid
import json
import re
import platform
from datetime import datetime

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "auto_video"))  # PyArmor 需要
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "jianying-editor" / "scripts"))

import config
from auto_video.ai_analyzer import AIAnalyzer
from auto_video.tts_generator import TTSGenerator, AudioSegment
from auto_video.video_searcher import VideoSearcher, VideoAsset
from auto_video.asr_generator import SubtitleGenerator, ASRGenerator
from auto_video.jianying_maker import JianYingMaker
from auto_video.license_manager import check_local_license, activate_license, get_machine_id, get_child_codes, generate_invite_codes, load_state
from auto_video.local_clip_matcher import (
    get_chromadb_status, get_vectorization_stats, search_materials,
    generate_local_script, calculate_audio_times, run_vectorization
)

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn


# ==================== Pydantic 请求/响应模型 ====================

class GenerateVideoRequest(BaseModel):
    """云端生成视频请求"""
    script: str = Field(..., min_length=5, description="口播文案")
    voice_key: str = Field(default="female-yujie", description="音色ID")
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速 0.5-2.0")
    enable_bgm: bool = Field(default=False, description="是否启用背景音乐")
    enable_sfx: bool = Field(default=False, description="是否启用音效")
    video_source: str = Field(default="Pexels (推荐)", description="素材来源")
    aspect_ratio: str = Field(default="16:9 (横屏)", description="视频比例")
    drafts_root: Optional[str] = Field(default=None, description="剪映草稿目录")

    # API Keys（可选，优先使用传入的）
    pexels_key: Optional[str] = Field(default=None, description="Pexels API Key")
    pixabay_key: Optional[str] = Field(default=None, description="Pixabay API Key")
    zhipu_key: Optional[str] = Field(default=None, description="智谱 API Key")
    modelverse_key: Optional[str] = Field(default=None, description="MiniMax API Key")
    siliconflow_key: Optional[str] = Field(default=None, description="SiliconFlow API Key")


class AnalyzeScriptRequest(BaseModel):
    """AI文案分析请求"""
    script: str = Field(..., min_length=5, description="口播文案")
    voice_duration: Optional[float] = Field(default=None, description="配音时长（秒）")
    use_zhipu: bool = Field(default=True, description="是否使用智谱AI")


class TTSRequest(BaseModel):
    """配音生成请求"""
    text: str = Field(..., min_length=1, description="配音文本")
    voice_key: str = Field(default="female-yujie", description="音色ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速 0.5-2.0")
    api_key: Optional[str] = Field(default=None, description="MiniMax API Key")


class VideoSearchRequest(BaseModel):
    """视频素材搜索请求"""
    keywords: List[str] = Field(..., min_length=1, description="搜索关键词列表")
    orientation: str = Field(default="landscape", description="视频方向 landscape/portrait")
    max_results: int = Field(default=5, ge=1, le=20, description="最大结果数")
    pexels_key: Optional[str] = Field(default=None, description="Pexels API Key")
    pixabay_key: Optional[str] = Field(default=None, description="Pixabay API Key")


class LicenseActivateRequest(BaseModel):
    """卡密激活请求"""
    license_code: str = Field(..., min_length=1, description="卡密")


class ConfigSaveRequest(BaseModel):
    """保存配置请求"""
    zhipu_key: Optional[str] = None
    modelverse_key: Optional[str] = None
    siliconflow_key: Optional[str] = None
    pexels_key: Optional[str] = None
    pixabay_key: Optional[str] = None
    drafts_root: Optional[str] = None
    local_materials_path: Optional[str] = None
    voice_key: str = "female-yujie"
    voice_speed: float = 1.0
    enable_bgm: bool = False
    enable_sfx: bool = False
    skip_keywords: List[str] = []


class VideoJobResponse(BaseModel):
    """视频生成任务响应"""
    job_id: str
    status: str
    message: str
    progress: int = 0
    steps: List[Dict[str, Any]] = []
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ==================== 任务状态存储 ====================

class JobStore:
    """内存任务存储（生产环境建议用 Redis）"""

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    def create(self) -> str:
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "steps": [],
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
        self._subscribers[job_id] = []
        return job_id

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        if job_id in self._subscribers:
            self._subscribers[job_id].append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue):
        if job_id in self._subscribers and queue in self._subscribers[job_id]:
            self._subscribers[job_id].remove(queue)

    async def notify(self, job_id: str, event_type: str, data: Dict[str, Any]):
        if job_id in self._subscribers:
            for q in self._subscribers[job_id]:
                try:
                    await q.put({"type": event_type, "data": data})
                except Exception:
                    pass

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        if job_id in self._jobs:
            self._jobs[job_id].update(kwargs)

    def add_step(self, job_id: str, step: str, message: str, progress: int, detail: str = None):
        if job_id in self._jobs:
            step_data = {
                "step": step,
                "message": message,
                "progress": progress,
                "timestamp": datetime.now().isoformat(),
            }
            if detail is not None:
                step_data["detail"] = detail
            self._jobs[job_id]["steps"].append(step_data)
            self._jobs[job_id]["progress"] = progress
            asyncio.create_task(self.notify(job_id, "step", step_data))

    def set_status(self, job_id: str, status: str, progress: int = None):
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = status
            if progress is not None:
                self._jobs[job_id]["progress"] = progress

    def set_result(self, job_id: str, result: Dict[str, Any]):
        if job_id in self._jobs:
            self._jobs[job_id]["result"] = result
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["progress"] = 100
            asyncio.create_task(self.notify(job_id, "result", result))

    def set_error(self, job_id: str, error: str):
        if job_id in self._jobs:
            self._jobs[job_id]["error"] = error
            self._jobs[job_id]["status"] = "failed"
            asyncio.create_task(self.notify(job_id, "error", {"error": error}))


job_store = JobStore()
progress_logs: List[Dict[str, Any]] = []


# ==================== FastAPI 应用 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动和关闭事件"""
    print("🚀 AI视频生成系统 API 服务启动")
    print(f"   项目路径: {PROJECT_ROOT}")
    print(f"   剪映草稿目录: {config.JIANYING_DRAFTS_ROOT}")
    yield
    print("👋 API 服务关闭")


app = FastAPI(
    title="AI 视频生成系统 API",
    description="""
提供以下核心功能：
- **AI分析** - 对文案进行语义分析，提取关键词、场景类型、情绪风格
- **配音生成** - 调用 MiniMax API 生成配音
- **视频搜索** - 从 Pexels/Pixabay 搜索视频素材
- **云端视频生成** - 端到端生成剪映草稿
- **会员管理** - 卡密激活与状态查询
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# 挂载静态文件目录（图片资源）
PROJECT_ROOT = Path(__file__).parent
app.mount("/img", StaticFiles(directory=str(PROJECT_ROOT / "img")), name="img")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 辅助函数 ====================

def _load_user_config() -> dict:
    """从 user_config.json 加载配置"""
    cfg_file = PROJECT_ROOT / "user_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _merge_api_keys(
    pexels_key=None, pixabay_key=None, zhipu_key=None,
    modelverse_key=None, siliconflow_key=None
):
    """合并 API Keys，优先使用传入值 > user_config.json > 环境变量"""
    user_cfg = _load_user_config()
    return {
        "pexels_key": pexels_key or user_cfg.get("pexels_key") or config.PEXELS_API_KEY,
        "pixabay_key": pixabay_key or user_cfg.get("pixabay_key") or config.PIXABAY_API_KEY,
        "zhipu_key": zhipu_key or user_cfg.get("zhipu_key") or config.ZHIPU_API_KEY,
        "modelverse_key": modelverse_key or user_cfg.get("modelverse_key") or config.MODELVERSE_API_KEY,
        "siliconflow_key": siliconflow_key or user_cfg.get("siliconflow_key") or config.SILICONFLOW_API_KEY,
        "drafts_root": user_cfg.get("drafts_root") or config.JIANYING_DRAFTS_ROOT,
    }


def _normalize_script(text: str) -> tuple:
    """预处理文案，返回 (句子列表, 完整文案)"""
    text = text.replace(',', '，').replace('!', '！').replace('?', '？').replace('.', '。')
    sentences = re.split(r'[。！？；\n]+', text)
    all_texts = [s.strip() for s in sentences if s.strip()]

    MIN_LEN, MAX_LEN = 10, 30
    temp_texts = []
    for t in all_texts:
        if len(t) > MAX_LEN:
            parts = re.split(r'[，]', t)
            temp_texts.extend([p.strip() for p in parts if p.strip()])
        else:
            temp_texts.append(t)

    final_texts = []
    for t in temp_texts:
        if not final_texts:
            final_texts.append(t)
        elif len(final_texts[-1]) < MIN_LEN:
            final_texts[-1] = final_texts[-1] + "，" + t
        elif len(t) < MIN_LEN and len(final_texts[-1]) < MAX_LEN:
            final_texts[-1] = final_texts[-1] + "，" + t
        else:
            final_texts.append(t)

    return final_texts, "。".join(final_texts)


# ==================== 核心业务逻辑 ====================

async def _run_cloud_generation(job_id: str, req: GenerateVideoRequest):
    """后台执行云端视频生成（完整流程）"""
    try:
        job_store.set_status(job_id, "running", 0)
        job_store.add_step(job_id, "init", "开始生成视频", 0)

        # 合并 API Keys
        keys = _merge_api_keys(
            req.pexels_key, req.pixabay_key, req.zhipu_key,
            req.modelverse_key, req.siliconflow_key
        )

        # ===== Step 1: 文案预处理 =====
        job_store.add_step(job_id, "analyze", "📝 分析文案", 5)
        all_texts, full_script = _normalize_script(req.script)
        job_store.add_step(job_id, "analyze", f"📝 文案共 {len(all_texts)} 句，{len(full_script)} 字", 10)

        # ===== Step 2: TTS 配音 =====
        job_store.add_step(job_id, "tts", "🎤 生成配音中", 15)
        tts_gen = TTSGenerator(api_key=keys["modelverse_key"])
        full_audio = await asyncio.to_thread(
            tts_gen.generate,
            full_script,
            req.voice_key,
            speed=req.voice_speed,
        )
        if not full_audio:
            job_store.set_error(job_id, "配音生成失败，请检查 MiniMax API Key")
            return

        total_audio_duration = full_audio.duration
        job_store.add_step(job_id, "tts", f"✅ 配音完成: {total_audio_duration:.1f}秒", 25)

        # ===== Step 3: 字幕生成 =====
        job_store.add_step(job_id, "subtitle", "📄 生成字幕", 30)

        subtitle_segments = []
        segment_times = []
        subtitle_path = None

        # 优先使用 MiniMax 原生字幕时间戳
        if full_audio.subtitle_url:
            job_store.add_step(job_id, "subtitle", "📄 生成字幕", 30,
                detail="📥 正在下载 MiniMax 字幕时间戳...")
            tts_gen = TTSGenerator(api_key=keys["modelverse_key"])
            json_path = await asyncio.to_thread(tts_gen.download_subtitle, full_audio.subtitle_url)
            if json_path:
                srt_gen = SubtitleGenerator()
                # 用 MiniMax 真实块时间戳分配 all_texts 对应的 segment_times，
                # 同时生成 sentence 级 subtitle_segments 用于 SRT
                segment_times, subtitle_segments = srt_gen.align_minimax_to_segments(
                    json_path, all_texts, total_audio_duration
                )
                if subtitle_segments:
                    srt_content = srt_gen._create_srt_from_segments(subtitle_segments)
                    out_path = config.SUBTITLES_DIR / f"subtitle_{int(datetime.now().timestamp())}.srt"
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    subtitle_path = str(out_path)
                    job_store.add_step(job_id, "subtitle", f"✅ 字幕生成完成: {len(subtitle_segments)} 句", 35,
                        detail=f"MiniMax 时间戳 + 标点分割，{len(segment_times)} 个视频片段")

        # Fallback：纯字数比例分配
        if not subtitle_segments:
            total_chars = sum(len(s) for s in all_texts)
            current_ms = 0

            for seg_idx, text in enumerate(all_texts):
                seg_chars = len(text)
                seg_dur_ms = (seg_chars / total_chars) * total_audio_duration * 1000 if total_chars > 0 else 0
                seg_start_ms = current_ms
                seg_end_ms = seg_start_ms + seg_dur_ms

                parts = re.split(r'([。！？，；、：.!?])', text)
                sentences = []
                for i in range(0, len(parts) - 1, 2):
                    seg = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
                    seg = seg.strip()
                    if seg:
                        sentences.append(seg)
                if len(parts) >= 1 and parts[-1].strip():
                    sentences.append(parts[-1].strip())
                if not sentences:
                    sentences = [text]

                part_chars_list = [len(p) for p in sentences]
                total_part_chars = sum(part_chars_list)

                for pi, part_text in enumerate(sentences):
                    part_chars = part_chars_list[pi]
                    part_dur_ms = (part_chars / total_part_chars) * seg_dur_ms if total_part_chars > 0 else 0
                    part_dur_ms = max(part_dur_ms, 100)
                    display_text = part_text.rstrip("，。！？,.!?;；、")
                    if display_text:
                        subtitle_segments.append({
                            "text": display_text,
                            "start": current_ms / 1000.0,
                            "end": (current_ms + part_dur_ms) / 1000.0
                        })
                    current_ms += part_dur_ms

                segment_times.append({
                    "text": text,
                    "start": seg_start_ms / 1000.0,
                    "end": seg_end_ms / 1000.0,
                    "duration": seg_dur_ms / 1000.0
                })

            if subtitle_segments:
                subtitle_segments[-1]["end"] = total_audio_duration
            if segment_times:
                segment_times[-1]["end"] = total_audio_duration
                segment_times[-1]["duration"] = segment_times[-1]["end"] - segment_times[-1]["start"]

            srt_gen = SubtitleGenerator()
            srt_content = srt_gen._create_srt_from_segments(subtitle_segments)
            out_path = config.SUBTITLES_DIR / f"subtitle_{int(datetime.now().timestamp())}.srt"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            subtitle_path = str(out_path)
            job_store.add_step(job_id, "subtitle", f"✅ 字幕生成完成: {len(subtitle_segments)} 句", 35,
                detail=f"总时长 {total_audio_duration:.1f}s，按字数比例分配")

        video_segments = segment_times  # 直接复用，8 个片段

        # ===== Step 5: AI 关键词分析 =====
        job_store.add_step(job_id, "ai", "🤖 AI 分析关键词", 45)
        analyzer = AIAnalyzer(use_zhipu=bool(keys["zhipu_key"]))
        if keys["zhipu_key"]:
            analyzer.zhipu_api_key = keys["zhipu_key"]
        video_segments, cached_emotion, cached_scene_type = await asyncio.to_thread(
            analyzer.generate_keywords_for_segments, video_segments, full_script
        )
        # 每片段关键词子日志
        for idx, seg in enumerate(video_segments):
            kws = seg.get("keywords_en", [])
            kw_str = ", ".join(kws) if kws else "（未识别）"
            full_text = seg.get("text", "")
            job_store.add_step(job_id, "ai", f"🤖 AI 分析关键词", 48,
                detail=f"片段 {idx+1}/{len(video_segments)}: 「{full_text}」→ {kw_str}")
        job_store.add_step(job_id, "ai", f"✅ 情绪: {cached_emotion}，场景: {cached_scene_type}", 50)

        # ===== Step 6: 搜索视频素材 =====
        job_store.add_step(job_id, "search", "🔍 搜索视频素材", 55)
        searcher = VideoSearcher(keys["pexels_key"], keys["pixabay_key"])
        is_vertical = "9:16" in req.aspect_ratio
        video_orientation = "portrait" if is_vertical else "landscape"
        search_results = {}

        # 并发搜索（最大4个并发）
        search_semaphore = asyncio.Semaphore(4)

        async def search_one(i, seg):
            async with search_semaphore:
                kw = seg.get("keywords_en", ["nature landscape"])
                kw_str = kw[0] if kw else "nature landscape"
                job_store.add_step(job_id, "search", f"🔍 搜索视频素材", 55,
                    detail=f"片段 {i+1}/{len(video_segments)}: 「{kw_str}」搜索中...")
                if "Pexels" in req.video_source and "Pixabay" not in req.video_source:
                    videos = await asyncio.to_thread(
                        searcher.search_pexels, kw, per_page=5, orientation=video_orientation
                    )
                elif "Pixabay" in req.video_source and "Pexels" not in req.video_source:
                    videos = await asyncio.to_thread(
                        searcher.search_pixabay, kw, per_page=5, orientation=video_orientation
                    )
                else:
                    videos = await asyncio.to_thread(
                        searcher.search, kw, max_results=5, orientation=video_orientation
                    )
                job_store.add_step(job_id, "search", f"🔍 搜索视频素材", 60,
                    detail=f"片段 {i+1}/{len(video_segments)}: 「{kw_str}」✓ 找到{len(videos)}个")
                return i, videos

        search_tasks = [search_one(i, seg) for i, seg in enumerate(video_segments)]
        search_responses = await asyncio.gather(*search_tasks)
        for i, videos in search_responses:
            search_results[i] = videos

        total_found = sum(len(v) for v in search_results.values())
        job_store.add_step(job_id, "search", f"✅ 搜索完成，共找到 {total_found} 个素材", 65,
            detail=f"全部 {len(video_segments)} 个片段搜索完毕，共计 {total_found} 个视频素材")

        # ===== Step 7: 下载素材 =====
        job_store.add_step(job_id, "download", "📥 下载视频素材", 70)
        selected_videos = []
        used_ids = set()

        for i, seg in enumerate(video_segments):
            videos = search_results.get(i, [])
            required = seg["duration"]  # 直接用字幕片段时长，不加 buffer
            sel = None
            for v in videos:
                vid = v.id if hasattr(v, 'id') else v.url
                if vid not in used_ids:
                    v_dur = v.duration if hasattr(v, 'duration') else 0
                    if v_dur >= required:
                        sel = v
                        used_ids.add(vid)
                        break
            if not sel:
                for v in videos:
                    vid = v.id if hasattr(v, 'id') else v.url
                    if vid not in used_ids:
                        sel = v
                        used_ids.add(vid)
                        break
            selected_videos.append((i, sel))
            basename = os.path.basename(sel.url) if sel and hasattr(sel, 'url') else (sel.id if sel else "无")
            job_store.add_step(job_id, "download", f"📥 下载视频素材", 70,
                detail=f"片段 {i+1}/{len(video_segments)}: 选中 「{basename}」(需{required:.1f}s)")

        to_dl = [(i, v) for i, v in selected_videos if v is not None]
        dl_map = {}

        if to_dl:
            unique_v = {}
            for i, v in to_dl:
                vid = v.id if hasattr(v, 'id') else v.url
                if vid not in unique_v:
                    unique_v[vid] = v
            v_list = list(unique_v.values())
            total_to_dl = len(v_list)

            # 多线程并发下载（最大4个并发）
            semaphore = asyncio.Semaphore(4)

            async def download_one(v_idx, v):
                async with semaphore:
                    basename = os.path.basename(v.url) if hasattr(v, 'url') else v.id
                    job_store.add_step(job_id, "download", f"📥 下载视频素材", 70,
                        detail=f"📥 [{v_idx+1}/{total_to_dl}] 下载中: {basename}...")
                    result = await asyncio.to_thread(searcher.download_video, v)
                    if result and not isinstance(result, Exception):
                        job_store.add_step(job_id, "download", f"📥 下载视频素材", 70,
                            detail=f"✅ [{v_idx+1}/{total_to_dl}] 下载完成: {os.path.basename(result)}")
                    return v_idx, v, result

            dl_results = await asyncio.gather(*[download_one(i, v) for i, v in enumerate(v_list)], return_exceptions=True)
            for item in dl_results:
                if item and not isinstance(item, Exception):
                    idx, v, result = item
                    if result and not isinstance(result, Exception):
                        vid = v.id if hasattr(v, 'id') else v.url
                        dl_map[vid] = {"path": result, "duration": v.duration}

        video_data = []
        last_path = None
        for i, seg in enumerate(video_segments):
            v_path = None
            for idx, v in selected_videos:
                if idx == i and v is not None:
                    vid = v.id if hasattr(v, 'id') else v.url
                    info = dl_map.get(vid)
                    if info:
                        v_path = info["path"]
                        last_path = v_path
                        break
            if not v_path and last_path:
                v_path = last_path
            if v_path:
                # 视频结束时间 = 下一个视频的开始时间（首尾相接，无间隙）
                if i < len(video_segments) - 1:
                    next_start = video_segments[i + 1]["start"]
                else:
                    next_start = seg["start"] + seg["duration"]
                video_data.append({
                    "path": v_path, "start": seg["start"],
                    "duration": next_start - seg["start"], "text": seg["text"]
                })

        print(f"[DEBUG] 最终 video_data: {len(video_data)} 个片段")
        for j, vd in enumerate(video_data):
            print(f"[DEBUG]   片段{j+1}: {os.path.basename(vd['path'])} start={vd['start']:.3f}s dur={vd['duration']:.3f}s")

        if not video_data:
            job_store.set_error(job_id, "未找到任何视频素材")
            return
            if not v_path and last_path:
                v_path = last_path
            if v_path:
                video_data.append({
                    "path": v_path, "start": seg["start"],
                    "duration": seg["duration"], "text": seg["text"]
                })

        if not video_data:
            job_store.set_error(job_id, "未找到任何视频素材")
            return

        job_store.add_step(job_id, "download", f"✅ 准备了 {len(video_data)} 个视频片段", 80)

        # ===== Step 8: 组装剪映草稿 =====
        title = req.script[:10].replace("。", "").replace("！", "").replace("？", "").strip() or "API生成视频"
        drafts_root = req.drafts_root or config.JIANYING_DRAFTS_ROOT

        maker = JianYingMaker(project_name=title, drafts_root=drafts_root)

        job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 85,
            detail="📦 开始组装素材到剪映...")

        config_data = {
            "title": title,
            "videos": [v["path"] for v in video_data],
            "video_start_times": [f"{v['start']:.6f}s" for v in video_data],
            "video_durations": [v["duration"] for v in video_data],
            "use_intelligent_tts": False,
            "full_audio_path": full_audio.audio_path,
            "subtitle_path": subtitle_path,
            "full_script": full_script,
            "total_duration": total_audio_duration,
            "segments": [{"text": s["text"], "duration": s["duration"]} for s in video_segments],
        }

        # BGM
        bgm_config = {"enabled": False}
        if req.enable_bgm:
            job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 85,
                detail="🎵 正在推荐背景音乐...")
            bgm_result = await asyncio.to_thread(
                analyzer.recommend_bgm, full_script,
                emotion=cached_emotion, scene_type=cached_scene_type
            )
            bgm_title = bgm_result.get("title", "未知")
            bgm_reason = bgm_result.get("reason", "")
            job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 87,
                detail=f"🎵 背景音乐:「{bgm_title}」- {bgm_reason}")
            bgm_config = {
                "enabled": True,
                "music_id": bgm_result.get("music_id"),
                "title": bgm_title,
                "reason": bgm_reason,
            }
        config_data["bgm_config"] = bgm_config

        # 音效
        sound_effects = []
        if req.enable_sfx:
            job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 88,
                detail="🔊 正在推荐音效...")
            sfx_result = await asyncio.to_thread(
                analyzer.recommend_sound_effects, full_script, video_segments
            )
            if sfx_result:
                for sfx in sfx_result:
                    sfx_time = sfx.get("time", 0)
                    sfx_title = sfx.get("title", "未知")
                    job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 89,
                        detail=f"🔊 音效:「{sfx_title}」@ {sfx_time:.1f}s")
                sound_effects = sfx_result
            else:
                job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 89,
                    detail="🔊 未匹配到合适音效，跳过")
        elif not req.enable_bgm:
            # BGM 和 SFX 都未开启，合并为一条
            job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 89,
                detail="🎵 BGM 未开启 | 🔊 音效未开启，已跳过")

        config_data["sound_effects"] = sound_effects

        job_store.add_step(job_id, "jianying", "🎬 创建剪映草稿", 92,
            detail="⚙️ 正在生成剪映草稿，这可能需要几十秒...")
        await asyncio.to_thread(maker.create_from_config, config_data)

        job_store.add_step(job_id, "done", f"🎉 生成完成！请打开剪映查看草稿: {title}", 100)
        job_store.set_result(job_id, {
            "title": title,
            "draft_path": str(Path(drafts_root) / maker.project_name),
            "video_count": len(video_data),
            "audio_duration": total_audio_duration,
            "subtitle_count": len(subtitle_segments),
            "emotion": cached_emotion,
            "scene_type": cached_scene_type,
        })

    except Exception as e:
        import traceback
        job_store.set_error(job_id, f"{str(e)}\n{traceback.format_exc()}")


# ==================== API 路由 ====================

@app.get("/", tags=["首页"])
async def serve_index():
    """返回前端页面"""
    return FileResponse(str(PROJECT_ROOT / "index.html"), media_type="text/html")


@app.get("/api/index.html", tags=["首页"])
async def serve_index_html():
    """返回前端页面（备用路径）"""
    return FileResponse(str(PROJECT_ROOT / "index.html"), media_type="text/html")
async def root():
    """服务健康检查"""
    return {
        "service": "AI 视频生成系统 API",
        "version": "1.0.0",
        "status": "running",
        "project_root": str(PROJECT_ROOT),
        "jianying_drafts_root": config.JIANYING_DRAFTS_ROOT,
    }


@app.get("/health", tags=["健康检查"])
async def health():
    """健康检查"""
    license_info = check_local_license()
    return {
        "status": "healthy",
        "license": {
            "activated": license_info.get("activated", False),
            "is_permanent": license_info.get("is_permanent", False),
            "remaining_days": license_info.get("remaining_days", 0),
        },
        "machine_id": get_machine_id(),
    }


# ----- AI 分析 -----

@app.post("/api/analyze", tags=["AI 分析"])
async def analyze_script(req: AnalyzeScriptRequest):
    """
    AI 文案分析

    对口播文案进行语义分析，返回：
    - 关键词列表
    - 场景类型
    - 情绪风格
    - 分段后的字幕片段（含时间戳）
    """
    analyzer = AIAnalyzer(use_zhipu=req.use_zhipu)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: analyzer.analyze(req.script, req.voice_duration)
    )

    return {
        "keywords": result.keywords,
        "scene_type": result.scene_type,
        "emotion": result.emotion,
        "segments": [
            {
                "text": seg.text,
                "duration": seg.duration,
                "keywords": seg.keywords,
                "start_time": seg.start_time,
            }
            for seg in result.segments
        ],
    }


# ----- 配音生成 -----

@app.post("/api/tts", tags=["配音生成"])
async def generate_tts(req: TTSRequest):
    """
    生成配音

    调用 MiniMax API 生成配音音频文件
    """
    keys = _merge_api_keys()
    modelverse_key = req.api_key or keys["modelverse_key"]

    if not modelverse_key:
        raise HTTPException(status_code=400, detail="MiniMax API Key 未配置")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: TTSGenerator(api_key=modelverse_key).generate(
            text=req.text,
            voice=req.voice_key,
            speed=req.speed,
        )
    )

    if not result:
        raise HTTPException(status_code=500, detail="配音生成失败")

    return {
        "text": result.text,
        "audio_path": result.audio_path,
        "duration": result.duration,
        "subtitle_url": result.subtitle_url,
    }


# ----- 视频素材搜索 -----

@app.post("/api/search", tags=["视频搜索"])
async def search_videos(req: VideoSearchRequest):
    """
    搜索视频素材

    从 Pexels / Pixabay 搜索视频素材（仅搜索不下载）
    """
    keys = _merge_api_keys(req.pexels_key, req.pixabay_key)
    searcher = VideoSearcher(keys["pexels_key"], keys["pixabay_key"])

    loop = asyncio.get_event_loop()
    videos = await loop.run_in_executor(
        None,
        lambda: searcher.search(
            keywords=req.keywords,
            max_results=req.max_results,
            orientation=req.orientation,
        )
    )

    return {
        "keywords": req.keywords,
        "orientation": req.orientation,
        "count": len(videos),
        "videos": [
            {
                "id": v.id,
                "source": v.source,
                "url": v.url,
                "thumbnail": v.thumbnail,
                "width": v.width,
                "height": v.height,
                "duration": v.duration,
                "photographer": v.photographer,
                "keywords": v.keywords,
            }
            for v in videos
        ],
    }


# ----- 云端视频生成 -----

@app.post("/api/generate", response_model=VideoJobResponse, tags=["视频生成"])
async def generate_video(req: GenerateVideoRequest, background_tasks: BackgroundTasks):
    """
    云端生成视频（异步）

    完整流程：文案分析 → 配音生成 → 字幕生成 → 素材搜索 → 下载 → 剪映草稿
    返回 job_id 用于查询进度和结果
    """
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="文案不能为空")

    job_id = job_store.create()
    job_store.update(job_id, message="任务已创建")

    background_tasks.add_task(_run_cloud_generation, job_id, req)

    return VideoJobResponse(
        job_id=job_id,
        status="pending",
        message="视频生成任务已创建",
        progress=0,
    )


@app.get("/api/jobs/{job_id}", response_model=VideoJobResponse, tags=["视频生成"])
async def get_job_status(job_id: str):
    """查询任务状态和结果"""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    return VideoJobResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=(job.get("result", {}).get("title", "") or "") if job.get("result") else (job.get("error") or ""),
        progress=job.get("progress", 0),
        steps=job.get("steps", []),
        result=job.get("result"),
        error=job.get("error"),
    )


@app.get("/api/jobs/{job_id}/stream", tags=["视频生成"])
async def stream_job_status(job_id: str):
    """
    SSE 推送：实时接收任务日志更新
    事件类型: step / result / error
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        queue = job_store.subscribe(job_id)

        # 先发送当前所有 steps
        for step in job.get("steps", []):
            yield f"data: {json.dumps({'type': 'step', 'data': step})}\n\n"

        # 如果已完成或失败，直接发送最终状态
        if job["status"] in ("completed", "failed"):
            if job["status"] == "completed":
                yield f"data: {json.dumps({'type': 'result', 'data': job.get('result', {})})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': {'error': job.get('error', '')}})}\n\n"
            return

        # 持续等待新事件
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("result", "error"):
                    break
            except asyncio.TimeoutError:
                # 心跳
                yield f": heartbeat\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ----- 会员管理 -----

@app.get("/api/license", tags=["会员管理"])
async def get_license_status():
    """查询当前会员状态（含邀请信息和子码列表）"""
    result = check_local_license()
    state = load_state()
    my_code = state.get("code", "")
    machine_id = get_machine_id()

    # 子码列表和邀请统计
    child_codes = []
    remaining_codes = 0
    if my_code:
        child_codes = get_child_codes(my_code)
        existing_count = len(child_codes)
        remaining_codes = max(0, 5 - existing_count)

    return {
        "activated": result.get("activated", False),
        "is_permanent": result.get("is_permanent", False),
        "remaining_days": result.get("remaining_days", 0),
        "expire_at": result.get("expire_at"),
        "machine_id": machine_id,
        "device_name": platform.node() or "未知设备",
        "my_code": my_code,
        "child_codes": child_codes,
        "remaining_codes": remaining_codes,
    }


@app.post("/api/license/activate", tags=["会员管理"])
async def activate(req: LicenseActivateRequest):
    """激活卡密"""
    result = activate_license(req.license_code)
    if result.get("success"):
        return {
            "success": True,
            "message": f"激活成功！{' +' + str(result.get('days_rewarded', 0)) + '天' if result.get('days_rewarded') else '永久会员'}",
            "days_rewarded": result.get("days_rewarded"),
            "is_permanent": result.get("is_permanent", False),
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "激活失败"))


@app.post("/api/license/generate", tags=["会员管理"])
async def generate_child_code():
    """为当前用户生成新的子码"""
    state = load_state()
    my_code = state.get("code", "")

    if not my_code:
        raise HTTPException(status_code=400, detail="请先激活卡密")

    codes, error = generate_invite_codes(my_code, count=1)

    if error:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "code": codes[0] if codes else None,
        "message": "子码生成成功" if codes else "生成失败"
    }


# ----- 配置信息 -----

@app.get("/api/config/voices", tags=["配置信息"])
async def list_voices():
    """获取可用音色列表"""
    return {
        "voices": [
            {"key": k, "name": v}
            for k, v in config.TTS_VOICES.items()
        ]
    }


@app.get("/api/config/scene-types", tags=["配置信息"])
async def list_scene_types():
    """获取支持的场景类型"""
    return {"scene_types": list(config.SCENE_TYPE_KEYWORDS.keys())}


@app.get("/api/config/emotions", tags=["配置信息"])
async def list_emotions():
    """获取支持的情绪类型"""
    return {"emotions": list(config.EMOTION_KEYWORDS.keys())}


# ==================== 配置管理 ====================

CONFIG_FILE = PROJECT_ROOT / "user_config.json"


def load_config() -> dict:
    """加载用户配置"""
    defaults = {
        "voice_key": "female-yujie",
        "voice_speed": 1.0,
        "enable_bgm": False,
        "enable_sfx": False,
        "skip_keywords": [],
        "pexels_key": config.PEXELS_API_KEY,
        "pixabay_key": config.PIXABAY_API_KEY,
        "zhipu_key": config.ZHIPU_API_KEY,
        "modelverse_key": config.MODELVERSE_API_KEY,
        "siliconflow_key": config.SILICONFLOW_API_KEY,
        "drafts_root": config.JIANYING_DRAFTS_ROOT,
        "local_materials_path": config.LOCAL_MATERIALS_PATH,
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update({k: v for k, v in saved.items() if v})
        except Exception:
            pass
    return defaults


@app.get("/api/config", tags=["配置管理"])
async def get_config():
    """获取当前配置"""
    return load_config()


@app.post("/api/config", tags=["配置管理"])
async def save_config(req: ConfigSaveRequest):
    """保存配置"""
    cfg = req.model_dump()
    # 清理空值
    cfg = {k: v for k, v in cfg.items() if v is not None}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "配置已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


# ==================== 静态文件 ====================

@app.get("/api/output/audio/{filename}", tags=["文件"])
async def download_audio(filename: str):
    """下载生成的配音文件"""
    audio_path = config.AUDIO_DIR / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(audio_path),
        filename=filename,
        media_type="audio/mpeg",
    )


@app.get("/api/output/subtitle/{filename}", tags=["文件"])
async def download_subtitle(filename: str):
    """下载生成的字幕文件"""
    sub_path = config.SUBTITLES_DIR / filename
    if not sub_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(sub_path),
        filename=filename,
        media_type="application/x-subrip",
    )


# ==================== 本地模式 API ====================

@app.get("/api/local/status", tags=["本地模式"])
async def get_local_status():
    """获取本地向量库状态"""
    try:
        stats = get_vectorization_stats()
        status = get_chromadb_status()
        return {
            "stats": stats,
            "status": status,
            "ready": status and stats.get("total", 0) > 0
        }
    except Exception as e:
        return {"stats": {}, "status": None, "ready": False, "error": str(e)}


class ScanFolderRequest(BaseModel):
    materials_path: str


@app.post("/api/local/scan-folder", tags=["本地模式"])
async def scan_folder(req: ScanFolderRequest):
    """扫描素材库文件夹，统计实际文件数量"""
    from config import SUPPORTED_IMAGE_EXTS, SUPPORTED_VIDEO_EXTS

    path = req.materials_path
    if not path or not os.path.exists(path):
        return {"error": "素材库路径不存在", "folder_videos": 0, "folder_images": 0}

    image_count = 0
    video_count = 0

    for root, dirs, files in os.walk(path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_IMAGE_EXTS:
                image_count += 1
            elif ext in SUPPORTED_VIDEO_EXTS:
                video_count += 1

    return {
        "folder_videos": video_count,
        "folder_images": image_count,
        "folder_total": video_count + image_count,
    }


class VectorizeRequest(BaseModel):
    materials_path: str
    scene_threshold: float = 27.0
    min_scene_duration: float = 1.0
    skip_keywords: List[str] = []


@app.post("/api/local/vectorize", tags=["本地模式"])
async def start_vectorization(req: VectorizeRequest, background_tasks: BackgroundTasks):
    """启动素材向量化（后台运行）"""
    job_id = str(uuid.uuid4())

    def progress_callback(msg):
        progress_logs.append({"job_id": job_id, "message": msg, "timestamp": datetime.now().isoformat()})

    async def run_in_background():
        try:
            result = run_vectorization(
                materials_path=req.materials_path,
                progress_callback=progress_callback,
                skip_keywords=req.skip_keywords if req.skip_keywords else None,
            )
            progress_logs.append({"job_id": job_id, "message": f"DONE:{json.dumps(result)}", "timestamp": datetime.now().isoformat()})
        except Exception as e:
            progress_logs.append({"job_id": job_id, "message": f"ERROR:{str(e)}", "timestamp": datetime.now().isoformat()})

    background_tasks.add_task(run_in_background)
    return {"job_id": job_id, "status": "started"}


@app.get("/api/local/vectorize/{job_id}", tags=["本地模式"])
async def get_vectorize_progress(job_id: str):
    """获取向量化进度"""
    logs = [l for l in progress_logs if l["job_id"] == job_id]
    last_msg = logs[-1]["message"] if logs else ""
    is_done = last_msg.startswith("DONE:") or last_msg.startswith("ERROR:")
    result = None
    error = None
    if last_msg.startswith("DONE:"):
        try:
            result = json.loads(last_msg[5:])
        except:
            result = last_msg[5:]
    elif last_msg.startswith("ERROR:"):
        error = last_msg[6:]
    return {
        "job_id": job_id,
        "logs": [{"message": l["message"], "timestamp": l["timestamp"]} for l in logs],
        "status": "completed" if is_done else "running",
        "result": result,
        "error": error
    }


class SemanticSearchRequest(BaseModel):
    query: str
    media_type: Optional[str] = None
    top_k: int = 5
    enhanced: bool = True


@app.post("/api/local/search", tags=["本地模式"])
async def semantic_search(req: SemanticSearchRequest):
    """语义搜索素材"""
    from auto_video.local_clip_matcher import search_materials

    try:
        results = search_materials(
            visual_prompt=req.query,
            top_k=req.top_k,
            media_type=req.media_type,
            enhanced=req.enhanced
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/local/open-file", tags=["本地模式"])
async def open_file_location(req: Request):
    """打开文件所在位置（Windows explorer）"""
    try:
        body = await req.json()
        file_path = body.get("path", "")
        if not file_path:
            return {"error": "路径为空"}

        import subprocess
        import platform

        # 获取目录路径
        directory = os.path.dirname(file_path)
        if not directory:
            return {"error": "无法获取目录"}

        if platform.system() == "Windows":
            subprocess.Popen(['explorer', '/select,', file_path])
        elif platform.system() == "Darwin":
            subprocess.Popen(['open', '-R', file_path])
        else:
            subprocess.Popen(['xdg-open', directory])

        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


class LocalGenerateRequest(BaseModel):
    script: str
    voice_key: str = "female-yujie"
    voice_speed: float = 1.0
    enable_bgm: bool = False
    enable_sfx: bool = False
    target_duration: int = 30
    top_k: int = 3
    match_type: str = "both"
    aspect_ratio: str = "16:9 (横屏)"
    drafts_root: Optional[str] = None
    zhipu_key: Optional[str] = None
    modelverse_key: Optional[str] = None
    siliconflow_key: Optional[str] = None


@app.post("/api/local/generate", tags=["本地模式"])
async def generate_local_video(req: LocalGenerateRequest, background_tasks: BackgroundTasks):
    """生成本地视频（后台运行）"""
    job_id = job_store.create()
    job_store.update(job_id, message="任务已创建", status="running")

    async def run_in_background():
        try:
            job_store.add_step(job_id, "script", "📝 生成分镜脚本...", 10)

            # Merge API keys
            merged_keys = _merge_api_keys({})
            zhipu_key = req.zhipu_key or merged_keys.get("zhipu_key") or config.ZHIPU_API_KEY
            modelverse_key = req.modelverse_key or merged_keys.get("modelverse_key") or config.MODELVERSE_API_KEY
            siliconflow_key = req.siliconflow_key or merged_keys.get("siliconflow_key") or config.SILICONFLOW_API_KEY

            # Step 1: Generate script
            job_store.add_step(job_id, "script", "🤖 正在调用智谱AI生成脚本...", 10)
            script_data = generate_local_script(req.script, zhipu_key, target_duration=req.target_duration)
            if not script_data:
                job_store.update(job_id, status="failed", error="脚本生成失败，请检查智谱 API Key")
                job_store.add_step(job_id, "script", "❌ 脚本生成失败", 0)
                return

            # 详细打印智谱AI输出的每个片段（visual_prompt画面描述）
            for idx, seg in enumerate(script_data):
                content_preview = seg.get("content", "")[:30]
                visual_preview = seg.get("visual_prompt", "")[:50]
                job_store.add_step(job_id, "script", f"📝 智谱AI输出片段", 20,
                    detail=f"片段 {idx+1}/{len(script_data)}: 「{content_preview}...」\n    🎬 画面:「{visual_preview}...」")
            job_store.add_step(job_id, "script", f"✅ 分镜脚本生成完成: {len(script_data)} 个片段", 20)
            job_store.add_step(job_id, "tts", "🎤 正在合成配音...", 30)

            # Step 2: TTS
            full_text = "。".join([s.get("content", "") for s in script_data])
            tts = TTSGenerator(api_key=modelverse_key)
            job_store.add_step(job_id, "tts", "🎤 正在合成配音...", 30,
                detail="📡 正在请求 MiniMax TTS API...")
            audio = tts.generate(full_text, voice=req.voice_key, speed=req.voice_speed)
            if not audio:
                job_store.update(job_id, status="failed", error="配音生成失败")
                job_store.add_step(job_id, "tts", "❌ 配音生成失败", 0)
                return

            total_dur = audio.duration
            job_store.add_step(job_id, "tts", f"✅ 配音完成: {total_dur:.1f}秒", 40,
                detail=f"📄 音频已生成，时长 {total_dur:.1f} 秒")
            job_store.add_step(job_id, "subtitle", "📄 正在生成字幕...", 50)
            subtitle_path = None
            subtitle_segs = []
            segment_times = []

            # 构建 all_texts 列表（对应视频片段数量）
            all_texts = [s.get("content", "") for s in script_data]

            # 优先使用 MiniMax 原生字幕时间戳（句子级真实时间戳）
            if audio.subtitle_url:
                job_store.add_step(job_id, "subtitle", "📄 正在处理字幕时间戳...", 50,
                    detail="📥 正在下载 MiniMax 字幕时间戳...")
                json_path = await asyncio.to_thread(tts.download_subtitle, audio.subtitle_url)
                if json_path:
                    srt_gen = SubtitleGenerator()
                    # 用 MiniMax 真实块时间戳分配 all_texts 对应的 segment_times，
                    # 同时在块内按标点细分生成 subtitle_segments
                    segment_times, subtitle_segs = srt_gen.align_minimax_to_segments(
                        json_path, all_texts, total_dur
                    )
                    if subtitle_segs:
                        srt_content = srt_gen._create_srt_from_segments(subtitle_segs)
                        out = config.SUBTITLES_DIR / f"local_seg_{int(datetime.now().timestamp())}.srt"
                        with open(out, "w", encoding="utf-8") as f:
                            f.write(srt_content)
                        subtitle_path = str(out)
                        job_store.add_step(job_id, "subtitle", f"✅ 字幕生成完成: {len(subtitle_segs)} 句", 55,
                            detail=f"MiniMax 时间戳 + 标点分割，{len(segment_times)} 个视频片段")

            # Fallback：纯字数比例分配
            if not subtitle_segs:
                # 按视频片段分配时间（按字符比例）
                total_chars = sum(len(s.get("content", "")) for s in script_data)
                current_time = 0.0

                for seg_data in script_data:
                    content = seg_data.get("content", "")
                    if not content:
                        continue

                    seg_chars = len(content)
                    seg_duration = (seg_chars / total_chars) * total_dur if total_chars > 0 else 0
                    seg_start = current_time

                    # 按标点切分当前片段
                    parts = re.split(r'([。！？，；、：.!?])', content)
                    sentences = []
                    for i in range(0, len(parts) - 1, 2):
                        t = (parts[i] + parts[i + 1]).strip() if i + 1 < len(parts) else parts[i].strip()
                        if t:
                            sentences.append(t)
                    if parts[-1].strip():
                        sentences.append(parts[-1].strip())
                    if not sentences:
                        sentences = [content]

                    # 按标点分配时间
                    part_chars = [len(p) for p in sentences]
                    total_part_chars = sum(part_chars)

                    for pi, part_text in enumerate(sentences):
                        part_chars_count = part_chars[pi]
                        part_dur = (part_chars_count / total_part_chars) * seg_duration if total_part_chars > 0 else 0
                        display_text = part_text.rstrip("，。！？,.!?;；、：")
                        if display_text:
                            subtitle_segs.append({
                                "text": display_text,
                                "start": current_time,
                                "end": current_time + part_dur,
                                "duration": part_dur
                            })
                        current_time += part_dur

                    segment_times.append({
                        "text": content,
                        "start": seg_start,
                        "end": seg_start + seg_duration,
                        "duration": seg_duration
                    })

                if subtitle_segs:
                    subtitle_segs[-1]["end"] = total_dur
                if segment_times:
                    segment_times[-1]["end"] = total_dur
                    segment_times[-1]["duration"] = segment_times[-1]["end"] - segment_times[-1]["start"]
                    # 生成 SRT
                    srt_gen = SubtitleGenerator()
                    srt = srt_gen._create_srt(subtitle_segs)
                    out = config.SUBTITLES_DIR / f"local_seg_{int(datetime.now().timestamp())}.srt"
                    with open(out, "w", encoding="utf-8") as f:
                        f.write(srt)
                    subtitle_path = str(out)
                    job_store.add_step(job_id, "subtitle", f"✅ 字幕生成完成: {len(subtitle_segs)} 句", 55,
                        detail=f"总时长 {total_dur:.1f}s，按字数比例分配")

            job_store.add_step(job_id, "subtitle", f"✅ 字幕对齐完成", 55)

            # Step 4: CLIP matching
            job_store.add_step(job_id, "match", "🔍 正在匹配素材...", 60)
            media_type_map = {"video": "video_scene", "image": "image", "both": None}
            media_filter = media_type_map.get(req.match_type, None)

            matched = []
            total_segs = len(script_data)
            used_paths = set()  # 记录已使用的素材路径，避免重复

            for i, seg in enumerate(script_data):
                vp = seg.get("visual_prompt", "")
                vp_preview = vp[:50] if len(vp) > 50 else vp
                job_store.add_step(job_id, "match", f"🔍 正在匹配素材...", 60,
                    detail=f"片段 {i+1}/{total_segs}: 「{vp_preview}...」搜索中...")
                results = search_materials(vp, top_k=req.top_k, media_type=media_filter)

                # 从 segment_times 获取该片段的真实时间（来自 MiniMax 或 Fallback 字符比例）
                seg_timing = segment_times[i] if i < len(segment_times) else {"start": 0, "end": total_dur}
                audio_start_ratio = seg_timing.get("start", 0) / total_dur if total_dur > 0 else 0
                audio_end_ratio = seg_timing.get("end", total_dur) / total_dur if total_dur > 0 else 1

                # 选择未使用的最佳素材
                selected = None
                if results:
                    for r in results:
                        meta = r["metadata"]
                        path = meta.get("source_file", "")
                        if path and path not in used_paths:
                            selected = r
                            used_paths.add(path)
                            break

                if selected:
                    meta = selected["metadata"]
                    matched.append({
                        "content": seg.get("content", ""),
                        "visual_prompt": vp,
                        "media_path": meta.get("source_file", ""),
                        "media_type": meta.get("type", "image"),
                        "video_start": meta.get("start_time", 0),
                        "video_end": meta.get("end_time", 0),
                        "similarity": selected["similarity"],
                        "audio_start_ratio": audio_start_ratio,
                        "audio_end_ratio": audio_end_ratio,
                    })
                    basename = os.path.basename(meta.get('source_file', ''))
                    job_store.add_step(job_id, "match", f"🔍 正在匹配素材...", 60,
                        detail=f"片段 {i+1}/{total_segs}: ✅ {basename} (相似度 {selected['similarity']:.3f})\n    🎬 画面:「{vp_preview}...」")
                else:
                    # 使用兜底素材
                    fallback_img = str(Path(PROJECT_ROOT) / "img" / "兜底素材.png")
                    if os.path.exists(fallback_img):
                        matched.append({
                            "content": seg.get("content", ""),
                            "visual_prompt": vp,
                            "media_path": fallback_img,
                            "media_type": "image",
                            "video_start": 0,
                            "video_end": 0,
                            "similarity": 0.0,
                            "audio_start_ratio": audio_start_ratio,
                            "audio_end_ratio": audio_end_ratio,
                        })
                        job_store.add_step(job_id, "match", f"🔍 正在匹配素材...", 60,
                            detail=f"片段 {i+1}/{total_segs}: ⚠️ 未匹配，使用兜底素材\n    🎬 画面:「{vp_preview}...」")
                    else:
                        job_store.add_step(job_id, "match", f"🔍 正在匹配素材...", 60,
                            detail=f"片段 {i+1}/{total_segs}: ⚠️ 未匹配到素材\n    🎬 画面:「{vp_preview}...」")

            if not matched:
                job_store.set_error(job_id, "所有片段都未能匹配到素材，且兜底素材也不存在")
                return

            job_store.add_step(job_id, "match", f"✅ 匹配完成: {len(matched)}/{total_segs}", 75,
                detail=f"成功匹配 {len(matched)} 个片段，{total_segs - len(matched)} 个未匹配到素材")

            # Step 5: BGM 和 音效
            bgm_cfg = {"enabled": False}
            sound_effects = []
            analyzer = AIAnalyzer(use_zhipu=bool(zhipu_key))
            if zhipu_key:
                analyzer.zhipu_api_key = zhipu_key
            analyzer._cached_emotion = "舒缓"
            analyzer._cached_scene_type = "生活"

            if req.enable_bgm:
                job_store.add_step(job_id, "bgm", "🎵 正在推荐背景音乐...", 80,
                    detail="🤖 正在分析文案情感并推荐 BGM...")
                bgm_r = analyzer.recommend_bgm(full_text)
                if bgm_r and bgm_r.get("music_id"):
                    bgm_cfg = {"enabled": True, "music_id": bgm_r["music_id"], "title": bgm_r.get("title", ""), "reason": bgm_r.get("reason", "")}
                    job_store.add_step(job_id, "bgm", f"🎵 BGM: {bgm_r.get('title', '')}", 82)
                else:
                    job_store.add_step(job_id, "bgm", "🎵 未找到合适BGM，跳过", 82)

            if req.enable_sfx:
                job_store.add_step(job_id, "sfx", "🔊 正在推荐音效...", 83,
                    detail="🤖 正在分析文案推荐音效...")
                # 构建片段信息用于音效推荐
                segments_for_sfx = []
                for seg in script_data:
                    content = seg.get("content", "")
                    if content:
                        segments_for_sfx.append({"text": content[:50]})
                sfx_result = analyzer.recommend_sound_effects(full_text, segments_for_sfx if segments_for_sfx else None)
                if sfx_result:
                    for sfx in sfx_result:
                        sfx_time = sfx.get("time", 0)
                        sfx_title = sfx.get("title", "未知")
                        job_store.add_step(job_id, "sfx", f"🔊 音效: {sfx_title} @ {sfx_time:.1f}s", 84)
                    sound_effects = sfx_result
                else:
                    job_store.add_step(job_id, "sfx", "🔊 未匹配到合适音效，跳过", 84)

            # Step 6: Create JianYing draft
            job_store.add_step(job_id, "draft", "🎬 正在创建剪映草稿...", 90,
                detail="⚙️ 正在组装素材到剪映，这可能需要几十秒...")
            title = f"本地_{req.script[:10].replace('。','').replace('！','').replace('？','').strip()}_{int(datetime.now().timestamp())}"
            drafts_root = req.drafts_root or config.JIANYING_DRAFTS_ROOT

            # 根据视频比例设置分辨率
            ratio = req.aspect_ratio or "16:9 (横屏)"
            if "9:16" in ratio or "竖屏" in ratio:
                width, height = 1080, 1920
            elif "4:3" in ratio:
                width, height = 1440, 1080
            elif "1:1" in ratio:
                width, height = 1080, 1080
            else:
                width, height = 1920, 1080  # 默认16:9横屏

            maker = JianYingMaker(project_name=title, drafts_root=str(drafts_root), width=width, height=height)

            # 构建视频时间轴：与云端模式一致，视频首尾相接（无间隙）
            v_paths, v_start_times, v_durations = [], [], []
            last_path = None
            for i, seg in enumerate(matched):
                v_path = seg.get("media_path")
                if not v_path:
                    v_path = last_path
                if v_path:
                    last_path = v_path
                    v_paths.append(v_path)
                    # 用 segment_times 计算视频开始时间
                    seg_timing = segment_times[i] if i < len(segment_times) else {"start": 0, "end": total_dur, "duration": total_dur}
                    clip_start = seg_timing.get("start", 0)
                    # 视频结束时间 = 下一个视频的开始时间（首尾相接，无间隙）
                    if i < len(segment_times) - 1:
                        next_start = segment_times[i + 1].get("start", clip_start + seg_timing.get("duration", 5))
                    else:
                        clip_dur = seg_timing.get("duration", seg_timing.get("end", total_dur) - clip_start)
                        next_start = clip_start + clip_dur
                    clip_dur = max(next_start - clip_start, 1.0)
                    v_start_times.append(f"{clip_start:.6f}s")
                    v_durations.append(clip_dur)

            cfg_data = {
                "title": title,
                "videos": v_paths,
                "video_start_times": v_start_times,
                "video_durations": v_durations,
                "use_intelligent_tts": False,
                "full_audio_path": audio.audio_path,
                "subtitle_path": subtitle_path,
                "full_script": full_text,
                "total_duration": total_dur,
                "bgm_config": bgm_cfg,
                "sound_effects": sound_effects,
            }
            maker.create_from_config(cfg_data)

            job_store.set_result(job_id, {
                "draft_path": str(Path(drafts_root) / title),
                "title": title,
                "video_count": len(matched),
                "audio_duration": total_dur,
            })

        except Exception as e:
            import traceback
            job_store.set_error(job_id, str(e))
            job_store.add_step(job_id, "error", f"❌ 错误: {str(e)}\n{traceback.format_exc()}", 0)

    background_tasks.add_task(run_in_background)
    return {"job_id": job_id, "status": "started"}


# ==================== 启动服务 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI 视频生成系统 FastAPI 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    local_url = f"http://127.0.0.1:{args.port}"
    network_url = f"http://{args.host}:{args.port}" if args.host != "0.0.0.0" else None
    print(f"\n{'='*60}")
    print(f"前端地址: {local_url}")
    if network_url:
        print(f"网络地址: {network_url}")
    print(f"{'='*60}\n")

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
    )
