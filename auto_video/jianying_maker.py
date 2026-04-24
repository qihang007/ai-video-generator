# -*- coding: utf-8 -*-
"""
剪映制作模块 (增强版)
=====================

充分利用 jianying-editor 的内置功能：
- 智能配音 (TTS)
- 智能字幕 (带配音)
- 云素材
- 特效与转场
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
try:
    from .log_utils import log_info, log_success, log_warning, log_error
except ImportError:
    from auto_video.log_utils import log_info, log_success, log_warning, log_error

# 尝试导入 jianying-editor 的 wrapper
JY_WRAPPER_AVAILABLE = False

def _import_jy_wrapper():
    """导入剪映 wrapper"""
    global JY_WRAPPER_AVAILABLE

    possible_paths = [
        Path(__file__).parent.parent / ".claude" / "skills" / "jianying-editor" / "scripts",
    ]

    for path in possible_paths:
        if path.exists() and (path / "jy_wrapper.py").exists():
            sys.path.insert(0, str(path))
            try:
                from jy_wrapper import JyProject
                JY_WRAPPER_AVAILABLE = True
                return True
            except ImportError as e:
                print(f"[剪映] 导入失败: {e}")
                break
    return False

_import_jy_wrapper()

import config


class JianYingMaker:
    """剪映草稿制作器 (增强版)"""

    # 配音角色映射 (剪映内置 - 使用正确的 speaker_id)
    TTS_SPEAKERS = {
        "male": "zh_male_iclvop_xiaolinkepu",      # 清亮男声
        "female": "BV001_fast_streaming",          # 小姐姐
        "child": "zh_female_xiaopengyou",          # 小孩/小朋友
        "male_mature": "BV701_streaming",          # 沉稳解说
    }

    def __init__(
        self,
        project_name: str = "AutoVideo",
        drafts_root: Optional[Path] = None,
        width: int = 1920,
        height: int = 1080,
        progress_callback: Optional[callable] = None
    ):
        # 添加时间戳后缀防止重复名称
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.project_name = f"{project_name}_{timestamp}"
        self.drafts_root = Path(drafts_root) if drafts_root else Path(config.JIANYING_DRAFTS_ROOT)
        self.width = width
        self.height = height
        self.project = None
        self.progress_callback = progress_callback

    def _init_project(self, overwrite: bool = True):
        """初始化剪映项目"""
        if not JY_WRAPPER_AVAILABLE:
            raise RuntimeError("无法导入剪映 wrapper")

        from jy_wrapper import JyProject
        import jy_wrapper
        print(f"[DEBUG] jy_wrapper module path: {jy_wrapper.__file__}")
        print(f"[DEBUG] JyProject class: {JyProject}")
        self.project = JyProject(
            self.project_name,
            width=self.width,
            height=self.height,
            drafts_root=str(self.drafts_root),
            overwrite=overwrite
        )
        log_success("剪映", f"项目已创建: {self.project_name}")

    def add_videos(
        self,
        video_paths: List[str],
        start_times: Optional[List[str]] = None,
        durations: Optional[List[str]] = None,
        source_start: str = "1s"
    ) -> List[Any]:
        """添加视频素材

        Args:
            video_paths: 视频文件路径列表
            start_times: 每个视频在时间轴上的开始时间
            durations: 每个视频的时长
            source_start: 视频素材的起始截取位置，默认从第1秒开始
        """
        if not self.project:
            self._init_project()

        clips = []
        current_start_us = 0

        for i, video_path in enumerate(video_paths):
            # 计算当前片段的时长（用于时间轴递进）
            # 如果视频不存在或获取时长失败，使用传入的时长或默认5秒
            segment_duration_s = 5.0  # 默认5秒
            if durations and i < len(durations) and durations[i]:
                dur_val = durations[i]
                if isinstance(dur_val, str):
                    segment_duration_s = float(dur_val.replace("s", ""))
                else:
                    segment_duration_s = float(dur_val)

            if not os.path.exists(video_path):
                log_warning("剪映", f"视频文件不存在: {video_path}，使用兜底素材")
                fallback_img = Path(__file__).parent.parent / "img" / "云端模式兜底素材.png"
                if fallback_img.exists():
                    start_s = round(current_start_us / 1000000.0, 6)
                    start = f"{start_s}s"
                    try:
                        clip = self.project.add_media_safe(
                            str(fallback_img),
                            start_time=start,
                            duration=f"{segment_duration_s}s",
                            track_name="VideoTrack"
                        )
                        if clip:
                            clip_end = clip.target_timerange.start + clip.target_timerange.duration
                            log_info("剪映", f"兜底素材 @ {start}, 时长: {segment_duration_s:.2f}s", "🖼️")
                            current_start_us = clip_end
                            clips.append(clip)
                            continue
                    except Exception as fallback_e:
                        print(f"[剪映] 兜底素材添加失败: {fallback_e}")
                # 即使兜底素材也失败，仍按预期时长递进时间轴
                current_start_us += int(segment_duration_s * 1000000)
                clips.append(None)
                continue

            # 获取视频实际时长
            video_duration_us = self._get_video_duration(video_path)
            video_duration_s = video_duration_us / 1000000

            # 使用传入的 duration 或者视频实际时长
            if durations and i < len(durations) and durations[i]:
                # 解析传入的 duration（可能是 "10s" 或 10 或 10.0）
                dur_val = durations[i]
                if isinstance(dur_val, str):
                    duration_s = float(dur_val.replace("s", ""))
                else:
                    duration_s = float(dur_val)
                dur_us = int(duration_s * 1000000)
            else:
                # 使用视频实际时长
                duration_s = video_duration_s
                dur_us = video_duration_us

            # 使用 current_start_us 确保时间轴连续
            # (不再依赖预计算的 start_times，因为浮点数精度可能导致不连续)
            # 注意：必须round到6位小数避免IEEE 754浮点精度问题导致的时间不连续
            start_s = round(current_start_us / 1000000.0, 6)
            start = f"{start_s}s"
            start_us = current_start_us

            # ===== 调试日志 =====
            print(f"[剪映] === 片段 {i} ===")
            print(f"[剪映]   video_path: {video_path}")
            print(f"[剪映]   video_duration_s: {video_duration_s:.3f}s ({video_duration_us}us)")
            print(f"[剪映]   requested duration_s: {duration_s:.3f}s ({dur_us}us)")
            print(f"[剪映]   current_start_us BEFORE: {current_start_us} ({start_s:.6f}s)")
            print(f"[剪映]   start string: '{start}'")

            try:
                # 计算实际可用的素材时长（从 source_start 开始）
                available_duration_s = video_duration_s - 1.0  # source_start = 1s
                print(f"[剪映]   available_duration_s: {available_duration_s:.3f}s")
                if duration_s > available_duration_s:
                    print(f"[剪映]   ⚠️ 请求时长 {duration_s:.2f}s 超过素材可用时长 {available_duration_s:.2f}s，将截断")
                    duration_s = available_duration_s

                # 调试：打印时间信息
                print(f"[剪映]   calling add_media_safe: start={start}, duration={duration_s}s, source_start={source_start}")

                clip = self.project.add_media_safe(
                    video_path,
                    start_time=start,
                    duration=f"{duration_s}s",
                    track_name="VideoTrack",
                    source_start=source_start
                )
                if clip:
                    # 打印片段的实际时间范围
                    clip_start = clip.target_timerange.start
                    clip_end = clip.target_timerange.start + clip.target_timerange.duration
                    print(f"[剪映]   clip返回: clip_start={clip_start}, clip_end={clip_end}, clip_duration={clip.target_timerange.duration}")
                    log_info("剪映", f"添加视频: {os.path.basename(video_path)} @ {start}, 时长: {duration_s:.2f}s", "🎬")
                    print(f"[剪映]   片段时间范围: {clip_start/1000000:.3f}s - {clip_end/1000000:.3f}s")
                    # 使用clip的实际结束位置更新current_start_us，确保后续片段时间连续
                    print(f"[剪映]   current_start_us UPDATE: {current_start_us} -> {clip_end}")
                    current_start_us = clip_end
                else:
                    print(f"[剪映]   ⚠️ clip为None，尝试使用兜底素材图片")
                    # clip为None时也尝试使用兜底素材
                    fallback_img = Path(__file__).parent.parent / "img" / "云端模式兜底素材.png"
                    if fallback_img.exists():
                        print(f"[剪映] 使用兜底素材图片: {fallback_img}")
                        try:
                            clip = self.project.add_media_safe(
                                str(fallback_img),
                                start_time=start,
                                duration=f"{duration_s}s",
                                track_name="VideoTrack"
                            )
                            if clip:
                                clip_start = clip.target_timerange.start
                                clip_end = clip.target_timerange.start + clip.target_timerange.duration
                                print(f"[剪映]   兜底素材添加成功: clip_start={clip_start}, clip_end={clip_end}")
                                current_start_us = clip_end
                                clips.append(clip)
                                continue
                            else:
                                print(f"[剪映]   兜底素材添加也失败，跳过此片段")
                        except Exception as fallback_e:
                            print(f"[剪映] 兜底素材添加异常: {fallback_e}")
                    else:
                        print(f"[剪映] 兜底素材图片不存在: {fallback_img}")
                clips.append(clip)

            except Exception as e:
                print(f"[剪映] 添加视频失败: {e}")
                print(f"[剪映] 调试信息: start={start}, duration_s={duration_s}, video_path={video_path}")
                import traceback
                traceback.print_exc()

                # 使用兜底素材图片作为替补
                fallback_img = Path(__file__).parent.parent / "img" / "云端模式兜底素材.png"
                if fallback_img.exists():
                    print(f"[剪映] 使用兜底素材图片作为替补: {fallback_img}")
                    try:
                        clip = self.project.add_media_safe(
                            str(fallback_img),
                            start_time=start,
                            duration=f"{duration_s}s",
                            track_name="VideoTrack"
                        )
                        if clip:
                            clip_start = clip.target_timerange.start
                            clip_end = clip.target_timerange.start + clip.target_timerange.duration
                            print(f"[剪映]   兜底素材添加成功: clip_start={clip_start}, clip_end={clip_end}")
                            current_start_us = clip_end
                            clips.append(clip)
                            continue
                        else:
                            print(f"[剪映]   兜底素材添加也失败，跳过此片段")
                    except Exception as fallback_e:
                        print(f"[剪映] 兜底素材添加异常: {fallback_e}")
                else:
                    print(f"[剪映] 兜底素材图片不存在: {fallback_img}")

                # 跳过这个视频，继续添加下一个
                continue

        return clips

    def _get_video_duration(self, video_path: str) -> int:
        """获取视频实际时长（微秒）"""
        try:
            from pymediainfo import MediaInfo
            mi = MediaInfo.parse(video_path)
            for track in mi.tracks:
                if track.track_type == "Video":
                    duration = getattr(track, "duration", None)
                    if duration:
                        return int(duration * 1000)  # 毫秒转微秒
        except Exception as e:
            print(f"[剪映] 获取视频时长失败: {e}")
        return 10000000  # 默认10秒

    def _parse_duration_to_ms(self, duration: str) -> int:
        """解析时长字符串为微秒"""
        duration = str(duration).strip()
        # 处理 "12.75s" 格式
        duration = duration.replace("s", "").replace("m", "")
        try:
            return int(float(duration) * 1000000)
        except:
            return 10000000

    def add_tts_intelligent(
        self,
        text: str,
        voice_style: str = "female",
        start_time: str = "0s",
        track_name: str = "AudioTrack"
    ) -> Optional[Any]:
        """
        使用剪映内置智能配音

        Args:
            text: 要配音的文本
            voice_style: 配音风格 (male/female/child/male_mature)
            start_time: 开始时间
            track_name: 轨道名称
        """
        if not self.project:
            self._init_project()

        speaker = self.TTS_SPEAKERS.get(voice_style, self.TTS_SPEAKERS["female"])

        try:
            audio = self.project.add_tts_intelligent(
                text,
                speaker=speaker,
                start_time=start_time,
                track_name=track_name
            )
            print(f"[剪映] 添加智能配音: {text[:20]}... @ {start_time} (角色: {speaker})")
            return audio
        except Exception as e:
            print(f"[剪映] 智能配音失败: {e}")
            return None

    def add_narrated_subtitles(
        self,
        text: str,
        voice_style: str = "female",
        start_time: str = "0s",
        track_name: str = "Subtitles"
    ) -> Optional[Any]:
        """
        使用剪映内置智能字幕 (配音+字幕一起生成，自动对齐!)

        这是最强大的功能：自动生成配音和字幕，时间自动对齐

        Args:
            text: 字幕文本
            voice_style: 配音风格
            start_time: 开始时间
            track_name: 轨道名称
        """
        if not self.project:
            self._init_project()

        speaker = self.TTS_SPEAKERS.get(voice_style, self.TTS_SPEAKERS["female"])

        try:
            subtitle = self.project.add_narrated_subtitles(
                text,
                speaker=speaker,
                start_time=start_time,
                track_name=track_name
            )
            print(f"[剪映] 添加智能字幕: {text[:20]}... @ {start_time}")
            return subtitle
        except Exception as e:
            print(f"[剪映] 智能字幕失败: {e}")
            return None

    def import_srt_subtitle(
        self,
        srt_path: str,
        track_name: str = "Subtitles",
        time_offset: str = "0s"
    ) -> Optional[Any]:
        """
        从 SRT 文件导入字幕

        Args:
            srt_path: SRT 字幕文件路径
            track_name: 字幕轨道名称
            time_offset: 时间偏移

        Returns:
            导入结果
        """
        if not self.project:
            self._init_project()

        if not os.path.exists(srt_path):
            print(f"[剪映] SRT 文件不存在: {srt_path}")
            return None

        try:
            # 使用 script.import_srt 而非 project.import_srt
            result = self.project.script.import_srt(
                srt_path,
                track_name,
                time_offset=time_offset
            )
            log_info("剪映", f"导入 SRT 字幕: {os.path.basename(srt_path)}", "📝")
            return result
        except Exception as e:
            print(f"[剪映] 导入 SRT 失败: {e}")
            return None

    def add_audio(
        self,
        audio_path: str,
        start_time: str = "0s",
        track_name: str = "AudioTrack"
    ) -> Optional[Any]:
        """
        添加配音/音频文件

        Args:
            audio_path: 音频文件路径
            start_time: 开始时间
            track_name: 轨道名称

        Returns:
            添加结果
        """
        if not self.project:
            self._init_project()

        if not os.path.exists(audio_path):
            print(f"[剪映] 音频文件不存在: {audio_path}")
            return None

        try:
            result = self.project.add_media_safe(
                audio_path,
                start_time=start_time,
                track_name=track_name
            )
            print(f"[剪映] 添加音频: {os.path.basename(audio_path)} @ {start_time}")
            return result
        except Exception as e:
            print(f"[剪映] 添加音频失败: {e}")
            return None

    def add_cloud_music(
        self,
        query: str,
        start_time: str = "0s",
        duration: str = "30s"
    ) -> Optional[Any]:
        """
        添加剪映云音乐

        Args:
            query: 搜索关键词
            start_time: 开始时间
            duration: 时长
        """
        if not self.project:
            self._init_project()

        try:
            music = self.project.add_cloud_music(
                query,
                start_time=start_time,
                duration_s=duration
            )
            print(f"[剪映] 添加云音乐: {query} @ {start_time}")
            return music
        except Exception as e:
            print(f"[剪映] 添加云音乐失败: {e}")
            return None

    def add_cloud_sound_effect(
        self,
        effect_id: str,
        start_time: str = "0s",
        title: str = "",
        duration_s: float = 3.0
    ) -> Optional[Any]:
        """
        添加剪映云音效（支持 Mock 模式）

        Args:
            effect_id: 音效 ID
            start_time: 开始时间
            title: 音效名称
            duration_s: 音效时长（秒）
        """
        if not self.project:
            self._init_project()

        try:
            # 尝试先通过 add_cloud_media 下载
            sfx_seg = self.project.add_cloud_media(
                effect_id,
                start_time=start_time,
                track_name="SFX"
            )
            if sfx_seg:
                print(f"[剪映] 添加云音效: {title} @ {start_time}")
                return sfx_seg

            # 下载失败，使用 Mock 模式（类似 add_cloud_music）
            from core.mocking_ops import MockAudioMaterial
            import pyJianYingDraft as draft
            from utils.formatters import safe_tim

            dur_us = int(duration_s * 1000000)
            dummy_path = f"cloud_sfx_{effect_id}.m4a"

            # 注入 patch
            self.project._cloud_audio_patches[dummy_path] = {
                "id": effect_id,
                "type": "sound_effect"
            }
            print(f"[DEBUG] Registered patch: {dummy_path} -> id={effect_id}, type=sound_effect")
            print(f"[DEBUG] Current patches: {dict(self.project._cloud_audio_patches)}")

            mat = MockAudioMaterial(effect_id, dur_us, title or f"CloudSFX_{effect_id}", dummy_path)
            seg = draft.AudioSegment(
                mat,
                draft.Timerange(safe_tim(start_time), dur_us),
                source_timerange=draft.Timerange(0, dur_us),
            )

            self.project._ensure_track(draft.TrackType.audio, "SFX")
            target_track = self.project._find_available_audio_track_name("SFX", seg)
            self.project.script.add_segment(seg, target_track)

            print(f"[剪映] 添加云音效(Mock): {title} @ {start_time}")
            return seg

        except Exception as e:
            print(f"[剪映] 添加云音效失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def add_effect(
        self,
        effect_name: str,
        start_time: str = "0s",
        duration: str = "3s",
        track_name: str = "EffectTrack"
    ) -> Optional[Any]:
        """添加视频特效"""
        if not self.project:
            self._init_project()

        try:
            effect = self.project.add_effect_simple(
                effect_name,
                start_time=start_time,
                duration=duration,
                track_name=track_name
            )
            print(f"[剪映] 添加特效: {effect_name}")
            return effect
        except Exception as e:
            print(f"[剪映] 添加特效失败: {e}")
            return None

    def add_transition(
        self,
        transition_name: str,
        duration: str = "1s"
    ) -> Optional[Any]:
        """添加转场效果"""
        if not self.project:
            self._init_project()

        try:
            transition = self.project.add_transition_simple(
                transition_name,
                duration=duration
            )
            print(f"[剪映] 添加转场: {transition_name}")
            return transition
        except Exception as e:
            print(f"[剪映] 添加转场失败: {e}")
            return None

    def add_simple_subtitles(
        self,
        segments: List[Dict[str, Any]]
    ) -> List[Any]:
        """添加普通字幕 (无配音)"""
        if not self.project:
            self._init_project()

        subtitles = []
        for segment in segments:
            text = segment.get("text", "")
            start_time = segment.get("start_time", 0)
            duration = segment.get("duration", 5)

            if not text:
                continue

            try:
                sub = self.project.add_text_simple(
                    text,
                    start_time=f"{start_time}s",
                    duration=f"{duration}s",
                    track_name="Subtitles"
                )
                subtitles.append(sub)
                print(f"[剪映] 添加字幕: {text[:20]}...")

            except Exception as e:
                print(f"[剪映] 添加字幕失败: {e}")

        return subtitles

    def create_from_config(
        self,
        config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        根据配置创建完整的视频项目

        支持两种模式:
        1. 智能模式: 使用 add_narrated_subtitles (配音+字幕一起)
        2. 普通模式: 外部配音 + 字幕分开添加
        """
        try:
            # 保留时间戳后缀，只在原有基础上添加标题前缀
            if config_data.get("title"):
                title = config_data["title"]
                # 检查是否已经有时间戳，避免重复添加
                if "_20" not in self.project_name or self.project_name.startswith(title):
                    self.project_name = f"{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if self.progress_callback:
                self.progress_callback("create", "🎬 创建剪映项目...")

            self._init_project()

            if self.progress_callback:
                self.progress_callback("videos", f"📹 添加 {len(config_data.get('videos', []))} 个视频...")

            # 添加视频
            video_paths = config_data.get("videos", [])
            if video_paths:
                start_times = config_data.get("video_start_times", None)
                durations = config_data.get("video_durations", None)
                self.add_videos(video_paths, start_times, durations)

            # 确定使用哪种模式
            use_intelligent = config_data.get("use_intelligent_tts", True)
            voice_style = config_data.get("voice_style", "female")

            if use_intelligent:
                # === 智能模式: 使用剪映内置的配音+字幕 ===
                if self.progress_callback:
                    self.progress_callback("tts", "🎤 生成配音和字幕...")

                segments = config_data.get("segments", [])
                current_time = 0

                for i, segment in enumerate(segments):
                    text = segment.get("text", "")
                    if not text:
                        continue

                    if self.progress_callback:
                        self.progress_callback("tts", f"🎤 生成配音: {text[:15]}...")

                    # 使用智能字幕 (配音+字幕一起生成)
                    self.add_narrated_subtitles(
                        text,
                        voice_style=voice_style,
                        start_time=f"{current_time}s"
                    )

                    # 估算时长 (中文每字约0.4秒)
                    duration = max(3, len(text) * 0.4)
                    current_time += int(duration)

                # 可以选择添加背景音乐
                bgm_query = config_data.get("bgm", "")
                if bgm_query:
                    total_duration = config_data.get("total_duration", 60)
                    self.add_cloud_music(
                        bgm_query,
                        start_time="0s",
                        duration=f"{total_duration}s"
                    )
            else:
                # === 普通模式: 外部配音 + 字幕 ===
                # 支持两种方式:
                # 1. 统一的完整 audio 文件 + 完整时间戳（推荐）
                # 2. 每个段落独立的 audio_path（已废弃）

                # 方式1: 统一完整配音（推荐）
                full_audio_path = config_data.get("full_audio_path", "")
                if full_audio_path and os.path.exists(full_audio_path):
                    self.project.add_media_safe(
                        full_audio_path,
                        start_time="0s",
                        track_name="AudioTrack"
                    )
                    log_info("剪映", f"添加配音: {os.path.basename(full_audio_path)}", "🎤")

                # 添加字幕 - 支持 SRT 文件或时间戳
                subtitle_path = config_data.get("subtitle_path", "")
                char_timestamps = config_data.get("char_timestamps", [])
                full_script = config_data.get("full_script", "")

                # 方式1: 导入 SRT 字幕文件（带默认描边样式）
                if subtitle_path and os.path.exists(subtitle_path):
                    try:
                        # 创建带描边的字幕样式模板
                        from pyJianYingDraft import TextSegment, TextStyle, TextBorder, ClipSettings, Timerange

                        subtitle_style_template = TextSegment(
                            text="",  # 模板文本，实际文本会被 SRT 内容替换
                            timerange=Timerange(0, 1000000),  # 占位时间
                            style=TextStyle(size=5.0, align=1, auto_wrapping=True),  # 居中，自动换行
                            border=TextBorder(color=(0.0, 0.0, 0.0), alpha=1.0, width=40.0),  # 黑色描边
                            clip_settings=ClipSettings(transform_y=-0.8)  # 底部位置
                        )

                        self.project.script.import_srt(
                            subtitle_path,
                            track_name="Subtitles",
                            time_offset="0s",
                            style_reference=subtitle_style_template,
                            clip_settings=None  # 使用模板的 clip_settings
                        )
                        print(f"[剪映] 导入 SRT 字幕: {subtitle_path}")
                    except Exception as e:
                        print(f"[剪映] 导入 SRT 失败: {e}")
                # 方式2: 按时间戳逐字添加字幕
                elif char_timestamps and len(char_timestamps) > 0:
                    for ts in char_timestamps:
                        try:
                            char = ts.get("char", "").strip()
                            if char:
                                self.project.add_text_simple(
                                    char,
                                    start_time=f"{ts.get('start', 0)}s",
                                    duration=f"{ts.get('end', 0) - ts.get('start', 0)}s",
                                    track_name="Subtitles"
                                )
                        except Exception as e:
                            print(f"[剪映] 添加字幕失败: {e}")
                            pass
                # 方式3: 没有时间戳时，显示完整文案作为字幕
                elif full_script:
                    duration = config_data.get("video_durations", [10])[0] if config_data.get("video_durations") else 10
                    self.project.add_text_simple(
                        full_script,
                        start_time="0s",
                        duration=f"{duration}s",
                        track_name="Subtitles"
                    )

            # === 添加背景音乐 ===
            bgm_config = config_data.get("bgm_config", {})
            if bgm_config.get("enabled"):
                music_id = bgm_config.get("music_id")
                total_duration = config_data.get("total_duration", 60)

                if music_id:
                    try:
                        if self.progress_callback:
                            self.progress_callback("bgm", f"🎵 添加背景音乐...")

                        # 添加云音乐，音量设为 0.2 (20%)
                        bgm_seg = self.project.add_cloud_music(
                            music_id,
                            start_time="0s",
                            duration=f"{total_duration}s",
                            track_name="BGM"
                        )

                        # 设置音量为 20%
                        if bgm_seg:
                            bgm_seg.volume = 0.2
                            log_info("剪映", f"添加背景音乐: {bgm_config.get('title', music_id)}, 音量: 20%", "🎵")
                            if self.progress_callback:
                                self.progress_callback("bgm", f"✅ 背景音乐: {bgm_config.get('title', '已添加')} (音量20%)")
                    except Exception as e:
                        print(f"[剪映] 添加背景音乐失败: {e}")

            # === 添加音效 ===
            sound_effects = config_data.get("sound_effects", [])
            if sound_effects:
                if self.progress_callback:
                    self.progress_callback("sfx", f"🔊 添加 {len(sound_effects)} 个音效...")

                for sfx in sound_effects:
                    effect_id = sfx.get("effect_id")
                    sfx_time = sfx.get("time", 0)
                    sfx_title = sfx.get("title", "")

                    if effect_id:
                        try:
                            # 使用专门的音效添加方法（支持 Mock 模式）
                            sfx_seg = self.add_cloud_sound_effect(
                                effect_id,
                                start_time=f"{sfx_time}s",
                                title=sfx_title,
                                duration_s=3.0  # 默认3秒
                            )
                            if sfx_seg:
                                log_info("剪映", f"添加音效: {sfx_title} @ {sfx_time}s", "🔊")
                        except Exception as e:
                            print(f"[剪映] 添加音效失败: {e}")

                if self.progress_callback:
                    self.progress_callback("sfx", f"✅ 音效添加完成")

            if self.progress_callback:
                self.progress_callback("save", "💾 保存草稿...")

            self.save()

            if self.progress_callback:
                self.progress_callback("done", f"✅ 视频生成完成！")

            return {
                "success": True,
                "project_name": self.project_name,
                "draft_path": str(Path(self.drafts_root) / self.project_name),
                "videos_count": len(video_paths),
                "mode": "intelligent" if use_intelligent else "normal"
            }

        except Exception as e:
            if self.progress_callback:
                self.progress_callback("error", f"❌ 生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def save(self):
        """保存项目"""
        if self.project:
            print(f"[DEBUG] save() called, patches: {dict(self.project._cloud_audio_patches)}")
            print(f"[DEBUG] self.project.save method: {self.project.save}")
            print(f"[DEBUG] self.project class: {type(self.project)}")
            result = self.project.save()
            print(f"[DEBUG] save() returned: {result}")
            log_success("剪映", f"项目已保存: {self.project_name}")

    def get_duration(self, track_name: str = "VideoTrack") -> int:
        """获取轨道时长（微秒）"""
        if self.project:
            return self.project.get_track_duration(track_name)
        return 0


def create_video(
    title: str,
    videos: List[str],
    segments: List[Dict[str, Any]],
    voice_style: str = "female",
    use_intelligent_tts: bool = True,
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    便捷函数：创建剪映视频项目

    Args:
        title: 项目标题
        videos: 视频文件路径列表
        segments: 字幕段落列表
        voice_style: 配音风格
        use_intelligent_tts: 是否使用智能配音
        project_name: 项目名称

    Returns:
        Dict: 创建结果
    """
    maker = JianYingMaker(project_name=project_name or title)

    return maker.create_from_config({
        "title": title,
        "videos": videos,
        "segments": segments,
        "voice_style": voice_style,
        "use_intelligent_tts": use_intelligent_tts
    })