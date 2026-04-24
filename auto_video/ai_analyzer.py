# -*- coding: utf-8 -*-
"""
AI 分析模块
============

对视频文案进行语义分析，提取关键词、场景类型、情绪类型，
并根据配音时长分割文案段落

支持两种模式：
1. 智谱AI（推荐）：智能语义分析，需要API Key
2. 本地规则：基于关键词匹配，无需API
"""

import re
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import csv
import config
try:
    from .log_utils import log_info, log_success, log_warning, log_error
except ImportError:
    from auto_video.log_utils import log_info, log_success, log_warning, log_error


@dataclass
class ScriptSegment:
    """文案段落"""
    text: str  # 段落文本
    duration: float  # 估计时长(秒)
    keywords: List[str]  # 段落关键词
    start_time: float = 0  # 开始时间


@dataclass
class AnalysisResult:
    """AI分析结果"""
    keywords: List[str]  # 核心关键词
    scene_type: str  # 场景类型
    emotion: str  # 情绪类型
    segments: List[ScriptSegment]  # 分割后的段落


class AIAnalyzer:
    """AI语义分析器"""

    def __init__(self, use_zhipu: bool = True):
        """
        初始化分析器

        Args:
            use_zhipu: 是否使用智谱AI (True=智能分析, False=本地规则)
        """
        self.scene_keywords = config.SCENE_TYPE_KEYWORDS
        self.emotion_keywords = config.EMOTION_KEYWORDS
        self.max_keywords = config.MAX_KEYWORDS
        self.use_zhipu = use_zhipu
        self.zhipu_api_key = config.ZHIPU_API_KEY
        self.zhipu_model = config.ZHIPU_MODEL
        self._cached_analysis = None  # 缓存分析结果
        self._cached_script = None  # 缓存对应的文案
        # 缓存情绪和场景，供BGM推荐使用
        self._cached_emotion = "舒缓"
        self._cached_scene_type = "生活"

    def analyze_emotion_and_scene(self, script: str, max_retries: int = 3, retry_delay: float = 2.0) -> Tuple[str, str]:
        """
        只分析情绪和场景，不分段（用于推荐BGM，带重试机制）

        Args:
            script: 视频文案
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            (情绪, 场景类型)
        """
        import time as time_module

        if not self.zhipu_api_key:
            return self._cached_emotion, self._cached_scene_type

        prompt = f"""分析以下视频文案的情绪和场景，只输出JSON：

{{"emotion": "情绪", "scene_type": "场景类型"}}

情绪可选：舒缓、动感、温暖、欢快、纪实、悲伤、紧张
场景可选：风景、城市、人物、美食、科技、动物、音乐、生活、访谈、室内

文案：
{script[:500]}"""

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.zhipu_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 100
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # 解析JSON
                    parsed = None
                    try:
                        parsed = json.loads(content)
                    except:
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        if start >= 0 and end > start:
                            try:
                                parsed = json.loads(content[start:end])
                            except:
                                pass

                    if parsed:
                        self._cached_emotion = parsed.get("emotion", "舒缓")
                        self._cached_scene_type = parsed.get("scene_type", "生活")
                        log_success("AI", f"情绪: {self._cached_emotion}, 场景: {self._cached_scene_type}")
                        return self._cached_emotion, self._cached_scene_type

            except Exception as e:
                is_retryable = isinstance(e, (ConnectionError, ConnectionResetError, TimeoutError))
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    log_warning("AI", f"网络错误 (尝试 {attempt + 1}/{max_retries}): {e}, {wait_time:.1f}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                log_warning("AI", f"分析情绪场景失败: {e}")

        return self._cached_emotion, self._cached_scene_type

    def generate_keywords_for_segments(self, segments: List[Dict[str, Any]], full_script: str = None) -> Tuple[List[Dict[str, Any]], str, str]:
        """
        为字幕片段生成英文搜索关键词，同时分析情绪和场景

        Args:
            segments: 字幕片段列表，每个包含 text, start, end, duration
            full_script: 完整文案（可选，用于分析情绪和场景）

        Returns:
            (片段列表, 情绪, 场景类型)
        """
        if not self.zhipu_api_key:
            print("[AI分析] 未配置智谱API Key")
            return segments, self._cached_emotion, self._cached_scene_type

        # 如果有完整文案，只分析情绪和场景（不分段）
        if full_script:
            self.analyze_emotion_and_scene(full_script)

        # 分批处理，每批最多7个片段，避免AI输出被截断
        BATCH_SIZE = 7
        all_segment_texts = [seg.get("text", "") for seg in segments]
        all_keywords = []

        for batch_start in range(0, len(segments), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(segments))
            batch_texts = all_segment_texts[batch_start:batch_end]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(segments) + BATCH_SIZE - 1) // BATCH_SIZE

            log_info("AI", f"处理批次 {batch_num}/{total_batches} (片段 {batch_start+1}-{batch_end})...", "🔄")

            batch_keywords = self._generate_keywords_batch(batch_texts)
            all_keywords.extend(batch_keywords)

        # 将关键词添加到片段
        for i, seg in enumerate(segments):
            if i < len(all_keywords) and all_keywords[i]:
                seg["keywords_en"] = all_keywords[i]
            else:
                seg["keywords_en"] = ["nature", "landscape"]

        return segments, self._cached_emotion, self._cached_scene_type

    def _generate_keywords_batch(self, segment_texts: List[str], max_retries: int = 3, retry_delay: float = 2.0) -> List[List[str]]:
        """
        为一批字幕片段生成英文关键词（带重试机制）

        Args:
            segment_texts: 字幕文本列表
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            关键词列表的列表
        """
        import time as time_module

        prompt = f"""你是视频素材搜索专家。为每个文案片段输出 1 个英文关键词，用于在 Pexels 搜索视频。

【示例 - 必须参考】
文案：没招了，就业环境是一年比一年恶劣
输出：`frustrated man laptop`

文案：开工第一天就收到了招聘需求，招聘要求一次比一次高
输出：`HR writing job description`

文案：从全日制本科到双一流、从年龄到性别，全都卡死了
输出：`job application form`

文案：只要有一项不符合要求的，根本没办法进入到面试
输出：`rejected candidate`

文案：现在的就业环境就是僧多肉少，企业能放出来的HC不多
输出：`crowded job fair`

文案：没人脉、没学历的人、能力不高的人求职之路难上加难
输出：`struggling job seeker`

【规则】
1. 必须输出英文！Pexels 只支持英文搜索
2. 输出格式：`关键词`（反引号包裹）
3. 关键词 = 具体的人/物 + 具体的动作/状态
4. 禁止抽象词：increasing、limited、challenges、pressure、demand、barrier
5. 禁止中文输出

文案片段：
{json.dumps(segment_texts, ensure_ascii=False, indent=2)}

输出（共 {len(segment_texts)} 行，每行一个英文关键词）：
片段1: `keyword`
片段2: `keyword`
..."""

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.zhipu_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 2048
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    print(f"[AI分析] 返回: (关键词提取中...)")

                    # 解析关键词
                    keywords_list = []

                    # 去掉代码块标记
                    content_clean = content.strip()
                    if content_clean.startswith("```"):
                        # 移除开头的 ``` 和可能的语言标识
                        lines = content_clean.split('\n')
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        content_clean = '\n'.join(lines)

                    lines = content_clean.strip().split('\n')

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        # 尝试提取反引号中的内容
                        import re
                        matches = re.findall(r'`([^`]+)`', line)
                        if matches:
                            keywords_list.append([matches[0]])
                        else:
                            # 检查是否是纯英文关键词行（没有中文，以字母开头）
                            # 去掉可能的 "片段1:" 前缀
                            if ':' in line:
                                parts = line.split(':', 1)
                                if len(parts) > 1:
                                    line = parts[1].strip()

                            # 检查是否是英文关键词（包含英文字母，不含中文）
                            if re.match(r'^[a-zA-Z]', line) and not re.search(r'[\u4e00-\u9fa5]', line):
                                keywords_list.append([line])

                    # 检查数量
                    if len(keywords_list) >= len(segment_texts):
                        keywords_list = keywords_list[:len(segment_texts)]
                        for i, kw in enumerate(keywords_list):
                            print(f"  片段: {segment_texts[i]} -> {kw}")
                        return keywords_list
                    elif keywords_list:
                        # 数量不足，补充默认值
                        print(f"[AI分析] ⚠️ 返回数量不足: {len(keywords_list)} vs {len(segment_texts)}")
                        while len(keywords_list) < len(segment_texts):
                            keywords_list.append(["nature landscape"])
                        return keywords_list[:len(segment_texts)]
                    else:
                        print(f"[AI分析] 未能解析关键词")

            except Exception as e:
                last_error = e
                # 判断是否是网络连接错误，需要重试
                is_retryable = isinstance(e, (ConnectionError, ConnectionResetError, TimeoutError))
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)  # 递增等待时间
                    print(f"[AI分析] 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}, {wait_time:.1f}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                print(f"[AI分析] 生成关键词失败: {e}")

        # 所有重试都失败，返回默认关键词
        print(f"[AI分析] ⚠️ 重试 {max_retries} 次后仍失败，返回默认关键词")
        return [["nature landscape"] for _ in segment_texts]

    def analyze_with_zhipu(self, script: str, max_retries: int = 3, retry_delay: float = 2.0) -> Dict[str, Any]:
        """
        使用智谱AI进行智能分析（带重试机制）

        Args:
            script: 输入文案
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            Dict: 分析结果
        """
        import time as time_module

        if not self.zhipu_api_key:
            print("[AI分析] 未配置智谱API Key，使用本地规则")
            return None

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }

        prompt = f"""你是一个视频素材搜索助手。请分析以下视频文案，按片段提取关键词。

核心原则：关键词必须是具体、可视化的画面描述，能在 Pexels 等素材网站搜到真实视频！

❌ 避免抽象词：financial stress, friendship, happiness, success
✅ 使用场景化词：anxious man laptop, friends coffee talk, bills calculator

【情绪→画面映射】
- 求职压力 → anxious man laptop, unemployed worried, job interview nervous
- 朋友支持 → friends coffee talk, two men conversation, shoulder pat friend
- 财务焦虑 → bills calculator, empty wallet, counting coins
- 工作压力 → office tired, stressed businessman, overtime night
- 幸福温暖 → family dinner, couple smiling, friends laughing

输出格式（JSON）：
{{
    "segments": [
        {{"text": "片段1文案（2-3句话）", "keywords": ["场景化关键词1", "场景化关键词2"]}},
        {{"text": "片段2文案（2-3句话）", "keywords": ["场景化关键词1", "场景化关键词2"]}}
    ],
    "scene_type": "场景类型",
    "emotion": "情绪风格"
}}

场景类型：风景/城市/人物/美食/科技/动物/音乐/生活/访谈/室内
情绪风格：舒缓/动感/温暖/欢快/纪实

视频文案：
{script}"""

        data = {
            "model": self.zhipu_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        for attempt in range(max_retries):
            try:
                print(f"[AI分析] 正在调用智谱AI分析文案...")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                    print(f"[AI分析] 返回: (场景情绪分析中...)")

                    # 尝试解析JSON
                    parsed = None

                    # 方式1：直接解析
                    try:
                        parsed = json.loads(content)
                    except:
                        pass

                    # 方式2：提取{}之间的内容
                    if not parsed:
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        if start >= 0 and end > start:
                            try:
                                json_str = content[start:end]
                                # 移除尾随逗号 (,] 或 ,})
                                json_str = re.sub(r',\s*]', ']', json_str)
                                json_str = re.sub(r',\s*}', '}', json_str)
                                parsed = json.loads(json_str)
                            except Exception as e:
                                print(f"[AI分析] JSON解析失败: {e}")

                    if parsed and isinstance(parsed, dict):
                        print(f"[AI分析] 成功！分段数: {len(parsed.get('segments', []))}")
                        return parsed
                    else:
                        print(f"[AI分析] 返回格式不正确")
                else:
                    print(f"[AI分析] 智谱API错误: {response.status_code}")
            except Exception as e:
                # 判断是否是网络连接错误，需要重试
                is_retryable = isinstance(e, (ConnectionError, ConnectionResetError, TimeoutError))
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"[AI分析] 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}, {wait_time:.1f}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                print(f"[AI分析] 智谱API异常: {e}")

        return None

    def extract_keywords_local(self, text: str) -> List[str]:
        """本地规则提取关键词"""
        stopwords = {
            "的", "了", "是", "在", "有", "和", "与", "或", "也", "都",
            "这", "那", "我", "你", "他", "她", "它", "们", "个", "把",
            "被", "让", "给", "对", "从", "到", "为", "以", "及", "等",
            "很", "非常", "特别", "最", "更", "很", "比较", "太", "真",
            "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "今天", "昨天", "明天", "现在", "刚才", "以后", "以前", "然后",
            "但是", "因为", "所以", "如果", "虽然", "只是", "而且", "或者",
            "可以", "能", "要", "会", "能", "想", "做", "去", "来", "看",
            "还", "再", "又", "就", "已", "已经", "正", "正在", "刚", "刚刚"
        }

        words = re.findall(r'[\u4e00-\u9fa5]+', text)
        word_freq = {}

        for word in words:
            if len(word) >= 2 and word not in stopwords:
                word_freq[word] = word_freq.get(word, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [w[0] for w in sorted_words[:self.max_keywords]]

        if len(keywords) < 3:
            keywords = words[:5] if words else ["视频"]

        return keywords[:self.max_keywords]

    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词（优先使用AI）"""
        return self.extract_keywords_local(text)

    def analyze_scene(self, text: str, keywords: List[str]) -> str:
        """分析场景类型"""
        all_text = text + " ".join(keywords)
        scores = {}

        for scene_type, scene_words in self.scene_keywords.items():
            score = sum(1 for word in scene_words if word in all_text)
            if score > 0:
                scores[scene_type] = score

        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return "风景"

    def analyze_emotion(self, text: str, keywords: List[str]) -> str:
        """分析情绪类型"""
        all_text = text + " ".join(keywords)
        scores = {}

        for emotion_type, emotion_words in self.emotion_keywords.items():
            score = sum(1 for word in emotion_words if word in all_text)
            if score > 0:
                scores[emotion_type] = score

        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return "舒缓"

    def segment_text_local(self, text: str, estimated_voice_duration: Optional[float] = None) -> List[ScriptSegment]:
        """本地规则分割文案（每2-3句话一个片段）"""
        sentences = re.split(r'[。！？\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [ScriptSegment(text=text, duration=10.0, keywords=self.extract_keywords(text))]

        # 每2-3句话合并为一个片段
        chars_per_second = 2.5
        segments = []
        current_time = 0

        # 分组：每3句话一个片段
        group_size = 3
        for i in range(0, len(sentences), group_size):
            group = sentences[i:i+group_size]
            segment_text = "。".join(group)
            if not segment_text.endswith("。"):
                segment_text += "。"

            duration = max(3.0, len(segment_text) / chars_per_second)

            if estimated_voice_duration and len(sentences) > 0:
                total_chars = sum(len(s) for s in sentences)
                duration = (len(segment_text) / total_chars) * estimated_voice_duration
                duration = max(3.0, min(duration, 30.0))

            # 提取这段文字的关键词
            keywords = self.extract_keywords(segment_text)

            segment = ScriptSegment(
                text=segment_text,
                duration=round(duration, 1),
                keywords=keywords,
                start_time=round(current_time, 1)
            )
            segments.append(segment)

            current_time += duration

        return segments

    def segment_text(self, text: str, estimated_voice_duration: Optional[float] = None) -> List[ScriptSegment]:
        """分割文案"""
        return self.segment_text_local(text, estimated_voice_duration)

    def analyze(
        self,
        script: str,
        voice_duration: Optional[float] = None,
        style: str = "vlog"
    ) -> AnalysisResult:
        """
        综合分析文案

        优先使用智谱AI进行分析，如果没有配置API则使用本地规则

        Args:
            script: 视频文案
            voice_duration: 配音时长（可选）
            style: 视频风格

        Returns:
            AnalysisResult: 分析结果
        """
        # 检查缓存：如果是同一文案，直接返回缓存结果
        if self._cached_script == script and self._cached_analysis:
            print(f"[AI分析] 使用缓存的分析结果")
            return self._cached_analysis

        print(f"[AI分析] 开始分析文案 ({len(script)} 字)")

        # 优先尝试智谱AI
        zhipu_result = None
        if self.use_zhipu and self.zhipu_api_key:
            print("[AI分析] 使用智谱AI智能分析...")
            zhipu_result = self.analyze_with_zhipu(script)

        if zhipu_result:
            # 转换智谱结果为AnalysisResult
            segments_data = zhipu_result.get("segments", [])
            print(f"[AI分析] 智谱AI返回: 片段数={len(segments_data)}, 场景={zhipu_result.get('scene_type')}")

            # 如果智谱返回了片段，直接使用
            if segments_data:
                segments = []
                current_time = 0
                all_keywords = []
                for seg_data in segments_data:
                    text = seg_data.get("text", "")
                    seg_keywords = seg_data.get("keywords", self.extract_keywords_local(text))
                    all_keywords.extend(seg_keywords)
                    duration = max(3.0, len(text) / 2.5)

                    segments.append(ScriptSegment(
                        text=text,
                        duration=round(duration, 1),
                        keywords=seg_keywords,
                        start_time=round(current_time, 1)
                    ))
                    current_time += duration

                # 从所有片段关键词中去重作为全局关键词
                keywords = list(dict.fromkeys(all_keywords))[:5]
            else:
                segments = self.segment_text_local(script, voice_duration)
                keywords = self.extract_keywords_local(script)

            result = AnalysisResult(
                keywords=keywords,
                scene_type=zhipu_result.get("scene_type", "风景"),
                emotion=zhipu_result.get("emotion", "舒缓"),
                segments=segments
            )
            # 缓存结果
            self._cached_script = script
            self._cached_analysis = result
            return result
        else:
            # 使用本地规则
            print("[AI分析] 使用本地规则分析...")
            keywords = self.extract_keywords_local(script)
            scene_type = self.analyze_scene(script, keywords)
            emotion = self.analyze_emotion(script, keywords)
            segments = self.segment_text_local(script, voice_duration)

            result = AnalysisResult(
                keywords=keywords,
                scene_type=scene_type,
                emotion=emotion,
                segments=segments
            )
            # 缓存结果
            self._cached_script = script
            self._cached_analysis = result
            return result

    def get_segment_keywords(self, segments: List[ScriptSegment]) -> List[List[str]]:
        """获取每个段落的关键词列表"""
        return [seg.keywords for seg in segments]

    def recommend_bgm(self, script: str, emotion: str = None, scene_type: str = None, max_retries: int = 3, retry_delay: float = 2.0) -> Dict[str, Any]:
        """
        使用智谱AI推荐背景音乐（带重试机制）

        Args:
            script: 视频文案
            emotion: 情绪类型（可选）
            scene_type: 场景类型（可选）
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            Dict: 包含推荐的背景音乐信息
        """
        import time as time_module

        if not self.zhipu_api_key:
            print("[AI分析] 未配置智谱API Key，使用默认背景音乐")
            return {"music_id": "7377952090247219263", "title": "舒缓背景音乐", "reason": "默认推荐"}

        # 加载音乐库
        music_library = self._load_music_library()
        if not music_library:
            print("[AI分析] 音乐库为空，使用默认")
            return {"music_id": "7377952090247219263", "title": "舒缓背景音乐", "reason": "默认推荐"}

        # 构建 prompt - 直接列出ID，不加序号
        music_list_str = "\n".join([
            f"music_id: {m['music_id']} | 标题: {m['title']} | 分类: {m.get('categories', '未知')}"
            for m in music_library[:25]  # 限制数量避免 prompt 过长
        ])

        prompt = f"""你是一个专业的视频配乐师。从下面的音乐列表中选择最合适的一首。

视频文案：
{script}

音乐列表：
{music_list_str}

【规则】
1. 返回 music_id 后面的完整数字串（如 7377952090247219263）
2. 不要返回序号，要返回真实的 music_id
3. 只输出JSON：

{{"music_id": "数字ID", "title": "标题", "reason": "简短理由"}}"""

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.zhipu_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }

        for attempt in range(max_retries):
            try:
                print("[AI分析] 正在推荐背景音乐...")
                response = requests.post(url, headers=headers, json=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    print(f"[AI分析] 推荐背景音乐中...")

                    # 解析JSON
                    parsed = None
                    try:
                        parsed = json.loads(content)
                    except:
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        if start >= 0 and end > start:
                            try:
                                parsed = json.loads(content[start:end])
                            except:
                                pass

                    if parsed and parsed.get("music_id"):
                        # 验证 music_id 是否存在于音乐库中
                        returned_id = parsed.get("music_id")
                        valid_ids = [m['music_id'] for m in music_library]

                        # 如果返回的ID有效，使用它
                        if returned_id in valid_ids:
                            print(f"[AI分析] 推荐背景音乐: {parsed.get('title')} (理由: {parsed.get('reason')})")
                            return parsed
                        else:
                            # AI返回的ID无效，尝试根据情绪/场景选择合适的音乐
                            print(f"[AI分析] AI返回的 music_id '{returned_id}' 无效，尝试匹配...")
                            matched_music = self._match_music_by_emotion(emotion, scene_type, music_library)
                            if matched_music:
                                return matched_music

            except Exception as e:
                is_retryable = isinstance(e, (ConnectionError, ConnectionResetError, TimeoutError))
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"[AI分析] 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}, {wait_time:.1f}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                print(f"[AI分析] 推荐背景音乐失败: {e}")

        # 失败时返回默认
        return {"music_id": "7377952090247219263", "title": "舒缓背景音乐", "reason": "默认推荐"}

    def recommend_sound_effects(self, script: str, segments: List[Dict] = None, max_retries: int = 3, retry_delay: float = 2.0) -> List[Dict[str, Any]]:
        """
        使用智谱AI推荐音效（带重试机制）

        Args:
            script: 视频文案
            segments: 字幕片段列表（可选，用于确定音效插入时间）
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            List[Dict]: 推荐的音效列表，每个包含 effect_id, title, time, reason
        """
        import time as time_module

        if not self.zhipu_api_key:
            print("[AI分析] 未配置智谱API Key，跳过音效推荐")
            return []

        # 加载音效库
        sfx_library = self._load_sfx_library()
        if not sfx_library:
            print("[AI分析] 音效库为空，跳过音效推荐")
            return []

        # 构建音效列表 - 直接列出ID，不加序号
        sfx_list_str = "\n".join([
            f"effect_id: {s['effect_id']} | 名称: {s['title']}"
            for s in sfx_library[:40]  # 限制数量
        ])

        # 如果有片段信息，构建时间信息
        time_info = ""
        if segments:
            time_info = "\n\n字幕时间轴：\n" + "\n".join([
                f"- {seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s: {seg.get('text', '')[:15]}..."
                for seg in segments[:8]
            ])

        prompt = f"""你是视频音效师。从下面列表中选择合适的音效。

视频文案：
{script}
{time_info}

音效列表：
{sfx_list_str}

【规则】
1. 返回 effect_id 后面的完整数字串（如 7135753343380606242）
2. time 是音效插入的时间点，只写一个数字（如 0.5、3.2）
3. 只输出JSON数组：

[{{"effect_id": "数字ID", "title": "名称", "time": 3.2, "reason": "理由"}}]

没有合适音效输出 []"""

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.zhipu_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }

        for attempt in range(max_retries):
            try:
                print("[AI分析] 正在推荐音效...")
                response = requests.post(url, headers=headers, json=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    print(f"[AI分析] 推荐音效中...")

                    # 解析JSON数组
                    parsed = None
                    try:
                        parsed = json.loads(content)
                    except:
                        start = content.find("[")
                        end = content.rfind("]") + 1
                        if start >= 0 and end > start:
                            try:
                                parsed = json.loads(content[start:end])
                            except:
                                pass

                    if parsed and isinstance(parsed, list):
                        # 获取所有有效的 effect_id
                        valid_effect_ids = {s['effect_id'] for s in sfx_library}

                        # 过滤有效的音效推荐
                        valid_sfx = []
                        for sfx in parsed:
                            effect_id = sfx.get("effect_id")
                            sfx_time_raw = sfx.get("time")
                            sfx_title = sfx.get("title", "")

                            if effect_id and sfx_time_raw is not None:
                                # 验证 effect_id 存在于库中
                                if effect_id in valid_effect_ids:
                                    # 解析时间：可能是数字、带s的数字、或时间段 "0.0s-3.2s"
                                    sfx_time = self._parse_sfx_time(sfx_time_raw)
                                    if sfx_time is not None:
                                        valid_sfx.append({
                                            "effect_id": effect_id,
                                            "title": sfx_title,
                                            "time": sfx_time,
                                            "reason": sfx.get("reason", "")
                                        })
                                else:
                                    print(f"[AI分析] 跳过无效音效ID: {effect_id}")

                        if valid_sfx:
                            print(f"[AI分析] 推荐 {len(valid_sfx)} 个音效")
                            for sfx in valid_sfx:
                                print(f"  - {sfx.get('title')} @ {sfx.get('time')}s: {sfx.get('reason')}")
                        else:
                            print("[AI分析] 没有找到有效的音效推荐")
                        return valid_sfx
                    else:
                        print(f"[AI分析] AI返回格式不正确: {type(parsed)}")

            except Exception as e:
                is_retryable = isinstance(e, (ConnectionError, ConnectionResetError, TimeoutError))
                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"[AI分析] 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}, {wait_time:.1f}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                print(f"[AI分析] 推荐音效失败: {e}")
                import traceback
                traceback.print_exc()

        return []

    def _load_music_library(self) -> List[Dict]:
        """加载云音乐库"""
        music_library = []
        music_csv = Path(__file__).parent.parent / ".claude" / "skills" / "jianying-editor" / "data" / "cloud_music_library.csv"

        if music_csv.exists():
            try:
                with open(music_csv, "r", encoding="utf-8") as f:
                    # 跳过注释行
                    lines = [line for line in f if not line.strip().startswith("#")]
                    reader = csv.DictReader(lines)
                    for row in reader:
                        music_library.append({
                            "music_id": row.get("music_id", ""),
                            "title": row.get("title", ""),
                            "duration_s": float(row.get("duration_s", 0) or 0),
                            "categories": row.get("categories", "")
                        })
                print(f"[AI分析] 加载音乐库: {len(music_library)} 首")
            except Exception as e:
                print(f"[AI分析] 加载音乐库失败: {e}")

        return music_library

    def _load_sfx_library(self) -> List[Dict]:
        """加载音效库"""
        sfx_library = []
        sfx_csv = Path(__file__).parent.parent / ".claude" / "skills" / "jianying-editor" / "data" / "cloud_sound_effects.csv"

        if sfx_csv.exists():
            try:
                with open(sfx_csv, "r", encoding="utf-8") as f:
                    # 跳过注释行
                    lines = [line for line in f if not line.strip().startswith("#")]
                    reader = csv.DictReader(lines)
                    for row in reader:
                        sfx_library.append({
                            "effect_id": row.get("effect_id", ""),
                            "title": row.get("title", ""),
                            "duration_s": float(row.get("duration_s", 0) or 0),
                            "categories": row.get("categories", "")
                        })
                print(f"[AI分析] 加载音效库: {len(sfx_library)} 个")
            except Exception as e:
                print(f"[AI分析] 加载音效库失败: {e}")

        return sfx_library

    def _parse_sfx_time(self, time_value) -> Optional[float]:
        """
        解析音效时间，支持多种格式

        Args:
            time_value: 时间值，可能是数字、字符串"3.5"、"3.5s"、"0.0s-3.2s"等

        Returns:
            float: 时间（秒），失败返回 None
        """
        if isinstance(time_value, (int, float)):
            return float(time_value)

        if not isinstance(time_value, str):
            return None

        # 移除空格
        time_str = time_value.strip()

        # 处理时间段格式 "0.0s-3.2s"，取开始时间
        if "-" in time_str:
            time_str = time_str.split("-")[0]

        # 移除 's' 后缀
        time_str = time_str.replace("s", "").strip()

        try:
            return float(time_str)
        except (ValueError, AttributeError):
            return None

    def _match_music_by_emotion(self, emotion: str, scene_type: str, music_library: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        根据情绪和场景匹配音乐

        Args:
            emotion: 情绪类型
            scene_type: 场景类型
            music_library: 音乐库

        Returns:
            匹配的音乐信息
        """
        # 情绪/场景与音乐分类的映射
        emotion_mapping = {
            "舒缓": ["舒缓", "VLOG", "旅行"],
            "温暖": ["VLOG", "推荐音乐", "旅行"],
            "动感": ["动感", "VLOG"],
            "神秘": ["未知"],
            "欢快": ["VLOG", "轻快", "可爱"],
            "纪实": ["VLOG"],
        }

        scene_mapping = {
            "风景": ["旅行", "VLOG", "舒缓"],
            "城市": ["VLOG", "动感"],
            "人物": ["VLOG"],
            "美食": ["VLOG", "可爱"],
            "科技": ["VLOG", "动感"],
            "动物": ["可爱", "萌宠"],
            "音乐": ["VLOG"],
            "生活": ["VLOG", "舒缓"],
        }

        # 获取匹配的分类
        preferred_categories = []
        if emotion and emotion in emotion_mapping:
            preferred_categories.extend(emotion_mapping[emotion])
        if scene_type and scene_type in scene_mapping:
            preferred_categories.extend(scene_mapping[scene_type])

        # 尝试匹配
        for music in music_library:
            music_cats = music.get("categories", "")
            for cat in preferred_categories:
                if cat in music_cats:
                    print(f"[AI分析] 根据情绪/场景匹配音乐: {music['title']} (分类: {music_cats})")
                    return {
                        "music_id": music["music_id"],
                        "title": music["title"],
                        "reason": f"根据{emotion or scene_type}情绪自动匹配"
                    }

        # 没有匹配，返回第一首VLOG分类的音乐或第一首
        for music in music_library:
            if "VLOG" in music.get("categories", ""):
                print(f"[AI分析] 使用默认VLOG音乐: {music['title']}")
                return {
                    "music_id": music["music_id"],
                    "title": music["title"],
                    "reason": "默认推荐"
                }

        # 兜底
        if music_library:
            return {
                "music_id": music_library[0]["music_id"],
                "title": music_library[0]["title"],
                "reason": "默认推荐"
            }

        return None


# 便捷函数
def analyze_script(
    script: str,
    voice_duration: Optional[float] = None,
    style: str = "vlog",
    use_zhipu: bool = True
) -> Dict[str, Any]:
    """
    便捷函数：分析视频文案

    Args:
        script: 视频文案
        voice_duration: 配音时长（可选）
        style: 视频风格
        use_zhipu: 是否使用智谱AI

    Returns:
        Dict: 分析结果字典
    """
    analyzer = AIAnalyzer(use_zhipu=use_zhipu)
    result = analyzer.analyze(script, voice_duration, style)

    return {
        "keywords": result.keywords,
        "scene_type": result.scene_type,
        "emotion": result.emotion,
        "segments": [
            {
                "text": seg.text,
                "duration": seg.duration,
                "keywords": seg.keywords,
                "start_time": seg.start_time
            }
            for seg in result.segments
        ]
    }


# 测试
if __name__ == "__main__":
    test_script = "今天天气真好，我们去海边玩吧。海浪拍打着礁石，风景非常美丽。这是一个完美的周末。"

    print("=== 测试AI分析 ===")
    analyzer = AIAnalyzer(use_zhipu=True)
    result = analyzer.analyze(test_script)

    print(f"关键词: {result.keywords}")
    print(f"场景: {result.scene_type}")
    print(f"情绪: {result.emotion}")
    print(f"片段数: {len(result.segments)}")
    for i, seg in enumerate(result.segments):
        print(f"  片段{i+1}: {seg.text[:30]}... 关键词: {seg.keywords}")