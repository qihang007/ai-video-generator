# -*- coding: utf-8 -*-
"""
本地模式 CLIP 语义匹配模块
===========================
封装方案b的 step3_clip_matcher_v4.py，提供给 Streamlit 页面调用
"""

import os
import sys
import json
import torch
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
LOCAL_MODELS_ROOT = PROJECT_ROOT / "auto_video"


# ==================== ChromaDB 状态查询 ====================

def _get_ai_video_config():
    """获取 ChromaDB 相关路径（使用主项目根目录的 chromadb_data）"""
    from config import CHROMADB_PATH, CHROMADB_COLLECTION_NAME
    chromadb_path = str(CHROMADB_PATH)
    mtime_cache_path = str(PROJECT_ROOT / "mtime_cache.json")
    return chromadb_path, CHROMADB_COLLECTION_NAME, mtime_cache_path

def get_chromadb_status() -> Optional[Dict[str, Any]]:
    """查询向量库状态"""
    from config import CHROMADB_PATH, CHROMADB_COLLECTION_NAME, LOCAL_MATERIALS_PATH

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
        collection = client.get_collection(name=CHROMADB_COLLECTION_NAME)
        count = collection.count()

        sample_path = ""
        try:
            results = collection.get(limit=1)
            if results and results.get("metadatas") and results["metadatas"][0]:
                sample_path = results["metadatas"][0].get("source_file", "")
        except:
            pass

        return {
            "count": count,
            "materials_path": LOCAL_MATERIALS_PATH,
            "chromadb_path": str(CHROMADB_PATH),
            "sample_path": sample_path
        }
    except Exception:
        return None


# ==================== CLIP 模型（懒加载单例） ====================

_clipl_model = None
_clip_preprocess = None


def get_clip_model():
    """获取/加载 CLIP 模型（单例）"""
    global _clipl_model, _clip_preprocess
    if _clipl_model is None:
        import cn_clip.clip as clip

        model_path = LOCAL_MODELS_ROOT / "clip_cn_vit-b-16.pt"
        if model_path.exists():
            _clipl_model, _clip_preprocess = clip.load_from_name(
                "ViT-B-16",
                device="cuda" if torch.cuda.is_available() else "cpu",
                download_root=str(LOCAL_MODELS_ROOT)
            )
        else:
            # 模型文件不存在，尝试从网络下载
            print("[CLIP模型] 本地模型文件不存在，正在尝试从网络下载...")
            _clipl_model, _clip_preprocess = clip.load_from_name(
                "ViT-B-16",
                device="cuda" if torch.cuda.is_available() else "cpu",
                download_root="./"
            )
            # 验证是否下载成功
            model_check = LOCAL_MODELS_ROOT / "clip_cn_vit-b-16.pt"
            if not model_check.exists():
                raise FileNotFoundError(
                    f"[CLIP模型] 模型文件缺失！\n"
                    f"请从网站下载 CLIP 模型并放入 auto_video/ 目录\n"
                    f"文件名：clip_cn_vit-b-16.pt\n"
                    f"放置路径：{str(model_check)}"
                )
        _clipl_model.eval()
    return _clipl_model, _clip_preprocess


# ==================== 素材检索 ====================

def search_materials(
    visual_prompt: str,
    top_k: int = 5,
    media_type: str = None,
    enhanced: bool = True,
) -> List[Dict[str, Any]]:
    """
    检索本地素材库中与 visual_prompt 语义匹配的视频/图片
    """
    from config import CHROMADB_PATH, CHROMADB_COLLECTION_NAME
    from auto_video.metadata_config import extract_entities_from_query, get_expanded_query

    model, preprocess = get_clip_model()

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
        collection = client.get_collection(name=CHROMADB_COLLECTION_NAME)
    except Exception:
        return []

    # === 智能增强处理 ===
    expanded_query = visual_prompt
    tag_filter = None

    if enhanced:
        entities = extract_entities_from_query(visual_prompt)
        expanded_query = get_expanded_query(visual_prompt)

        # 优先使用字典命中的标签
        if entities["tags"]:
            tag_filter = entities["tags"][0]
        # 注意：path_words 不适合做标签过滤，因为是从查询分词出来的，
        # 和素材的 tags 字段不对应，如果强行过滤会导致查不到任何结果

    # 文本编码（使用扩展后的查询）
    import cn_clip.clip as clip
    text_input = clip.tokenize([expanded_query]).to(
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    with torch.no_grad():
        text_feature = model.encode_text(text_input)
        text_feature /= text_feature.norm(dim=-1, keepdim=True)

    query_embedding = text_feature.squeeze().cpu().numpy().tolist()

    # 构建过滤条件
    where_filter = None
    if media_type:
        where_filter = {"type": media_type}

    # 标签过滤（精确匹配）
    if tag_filter:
        if where_filter:
            where_filter = {"$and": [where_filter, {"tags": tag_filter}]}
        else:
            where_filter = {"tags": tag_filter}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 3,
            where=where_filter,
            include=["metadatas", "distances"]
        )
    except Exception:
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    matched = []
    for meta, distance in zip(results["metadatas"][0], results["distances"][0]):
        source_file = meta.get("source_file", "")
        if not source_file or not os.path.exists(source_file):
            continue
        matched.append({
            "metadata": meta,
            "similarity": round(1 - distance, 4)
        })
        if len(matched) >= top_k:
            break

    return matched


