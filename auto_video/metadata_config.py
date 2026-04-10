# -*- coding: utf-8 -*-
"""
元数据标签配置
==============
定义标签词典、抽象概念映射、NER 规则等
"""

# ==================== 标签词典 ====================

# 地点词典
LOCATION_TAGS = {
    "北京": ["北京", "Beijing", "帝都"],
    "上海": ["上海", "Shanghai", "魔都"],
    "杭州": ["杭州", "Hangzhou", "西湖"],
    "成都": ["成都", "Chengdu", "天府"],
    "西安": ["西安", "Xian", "兵马俑"],
    "重庆": ["重庆", "Chongqing", "山城"],
    "广州": ["广州", "Guangzhou", "羊城"],
    "深圳": ["深圳", "Shenzhen", "鹏城"],
    "南京": ["南京", "Nanjing", "金陵"],
    "苏州": ["苏州", "Suzhou", "姑苏"],
    "厦门": ["厦门", "Xiamen", "鹭岛"],
    "三亚": ["三亚", "Sanya", "海南"],
    "拉萨": ["拉萨", "Lhasa", "西藏"],
    "丽江": ["丽江", "Lijiang", "云南"],
    "桂林": ["桂林", "Guilin"],
    "张家界": ["张家界", "Zhangjiajie"],
    "东京": ["东京", "Tokyo", "日本"],
    "巴黎": ["巴黎", "Paris", "法国"],
    "纽约": ["纽约", "New York", "NYC"],
    "伦敦": ["伦敦", "London", "英国"],
    "迪拜": ["迪拜", "Dubai", "阿联酋"],
    "新加坡": ["新加坡", "Singapore"],
    "首尔": ["首尔", "Seoul", "韩国"],
    "长城": ["长城", "Great Wall"],
    "故宫": ["故宫", "紫禁城", "Forbidden City"],
    "西湖": ["西湖", "West Lake"],
    "洱海": ["洱海", "大理", "云南", "湖"],
    "苍山": ["苍山", "大理", "云南", "山"],
    "大理": ["大理", "云南", "古镇"],
    "青海湖": ["青海湖", "青海", "湖", "高原"],
    "纳木错": ["纳木错", "西藏", "湖", "圣地"],
}

# 人物类型标签
PERSON_TAGS = {
    "老人": ["老人", "老奶奶", "老爷爷", "elderly", "senior"],
    "儿童": ["儿童", "小孩", "孩子", "小朋友", "child", "kid", "baby"],
    "情侣": ["情侣", "couple", "恋人", "约会"],
    "家庭": ["家庭", "家人", "全家", "family", "父母", "亲子"],
    "学生": ["学生", "student", "校园"],
    "职场人": ["职场", "上班族", "office", "白领", "商务"],
    "运动员": ["运动员", "运动", "athlete", "健身", "跑步"],
}

# 场景类型标签
SCENE_TAGS = {
    "室内": ["室内", "indoor", "房间", "屋内"],
    "户外": ["户外", "outdoor", "室外", "露天"],
    "办公室": ["办公室", "office", "写字楼", "会议室"],
    "咖啡馆": ["咖啡馆", "咖啡厅", "coffee", "cafe"],
    "餐厅": ["餐厅", "饭馆", "restaurant", "用餐"],
    "公园": ["公园", "park", "花园"],
    "海滩": ["海滩", "沙滩", "海边", "beach"],
    "森林": ["森林", "树林", "forest", "丛林"],
    "山脉": ["山脉", "山峰", "mountain", "山景"],
    "城市": ["城市", "都市", "city", "街道", "街景"],
    "农村": ["农村", "乡村", "village", "rural"],
    "夜景": ["夜景", "夜晚", "night", "灯光", "霓虹"],
    "日出": ["日出", "黎明", "sunrise", "晨曦"],
    "日落": ["日落", "黄昏", "夕阳", "sunset"],
}

# 动作/活动标签
ACTION_TAGS = {
    "运动": ["运动", "健身", "exercise", "跑步", "瑜伽", "游泳", "骑车"],
    "旅行": ["旅行", "旅游", "travel", "观光", "度假"],
    "工作": ["工作", "办公", "work", "开会", "打字"],
    "学习": ["学习", "读书", "study", "上课", "写字"],
    "烹饪": ["烹饪", "做饭", "cooking", "厨房", "炒菜"],
    "购物": ["购物", "逛街", "shopping", "商场"],
    "聚会": ["聚会", "派对", "party", "庆祝", "聚餐"],
    "音乐": ["音乐", "唱歌", "music", "弹琴", "吉他"],
    "舞蹈": ["舞蹈", "跳舞", "dance"],
}

