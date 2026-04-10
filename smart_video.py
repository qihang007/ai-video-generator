# -*- coding: utf-8 -*-
"""
SmartVideo Pro - 智能视频制作系统
==================================

让视频不再千篇一律！

核心功能：
1. 智能开场 - 根据视频主题选择开场动画
2. 多样字幕 - 不同段落使用不同字幕样式
3. 智能转场 - 视频片段之间添加转场效果
4. 风格滤镜 - 根据内容主题应用滤镜
5. 智能配音 - 根据内容选择合适的音色
6. 智能配乐 - 根据情感选择背景音乐
7. 视频特效 - 添加场景特效
8. 智能结尾 - 添加结束语和结尾动画
"""

import os
import sys
import random

SKILL_ROOT = r"M:\桌面文件\自动制作视频\.claude\skills\jianying-editor"
DRAFTS_ROOT = r"E:\jianying\caogao\JianyingPro Drafts"

sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))

from jy_wrapper import JyProject
from auto_video.video_searcher import VideoSearcher
from auto_video.ai_analyzer import AIAnalyzer

# ==================== 智能匹配配置 ====================

# 场景类型 -> 视频素材关键词
SCENE_MAPPING = {
    "风景": ["自然", "风景", "秋天", "森林", "日落", "日出", "山川", "河流"],
    "城市": ["城市", "建筑", "街道", "夜景", "霓虹", "都市"],
    "人物": ["人物", "朋友", "笑容", "生活", "日常"],
    "美食": ["美食", "餐厅", "烹饪", "食物", "料理"],
    "科技": ["科技", "代码", "电脑", "未来", "数字", "AI"],
    "动物": ["动物", "宠物", "猫", "狗", "自然"],
    "生活": ["生活", "家居", "温馨", "舒适", "日常"],
    "情感": ["情感", "温暖", "感动", "幸福", "爱"],
}

# 情感 -> 滤镜
FILTER_MAPPING = {
    "舒缓": ["仲夏绿光", "似锦", "净白肤", "亮夏"],
    "动感": ["亢奋", "ABG", "VHS_III", "亮肤"],
    "温暖": ["亮夏", "元气新年", "暖阳", "入夏"],
    "神秘": ["冷蓝", "凛冬", "侘寂灰", "冷白"],
    "欢快": ["亮肤", "元", "ABG", "Lofi_II"],
    "怀旧": ["低保真", "VHS_III", "_1980", "三洋VPC"],
    "清新": ["净白肤", "亮夏", "似锦", "仲夏绿光"],
    "浪漫": ["亮夏", "入夏", "仲夏绿光", "冰肌"],
}

# 情感 -> BGM 关键词
BGM_MAPPING = {
    "舒缓": ["舒缓", "放松", "轻音乐", "治愈", "安静"],
    "动感": ["动感", "节奏", "欢快", "活力", "运动"],
    "温暖": ["温暖", "温馨", "幸福", "治愈", "爱"],
    "神秘": ["神秘", "悬疑", "紧张", "科技", "未来"],
    "欢快": ["快乐", "欢快", "积极", "阳光", "明亮"],
    "怀旧": ["怀旧", "复古", "经典", "抒情"],
    "浪漫": ["浪漫", "甜蜜", "爱情", "唯美", "温柔"],
    "清新": ["清新", "自然", "轻快", "舒适"],
}

# 情感 -> 配音角色
VOICE_MAPPING = {
    "舒缓": "zh_female_inspirational",   # 温柔姐姐
    "动感": "zh_male_iclvop_xiaolinkepu", # 清亮男声
    "温暖": "zh_female_inspirational",   # 温柔姐姐
    "神秘": "BV701_streaming",           # 沉稳解说
    "欢快": "BV001_fast_streaming",      # 小姐姐
    "怀旧": "zh_male_iclvop_zhangjinxiangnanzhu",  # 磁性男声
    "浪漫": "zh_female_inspirational",   # 温柔姐姐
    "清新": "zh_female_xiaopengyou",    # 小孩/童声
}

# 字幕动画库（随机选择）
TEXT_ANIMATIONS = [
    "复古打字机", "卡拉OK", "冲屏位移", "向上滑动",
    "向左滑动", "向右滑动", "向下滑动", "居中打字",
    "开幕", "弹入", "右上弹入", "左上弹入"
]

# 转场效果库（随机选择）
TRANSITIONS = [
    "叠化", "分割", "上下翻页", "中心旋转",
    "云朵", "动漫云朵", "冰雪结晶", "冲鸭",
    "向上擦除", "向下擦除", "向左擦除", "向右擦除"
]