# ==================== 脚本生成（调用智谱）====================

def generate_local_script(
    script_content: str,
    api_key: str,
    model_name: str = "glm-4-flash",
    target_duration: int = 30
) -> Optional[List[Dict[str, str]]]:
    """
    使用智谱 AI 为本地模式生成分镜脚本
    同时产出 content（口播文案）和 visual_prompt（画面描述）
    """
    if not api_key or api_key == "YOUR_ZHIPU_API_KEY_HERE":
        return None

    import requests

    prompt = f"""你是一个专业的短视频带货脚本专家。
请为以下口播文案生成一个 {target_duration} 秒的短视频分镜脚本。

要求：
1. 输出必须是纯 JSON 格式（数组），不要包含 Markdown 标记。
2. 风格：快节奏、口语化、有感染力（类似抖音/小红书博主）。
3. 数组中的每个对象代表一个镜头片段，必须包含以下字段：
   - "content": 实际的口播文案（从原文拆分，2-4句话一段）。
   - "visual_prompt": 详细的画面描述（用于在素材库中匹配视频/图片，要求具体、可视化）。

口播文案：
{script_content}

请直接输出 JSON：
"""

    try:
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        raw = result["choices"][0]["message"]["content"]
        if "```json" in raw:
            raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[本地脚本生成] 失败: {e}")
        return None


# ==================== 计算音频时间比例 ====================

def calculate_audio_times(segments: List[Dict]) -> List[Dict]:
    """根据字符数比例计算每个片段的音频时间范围"""
    total_chars = sum(len(seg.get("content", "")) for seg in segments)
    if total_chars == 0:
        return []

    times = []
    current_ratio = 0.0
    for seg in segments:
        content = seg.get("content", "")
        char_ratio = len(content) / total_chars
        times.append({
            "char_count": len(content),
            "audio_start_ratio": current_ratio,
            "audio_end_ratio": current_ratio + char_ratio,
        })
        current_ratio += char_ratio
    return times


# ==================== 向量库统计 ====================