# 情绪/氛围标签
MOOD_TAGS = {
    "快乐": ["快乐", "开心", "happy", "笑容", "欢笑"],
    "温馨": ["温馨", "温暖", "warm", "亲情", "拥抱"],
    "浪漫": ["浪漫", "romantic", "爱情", "甜蜜"],
    "宁静": ["宁静", "安静", "peaceful", "放松", "平静"],
    "激动": ["激动", "兴奋", "excited", "欢呼"],
    "悲伤": ["悲伤", "难过", "sad", "忧郁"],
    "紧张": ["紧张", "nervous", "焦虑"],
}

# 天气/季节标签
WEATHER_TAGS = {
    "晴天": ["晴天", "阳光", "sunny", "晴朗"],
    "雨天": ["雨天", "下雨", "rain", "雨滴"],
    "雪天": ["雪天", "下雪", "snow", "雪景"],
    "雾天": ["雾天", "大雾", "fog"],
    "春天": ["春天", "春季", "spring", "花开"],
    "夏天": ["夏天", "夏季", "summer", "炎热"],
    "秋天": ["秋天", "秋季", "autumn", "fall", "落叶", "金黄"],
    "冬天": ["冬天", "冬季", "winter", "寒冷"],
}

# ==================== 抽象概念映射 ====================
# 将抽象概念转换为具体的画面描述词

ABSTRACT_MAPPING = {
    "内卷": ["加班", "深夜办公", "疲惫", "电脑屏幕", "咖啡杯", "文件堆积"],
    "躺平": ["沙发", "手机", "放松", "慵懒", "阳光", "午睡"],
    "AI时代": ["机器人", "代码", "科技感", "人工智能", "数据流", "未来"],
    "元宇宙": ["虚拟现实", "VR眼镜", "数字世界", "科幻", "3D"],
    "治愈": ["猫咪", "阳光", "花朵", "微笑", "温暖", "自然"],
    "松弛感": ["咖啡", "书", "阳光", "沙发", "植物", "慢生活"],
    "仪式感": ["烛光", "蛋糕", "礼物", "鲜花", "香槟", "精心布置"],
    "生活气息": ["菜市场", "烟火", "街道", "人群", "早餐", "炊烟"],
    "创业": ["团队", "讨论", "办公室", "白板", "激情", "年轻人"],
}

# ==================== 合并所有标签 ====================

ALL_TAGS = {}
ALL_TAGS.update(LOCATION_TAGS)
ALL_TAGS.update(PERSON_TAGS)
ALL_TAGS.update(SCENE_TAGS)
ALL_TAGS.update(ACTION_TAGS)
ALL_TAGS.update(MOOD_TAGS)
ALL_TAGS.update(WEATHER_TAGS)


