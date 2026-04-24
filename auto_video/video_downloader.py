# -*- coding: utf-8 -*-
"""
多线程视频下载模块
===================
支持多线程并行下载视频
"""

import os
import requests
from pathlib import Path
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

import config

# 线程安全的日志存储
_download_logs = []
_download_logs_lock = None


def get_download_logs():
    """获取下载日志"""
    global _download_logs
    return _download_logs


def clear_download_logs():
    """清空下载日志"""
    global _download_logs
    _download_logs = []


def download_single_video(video, cache_dir: Path, log_collector: Optional[Callable] = None) -> Optional[str]:
    """
    下载单个视频

    Args:
        video: VideoAsset 对象
        cache_dir: 缓存目录
        log_collector: 日志收集回调 (线程安全)

    Returns:
        本地路径或None
    """
    # 生成文件名
    ext = "mp4"
    try:
        url_ext = video.url.split("?")[0].split(".")[-1][:4]
        if url_ext in ["mp4", "webm", "mov"]:
            ext = url_ext
    except:
        pass

    filename = f"{video.source}_{video.id}.{ext}"
    local_path = cache_dir / filename

    # 如果已存在，验证实际时长
    if local_path.exists():
        # 验证缓存文件的实际时长
        try:
            from pymediainfo import MediaInfo
            mi = MediaInfo.parse(str(local_path))
            for track in mi.tracks:
                if track.track_type == "Video":
                    actual_duration = float(getattr(track, "duration", 0) or 0) / 1000
                    video.duration = actual_duration  # 更新为实际时长
                    break
        except:
            pass

        # 检查缓存文件是否有效（至少有一些时长）
        if video.duration > 0:
            if log_collector:
                log_collector("cache", f"✅ 使用缓存: {filename} (实际时长: {video.duration:.1f}s)")
            return str(local_path)
        else:
            # 缓存文件无效，删除重新下载
            if log_collector:
                log_collector("cache", f"⚠️ 缓存文件无效，重新下载: {filename}")
            local_path.unlink()

    try:
        if log_collector:
            log_collector("download", f"📥 开始下载: {video.id}")

        # 先 HEAD 请求检查文件大小
        head_resp = requests.head(video.url, timeout=30, allow_redirects=True)
        if head_resp.status_code == 200:
            file_size = int(head_resp.headers.get("content-length", 0))
            max_size = 150 * 1024 * 1024  # 150MB

            if file_size > max_size:
                if log_collector:
                    log_collector("skip", f"⏭️ 跳过 {video.id}: 文件过大 ({file_size/1024/1024:.1f}MB > 150MB)")
                return None

            # 记录文件大小
            if hasattr(video, 'size'):
                video.size = file_size

        response = requests.get(video.url, stream=True, timeout=120)

        if response.status_code == 200:
            total_size = int(response.headers.get("content-length", 0))

            with open(local_path, "wb") as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit="B", unit_scale=True, desc=filename) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            # 验证实际下载的视频时长
            try:
                from pymediainfo import MediaInfo
                mi = MediaInfo.parse(str(local_path))
                for track in mi.tracks:
                    if track.track_type == "Video":
                        actual_duration = float(getattr(track, "duration", 0) or 0) / 1000  # 毫秒转秒
                        if actual_duration > 0:
                            video.duration = actual_duration  # 更新为实际时长
                            if log_collector:
                                log_collector("download", f"✅ 下载完成: {filename} (实际时长: {actual_duration:.1f}s)")
                        break
            except Exception as e:
                if log_collector:
                    log_collector("download", f"✅ 下载完成: {filename}")

            return str(local_path)

    except Exception as e:
        if log_collector:
            log_collector("error", f"❌ 下载失败: {e}")
        if local_path.exists():
            local_path.unlink()

    return None


def download_videos_multithread(
    videos: List,
    cache_dir: Path,
    max_workers: int = 3,
    log_collector: Optional[Callable] = None
) -> List:
    """
    多线程下载视频

    Args:
        videos: VideoAsset 列表
        cache_dir: 缓存目录
        max_workers: 最大线程数
        log_collector: 日志收集回调

    Returns:
        下载成功的视频列表（保持输入顺序）
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    log_collector = log_collector or (lambda s, m: print(f"[{s}] {m}"))

    # 使用字典保存结果，key 为 video.id
    results = {}

    # 使用线程池并行下载
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有下载任务
        future_to_video = {
            executor.submit(download_single_video, v, cache_dir, log_collector): v
            for v in videos
        }

        # 收集结果
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            try:
                local_path = future.result()
                if local_path:
                    video.local_path = local_path
                    results[video.id] = video
            except Exception as e:
                log_collector("error", f"❌ {video.id} 下载异常: {e}")

    # 按输入顺序返回结果
    downloaded = []
    for v in videos:
        if v.id in results:
            downloaded.append(results[v.id])

    return downloaded