def get_vectorization_stats() -> Dict[str, Any]:
    """获取向量库统计信息"""
    chromadb_path, CHROMADB_COLLECTION_NAME, _ = _get_ai_video_config()

    try:
        import chromadb
        client = chromadb.PersistentClient(path=chromadb_path)
        collection = client.get_or_create_collection(
            name=CHROMADB_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        total = collection.count()

        if total == 0:
            return {"total": 0, "videos": 0, "images": 0, "scenes": 0}

        # 使用 get 获取所有数据的 metadata（适合小数据量，大数据量建议用 where 过滤）
        sample_size = min(total, 10000)
        try:
            all_data = collection.get(limit=sample_size, include=["metadatas"])
        except Exception:
            all_data = None

        video_count = 0
        image_count = 0
        scene_count = 0

        if all_data and all_data.get("metadatas"):
            for meta in all_data["metadatas"]:
                t = meta.get("type", "")
                if t == "image":
                    image_count += 1
                elif t == "video_scene":
                    scene_count += 1
                    video_count += 1

        # 如果实际数量大于采样数，按比例估算
        if total > sample_size:
            import math
            ratio = total / sample_size
            image_count = math.ceil(image_count * ratio)
            scene_count = math.ceil(scene_count * ratio)
            video_count = scene_count

        return {
            "total": total,
            "videos": video_count,
            "images": image_count,
            "scenes": scene_count,
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== 运行向量化（Step0） ====================

def _format_duration(seconds: float) -> str:
    """秒数转为可读格式"""
    total_sec = int(seconds)
    h, r = divmod(total_sec, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}小时{m}分{s}秒"
    elif m > 0:
        return f"{m}分{s}秒"
    else:
        return f"{s}秒"


def run_vectorization(
    materials_path: str,
    progress_callback=None,
    skip_keywords: list = None,
) -> Dict[str, Any]:
    """
    运行 Step0 向量化处理
    使用本地素材库的向量化处理模块

    Args:
        materials_path: 素材库路径
        progress_callback: 进度回调函数
        skip_keywords: 关键词列表，包含这些关键词的视频将跳过镜头检测
    """
    import chromadb
    import cv2
    import numpy as np
    from PIL import Image
    from tqdm import tqdm

    # 从主项目 config 导入（不使用 ai-video-generator 里的配置）
    from config import (
        SCENE_THRESHOLD,
        MIN_SCENE_DURATION,
        SUPPORTED_IMAGE_EXTS,
        SUPPORTED_VIDEO_EXTS,
        SKIP_SCENE_DETECTION_KEYWORDS,
        LOCAL_MODEL_PATH,
    )
    from scenedetect import detect, ContentDetector
    from auto_video.metadata_config import extract_tags_from_path

    # 合并默认关键词和自定义关键词
    all_skip_keywords = list(SKIP_SCENE_DETECTION_KEYWORDS)
    if skip_keywords:
        for kw in skip_keywords:
            if kw.strip() and kw.strip() not in all_skip_keywords:
                all_skip_keywords.append(kw.strip())

    def _should_skip(filename: str) -> bool:
        """根据文件名判断是否跳过镜头检测"""
        fn = filename.lower()
        return any(kw in fn for kw in all_skip_keywords)
    if progress_callback:
        progress_callback("加载 CLIP 模型...")

    # CLIP 模型
    import cn_clip.clip as clip
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    clip_model_path = str(LOCAL_MODEL_PATH)
    if os.path.exists(clip_model_path):
        model, preprocess = clip.load_from_name(
            "ViT-B-16",
            device=DEVICE,
            download_root=os.path.dirname(clip_model_path)
        )
    else:
        model, preprocess = clip.load_from_name(
            "ViT-B-16",
            device=DEVICE,
            download_root=str(LOCAL_MODELS_ROOT)
        )
    model.eval()

    # ChromaDB - 使用主项目根目录的 chromadb_data
    chromadb_path, CHROMADB_COLLECTION_NAME, MTIME_CACHE_STR = _get_ai_video_config()
    client = chromadb.PersistentClient(path=chromadb_path)
    collection = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    MTIME_CACHE_PATH = Path(MTIME_CACHE_STR)
    mtime_cache = {}
    if MTIME_CACHE_PATH.exists():
        with open(MTIME_CACHE_PATH, 'r', encoding='utf-8') as f:
            mtime_cache = json.load(f)

    # 扫描素材
    if progress_callback:
        progress_callback(f"扫描: {materials_path}")

    image_files, video_files = [], []
    for root, dirs, files in os.walk(materials_path):
        for filename in files:
            filepath = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_IMAGE_EXTS:
                image_files.append(filepath)
            elif ext in SUPPORTED_VIDEO_EXTS:
                video_files.append(filepath)

    stats = {
        'new_images': 0, 'skipped_images': 0,
        'new_videos': 0, 'skipped_videos': 0,
        'new_scenes': 0,
        'total_video_duration': 0.0,  # 总视频时长（秒）
        'new_video_duration': 0.0,    # 新处理视频时长
    }

    # 处理图片
    for filepath in tqdm(image_files, desc="图片"):
        file_mtime = str(os.path.getmtime(filepath))
        if mtime_cache.get(filepath) == file_mtime:
            stats['skipped_images'] += 1
            continue

        try:
            collection.delete(where={"source_file": filepath})
        except:
            pass

        try:
            image = preprocess(Image.open(filepath).convert("RGB")).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                feat = model.encode_image(image)
                feat /= feat.norm(dim=-1, keepdim=True)

            tags_info = extract_tags_from_path(filepath)
            collection.add(
                ids=[filepath],
                embeddings=[feat.squeeze().cpu().numpy().tolist()],
                metadatas=[{
                    "type": "image",
                    "source_file": filepath,
                    "filename": os.path.basename(filepath),
                    "mtime": file_mtime,
                    "tags": ",".join(tags_info["tags"]),
                    "locations": ",".join(tags_info["locations"]),
                    "scenes": ",".join(tags_info["scenes"]),
                    "persons": ",".join(tags_info["persons"]),
                    "actions": ",".join(tags_info["actions"]),
                }]
            )
            mtime_cache[filepath] = file_mtime
            stats['new_images'] += 1
        except Exception as e:
            print(f"  图片失败: {filepath} - {e}")

    if progress_callback:
        progress_callback(f"处理视频: {len(video_files)} 个...")

    # 处理视频
    for filepath in tqdm(video_files, desc="视频"):
        file_mtime = str(os.path.getmtime(filepath))

        # 先快速获取视频时长（用于统计，跳过处理也要统计）
        try:
            cap_tmp = cv2.VideoCapture(filepath)
            fps_tmp = cap_tmp.get(cv2.CAP_PROP_FPS)
            frames_tmp = int(cap_tmp.get(cv2.CAP_PROP_FRAME_COUNT))
            cap_tmp.release()
            video_duration = frames_tmp / fps_tmp if fps_tmp > 0 else 0
            stats['total_video_duration'] += video_duration
        except:
            video_duration = 0

        if mtime_cache.get(filepath) == file_mtime:
            stats['skipped_videos'] += 1
            continue

        try:
            collection.delete(where={"source_file": filepath})
        except:
            pass

        filename = os.path.basename(filepath)
        skip_detection = _should_skip(filename)

        if skip_detection:
            cap = cv2.VideoCapture(filepath)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            duration = total_frames / fps if fps > 0 else 0
            scenes = [(0.0, duration)]
        else:
            try:
                detected = detect(filepath, ContentDetector(threshold=SCENE_THRESHOLD))
                scenes = [
                    (s[0].get_seconds(), s[1].get_seconds())
                    for s in detected
                    if s[1].get_seconds() - s[0].get_seconds() >= MIN_SCENE_DURATION
                ]
                if not scenes:
                    cap = cv2.VideoCapture(filepath)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap.release()
                    duration = total_frames / fps if fps > 0 else 0
                    scenes = [(0.0, duration)]
            except Exception:
                cap = cv2.VideoCapture(filepath)
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
                duration = total_frames / fps if fps > 0 else 0
                scenes = [(0.0, duration)]

        tags_info = extract_tags_from_path(filepath)

        for scene_idx, (start_time, end_time) in enumerate(scenes):
            sample_time = (start_time + end_time) / 2
            cap = cv2.VideoCapture(filepath)
            fps_v = cap.get(cv2.CAP_PROP_FPS)
            frame_idx = int(sample_time * fps_v)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                continue

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame)
            img_t = preprocess(pil_img).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                feat = model.encode_image(img_t)
                feat /= feat.norm(dim=-1, keepdim=True)

            scene_id = f"{filepath}@scene_{scene_idx:03d}"
            collection.add(
                ids=[scene_id],
                embeddings=[feat.squeeze().cpu().numpy().tolist()],
                metadatas=[{
                    "type": "video_scene",
                    "source_file": filepath,
                    "filename": filename,
                    "scene_index": scene_idx,
                    "start_time": round(start_time, 2),
                    "end_time": round(end_time, 2),
                    "duration": round(end_time - start_time, 2),
                    "sample_time": round(sample_time, 2),
                    "detection_skipped": skip_detection,
                    "mtime": file_mtime,
                    "tags": ",".join(tags_info["tags"]),
                    "locations": ",".join(tags_info["locations"]),
                    "scenes": ",".join(tags_info["scenes"]),
                    "persons": ",".join(tags_info["persons"]),
                    "actions": ",".join(tags_info["actions"]),
                }]
            )

        mtime_cache[filepath] = file_mtime
        stats['new_videos'] += 1
        stats['new_scenes'] += len(scenes)
        stats['new_video_duration'] += video_duration

        if progress_callback:
            total_str = _format_duration(stats['total_video_duration'])
            new_str = _format_duration(stats['new_video_duration'])
            progress_callback(
                f"已处理 {stats['new_videos']}/{len(video_files)} 个视频，"
                f"总时长 {total_str}（新增 {new_str}），{stats['new_scenes']} 个镜头"
            )

    # 保存缓存
    with open(MTIME_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(mtime_cache, f, ensure_ascii=False, indent=2)

    # 添加时长可读格式
    stats['total_duration_str'] = _format_duration(stats['total_video_duration'])
    stats['new_duration_str'] = _format_duration(stats['new_video_duration'])

    return stats