def extract_tags_from_path(filepath: str) -> dict:
    """
    从文件路径中提取标签（基于路径分词，自动从文件夹/文件名中提取）

    例如：D:/素材/云南大理洱海/咩咩.mp4
    提取：["云南", "大理", "洱海", "咩咩", "素材", "mp4"]

    Returns:
        dict: {
            "tags": ["标签1", "标签2"],
            "locations": ["地点"],
            "scenes": ["场景"],
            "persons": ["人物类型"],
            "actions": ["动作"],
            "moods": ["情绪"],
            "weather": ["天气/季节"]
        }
    """
    import jieba

    result = {
        "tags": [],
        "locations": [],
        "scenes": [],
        "persons": [],
        "actions": [],
        "moods": [],
        "weather": []
    }

    # 停用词：单字和常见无意义词
    stop_words = {
        "的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它",
        "这", "那", "上", "下", "中", "与", "或", "个", "之", "为", "被",
        "把", "让", "给", "向", "从", "到", "及", "与", "被", "以", "着",
        "也", "就", "都", "而", "但", "却", "会", "能", "可", "要", "等",
        "说", "看", "想", "做", "来", "去", "过", "把", "又", "很", "最",
        "一", "不", "人", "什么", "怎么", "怎样", "样", "使", "让", "请",
        "更", "最", "太", "还真", "其实", "并", "不", "再", "已", "正在",
        "文件", "素材", "video", "image", "photo", "img", "pic", "folder",
        "dir", "new", "old", "test", "temp", "备份", "副本",
    }

    # 清理路径，保留中文、英文、数字
    path_parts = filepath.replace("\\", "/").split("/")
    filename = path_parts[-1] if path_parts else ""
    # 去掉文件扩展名
    if "." in filename:
        filename = filename.rsplit(".", 1)[0]

    # 路径中除最后一个（文件名）外的所有部分
    path_folders = path_parts[:-1]

    # 合并所有文本进行分词
    all_text = " ".join(path_folders) + " " + filename
    all_text = all_text.lower()

    # jieba分词
    words = jieba.cut(all_text)

    # 提取有意义的词
    for word in words:
        word = word.strip()
        # 过滤：长度<=1 或 在停用词中
        if len(word) <= 1 and not word.isalnum():
            continue
        if word.lower() in stop_words:
            continue
        # 过滤纯数字
        if word.isdigit():
            continue
        # 过滤扩展名
        exts = {"mp4", "avi", "mov", "mkv", "flv", "wmv", "jpg", "jpeg", "png", "gif", "bmp", "webp", "mp3", "wav", "m4a"}
        if word.lower() in exts:
            continue
        result["tags"].append(word)

    # 字典匹配（保留原有逻辑，补充分词无法覆盖的）
    text_to_match = " ".join(path_parts).lower()

    for tag, keywords in LOCATION_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["locations"]:
                    result["locations"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for tag, keywords in SCENE_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["scenes"]:
                    result["scenes"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for tag, keywords in PERSON_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["persons"]:
                    result["persons"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for tag, keywords in ACTION_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["actions"]:
                    result["actions"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for tag, keywords in MOOD_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["moods"]:
                    result["moods"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for tag, keywords in WEATHER_TAGS.items():
        for kw in keywords:
            if kw.lower() in text_to_match:
                if tag not in result["weather"]:
                    result["weather"].append(tag)
                if tag not in result["tags"]:
                    result["tags"].append(tag)
                break

    for key in result:
        result[key] = list(set(result[key]))

    return result


def extract_entities_from_query(query: str) -> dict:
    """
    从用户查询中提取实体（用于检索时的元数据过滤）

    Args:
        query: 用户输入的查询文本

    Returns:
        dict: {
            "tags": ["提取的标签"],
            "abstract_concepts": ["抽象概念"],
            "expanded_terms": ["扩展后的具体词"],
            "path_words": ["从查询中分词提取的路径词"]
        }
    """
    import jieba

    result = {
        "tags": [],
        "abstract_concepts": [],
        "expanded_terms": [],
        "path_words": []
    }

    query_lower = query.lower()

    # 0. 路径词提取：分词后直接作为 path_words
    # 用于匹配从文件路径中提取的标签（如"洱海"、"大理"等）
    stop_words = {
        "的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它",
        "这", "那", "上", "下", "中", "与", "或", "个", "之", "为", "被",
        "把", "让", "给", "向", "从", "到", "及", "以", "着", "也", "就",
        "都", "而", "但", "却", "会", "能", "可", "要", "等", "说", "看",
        "想", "做", "来", "去", "过", "又", "很", "最", "太", "其实", "并",
        "再", "已", "正在", "什么", "怎么", "怎样", "一", "不", "人",
    }
    words = jieba.cut(query_lower)
    for word in words:
        word = word.strip()
        if len(word) <= 1:
            continue
        if word in stop_words:
            continue
        if word.isdigit():
            continue
        result["path_words"].append(word)

    # 1. 匹配具体标签
    for tag, keywords in ALL_TAGS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                result["tags"].append(tag)
                break

    # 2. 匹配抽象概念并扩展
    for concept, expansions in ABSTRACT_MAPPING.items():
        if concept in query:
            result["abstract_concepts"].append(concept)
            result["expanded_terms"].extend(expansions)

    # 去重
    for key in result:
        result[key] = list(set(result[key]))

    return result


def get_expanded_query(query: str) -> str:
    """
    获取扩展后的查询词（用于向量检索）
    将抽象概念转换为具体画面描述

    Args:
        query: 原始查询

    Returns:
        str: 扩展后的查询词
    """
    entities = extract_entities_from_query(query)

    if entities["expanded_terms"]:
        # 组合原始查询 + 扩展词
        expanded = query + " " + " ".join(entities["expanded_terms"][:5])  # 最多取5个
        return expanded

    return query