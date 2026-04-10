# -*- coding: utf-8 -*-
"""
AutoVideo System - 主入口
==========================

自动视频制作系统主程序
"""

import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from auto_video import (
    parse_input,
    VideoInput,
    AIAnalyzer,
    VideoSearcher,
    JianYingMaker,
    TTSGenerator,
    SubtitleGenerator
)


class AutoVideoMaker:
    """自动视频制作器主类"""

    # 配音风格映射到优刻得音色
    VOICE_STYLE_MAP = {
        "female": "female-yujie",      # 御姐
        "female_gentle": "female-tianmei",  # 甜美
        "female_young": "female-shaonv",    # 少女
        "male": "male-qn-qingse",      # 青涩青年
        "male_mature": "male-qn-jingying",  # 精英青年
        "male_deep": "Chinese (Mandarin)_Gentle_Youth",  # 温润青年
        "child": "lovely_girl",        # 萌萌女童
    }

    def __init__(
        self,
        pexels_api_key: str = None,
        pixabay_api_key: str = None,
        drafts_root: str = None
    ):
        """
        初始化自动视频制作器

        Args:
            pexels_api_key: Pexels API Key
            pixabay_api_key: Pixabay API Key
            drafts_root: 剪映草稿目录
        """
        self.pexels_api_key = pexels_api_key or config.PEXELS_API_KEY
        self.pixabay_api_key = pixabay_api_key or config.PIXABAY_API_KEY
        self.drafts_root = drafts_root

        # 初始化各模块
        self.ai_analyzer = AIAnalyzer()
        self.video_searcher = VideoSearcher(
            pexels_api_key=self.pexels_api_key,
            pixabay_api_key=self.pixabay_api_key
        )
        self.tts_generator = TTSGenerator()

    def make_video(
        self,
        title: str,
        script: str,
        style: str = "vlog",
        voice_style: str = "female",
        duration: int = None,
        max_video_results: int = 5
    ) -> dict:
        """
        制作视频（完整流程）

        Args:
            title: 视频标题
            script: 视频文案
            style: 视频风格
            voice_style: 配音风格
            duration: 目标时长
            max_video_results: 最大视频素材数量

        Returns:
            dict: 制作结果
        """
        print("\n" + "="*50)
        print(f"开始制作视频: {title}")
        print("="*50 + "\n")

        # 步骤1: 解析输入
        print("[1/5] 解析输入...")
        video_input = parse_input(
            title=title,
            script=script,
            style=style,
            voice_style=voice_style,
            duration=duration
        )
        print(f"  - 标题: {video_input.title}")
        print(f"  - 文案长度: {len(video_input.script)} 字符")
        print(f"  - 风格: {video_input.style}")
        print(f"  - 配音: {video_input.voice_style}")

        # 步骤2: AI分析
        print("\n[2/5] AI分析文案...")
        analysis_result = self.ai_analyzer.analyze(
            video_input.script,
            style=video_input.style
        )
        print(f"  - 关键词: {', '.join(analysis_result.keywords[:5])}")
        print(f"  - 场景类型: {analysis_result.scene_type}")
        print(f"  - 情绪类型: {analysis_result.emotion}")
        print(f"  - 段落数: {len(analysis_result.segments)}")

        # 步骤3: 搜索视频素材（每个段落对应一个视频）
        print("\n[3/5] 搜索视频素材...")

        # 为每个段落搜索对应关键词的视频
        videos = []
        for i, segment in enumerate(analysis_result.segments):
            # 使用段落的关键词搜索
            keywords = segment.keywords if segment.keywords else analysis_result.keywords
            print(f"  - 段落{i+1} 关键词: {keywords[:3]}")

            # 搜索多个结果，防止第一个视频不符合要求时被跳过
            segment_videos = self.video_searcher.search_and_download(
                keywords,
                max_results=3  # 搜索多个，下载时会自动跳过不符合的
            )

            if segment_videos:
                video = segment_videos[0]
                video.segment_index = i
                video.segment_duration = segment.duration
                video.segment_start = segment.start_time
                videos.append(video)
                print(f"    -> 找到视频: {video.id} ({video.duration}s)")
            else:
                print(f"    -> 未找到视频")

        print(f"  - 共找到视频: {len(videos)} 个")

        if not videos:
            print("  警告: 未能找到视频素材，视频轨道将为空")

        # 步骤4: 生成配音和字幕（使用优刻得 API）
        print("\n[4/5] 生成配音和字幕...")

        # 获取对应的优刻得音色
        voice_id = self.VOICE_STYLE_MAP.get(voice_style, "female-yujie")
        print(f"  - 使用音色: {voice_id}")

        # 生成配音（带字幕）
        tts_result = self.tts_generator.generate(
            video_input.script,
            voice=voice_id
        )

        if not tts_result:
            print("  ❌ 配音生成失败")
            return {"success": False, "error": "配音生成失败"}

        print(f"  - 配音文件: {os.path.basename(tts_result.audio_path)}")
        print(f"  - 配音时长: {tts_result.duration:.1f}秒")

        # 下载字幕并转换为 SRT（按标点分割）
        audio_path = tts_result.audio_path
        subtitle_path = None

        if tts_result.subtitle_url:
            subtitle_json_path = self.tts_generator.download_subtitle(tts_result.subtitle_url)
            if subtitle_json_path:
                subtitle_gen = SubtitleGenerator()
                subtitle_path = subtitle_gen.convert_minimax_subtitle(
                    subtitle_json_path,
                    split_by_punctuation=True
                )
                print(f"  - 字幕文件: {os.path.basename(subtitle_path)}")

        # 准备字幕段落数据
        subtitle_segments = [
            {
                "text": seg.text,
                "start_time": seg.start_time,
                "duration": seg.duration
            }
            for seg in analysis_result.segments
        ]

        # 使用配音实际时长
        total_duration = tts_result.duration
        print(f"  - 总时长: {total_duration:.1f}秒")

        # 步骤5: 创建剪映项目（使用外部配音）
        print("\n[5/5] 创建剪映项目（外部配音+字幕）...")

        # 准备视频路径、开始时间和时长（按段落顺序）
        video_data = []
        current_time = 0
        for v in videos:
            if v.local_path and os.path.exists(v.local_path):
                dur = getattr(v, 'segment_duration', None) or v.duration
                video_data.append({
                    "path": v.local_path,
                    "start": f"{current_time}s",
                    "duration": f"{int(dur)}s"
                })
                current_time += int(dur)
                print(f"  - 视频: {os.path.basename(v.local_path)} @ {video_data[-1]['start']}, 时长: {video_data[-1]['duration']}")

        video_paths = [d["path"] for d in video_data]
        start_times = [d["start"] for d in video_data]
        durations = [d["duration"] for d in video_data]

        # 创建剪映项目（使用外部配音模式）
        maker = JianYingMaker(
            project_name=title,
            drafts_root=self.drafts_root
        )

        # 调用 create_from_config，传入配音和字幕
        result = maker.create_from_config({
            "title": title,
            "videos": video_paths,
            "video_start_times": start_times,
            "video_durations": durations,
            "full_audio_path": audio_path,  # 配音文件
            "subtitle_path": subtitle_path,  # 字幕文件
            "segments": subtitle_segments,
            "voice_style": voice_id,
            "use_intelligent_tts": False,  # 使用外部配音
            "total_duration": total_duration,
            "bgm": "舒缓"
        })

        # 输出结果
        print("\n" + "="*50)
        print("视频制作完成!")
        print("="*50)
        print(f"✅ 项目名称: {result.get('project_name', title)}")
        print(f"✅ 草稿路径: {result.get('draft_path', 'N/A')}")
        print(f"✅ 视频素材: {result.get('videos_count', len(video_paths))} 个")
        print(f"✅ 配音文件: {os.path.basename(audio_path)}")
        if subtitle_path:
            print(f"✅ 字幕文件: {os.path.basename(subtitle_path)}")
        print(f"✅ 配音模式: 优刻得 API")
        print(f"✅ 字幕模式: SRT 导入")
        print("="*50)
        print("\n请打开剪映，在【我的草稿】中查看: 自动生成的视频")
        print("="*50 + "\n")

        is_success = result.get("success", True)  # 默认为True，因为项目已保存

        return {
            "success": is_success,
            "title": title,
            "project_name": result.get("project_name", title),
            "draft_path": result.get("draft_path", "N/A"),
            "video_count": len(video_paths),
            "segments_count": len(subtitle_segments),
            "keywords": analysis_result.keywords,
            "scene_type": analysis_result.scene_type,
            "emotion": analysis_result.emotion,
            "mode": result.get("mode", "intelligent"),
            "error": result.get("error")
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="AutoVideo - 自动视频制作系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --script "今天天气真好，我们去海边玩吧。"
  python main.py --script "视频文案" --title "我的视频" --style vlog
  python main.py --script "文案" --pexels-key YOUR_KEY --pixabay-key YOUR_KEY

API Key 配置:
  可以通过环境变量设置: PEXELS_API_KEY, PIXABAY_API_KEY
  或通过命令行参数: --pexels-key, --pixabay-key
        """
    )

    parser.add_argument(
        "--script", "-s",
        required=True,
        help="视频文案内容"
    )

    parser.add_argument(
        "--title", "-t",
        help="视频标题 (默认: 自动生成的视频)"
    )

    parser.add_argument(
        "--style",
        choices=["vlog", "news", "tutorial", "story"],
        default="vlog",
        help="视频风格 (默认: vlog)"
    )

    parser.add_argument(
        "--voice",
        choices=["male", "female", "child", "male_mature"],
        default="female",
        help="配音风格 (默认: female)"
    )

    parser.add_argument(
        "--duration", "-d",
        type=int,
        choices=[60, 120, 180],
        help="目标时长 (秒)"
    )

    parser.add_argument(
        "--pexels-key",
        help="Pexels API Key"
    )

    parser.add_argument(
        "--pixabay-key",
        help="Pixabay API Key"
    )

    parser.add_argument(
        "--max-videos",
        type=int,
        default=5,
        help="最大视频素材数量 (默认: 5)"
    )

    parser.add_argument(
        "--drafts-root",
        help="剪映草稿保存目录"
    )

    args = parser.parse_args()

    # 创建自动视频制作器
    maker = AutoVideoMaker(
        pexels_api_key=args.pexels_key,
        pixabay_api_key=args.pixabay_key,
        drafts_root=args.drafts_root
    )

    # 执行视频制作
    try:
        result = maker.make_video(
            title=args.title or "自动生成的视频",
            script=args.script,
            style=args.style,
            voice_style=args.voice,
            duration=args.duration,
            max_video_results=args.max_videos
        )

        is_ok = result.get("success", True)
        if is_ok:
            print("\n" + "="*50)
            print("🎉 视频制作成功!")
            print("="*50)
            print("请打开剪映，在【我的草稿】中查看")
            print("="*50)
        else:
            print(f"\n❌ 视频制作失败: {result.get('error')}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()