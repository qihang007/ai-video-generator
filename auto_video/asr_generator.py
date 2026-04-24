# -*- coding: utf-8 -*-
"""
字幕生成模块
============

根据文案和配音时长生成对齐的 SRT 字幕文件
支持两种方式：
1. 按配音时长比例分配（简单精准）
2. ASR 语音识别（适用于外部配音）
"""

import os
import re
import json
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import config


class SubtitleGenerator:
    """字幕生成器"""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or config.SUBTITLES_DIR
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_srt_from_text(
        self,
        text: str,
        audio_duration: float,
        output_path: Optional[str] = None
    ) -> str:
        """
        根据文案和配音时长生成 SRT 字幕

        Args:
            text: 完整文案
            audio_duration: 配音实际时长（秒）
            output_path: 输出路径

        Returns:
            SRT 文件路径
        """
        if output_path is None:
            output_path = self.output_dir / f"subtitles_{int(datetime.now().timestamp())}.srt"

        # 按标点符号分割成句子
        sentences = re.split(r'([。！？；\n]+)', text)

        # 合并句子和标点
        segments = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                seg_text = sentences[i] + sentences[i + 1]
            else:
                seg_text = sentences[i]
            seg_text = seg_text.strip()
            if seg_text:
                segments.append({"text": seg_text})

        if not segments:
            segments = [{"text": text.strip()}]

        # 按文字长度比例分配时间
        total_chars = sum(len(seg["text"]) for seg in segments)
        if total_chars == 0:
            total_chars = 1

        current_time = 0.0
        for seg in segments:
            char_ratio = len(seg["text"]) / total_chars
            duration = audio_duration * char_ratio
            duration = max(duration, 0.3)  # 最少0.3秒

            seg["start"] = current_time
            seg["end"] = current_time + duration
            current_time += duration

        # 调整最后一段结束时间
        if segments and current_time < audio_duration:
            segments[-1]["end"] = audio_duration

        print(f"[字幕] 生成 {len(segments)} 个片段，总时长 {audio_duration:.1f}秒")

        # 生成 SRT 内容
        srt_content = self._create_srt(segments)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        return str(output_path)

    def _create_srt(self, segments: List[Dict]) -> str:
        """将段落转换为 SRT 格式"""
        srt_lines = []
        subtitle_index = 1
        for seg in segments:
            text = seg.get("text", "").strip()
            text = text.rstrip("。！？，；、：,.!?;:")
            if not text:
                continue
            start_time = self._format_srt_time(seg.get("start", 0))
            end_time = self._format_srt_time(seg.get("end", 0))
            srt_lines.append(str(subtitle_index))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")
            subtitle_index += 1
        return "\n".join(srt_lines)

    def _format_srt_time(self, seconds: float) -> str:
        """格式化时间为 SRT 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def get_audio_duration(self, audio_path: str) -> float:
        """获取音频实际时长"""
        try:
            import pymediainfo
            mi = pymediainfo.MediaInfo.parse(audio_path)
            for track in mi.tracks:
                if track.track_type == "Audio":
                    return float(track.duration) / 1000
        except Exception as e:
            print(f"[字幕] 获取音频时长失败: {e}")
        # 估算：中文每字约0.15秒
        return 60.0

    def convert_minimax_subtitle(
        self,
        json_path: str,
        output_path: Optional[str] = None,
        split_by_punctuation: bool = True
    ) -> str:
        """
        将优刻得 API 返回的字幕 JSON 转换为 SRT 格式

        Args:
            json_path: 字幕 JSON 文件路径
            output_path: 输出 SRT 路径
            split_by_punctuation: 是否按标点符号再分割

        Returns:
            SRT 文件路径
        """
        with open(json_path, "r", encoding="utf-8") as f:
            subtitle_data = json.load(f)

        if output_path is None:
            output_path = Path(json_path).with_suffix(".srt")

        segments = []
        for item in subtitle_data:
            start_ms = item.get("time_begin", 0)
            end_ms = item.get("time_end", 0)
            text = item.get("text", "").strip()

            if not text:
                continue

            if split_by_punctuation:
                # 按标点符号分割文本
                parts = self._split_by_punctuation(text)
                total_chars = len(text)
                duration_ms = end_ms - start_ms
                current_ms = start_ms

                for part in parts:
                    part_chars = len(part)
                    part_duration = (part_chars / total_chars) * duration_ms if total_chars > 0 else 0
                    display_text = part.rstrip("，。！？,.!?;；、")
                    if display_text:
                        segments.append({
                            "start": current_ms / 1000.0,
                            "end": (current_ms + part_duration) / 1000.0,
                            "text": display_text
                        })
                    current_ms += part_duration
            else:
                segments.append({
                    "start": start_ms / 1000,
                    "end": end_ms / 1000,
                    "text": text
                })

        srt_content = self._create_srt(segments)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        print(f"[字幕] 转换为 SRT: {output_path} ({len(segments)} 个片段)")
        return str(output_path)

    def parse_subtitle_timestamps(self, json_path: str) -> List[Dict]:
        """
        解析MiniMax字幕JSON，在每个时间戳内按标点细分，再按字符比例分配时间

        Args:
            json_path: 字幕 JSON 文件路径

        Returns:
            List[Dict]: 包含 text, start, end, duration 的片段列表
        """
        with open(json_path, "r", encoding="utf-8") as f:
            subtitle_data = json.load(f)

        segments = []
        for item in subtitle_data:
            start_ms = item.get("time_begin", 0)
            end_ms = item.get("time_end", 0)
            text = item.get("text", "").strip()

            if not text:
                continue

            duration_ms = end_ms - start_ms

            # 按标点切分文本
            parts = self._split_by_punctuation(text)
            total_chars = len(text)

            # 在当前时间戳内，按字符比例分配时间
            current_ms = start_ms
            for part in parts:
                part_chars = len(part)
                part_duration = (part_chars / total_chars) * duration_ms if total_chars > 0 else 0

                # 去除末尾标点显示
                display_text = part.rstrip("，。！？,.!?;；、")

                if display_text:
                    segments.append({
                        "text": display_text,
                        "start": current_ms / 1000.0,
                        "end": (current_ms + part_duration) / 1000.0,
                        "duration": part_duration / 1000.0
                    })

                current_ms += part_duration

        return segments

    def _split_by_punctuation(self, text: str) -> List[str]:
        """
        按标点符号分割字幕，返回文本片段列表

        Args:
            text: 文本

        Returns:
            分割后的字符串列表
        """
        import re

        # 分割标点：同时支持中文和英文标点
        parts = re.split(r'([。！？，；、：.!?])', text)

        # 合并内容和标点
        sentences = []
        i = 0
        while i < len(parts):
            part = parts[i].strip()
            if i + 1 < len(parts) and re.match(r'^[。！？，；、：.!?]$', parts[i + 1].strip()):
                # 当前是文本，下一个是标点：合并
                seg = part + parts[i + 1].strip()
                if seg.strip():
                    sentences.append(seg.strip())
                i += 2
            elif part:
                # 单独的文本（可能是最后一段）
                sentences.append(part)
                i += 1
            else:
                # 空元素，跳过
                i += 1

        return sentences if sentences else [text]

    def _create_srt_from_segments(self, segments: List[Dict]) -> str:
        """将片段转换为 SRT 格式"""
        srt_lines = []
        subtitle_index = 1
        for seg in segments:
            text = seg.get("text", "").strip()
            text = text.rstrip("。！？，；、：,.!?;:")
            if not text:
                continue
            start_time = self._format_srt_time(seg.get("start", 0))
            end_time = self._format_srt_time(seg.get("end", 0))
            srt_lines.append(str(subtitle_index))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")
            subtitle_index += 1
        return "\n".join(srt_lines)

    def _split_by_punctuation_with_time(
        self,
        text: str,
        start_time: float,
        end_time: float
    ) -> List[Dict]:
        """按标点符号分割字幕，同时支持中文和英文标点，返回带时间戳的片段"""
        import re
        parts = re.split(r'([。！？，；、：.!?])', text)

        # 用 while 循环正确处理所有情况（包含尾部无标点的片段）
        sentences = []
        i = 0
        while i < len(parts):
            part = parts[i].strip()
            if i + 1 < len(parts) and re.match(r'^[。！？，；、：.!?]$', parts[i + 1].strip()):
                seg = part + parts[i + 1].strip()
                if seg.strip():
                    sentences.append(seg.strip())
                i += 2
            elif part:
                sentences.append(part)
                i += 1
            else:
                i += 1

        if not sentences:
            return [{"start": start_time, "end": end_time, "text": text}]

        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            total_chars = 1

        result = []
        current_time = start_time

        for seg_text in sentences:
            char_ratio = len(seg_text) / total_chars
            duration = (end_time - start_time) * char_ratio
            duration = max(duration, 0.3)
            result.append({
                "start": current_time,
                "end": current_time + duration,
                "text": seg_text
            })
            current_time += duration

        if result and current_time < end_time:
            result[-1]["end"] = end_time

        return result

    def align_minimax_to_segments(
        self,
        json_path: str,
        all_texts: List[str],
        total_audio_duration: float
    ) -> tuple:
        """
        用 MiniMax 字幕块的真实时间戳，来分配 all_texts 对应的 segment_times，
        同时生成 sentence 级 subtitle_segments 用于 SRT。
        """
        import json

        with open(json_path, "r", encoding="utf-8") as f:
            minimax_blocks = json.load(f)

        # 每个块按标点细分后的句子（带真实时间戳）
        all_subs = []
        for item in minimax_blocks:
            start_ms = item.get("time_begin", 0)
            end_ms = item.get("time_end", 0)
            text = item.get("text", "").strip()
            if not text:
                continue
            subs = self._split_by_punctuation_with_time(text, start_ms / 1000, end_ms / 1000)
            all_subs.extend(subs)

        # 构建 subtitle_segments（直接用 all_subs，句子级精度）
        subtitle_segments = all_subs

        # 构建 segment_times（基于 all_texts）
        # 策略：按字幕句子文本内容，匹配到对应的 all_texts[i]
        # 每个 all_texts[i] 包含的字幕句子的时间范围 = 视频片段时间范围
        segment_times = []

        # 预处理：去除标点，用于文本匹配
        import re
        all_texts_clean = [re.sub(r'[，。！？；：、]', '', t) for t in all_texts]

        # 将字幕句子按顺序分配到对应的 all_texts[i]
        segment_subs = [[] for _ in all_texts]  # segment_subs[i] = 属于 all_texts[i] 的字幕句子列表
        unassigned_subs = []  # 未能分配的字幕句子

        for sub in all_subs:
            sub_clean = re.sub(r'[，。！？；：、]', '', sub["text"])
            if not sub_clean:
                continue

            assigned = False
            for i, at_clean in enumerate(all_texts_clean):
                # 双向包含判断
                if (sub_clean in at_clean or at_clean in sub_clean or
                    len(sub_clean) >= 5 and sub_clean[:5] in at_clean or
                    len(at_clean) >= 5 and at_clean[:5] in sub_clean):
                    segment_subs[i].append(sub)
                    assigned = True
                    break

            if not assigned:
                unassigned_subs.append(sub)

        # 处理未分配的字幕：按顺序追加到前一个已分配的 segment
        current_seg_idx = 0
        for sub in unassigned_subs:
            while current_seg_idx < len(segment_subs) - 1 and len(segment_subs[current_seg_idx]) == 0:
                current_seg_idx += 1
            if len(segment_subs[current_seg_idx]) > 0:
                segment_subs[current_seg_idx].append(sub)

        # 构建 segment_times
        for i, text in enumerate(all_texts):
            subs = segment_subs[i]
            if subs:
                segment_times.append({
                    "text": text,
                    "start": subs[0]["start"],
                    "end": subs[-1]["end"],
                    "duration": subs[-1]["end"] - subs[0]["start"]
                })
            else:
                # 兜底：比例分配
                seg_chars = len(text)
                total_chars = sum(len(t) for t in all_texts) or 1
                seg_dur = (seg_chars / total_chars) * total_audio_duration
                seg_start = segment_times[-1]["end"] if segment_times else 0
                segment_times.append({
                    "text": text,
                    "start": seg_start,
                    "end": seg_start + seg_dur,
                    "duration": seg_dur
                })

        return segment_times, subtitle_segments


# 便捷函数
def generate_subtitles(
    text: str,
    audio_path: str,
    output_path: Optional[str] = None
) -> Optional[str]:
    """
    从文案和音频生成字幕

    Args:
        text: 配音文案
        audio_path: 音频文件路径
        output_path: 输出 SRT 路径

    Returns:
        SRT 文件路径
    """
    generator = SubtitleGenerator()

    # 获取音频实际时长
    audio_duration = generator.get_audio_duration(audio_path)

    # 生成 SRT
    return generator.generate_srt_from_text(text, audio_duration, output_path)


# ==================== ASR 部分（保留用于外部配音）====================

class ASRGenerator:
    """ASR 语音识别生成器（用于外部配音文件）"""

    # SiliconFlow FunAudioLLM/SenseVoiceSmall API Key（免费使用）
    SILICONFLOW_ASR_KEY = "sk-kkgiwuhevadnvdwathpmywwqtfgvbhbblyywcxycpkcgjthw"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self.SILICONFLOW_ASR_KEY

    def recognize_audio(self, audio_path: str) -> Optional[Dict]:
        """
        识别音频文件，返回带时间戳的结果

        Args:
            audio_path: 音频文件路径

        Returns:
            识别结果，包含 segments 列表
        """
        if not self.api_key or self.api_key == "sk-your-api-key-here":
            print("[ASR] 请先设置 SILICONFLOW_API_KEY")
            return None

        # 使用 SiliconFlow ASR 接口
        url = "https://api.siliconflow.cn/v1/audio/transcriptions"

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        # 获取文件扩展名
        ext = Path(audio_path).suffix.lower()
        mime_type = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/m4a",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg"
        }.get(ext, "audio/wav")

        try:
            # 读取音频文件
            with open(audio_path, "rb") as f:
                files = {
                    "file": (os.path.basename(audio_path), f, mime_type)
                }
                data = {
                    "model": "FunAudioLLM/SenseVoiceSmall",
                    "response_format": "verbose_json",
                    "timestamp_granularity": "word"
                }

                print(f"[ASR] 正在识别: {os.path.basename(audio_path)}")
                response = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300  # ASR 可能需要较长时间
                )

            if response.status_code == 200:
                result = response.json()
                print(f"[ASR] 识别完成")
                return result
            else:
                print(f"[ASR] 识别失败: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"[ASR] 识别异常: {e}")
            return None

    def generate_srt_from_asr(self, audio_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        从音频生成 SRT 字幕文件

        Args:
            audio_path: 音频文件路径
            output_path: 输出 SRT 文件路径

        Returns:
            SRT 文件路径
        """
        result = self.recognize_audio(audio_path)

        if not result:
            return None

        # 解析 ASR 结果并生成 SRT
        if output_path is None:
            audio_name = Path(audio_path).stem
            output_path = config.SUBTITLES_DIR / f"{audio_name}.srt"

        # SiliconFlow 返回格式: {"text": "完整文案"}
        full_text = result.get("text", "").strip()

        if not full_text:
            print("[ASR] 未识别到文字内容")
            return None

        # 按标点符号分割成多个片段
        import re
        # 保留标点符号用于分割
        sentences = re.split(r'([。！？；\n]+)', full_text)

        # 合并句子和标点
        segments = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                text = sentences[i] + sentences[i+1]
            else:
                text = sentences[i]
            text = text.strip()
            if text:
                segments.append({"text": text})

        if not segments:
            # 如果分割失败，整个作为一段
            segments = [{"text": full_text}]

        # 获取音频总时长
        total_duration = self._get_audio_duration(audio_path)

        # 按文字长度比例分配时间
        total_chars = sum(len(seg["text"]) for seg in segments)
        if total_chars == 0:
            total_chars = 1

        current_time = 0.0
        for seg in segments:
            # 计算这段的时长
            char_ratio = len(seg["text"]) / total_chars
            duration = total_duration * char_ratio

            # 确保最小时长
            duration = max(duration, 0.5)

            seg["start"] = current_time
            seg["end"] = current_time + duration
            current_time += duration

        # 如果最后时间小于总时长，调整最后一段
        if current_time < total_duration and segments:
            segments[-1]["end"] = total_duration

        print(f"[ASR] 识别到 {len(segments)} 个片段，总时长 {total_duration:.1f}秒")

        # 生成 SRT
        srt_content = self._create_srt(segments)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        print(f"[ASR] 字幕已生成: {output_path}")
        return str(output_path)

    def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        try:
            import pymediainfo
            mi = pymediainfo.MediaInfo.parse(audio_path)
            for track in mi.tracks:
                if track.track_type == "Audio":
                    return float(track.duration) / 1000
        except:
            pass
        return 60.0  # 默认 60 秒

    def _create_srt(self, segments: List[Dict]) -> str:
        """将识别结果转换为 SRT 格式"""
        srt_lines = []
        subtitle_index = 1

        for seg in segments:
            text = seg.get("text", "").strip()
            text = text.rstrip("。！？，；、：,.!?;:")
            if not text:
                continue
            start_time = self._format_srt_time(seg.get("start", 0))
            end_time = self._format_srt_time(seg.get("end", 0))
            srt_lines.append(str(subtitle_index))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")
            subtitle_index += 1

        return "\n".join(srt_lines)

    def _format_srt_time(self, seconds: float) -> str:
        """格式化时间为 SRT 格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# 便捷函数
def audio_to_subtitle(
    audio_path: str,
    output_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> Optional[str]:
    """
    从音频文件生成字幕

    Args:
        audio_path: 音频文件路径
        output_path: 输出 SRT 路径
        api_key: SiliconFlow API Key

    Returns:
        SRT 文件路径
    """
    generator = ASRGenerator(api_key)
    return generator.generate_srt_from_asr(audio_path, output_path)


# 测试
if __name__ == "__main__":
    # 测试 ASR
    test_audio = "output/audio/tts_test.wav"
    if os.path.exists(test_audio):
        result = audio_to_subtitle(test_audio)
        print(f"生成结果: {result}")
    else:
        print(f"测试音频不存在: {test_audio}")