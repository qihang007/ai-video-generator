# -*- coding: utf-8 -*-
"""
统一配置文件 - AI 视频生成系统
=============================================
合并云端模式（方案a）和本地模式（方案b）的配置
API Keys 默认值为空，实际值通过 user_config.json 传入
Supabase 授权配置硬编码在 license_manager.py 中
"""

import os
from pathlib import Path

# ==================== 项目路径 ====================
PROJECT_ROOT = Path(__file__).parent

# ==================== 输出目录 ====================
OUTPUT_DIR = PROJECT_ROOT / "output"
VIDEOS_DIR = OUTPUT_DIR / "videos"
AUDIO_DIR = OUTPUT_DIR / "audio"
SUBTITLES_DIR = OUTPUT_DIR / "subtitles"
DRAFTS_DIR = OUTPUT_DIR / "drafts"

for dir_path in [OUTPUT_DIR, VIDEOS_DIR, AUDIO_DIR, SUBTITLES_DIR, DRAFTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ==================== API Keys（从环境变量读取） ====================

# 智谱 AI（文案分析、BGM/音效推荐、脚本生成）
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", "glm-4-plus")

# MiniMax / 优刻得配音 API
MODELVERSE_API_KEY = os.getenv("MODELVERSE_API_KEY", "")
MODELVERSE_URL = "https://api.minimaxi.com/v1/t2a_v2"

# Pexels / Pixabay（云端模式视频素材）
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# SiliconFlow ASR（字幕识别）
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

# ==================== 剪映配置 ====================
JIANYING_DRAFTS_ROOT = os.getenv(
    "JIANYING_DRAFTS_ROOT",
    r"E:\jianying\caogao\JianyingPro Drafts"
)

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30

# ==================== 配音音色（MiniMax/优刻得）====================
TTS_VOICES = {
    "male-qn-qingse": "青涩青年",
    "male-qn-jingying": "精英青年",
    "male-qn-badao": "霸道青年",
    "male-qn-daxuesheng": "青年大学生",
    "female-shaonv": "少女",
    "female-yujie": "御姐",
    "female-chengshu": "成熟女性",
    "female-tianmei": "甜美女性",
    "Chinese (Mandarin)_Gentleman": "温润男声",
    "Chinese (Mandarin)_Warm_Girl": "温暖少女",
    "Chinese (Mandarin)_Gentle_Youth": "温润青年",
    "Chinese (Mandarin)_Sincere_Adult": "真诚青年",
    "Chinese (Mandarin)_Sweet_Lady": "甜美女声",
    "Chinese (Mandarin)_Crisp_Girl": "清脆少女",
    "Chinese (Mandarin)_Warm_Bestie": "温暖闺蜜",
    "Chinese (Mandarin)_Southern_Young_Man": "南方小哥",
    "Chinese (Mandarin)_Male_Announcer": "播报男声",
    "Chinese (Mandarin)_Radio_Host": "电台男主播",
    "Chinese (Mandarin)_Lyrical_Voice": "抒情男声",
    "Chinese (Mandarin)_News_Anchor": "新闻女声",
    "Chinese (Mandarin)_Wise_Women": "阅历姐姐",
    "Chinese (Mandarin)_Kind-hearted_Antie": "热心大婶",
    "Chinese (Mandarin)_Humorous_Elder": "搞笑大爷",
    "Chinese (Mandarin)_Kind-hearted_Elder": "花甲奶奶",
    "Chinese (Mandarin)_Cute_Spirit": "憨憨萌兽",
    "Chinese (Mandarin)_Straightforward_Boy": "率真弟弟",
    "Chinese (Mandarin)_Gentle_Senior": "温柔学姐",
    "Chinese (Mandarin)_Pure-hearted_Boy": "清澈邻家弟弟",
    "Chinese (Mandarin)_Soft_Girl": "柔和少女",
    "clever_boy": "聪明男童",
    "cute_boy": "可爱男童",
    "lovely_girl": "萌萌女童",
}

# 剪映内置音色（jianying-editor skill 内部使用）
JIANYING_TTS_SPEAKERS = {
    "male": "zh_male_iclvop_xiaolinkepu",
    "female": "BV001_fast_streaming",
    "child": "zh_female_xiaopengyou",
    "male_mature": "BV701_streaming",
}

# ==================== 视频素材配置（云端模式） ====================
VIDEO_QUALITY_PREFERENCE = ["4k", "hd", "sd"]
VIDEO_MIN_DURATION = 5
VIDEO_MAX_DURATION = 60

# ==================== AI 分析配置 ====================
MAX_KEYWORDS = 10
SCENE_TYPE_KEYWORDS = {
    "风景": ["海", "山", "日落", "日出", "森林", "草原", "天空", "云", "花", "树", "自然", "旅行"],
    "城市": ["城市", "建筑", "街道", "夜景", "灯", "车", "人", "现代化", "都市"],
    "人物": ["人", "朋友", "家人", "孩子", "男人", "女人", "笑容", "运动"],
    "美食": ["食物", "餐厅", "烹饪", "美食", "菜", "吃", "厨房"],
    "科技": ["电脑", "手机", "科技", "代码", "数据", "AI", "未来", "数字"],
    "动物": ["狗", "猫", "鸟", "动物", "海洋", "鱼", "野生动物"],
    "音乐": ["音乐", "舞蹈", "演唱会", "乐器", "弹奏", "唱歌"],
    "生活": ["生活", "日常", "home", "家居", "放松", "休闲"],
}
EMOTION_KEYWORDS = {
    "舒缓": ["放松", "平静", "安静", "休闲", "舒适", "慢", "轻松"],
    "动感": ["快", "运动", "活力", "激情", "兴奋", "跑", "跳"],
    "温暖": ["温暖", "幸福", "爱", "家", "温馨", "亲情", "友情"],
    "神秘": ["神秘", "黑暗", "夜晚", "未知", "科幻", "魔法"],
    "欢快": ["快乐", "开心", "笑", "庆祝", "节日", "派对"],
}

# ==================== 本地模式配置（方案b） ====================

# 素材库根目录（递归扫描，支持 images/ + videos/ 或混放）
LOCAL_MATERIALS_PATH = os.getenv("LOCAL_MATERIALS_PATH", "")

# ChromaDB 持久化目录
CHROMADB_PATH = PROJECT_ROOT / "chromadb_data"

# 向量增量检测缓存文件
MTIME_CACHE_FILE = PROJECT_ROOT / "mtime_cache.json"

# CLIP 模型配置
MODEL_NAME = "ViT-B-16"
LOCAL_MODEL_PATH = PROJECT_ROOT / "auto_video" / "clip_cn_vit-b-16.pt"
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"

# 镜头检测配置
SCENE_THRESHOLD = 27.0
MIN_SCENE_DURATION = 1.0
SKIP_SCENE_DETECTION_KEYWORDS = [
    "pixabay", "pexels", "videvo", "mixkit", "coverr", "mazwai"
]
SAMPLE_FRAMES_PER_SCENE = 1
CHROMADB_COLLECTION_NAME = "video_materials"

# 支持的文件格式
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
SUPPORTED_VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
DEFAULT_TOP_K = 5

# ==================== 辅助函数 ====================

def should_skip_scene_detection(filename: str) -> bool:
    """根据文件名判断是否跳过镜头检测"""
    fn = filename.lower()
    return any(kw in fn for kw in SKIP_SCENE_DETECTION_KEYWORDS)
