# -*- coding: utf-8 -*-
"""
配音生成模块 - 优刻得 (Modelverse) API v2
=========================================
新版 API 支持直接返回字幕文件
"""

import os
import time
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

import config
try:
    from .log_utils import log_info, log_success, log_warning, log_error
except ImportError:
    from auto_video.log_utils import log_info, log_success, log_warning, log_error


@dataclass
class AudioSegment:
    """配音片段"""
    text: str
    audio_path: str
    duration: float  # 时长(秒)
    subtitle_url: Optional[str] = None  # 字幕下载链接


class TTSGenerator:
    """配音生成器 - 优刻得 API v2"""

    VOICES = config.TTS_VOICES

    def __init__(
        self,
        api_key: Optional[str] = None,
        output_dir: Optional[Path] = None
    ):
        self.api_key = api_key or config.MODELVERSE_API_KEY
        self.url = config.MODELVERSE_URL
        self.output_dir = output_dir or config.AUDIO_DIR
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        text: str,
        voice: str = "female-yujie",
        speed: float = 1.0,
        progress_callback=None,
        enable_subtitle: bool = True,
        emotion: str = "fluent"
    ) -> Optional[AudioSegment]:
        """
        生成配音

        Args:
            text: 要转换的文本
            voice: 音色ID (如 female-yujie, male-qn-qingse)
            speed: 语速，范围 [0.5, 2.0]，默认 1.0，值越大语速越快
            progress_callback: 进度回调
            enable_subtitle: 是否启用字幕
            emotion: 情感风格，默认 fluent（生动）

        Returns:
            AudioSegment 或 None
        """
        if progress_callback:
            progress_callback("tts", f"🎤 生成配音: {text[:20]}...")

        log_info("配音", f"生成配音: {text[:30]}...", "🎤")

        # 生成文件名
        text_hash = hash(text) % 100000
        output_file = self.output_dir / f"tts_{text_hash}_{int(time.time())}.mp3"

        # 新版 API 请求 - 增强版参数
        payload = {
            "model": "speech-2.6-hd",
            "text": text,
            "voice_setting": {
                "voice_id": voice,
                "speed": speed,  # 语速，范围 [0.5, 2.0]
                "vol": 1.2,
                "pitch": 0,
                # "emotion": emotion  # 情感风格：fluent(生动)
            },
            "voice_modify": {
                "pitch": 10,       # 稍微明亮
                "intensity": -20,  # 有力量感
                "timbre": 20       # 清脆
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1
            },
            "subtitle_enable": enable_subtitle,
            "output_format": "url"  # 返回音频 URL
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()

                # 调试：打印完整响应
                log_info("配音", f"API响应: {json.dumps(result, ensure_ascii=False)[:500]}", "📡")

                # 解析响应 - 兼容多种格式
                data = result.get("data", {})
                extra_info = result.get("extra_info", {})

                # 如果 data 为空，尝试从顶层获取
                if not data:
                    data = result

                # 获取音频 URL 并下载（带重试）
                audio_url = data.get("audio")
                if audio_url:
                    log_info("配音", "下载音频文件...", "↓")
                    max_retries = 3
                    last_error = None
                    for attempt in range(max_retries):
                        try:
                            audio_resp = requests.get(audio_url, timeout=120)
                            audio_resp.raise_for_status()
                            with open(output_file, "wb") as f:
                                f.write(audio_resp.content)
                            break  # 成功则跳出重试循环
                        except Exception as e:
                            last_error = e
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt  # 指数退避: 1s, 2s
                                log_warning("配音", f"下载失败 (尝试 {attempt+1}/{max_retries}): {e}, {wait_time}秒后重试...")
                                time.sleep(wait_time)
                            else:
                                log_error("配音", f"下载失败 (已重试{max_retries}次): {e}")
                                raise  # 重试完成后仍失败，抛出异常

                    # 优先使用API返回的时长（毫秒转秒）
                    audio_length_ms = extra_info.get("audio_length", 0)
                    if audio_length_ms > 0:
                        duration = audio_length_ms / 1000.0
                        log_success("配音", f"完成: 时长 {duration:.1f}秒 (来自API)")
                    else:
                        # 备用：从文件获取时长
                        duration = self._get_audio_duration(str(output_file))
                        log_success("配音", f"完成: 时长 {duration:.1f}秒")
                else:
                    log_warning("配音", "未获取到音频URL")
                    duration = 0

                # 获取字幕链接
                subtitle_url = data.get("subtitle_file")

                if progress_callback:
                    progress_callback("tts", f"✅ 配音生成完成: {duration:.1f}秒")

                return AudioSegment(
                    text=text,
                    audio_path=str(output_file),
                    duration=duration,
                    subtitle_url=subtitle_url
                )
            else:
                log_error("配音", f"API 错误: {response.status_code} - {response.text[:200]}")
                if progress_callback:
                    progress_callback("tts", f"❌ 配音生成失败")

        except Exception as e:
            log_error("配音", f"异常: {e}")
            if progress_callback:
                progress_callback("tts", f"❌ 错误: {e}")

        return None



    def download_subtitle(self, subtitle_url: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        下载字幕文件（带重试）

        Args:
            subtitle_url: 字幕下载链接
            output_path: 输出路径

        Returns:
            字幕文件路径
        """
        if not subtitle_url:
            return None

        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                resp = requests.get(subtitle_url, timeout=30)
                if resp.status_code == 200:
                    subtitle_data = resp.json()

                    if output_path is None:
                        output_path = config.SUBTITLES_DIR / f"subtitle_{int(time.time())}.json"

                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(subtitle_data, f, ensure_ascii=False, indent=2)

                    log_success("字幕", f"下载完成: {output_path}")
                    return str(output_path)
                else:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        log_warning("字幕", f"下载失败 (尝试 {attempt+1}/{max_retries}): {last_error}, {wait_time}秒后重试...")
                        time.sleep(wait_time)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    log_warning("字幕", f"下载失败 (尝试 {attempt+1}/{max_retries}): {e}, {wait_time}秒后重试...")
                    time.sleep(wait_time)

        log_warning("字幕", f"下载失败 (已重试{max_retries}次): {last_error}")
        return None

    def get_available_voices(self) -> Dict[str, str]:
        """获取可用的音色列表"""
        return self.VOICES.copy()


# 便捷函数
def generate_voice(
    text: str,
    voice: str = "female-yujie",
    api_key: Optional[str] = None
) -> Optional[AudioSegment]:
    """生成配音"""
    generator = TTSGenerator(api_key)
    return generator.generate(text, voice)


def generate_full_audio(
    script: str,
    voice: str = "female-yujie",
    api_key: Optional[str] = None,
    progress_callback=None
) -> Optional[AudioSegment]:
    """
    一次性生成完整配音（合并所有文案）

    Args:
        script: 完整文案
        voice: 音色
        api_key: API Key
        progress_callback: 回调

    Returns:
        AudioSegment: 包含完整配音和时间戳
    """
    generator = TTSGenerator(api_key)

    if progress_callback:
        progress_callback("tts", "🎤 正在生成完整配音...")

    return generator.generate(script, voice, progress_callback)