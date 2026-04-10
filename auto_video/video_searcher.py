# -*- coding: utf-8 -*-
"""
视频素材搜索模块
=================

支持 Pexels API 和 Pixabay API 视频素材搜索与下载
"""

import os
import hashlib
import time
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests
from tqdm import tqdm

import config

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class VideoAsset:
    """视频素材数据类"""
    id: str
    source: str  # "pexels" or "pixabay"
    url: str  # 下载链接
    thumbnail: str  # 缩略图
    width: int
    height: int
    duration: int  # 时长(秒)
    photographer: str
    keywords: List[str]
    size: int = 0  # 文件大小(字节)
    local_path: Optional[str] = None


class VideoSearcher:
    """视频素材搜索器"""

    def __init__(
        self,
        pexels_api_key: Optional[str] = None,
        pixabay_api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        progress_callback: Optional[callable] = None
    ):
        """
        初始化搜索器

        Args:
            pexels_api_key: Pexels API Key
            pixabay_api_key: Pixabay API Key
            cache_dir: 视频缓存目录
            progress_callback: 进度回调函数 (stage, message)
        """
        self.pexels_api_key = pexels_api_key or config.PEXELS_API_KEY
        self.pixabay_api_key = pixabay_api_key or config.PIXABAY_API_KEY
        self.progress_callback = progress_callback

        # 确保缓存目录存在 - 使用更安全的初始化方式
        # 默认使用项目根目录下的 output/videos
        default_cache = Path(PROJECT_ROOT) / "output" / "videos"

        if cache_dir is None:
            self.cache_dir = default_cache
        elif isinstance(cache_dir, str):
            self.cache_dir = Path(cache_dir)
        elif hasattr(cache_dir, 'mkdir'):
            self.cache_dir = cache_dir
        else:
            try:
                self.cache_dir = Path(cache_dir)
            except Exception:
                self.cache_dir = default_cache

        # 确保是 Path 对象
        if not isinstance(self.cache_dir, Path):
            self.cache_dir = Path(str(self.cache_dir))

        # 创建目录
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"创建缓存目录失败: {e}")
            # 回退到临时目录
            import tempfile
            self.cache_dir = Path(tempfile.gettempdir()) / "autovideo_videos"
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 下载记录缓存
        self.download_cache_file = self.cache_dir / "download_cache.json"
        self.download_cache = self._load_download_cache()

    def _load_download_cache(self) -> Dict[str, Any]:
        """加载下载缓存"""
        if self.download_cache_file.exists():
            try:
                with open(self.download_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_download_cache(self):
        """保存下载缓存"""
        with open(self.download_cache_file, "w", encoding="utf-8") as f:
            json.dump(self.download_cache, f, ensure_ascii=False, indent=2)

    def _get_cache_key(self, video_id: str, source: str) -> str:
        """获取缓存键"""
        return f"{source}_{video_id}"

    def _get_cached_video(self, video_id: str, source: str) -> Optional[VideoAsset]:
        """获取缓存的视频"""
        cache_key = self._get_cache_key(video_id, source)
        if cache_key in self.download_cache:
            cached = self.download_cache[cache_key]
            local_path = Path(cached.get("local_path", ""))
            if local_path.exists():
                return VideoAsset(
                    id=video_id,
                    source=source,
                    url=cached.get("url", ""),
                    thumbnail=cached.get("thumbnail", ""),
                    width=cached.get("width", 0),
                    height=cached.get("height", 0),
                    duration=cached.get("duration", 0),
                    photographer=cached.get("photographer", ""),
                    keywords=cached.get("keywords", []),
                    local_path=str(local_path)
                )
        return None

    def _save_video_info(self, video: VideoAsset):
        """保存视频信息到缓存"""
        cache_key = self._get_cache_key(video.id, video.source)
        self.download_cache[cache_key] = {
            "id": video.id,
            "source": video.source,
            "url": video.url,
            "thumbnail": video.thumbnail,
            "width": video.width,
            "height": video.height,
            "duration": video.duration,
            "photographer": video.photographer,
            "keywords": video.keywords,
            "local_path": video.local_path,
            "cached_at": datetime.now().isoformat()
        }
        self._save_download_cache()

    def search_pexels(
        self,
        keywords: List[str],
        min_duration: int = 5,
        max_duration: int = 60,
        per_page: int = 15,
        orientation: str = "landscape",  # landscape(横屏) 或 portrait(竖屏)
        max_retries: int = 3
    ) -> List[VideoAsset]:
        """
        搜索 Pexels 视频素材

        Args:
            keywords: 关键词列表
            min_duration: 最小时长(秒)
            max_duration: 最大时长(秒)
            per_page: 每次请求返回数量
            orientation: 视频方向 landscape/portrait
            max_retries: 最大重试次数

        Returns:
            List[VideoAsset]: 视频素材列表
        """
        if self.progress_callback:
            self.progress_callback("search", f"🔍 搜索 Pexels 视频: {keywords[0] if keywords else ''}")

        if not self.pexels_api_key:
            print("[Pexels] API Key 未设置")
            return []

        # 只用第一个关键词搜索（每个关键词已经是完整短语）
        query = keywords[0] if keywords else "nature"

        headers = {
            "Authorization": self.pexels_api_key
        }

        params = {
            "query": query,
            "per_page": per_page,
            "min_width": 1280,
            "min_height": 720,
            "min_duration": min_duration,
            "orientation": orientation,  # Pexels API 支持方向过滤
        }

        videos = []
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers=headers,
                    params=params,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("videos", []):
                        # 选择最佳质量的视频文件（排除4K）
                        video_files = item.get("video_files", [])
                        best_video = None
                        for vf in video_files:
                            height = vf.get("height", 0)
                            # 排除4K视频（2160p及以上），优先选择HD/全高清
                            if height >= 2160:
                                continue  # 跳过4K
                            if height >= 1080:
                                best_video = vf
                                break
                            elif height >= 720 and not best_video:
                                best_video = vf

                        if not best_video and video_files:
                            best_video = video_files[0]

                        if best_video:
                            width = best_video.get("width", 0)
                            height = best_video.get("height", 0)

                            # 检查是否符合方向要求
                            is_landscape = width >= height
                            if orientation == "landscape" and not is_landscape:
                                continue  # 跳过竖屏视频
                            if orientation == "portrait" and is_landscape:
                                continue  # 跳过横屏视频

                            video = VideoAsset(
                                id=str(item.get("id", "")),
                                source="pexels",
                                url=best_video.get("link", ""),
                                thumbnail=item.get("image", ""),
                                width=width,
                                height=height,
                                duration=item.get("duration", 0),
                                photographer=item.get("user", {}).get("name", ""),
                                keywords=keywords
                            )
                            videos.append(video)
                    # 只打印找到的数量，不打印每个视频详情
                    if videos:
                        print(f"[Pexels] 搜索完成，找到 {len(videos)} 个视频")
                    break  # 成功，跳出重试循环

                elif response.status_code == 401:
                    print("[Pexels] API Key 无效")
                    break
                elif response.status_code == 429:
                    print(f"[Pexels] 请求频率限制，等待后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    print(f"[Pexels] 请求失败: {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(1)

            except requests.exceptions.SSLError as e:
                print(f"[Pexels] SSL 错误，重试中 ({attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except requests.exceptions.Timeout as e:
                print(f"[Pexels] 请求超时，重试中 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)
            except requests.exceptions.ConnectionError as e:
                print(f"[Pexels] 连接错误，重试中 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                print(f"[Pexels] 搜索出错: {e}")
                break

        return videos

    def search_pixabay(
        self,
        keywords: List[str],
        min_duration: int = 5,
        max_duration: int = 60,
        per_page: int = 20,
        orientation: str = "landscape",  # landscape(横屏) 或 portrait(竖屏)
        max_retries: int = 3
    ) -> List[VideoAsset]:
        """
        搜索 Pixabay 视频素材

        Args:
            keywords: 关键词列表
            min_duration: 最小时长(秒)
            max_duration: 最大时长(秒)
            per_page: 每次请求返回数量 (最少3个)
            orientation: 视频方向 landscape/portrait
            max_retries: 最大重试次数

        Returns:
            List[VideoAsset]: 视频素材列表
        """
        # Pixabay API 要求 per_page 至少为 3
        per_page = max(per_page, 3)

        if not self.pixabay_api_key:
            print("[Pixabay] API Key 未设置")
            return []

        # 只用第一个关键词搜索（每个关键词已经是完整短语）
        query = keywords[0] if keywords else "nature"

        params = {
            "key": self.pixabay_api_key,
            "q": query,
            "per_page": per_page,
            "video_type": "film",
            "min_width": 1280,
            "min_height": 720,
            "orientation": orientation,  # horizontal/vertical
        }

        videos = []
        for attempt in range(max_retries):
            try:
                # 添加 User-Agent 避免被限流
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                response = requests.get(
                    "https://pixabay.com/api/videos/",
                    params=params,
                    headers=headers,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("hits", []):
                        # 选择最佳质量的视频 (large, medium, small)，排除4K
                        video_variants = item.get("videos", {})
                        best_video = None
                        # 优先选择 large（完整版），避免 small 预览版时长不足
                        for quality in ["large", "medium", "small"]:
                            vf = video_variants.get(quality)
                            if vf and vf.get("height", 0) < 2160:
                                # 检查这个变体是否有时长信息，如果有则使用
                                variant_duration = vf.get("duration")
                                best_video = vf
                                best_video["_quality"] = quality  # 记录质量级别
                                break

                        if best_video:
                            width = best_video.get("width", 0)
                            height = best_video.get("height", 0)

                            # 检查是否符合方向要求
                            is_landscape = width >= height
                            if orientation == "landscape" and not is_landscape:
                                continue  # 跳过竖屏视频
                            if orientation == "portrait" and is_landscape:
                                continue  # 跳过横屏视频

                            # 优先使用变体时长，如果没有则用 item 级别时长
                            # 注意：small 版本可能是预览版，时长可能短于完整版
                            duration = int(item.get("duration", 0) or 0)
                            video = VideoAsset(
                                id=str(item.get("id", "")),
                                source="pixabay",
                                url=best_video.get("url", ""),
                                thumbnail=item.get("largeImageURL", ""),
                                width=width,
                                height=height,
                                duration=duration,
                                photographer=item.get("user", ""),
                                keywords=keywords
                            )
                            videos.append(video)
                    if videos:
                        print(f"[Pixabay] 搜索完成，找到 {len(videos)} 个视频")
                    break  # 成功，跳出重试循环

                elif response.status_code == 429:
                    print(f"[Pixabay] 请求频率限制，等待后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(2 ** attempt)
                else:
                    print(f"[Pixabay] 请求失败: {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(1)

            except requests.exceptions.SSLError as e:
                print(f"[Pixabay] SSL 错误，重试中 ({attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except requests.exceptions.Timeout as e:
                print(f"[Pixabay] 请求超时，重试中 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)
            except requests.exceptions.ConnectionError as e:
                print(f"[Pixabay] 连接错误，重试中 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                print(f"[Pixabay] 搜索出错: {e}")
                break

        return videos

    def download_video(
        self,
        video: VideoAsset,
        filename: Optional[str] = None
    ) -> Optional[str]:
        """
        下载视频到本地

        Args:
            video: 视频素材
            filename: 自定义文件名

        Returns:
            str: 本地文件路径，失败返回None
        """
        # 检查缓存
        cached = self._get_cached_video(video.id, video.source)
        if cached:
            if self.progress_callback:
                self.progress_callback("cache", f"✅ 使用缓存: {cached.local_path}")
            return cached.local_path

        # 生成文件名
        ext = "mp4"
        try:
            url_ext = video.url.split("?")[0].split(".")[-1][:4]
            if url_ext in ["mp4", "webm", "mov"]:
                ext = url_ext
        except:
            pass

        if filename is None:
            filename = f"{video.source}_{video.id}.{ext}"

        if self.progress_callback:
            self.progress_callback("download", f"📥 开始下载视频...")

        # 确保 cache_dir 存在
        if self.cache_dir is None:
            self.cache_dir = Path("output/videos")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        local_path = self.cache_dir / filename

        try:
            print(f"[下载] 开始下载: {video.url[:50]}...")

            # 先 HEAD 请求检查文件大小
            head_resp = requests.head(video.url, timeout=30, allow_redirects=True)
            if head_resp.status_code == 200:
                file_size = int(head_resp.headers.get("content-length", 0))
                max_size = 150 * 1024 * 1024  # 150MB

                if file_size > max_size:
                    print(f"[下载] 跳过 {video.id}: 文件过大 ({file_size/1024/1024:.1f}MB > 150MB)")
                    if self.progress_callback:
                        self.progress_callback("skip", f"⏭️ 跳过: 文件过大")
                    return None

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

                # 保存到缓存
                video.local_path = str(local_path)
                self._save_video_info(video)

                print(f"[下载] 完成: {local_path}")
                if self.progress_callback:
                    self.progress_callback("download", f"✅ 下载完成: {os.path.basename(local_path)}")
                return str(local_path)
            else:
                print(f"[下载] 失败: HTTP {response.status_code}")
                if self.progress_callback:
                    self.progress_callback("error", f"❌ 下载失败: HTTP {response.status_code}")

        except Exception as e:
            print(f"[下载] 出错: {e}")
            if self.progress_callback:
                self.progress_callback("error", f"❌ 下载出错: {e}")
            # 清理失败的下载
            if local_path.exists():
                local_path.unlink()

        return None

    def search(
        self,
        keywords: List[str],
        min_duration: int = 5,
        max_duration: int = 60,
        max_results: int = 5,
        orientation: str = "landscape"
    ) -> List[VideoAsset]:
        """
        综合搜索（优先Pexels，失败则用Pixabay）

        Args:
            keywords: 关键词列表
            min_duration: 最小时长
            max_duration: 最大时长
            max_results: 最大结果数
            orientation: 视频方向 landscape/portrait

        Returns:
            List[VideoAsset]: 视频素材列表
        """
        results = []

        # 1. 优先尝试 Pexels
        if self.pexels_api_key:
            print(f"\n=== 搜索 Pexels (关键词: {keywords[0] if keywords else 'nature'}, 方向: {orientation}) ===")
            pexels_results = self.search_pexels(keywords, min_duration, max_duration, orientation=orientation)
            results.extend(pexels_results[:max_results])

        # 2. 如果Pexels没有足够结果，尝试Pixabay
        if len(results) < max_results and self.pixabay_api_key:
            print(f"\n=== 搜索 Pixabay (关键词: {keywords[0] if keywords else 'nature'}, 方向: {orientation}) ===")
            needed = max_results - len(results)
            pixabay_results = self.search_pixabay(keywords, min_duration, max_duration, orientation=orientation)
            # 过滤掉已在结果中的视频
            existing_ids = {v.id for v in results}
            for v in pixabay_results:
                if v.id not in existing_ids and len(results) < max_results:
                    results.append(v)

        return results[:max_results]

    def search_and_download(
        self,
        keywords: List[str],
        min_duration: int = 5,
        max_duration: int = 60,
        max_results: int = 5
    ) -> List[VideoAsset]:
        """
        搜索并下载视频素材

        Args:
            keywords: 关键词列表
            min_duration: 最小时长
            max_duration: 最大时长
            max_results: 最大结果数

        Returns:
            List[VideoAsset]: 包含本地路径的视频素材列表
        """
        if self.progress_callback:
            self.progress_callback("search", f"🔍 搜索视频素材: {keywords}")

        videos = self.search(keywords, min_duration, max_duration, max_results)

        if self.progress_callback:
            self.progress_callback("search", f"✅ 找到 {len(videos)} 个视频素材")

        # 下载所有视频
        downloaded = []
        for i, video in enumerate(videos):
            if self.progress_callback:
                self.progress_callback("download", f"📥 下载视频 {i+1}/{len(videos)}")

            local_path = self.download_video(video)
            if local_path:
                video.local_path = local_path
                downloaded.append(video)

        return downloaded


# 便捷函数
def search_videos(
    keywords: List[str],
    pexels_api_key: Optional[str] = None,
    pixabay_api_key: Optional[str] = None,
    max_results: int = 5
) -> List[VideoAsset]:
    """
    便捷函数：搜索视频素材

    Args:
        keywords: 关键词列表
        pexels_api_key: Pexels API Key
        pixabay_api_key: Pixabay API Key
        max_results: 最大结果数

    Returns:
        List[VideoAsset]: 视频素材列表
    """
    searcher = VideoSearcher(pexels_api_key, pixabay_api_key)
    return searcher.search_and_download(
        keywords,
        min_duration=config.VIDEO_MIN_DURATION,
        max_duration=config.VIDEO_MAX_DURATION,
        max_results=max_results
    )