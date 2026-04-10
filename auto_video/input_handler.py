# -*- coding: utf-8 -*-
"""
输入处理模块
=============

处理视频文案输入，支持多种格式
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoInput:
    """视频输入数据类"""
    title: str
    script: str
    style: Optional[str] = "vlog"  # vlog, news, tutorial, story
    duration: Optional[int] = None  # 目标时长(秒): 60, 120, 180
    voice_style: Optional[str] = "female"  # male, female, child


def parse_input(
    title: Optional[str] = None,
    script: Optional[str] = None,
    style: str = "vlog",
    duration: Optional[int] = None,
    voice_style: str = "female",
    **kwargs
) -> VideoInput:
    """
    解析并验证输入参数

    Args:
        title: 视频标题
        script: 视频文案
        style: 视频风格
        duration: 目标时长
        voice_style: 配音风格

    Returns:
        VideoInput: 验证后的输入对象
    """
    # 验证必填参数
    if not title or not title.strip():
        title = "自动生成的视频"
    if not script or not script.strip():
        raise ValueError("视频文案(script)不能为空")

    # 清理文本
    title = title.strip()
    script = script.strip()

    # 验证可选参数
    valid_styles = ["vlog", "news", "tutorial", "story"]
    if style not in valid_styles:
        style = "vlog"

    valid_durations = [None, 60, 120, 180]
    if duration not in valid_durations:
        duration = None

    valid_voices = ["male", "female", "child", "male_mature"]
    if voice_style not in valid_voices:
        voice_style = "female"

    return VideoInput(
        title=title,
        script=script,
        style=style,
        duration=duration,
        voice_style=voice_style
    )