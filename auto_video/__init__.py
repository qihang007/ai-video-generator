# -*- coding: utf-8 -*-
"""
AutoVideo System
=================
自动视频制作系统核心包

功能:
- 输入处理
- AI语义分析
- 视频素材搜索
- 配音生成
- 字幕生成
- 剪映草稿制作
"""

__version__ = "1.0.0"
__author__ = "AutoVideo Team"

from .input_handler import VideoInput, parse_input
from .ai_analyzer import AIAnalyzer, analyze_script
from .video_searcher import VideoSearcher, search_videos
from .tts_generator import TTSGenerator, generate_voice
from .subtitle_generator import SubtitleGenerator, generate_subtitles
from .asr_generator import ASRGenerator, audio_to_subtitle
from .jianying_maker import JianYingMaker, create_video

__all__ = [
    "VideoInput",
    "parse_input",
    "AIAnalyzer",
    "analyze_script",
    "VideoSearcher",
    "search_videos",
    "TTSGenerator",
    "generate_voice",
    "SubtitleGenerator",
    "generate_subtitles",
    "ASRGenerator",
    "audio_to_subtitle",
    "JianYingMaker",
    "create_video",
]