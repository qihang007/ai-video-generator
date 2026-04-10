# -*- coding: utf-8 -*-
"""
美化日志输出工具
================

提供统一的、美化的终端日志输出格式
"""

import os
from datetime import datetime

# ANSI 颜色代码
class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    # Windows 兼容
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            pass


def get_timestamp():
    """获取当前时间戳"""
    return datetime.now().strftime("%H:%M:%S")


def log_header(title):
    """输出标题头"""
    width = 60
    print()
    print(f"{Colors.CYAN}{'=' * width}{Colors.RESET}")
    print(f"{Colors.CYAN}│{Colors.BOLD}  {title.center(width - 4)}  {Colors.RESET}{Colors.CYAN}│{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * width}{Colors.RESET}")
    print()


def log_step(step_num, title, status="start"):
    """输出步骤信息"""
    icons = {
        "start": "▶",
        "done": "✓",
        "error": "✗",
        "skip": "○"
    }
    colors = {
        "start": Colors.BLUE,
        "done": Colors.GREEN,
        "error": Colors.RED,
        "skip": Colors.YELLOW
    }

    icon = icons.get(status, "•")
    color = colors.get(status, Colors.RESET)

    if status == "start":
        print(f"\n{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {color}{icon}{Colors.RESET} Step {step_num}: {Colors.BOLD}{title}{Colors.RESET}")
    elif status == "done":
        print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {color}{icon}{Colors.RESET} Step {step_num}: {title} {Colors.GREEN}完成{Colors.RESET}")
    elif status == "error":
        print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {color}{icon}{Colors.RESET} Step {step_num}: {title} {Colors.RED}失败{Colors.RESET}")


def log_info(tag, message, icon="•"):
    """输出普通信息"""
    print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {Colors.BLUE}{icon}{Colors.RESET} [{Colors.CYAN}{tag}{Colors.RESET}] {message}")


def log_success(tag, message):
    """输出成功信息"""
    print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {Colors.GREEN}✓{Colors.RESET} [{Colors.CYAN}{tag}{Colors.RESET}] {Colors.GREEN}{message}{Colors.RESET}")


def log_warning(tag, message):
    """输出警告信息"""
    print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {Colors.YELLOW}⚠{Colors.RESET} [{Colors.CYAN}{tag}{Colors.RESET}] {Colors.YELLOW}{message}{Colors.RESET}")


def log_error(tag, message):
    """输出错误信息"""
    print(f"{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {Colors.RED}✗{Colors.RESET} [{Colors.CYAN}{tag}{Colors.RESET}] {Colors.RED}{message}{Colors.RESET}")


def log_debug(tag, message):
    """输出调试信息（灰色）"""
    print(f"{Colors.DIM}[{get_timestamp()}] [{tag}] {message}{Colors.RESET}")


def log_progress(current, total, prefix="进度", suffix=""):
    """输出进度"""
    percent = (current / total * 100) if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_length - filled)
    print(f"\r{Colors.DIM}[{get_timestamp()}]{Colors.RESET} {prefix}: [{Colors.GREEN}{bar}{Colors.RESET}] {percent:.0f}% {suffix}", end='', flush=True)
    if current >= total:
        print()  # 完成时换行


def log_segment(index, total, text, keywords, duration=None):
    """输出片段信息"""
    text_preview = text[:25] + "..." if len(text) > 25 else text
    duration_str = f"({duration:.1f}s)" if duration else ""
    print(f"  {Colors.DIM}{index+1:>2}/{total}{Colors.RESET} │ {text_preview} {duration_str}")
    print(f"       └─ {Colors.GREEN}关键词{Colors.RESET}: {Colors.YELLOW}{keywords}{Colors.RESET}")


def log_video_download(index, total, video_id, source, duration):
    """输出视频下载信息"""
    print(f"  {Colors.DIM}{index+1:>2}/{total}{Colors.RESET} │ {Colors.GREEN}↓{Colors.RESET} {source}_{video_id} ({duration:.1f}s)")


def log_search_results(keyword, count, source=""):
    """输出搜索结果"""
    source_str = f"[{source}] " if source else ""
    print(f"  {Colors.BLUE}🔍{Colors.RESET} {source_str}搜索 \"{Colors.YELLOW}{keyword}{Colors.RESET}\" → {Colors.GREEN}{count}{Colors.RESET} 个结果")


def log_final_result(success, title, draft_path, stats=None):
    """输出最终结果"""
    print()
    width = 50
    if success:
        print(f"{Colors.GREEN}{'─' * width}{Colors.RESET}")
        print(f"{Colors.GREEN}│  🎉 视频生成成功！{Colors.RESET}")
        print(f"{Colors.GREEN}{'─' * width}{Colors.RESET}")
        print(f"  📁 草稿: {Colors.CYAN}{title}{Colors.RESET}")
        print(f"  📍 路径: {Colors.DIM}{draft_path}{Colors.RESET}")
        if stats:
            print(f"  📊 统计: {stats}")
    else:
        print(f"{Colors.RED}{'─' * width}{Colors.RESET}")
        print(f"{Colors.RED}│  ❌ 视频生成失败{Colors.RESET}")
        print(f"{Colors.RED}{'─' * width}{Colors.RESET}")
    print()


# 简化标签
TAG_TTS = "配音"
TAG_SEARCH = "搜索"
TAG_DOWNLOAD = "下载"
TAG_AI = "AI"
TAG_JIANYING = "剪映"
TAG_ANALYZE = "分析"