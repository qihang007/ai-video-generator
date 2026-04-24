# -*- coding: utf-8 -*-
"""
AutoVideo 智能视频生成器
=========================

结合 Pexels/Pixabay 视频素材 + jianying-editor skill
支持自然语言输入
"""

import os
import sys
import argparse

# jianying-editor skill 路径
SKILL_ROOT = r"M:\桌面文件\自动制作视频\.claude\skills\jianying-editor"
DRAFTS_ROOT = r"E:\jianying\caogao\JianyingPro Drafts"

sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))

from jy_wrapper import JyProject
import config
from auto_video.video_searcher import VideoSearcher
from auto_video.ai_analyzer import AIAnalyzer


# 默认文案模板
DEFAULT_SCRIPTS = {
    "秋天第一杯奶茶": """秋天的第一杯奶茶，你喝了吗？
随着第一片叶子落下，秋天悄然来临。
手捧一杯温热的奶茶，感受淡淡的奶香与茶香交织。
这是属于秋天的仪式感，温暖又甜蜜。
在这个微凉的季节里，让一杯奶茶给你带来好心情。""",

    "科技前沿": """欢迎来到科技前沿节目。
今天我们要讨论的是人工智能的最新发展。
从ChatGPT到Sora，AI正在改变我们的生活。
让我们一起探索未来的可能性。
关注科技前沿，了解更多前沿资讯。""",

    "美食分享": """今天给大家分享一道美味的家常菜。
这道菜简单易做，营养丰富。
首先准备好所需的食材。
现在开始制作...
一道美味的菜肴就完成了。
希望大家喜欢这道菜。""",
}


def create_video(
    title: str,
    script: str,
    theme: str = None,
    voice_style: str = "female",
    bgm_theme: str = "温馨",
    drafts_root: str = DRAFTS_ROOT
):
    """
    创建视频

    Args:
        title: 视频标题
        script: 视频文案
        theme: 视频主题/关键词（用于搜索视频素材）
        voice_style: 配音风格
        bgm_theme: BGM 主题
    """
    print(f"\n{'='*60}")
    print(f"🎬 开始制作视频: {title}")
    print(f"{'='*60}\n")

    # 1. 分析文案，提取关键词
    print("📝 [1/4] 分析文案...")
    analyzer = AIAnalyzer()
    analysis = analyzer.analyze(script)
    print(f"   关键词: {analysis.keywords[:5]}")
    print(f"   场景: {analysis.scene_type}")
    print(f"   段落数: {len(analysis.segments)}")

    # 2. 搜索视频素材 (使用 Pexels/Pixabay)
    print("\n🎥 [2/4] 搜索视频素材...")
    searcher = VideoSearcher()

    # 根据主题或关键词搜索
    search_keywords = [theme] if theme else analysis.keywords[:3]
    videos = searcher.search_and_download(search_keywords, max_results=2)

    if not videos:
        print("   ⚠️ 未找到视频素材，将使用云端素材")
        use_cloud = True
    else:
        print(f"   ✅ 找到 {len(videos)} 个视频素材")
        use_cloud = False
        for v in videos:
            print(f"      - {os.path.basename(v.local_path)}")

    # 3. 创建剪映项目
    print("\n🎬 [3/4] 创建剪映项目...")
    project = JyProject(title, overwrite=True, drafts_root=drafts_root)

    # 添加视频素材
    if not use_cloud:
        current_time = 0
        for v in videos:
            if v.local_path and os.path.exists(v.local_path):
                dur = min(v.duration, 10)  # 限制最长10秒
                project.add_media_safe(
                    v.local_path,
                    start_time=f"{current_time}s",
                    duration=f"{dur}s",
                    track_name="VideoTrack"
                )
                current_time += dur
    else:
        # 使用云端素材作为备选
        project.add_cloud_media("自然", start_time="0s", duration="10s", track_name="VideoTrack")

    # 4. 添加配音和字幕
    print("\n🎤 [4/4] 添加配音和字幕...")

    # 配音角色映射
    SPEAKERS = {
        "female": "zh_female_inspirational",  # 温柔女声
        "male": "zh_male_iclvop_xiaolinkepu",  # 清亮男声
        "child": "zh_female_xiaopengyou",      # 小孩
    }
    speaker = SPEAKERS.get(voice_style, SPEAKERS["female"])

    cursor = 500000
    sentences = [s.strip() for s in script.split("。") if s.strip()]

    for sentence in sentences:
        if not sentence:
            continue
        sentence = sentence + "。" if not sentence.endswith("。") else sentence

        cursor = project.add_narrated_subtitles(
            text=sentence,
            speaker=speaker,
            start_time=cursor,
            track_name="Subtitles"
        )

        # 估算时长
        duration = max(2000000, int(len(sentence) * 0.4 * 1000000))
        cursor += duration

    # 添加背景音乐
    print("   🎵 添加背景音乐...")
    music_keywords = [bgm_theme, "温暖", "舒缓", "治愈"]
    for kw in music_keywords:
        music = project.add_cloud_music(kw, start_time="0s", duration="15s")
        if music:
            print(f"      ✅ BGM: {kw}")
            break

    # 添加标题
    project.add_text_simple(
        title,
        start_time="0.3s",
        duration="3s",
        track_name="TitleTrack",
        font_size=15.0,
        color_rgb=(1, 1, 1),
        transform_y=-0.5,
        anim_in="复古打字机"
    )

    # 保存
    result = project.save()

    print(f"\n{'='*60}")
    print(f"✅ 视频制作完成!")
    print(f"📁 草稿路径: {result.get('draft_path')}")
    print(f"{'='*60}\n")

    return result


def main():
    parser = argparse.ArgumentParser(description="AutoVideo 智能视频生成器")
    parser.add_argument("--title", "-t", help="视频标题")
    parser.add_argument("--script", "-s", help="视频文案")
    parser.add_argument("--theme", help="视频主题/关键词 (用于搜索视频)")
    parser.add_argument("--voice", "-v", default="female", choices=["male", "female", "child"], help="配音风格")
    parser.add_argument("--bgm", "-b", default="温馨", help="BGM 主题")
    parser.add_argument("--template", help="使用预设模板: 秋天第一杯奶茶/科技前沿/美食分享")

    args = parser.parse_args()

    # 确定标题和文案
    if args.template and args.template in DEFAULT_SCRIPTS:
        title = args.title or args.template
        script = DEFAULT_SCRIPTS[args.template]
    else:
        title = args.title or "自动生成视频"
        script = args.script

        if not script:
            print("❌ 请提供文案 --script 或使用 --template")
            print(f"\n可用模板: {', '.join(DEFAULT_SCRIPTS.keys())}")
            sys.exit(1)

    # 创建视频
    create_video(
        title=title,
        script=script,
        theme=args.theme,
        voice_style=args.voice,
        bgm_theme=args.bgm
    )


if __name__ == "__main__":
    main()