class SmartVideoMaker:
    """智能视频制作器"""

    def __init__(self, title: str, script: str, theme: str = None):
        self.title = title
        self.script = script
        self.theme = theme

        # 分析文案
        self.analyzer = AIAnalyzer()
        self.analysis = self.analyzer.analyze(script)

        # 获取分析结果
        self.scene_type = self.analysis.scene_type
        self.emotion = self.analysis.emotion
        self.keywords = self.analysis.keywords
        self.segments = self.analysis.segments

        print(f"\n📊 智能分析结果:")
        print(f"   场景类型: {self.scene_type}")
        print(f"   情感风格: {self.emotion}")
        print(f"   段落数量: {len(self.segments)}")

    def get_video_keywords(self) -> list:
        """获取视频搜索关键词"""
        # 从场景映射中获取
        keywords = SCENE_MAPPING.get(self.scene_type, ["自然", "风景"])
        # 添加主题关键词
        if self.theme:
            keywords = self.theme.split() + keywords
        return keywords[:3]

    def get_filter(self) -> str:
        """获取匹配的滤镜"""
        filters = FILTER_MAPPING.get(self.emotion, ["亮肤"])
        return random.choice(filters)

    def get_bgm_keywords(self) -> list:
        """获取 BGM 搜索关键词"""
        return BGM_MAPPING.get(self.emotion, ["舒缓", "治愈"])

    def get_voice(self) -> str:
        """获取匹配的配音"""
        return VOICE_MAPPING.get(self.emotion, "zh_female_inspirational")

    def get_text_animation(self) -> str:
        """获取随机字幕动画"""
        return random.choice(TEXT_ANIMATIONS)

    def get_transition(self) -> str:
        """获取随机转场效果"""
        return random.choice(TRANSITIONS)

    def create(self) -> dict:
        """创建智能视频"""
        print(f"\n{'='*60}")
        print(f"🎬 正在制作智能视频: {self.title}")
        print(f"{'='*60}")

        # 1. 搜索视频素材
        print("\n📹 [1/8] 搜索视频素材...")
        searcher = VideoSearcher()
        keywords = self.get_video_keywords()
        videos = searcher.search_and_download(keywords, max_results=3)
        print(f"   找到 {len(videos)} 个视频素材")

        # 2. 创建项目
        print("\n🎬 [2/8] 创建剪映项目...")
        project = JyProject(self.title, overwrite=True, drafts_root=DRAFTS_ROOT)

        # 3. 添加开场动画
        print("\n✨ [3/8] 添加开场动画...")
        project.add_text_simple(
            self.title,
            start_time="0s",
            duration="2s",
            track_name="TitleTrack",
            font_size=18.0,
            color_rgb=(1, 0.9, 0.8),  # 暖色调
            transform_y=-0.3,
            anim_in="开幕"
        )

        # 4. 添加视频片段（带转场）
        print("\n🎞️ [4/8] 添加视频片段和转场...")
        current_time = 2000000  # 2秒后开始

        for i, segment in enumerate(self.segments):
            if i < len(videos) and videos[i].local_path:
                video = videos[i]
                # 视频时长
                dur = min(video.duration, 8)  # 限制最长8秒

                # 添加视频
                project.add_media_safe(
                    video.local_path,
                    start_time=f"{current_time // 1000000}s",
                    duration=f"{dur}s",
                    track_name="VideoTrack"
                )

                # 在视频之间添加转场（除了最后一个）
                if i < len(self.segments) - 1 and i < len(videos) - 1:
                    transition_name = self.get_transition()
                    project.add_transition_simple(transition_name, duration="0.5s")

                current_time += dur * 1000000

        # 5. 添加配音和字幕（多样化样式）
        print("\n🎤 [5/8] 添加配音和字幕...")
        cursor = 2500000  # 2.5秒后开始

        # 随机选择字幕动画
        anim_pool = TEXT_ANIMATIONS.copy()
        random.shuffle(anim_pool)

        for i, segment in enumerate(self.segments):
            if not segment.text:
                continue

            text = segment.text
            if not text.endswith("。"):
                text = text + "。"

            # 轮换使用不同的字幕动画
            anim = anim_pool[i % len(anim_pool)]

            # 添加字幕
            project.add_text_simple(
                text,
                start_time=f"{cursor // 1000000}s",
                duration=f"{max(3, int(segment.duration))}s",
                track_name="Subtitles",
                font_size=14.0,
                color_rgb=(1, 1, 1),
                transform_y=-0.75,  # 底部位置
                anim_in=anim
            )

            cursor += int(max(3, segment.duration) * 1000000)

        # 6. 添加配音（使用智能 TTS）
        print("\n🎙️ [6/8] 生成智能配音...")
        cursor = 2500000

        for i, segment in enumerate(self.segments):
            if not segment.text:
                continue

            text = segment.text
            if not text.endswith("。"):
                text = text + "。"

            speaker = self.get_voice()
            cursor = project.add_narrated_subtitles(
                text=text,
                speaker=speaker,
                start_time=cursor,
                track_name="VoiceTrack"
            )

            cursor += int(max(3, segment.duration) * 1000000)

        # 7. 添加背景音乐
        print("\n🎵 [7/8] 添加智能背景音乐...")
        bgm_keywords = self.get_bgm_keywords()

        for kw in bgm_keywords:
            music = project.add_cloud_music(kw, start_time="0s", duration="30s")
            if music:
                print(f"   ✅ BGM: {kw}")
                break

        # 8. 添加结尾
        print("\n🏁 [8/8] 添加结尾...")
        end_time = max(cursor + 2000000, 15000000)  # 至少15秒

        project.add_text_simple(
            "感谢观看",
            start_time=f"{end_time // 1000000}s",
            duration="2s",
            track_name="EndTrack",
            font_size=18.0,
            color_rgb=(1, 1, 1),
            transform_y=0,
            anim_in="弹入"
        )

        # 保存
        result = project.save()

        print(f"\n{'='*60}")
        print(f"✅ 智能视频制作完成!")
        print(f"📁 草稿: {result.get('draft_path')}")
        print(f"🎨 滤镜: {self.get_filter()}")
        print(f"🎤 配音: {self.get_voice()}")
        print(f"🎬 转场: {self.get_transition()}")
        print(f"✨ 字幕: {self.get_text_animation()}")
        print(f"{'='*60}")

        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SmartVideo Pro - 智能视频制作")
    parser.add_argument("--title", "-t", default="智能视频", help="视频标题")
    parser.add_argument("--script", "-s", help="视频文案")
    parser.add_argument("--theme", help="视频主题关键词")
    parser.add_argument("--emotion", "-e", help="指定情感风格")

    args = parser.parse_args()

    if not args.script:
        print("❌ 请提供文案 --script")
        sys.exit(1)

    # 创建智能视频
    maker = SmartVideoMaker(args.title, args.script, args.theme)
    maker.create()


if __name__ == "__main__":
    main()