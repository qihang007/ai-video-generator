# -*- coding: utf-8 -*-
"""
字幕生成模块
============

生成 SRT 格式字幕文件
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import config


class SubtitleGenerator:
    """字幕生成器"""

    def __init__(self, output_dir: Optional[Path] = None):
        """
        初始化字幕生成器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = output_dir or config.SUBTITLES_DIR
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_time(self, seconds: float) -> str:
        """
        格式化时间为 SRT 格式

        Args:
            seconds: 秒数

        Returns:
            str: 格式化后的时间 (HH:MM:SS,mmm)
        """
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        millis = td.microseconds // 1000

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_srt(
        self,
        segments: List[Dict[str, Any]],
        offset: float = 0.0
    ) -> str:
        """
        生成 SRT 格式字幕

        Args:
            segments: 段落列表，每个包含 text, start_time, duration
            offset: 时间偏移（秒）

        Returns:
            str: SRT 格式的字幕内容
        """
        srt_lines = []
        subtitle_index = 1

        for segment in segments:
            text = segment.get("text", "")
            start_time = segment.get("start_time", 0) + offset
            duration = segment.get("duration", 5)

            if not text:
                continue

            # 格式化时间
            start_str = self._format_time(start_time)
            end_str = self._format_time(start_time + duration)

            # 添加字幕条目
            srt_lines.append(str(subtitle_index))
            srt_lines.append(f"{start_str} --> {end_str}")
            srt_lines.append(text)
            srt_lines.append("")  # 空行

            subtitle_index += 1

        return "\n".join(srt_lines)

    def save_srt(
        self,
        segments: List[Dict[str, Any]],
        filename: str,
        offset: float = 0.0
    ) -> str:
        """
        保存 SRT 字幕文件

        Args:
            segments: 段落列表
            filename: 文件名
            offset: 时间偏移（秒）

        Returns:
            str: 保存的文件路径
        """
        # 确保文件名有 .srt 扩展名
        if not filename.endswith(".srt"):
            filename = filename + ".srt"

        filepath = self.output_dir / filename
        srt_content = self.generate_srt(segments, offset)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(srt_content)

        print(f"[字幕] 已保存: {filepath}")
        return str(filepath)

    def generate_from_audio_duration(
        self,
        text: str,
        audio_duration: float,
        style: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        根据音频时长均分字幕段落

        Args:
            text: 完整文案
            audio_duration: 音频时长
            style: 分割风格

        Returns:
            List[Dict]: 字幕段落列表
        """
        # 按句子分割
        import re
        sentences = re.split(r'[。！？\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        # 计算每个段落的时长
        total_chars = sum(len(s) for s in sentences)
        segments = []
        current_time = 0.0

        for sentence in sentences:
            if not sentence:
                continue

            # 按字数比例分配时长
            duration = (len(sentence) / total_chars) * audio_duration
            # 保持最小和最大时长
            duration = max(2.0, min(duration, 10.0))

            segments.append({
                "text": sentence,
                "start_time": round(current_time, 2),
                "duration": round(duration, 2)
            })

            current_time += duration

        return segments

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
                sub_segments = self._split_by_punctuation(
                    text, start_ms / 1000, end_ms / 1000
                )
                segments.extend(sub_segments)
            else:
                segments.append({
                    "start": start_ms / 1000,
                    "end": end_ms / 1000,
                    "text": text
                })

        srt_content = self._create_srt_from_segments(segments)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        print(f"[字幕] 转换为 SRT: {output_path} ({len(segments)} 个片段)")
        return str(output_path)

    def parse_subtitle_timestamps(self, json_path: str) -> List[Dict]:
        """
        解析优刻得字幕 JSON，返回每个片段的时间戳信息

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

            # 按标点分割，但保持时间戳比例
            sub_segments = self._split_by_punctuation(
                text, start_ms / 1000, end_ms / 1000
            )

            for seg in sub_segments:
                segments.append({
                    "text": seg["text"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "duration": seg["end"] - seg["start"]
                })

        return segments

    def _split_by_punctuation(
        self,
        text: str,
        start_time: float,
        end_time: float
    ) -> List[Dict]:
        """按标点符号分割字幕，同时支持中文和英文标点"""
        # 中文：。！？，；、：
        # 英文：. ! ? , ;
        parts = re.split(r'([。！？，；、：.!?])', text)

        # 过滤空白元素，同时记录原始位置
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

        策略：直接用 MiniMax 块的真实起止时间作为 all_texts 的 segment_times，
        在块内按标点细分生成 subtitle_segments。
        如果 MiniMax 块数量 >= all_texts 数量，直接取前 all_texts 个块的时间；
        否则用块时间按比例分配给 all_texts。

        Args:
            json_path: MiniMax 字幕 JSON 文件路径
            all_texts: 原始分镜句子列表（对应视频片段数量）
            total_audio_duration: 音频总时长（秒）

        Returns:
            (segment_times, subtitle_segments)
        """
        import re

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
            subs = self._split_by_punctuation(text, start_ms / 1000, end_ms / 1000)
            all_subs.extend(subs)

        # 构建 subtitle_segments（直接用 all_subs，句子级精度）
        subtitle_segments = all_subs

        # 构建 segment_times（基于 all_texts）
        # 策略：按字幕句子文本内容，匹配到对应的 all_texts[i]
        # 每个 all_texts[i] 包含的字幕句子的时间范围 = 视频片段时间范围
        segment_times = []

        # 预处理：去除标点，用于文本匹配
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

    def _create_srt_from_segments(self, segments: List[Dict]) -> str:
        """将片段转换为 SRT 格式"""
        srt_lines = []
        subtitle_index = 1
        for seg in segments:
            text = seg.get("text", "").strip()
            text = text.rstrip("。！？，；、：,.!?;:")
            if not text:
                continue
            start_time = self._format_time(seg.get("start", 0))
            end_time = self._format_time(seg.get("end", 0))
            srt_lines.append(str(subtitle_index))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")
            subtitle_index += 1

        return "\n".join(srt_lines)


# 便捷函数
def generate_subtitles(
    segments: List[Dict[str, Any]],
    output_filename: str = "subtitles.srt",
    offset: float = 0.0
) -> str:
    """
    便捷函数：生成字幕文件

    Args:
        segments: 段落列表
        output_filename: 输出文件名
        offset: 时间偏移

    Returns:
        str: 保存的文件路径
    """
    generator = SubtitleGenerator()
    return generator.save_srt(segments, output_filename, offset)