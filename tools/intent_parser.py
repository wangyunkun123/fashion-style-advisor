#!/usr/bin/env python3
"""
用户意图结构化解析层 — LLM 语义解析 + 正则精确提取

两阶段架构：
  Phase 1（正则，<1ms）：ITEM_ID 精确匹配 + 城市提取 + 日期偏移 + 新入库意图
  Phase 2（LLM，~500ms）：occasion / activity / vibe / style_preference / explore_mood

设计原则：确定性信号（ID/城市/日期）走正则，语义信号（场合/氛围）走 LLM。
Phase 1 在精确匹配上胜出，Phase 2 补充语义层。
LLM 调用失败时降级为最小关键词兜底，不影响管线继续运行。
"""

import datetime
import json
import os
import re
import time
from typing import Optional, List, Tuple

from tools.ai_api import call_doubao_chat, extract_json

# ═══════════════════════════════════════════════════════════
# 单品 ID 正则（中文兼容版 — 不依赖 \b，因 Python 3.x 中 CJK 字符属于 \w）
# ═══════════════════════════════════════════════════════════
# 不同于 common.py 的 ITEM_ID_PATTERN（使用 \b 用于解析已保存的 markdown 文件），
# 中文用户输入中没有空格分隔，\b 在 CJK+ASCII 混合文本中失效。
# 此版本使用 (?<![A-Za-z0-9]) 替代 \b，正确匹配中文语境下的 ID。
_ITEM_ID_CATEGORIES = (
    'TS|SH|PT|JK|SHIRT|SHOE|BAG|HAT|SUN|SOCK|ACC|TANK|LS'
    '|DRESS|SKIRT|JMP|BLOUSE|KNIT'
)
_ITEM_ID_PATTERN_CN = re.compile(
    rf'(?<![A-Za-z0-9])((?:{_ITEM_ID_CATEGORIES})-\d+)(?![A-Za-z0-9])'
)

# ═══════════════════════════════════════════════════════════
# Phase 1: 正则精确提取（零延迟，100% 准确）
# ═══════════════════════════════════════════════════════════

# ── 城市中→英映射（wttr.in 需要英文/拼音城市名）──
_CITY_CN_TO_EN = {
    # 中国大陆主要城市
    '北京': 'Beijing', '上海': 'Shanghai', '广州': 'Guangzhou', '深圳': 'Shenzhen',
    '成都': 'Chengdu', '杭州': 'Hangzhou', '武汉': 'Wuhan', '西安': 'Xian',
    '南京': 'Nanjing', '长沙': 'Changsha', '重庆': 'Chongqing', '天津': 'Tianjin',
    '苏州': 'Suzhou', '郑州': 'Zhengzhou', '东莞': 'Dongguan', '青岛': 'Qingdao',
    '沈阳': 'Shenyang', '宁波': 'Ningbo', '昆明': 'Kunming', '大连': 'Dalian',
    '厦门': 'Xiamen', '合肥': 'Hefei', '佛山': 'Foshan', '福州': 'Fuzhou',
    '哈尔滨': 'Harbin', '济南': 'Jinan', '温州': 'Wenzhou', '长春': 'Changchun',
    '石家庄': 'Shijiazhuang', '常州': 'Changzhou', '泉州': 'Quanzhou', '南宁': 'Nanning',
    '贵阳': 'Guiyang', '南昌': 'Nanchang', '太原': 'Taiyuan', '烟台': 'Yantai',
    '嘉兴': 'Jiaxing', '南通': 'Nantong', '金华': 'Jinhua', '珠海': 'Zhuhai',
    '惠州': 'Huizhou', '徐州': 'Xuzhou', '海口': 'Haikou', '乌鲁木齐': 'Urumqi',
    '兰州': 'Lanzhou', '中山': 'Zhongshan', '三亚': 'Sanya', '无锡': 'Wuxi',
    '拉萨': 'Lhasa', '呼和浩特': 'Hohhot', '银川': 'Yinchuan', '西宁': 'Xining',
    # 常见别名
    '魔都': 'Shanghai', '帝都': 'Beijing', '妖都': 'Guangzhou',
    '蓉城': 'Chengdu', '江城': 'Wuhan', '山城': 'Chongqing',
    # 港澳台
    '香港': 'Hong Kong', '澳门': 'Macau', '台北': 'Taipei',
    '台中': 'Taichung', '高雄': 'Kaohsiung', '台南': 'Tainan',
    # 国际城市
    '东京': 'Tokyo', '大阪': 'Osaka', '京都': 'Kyoto', '札幌': 'Sapporo',
    '首尔': 'Seoul', '釜山': 'Busan', '济州': 'Jeju',
    '曼谷': 'Bangkok', '清迈': 'Chiang Mai', '普吉': 'Phuket',
    '新加坡': 'Singapore', '吉隆坡': 'Kuala Lumpur',
    '纽约': 'New York', '洛杉矶': 'Los Angeles', '旧金山': 'San Francisco',
    '芝加哥': 'Chicago', '波士顿': 'Boston', '西雅图': 'Seattle',
    '伦敦': 'London', '巴黎': 'Paris', '米兰': 'Milan', '罗马': 'Rome',
    '巴塞罗那': 'Barcelona', '柏林': 'Berlin', '阿姆斯特丹': 'Amsterdam',
    '悉尼': 'Sydney', '墨尔本': 'Melbourne', '迪拜': 'Dubai',
}

_CITY_CN_PATTERN = re.compile(
    '(' + '|'.join(re.escape(c) for c in sorted(_CITY_CN_TO_EN.keys(), key=len, reverse=True)) + ')'
)

# ── 日期偏移关键词 ──
_DATE_KEYWORDS = {
    '大后天': 3, '后天': 2, '后日': 2,
    '明天': 1, '明日': 1, '明儿': 1,
    '今天': 0, '今日': 0,
    '昨天': -1, '昨日': -1,
}

_WEEKDAY_CN = {
    '周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6,
    '星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3, '星期五': 4, '星期六': 5, '星期日': 6,
    '礼拜一': 0, '礼拜二': 1, '礼拜三': 2, '礼拜四': 3, '礼拜五': 4, '礼拜六': 5, '礼拜天': 6,
}

# ── 新入库意图关键词 ──
_NEW_ITEM_KEYWORDS = [
    '最新', '新款', '新买', '新到', '新入', '新入库', '最近添加',
    '新衣服', '新单品', '新到的', '刚买', '刚入库', '最新入库',
    '新买的', '新的', '最新款', '新货',
]

# ── 探索情绪快速检测（高频场景走正则，避免 LLM 延迟）──
_EXPLORE_MOOD_FAST = {
    'bold': ['大胆', '另类', '冒险', '突破', '跨界', '夸张', '前卫', '激进', '颠覆',
             '大胆一点', '出格', '炸街', '混搭', '乱搭', '随便', '随机'],
    'fresh': ['探索', '新尝试', '新鲜', '微调', '换换口味', '尝鲜', '换口味',
              '不一样的', '不同风格', '换个风格', '换风格', '来点新的'],
    'safe': ['稳妥', '保守', '安全', '不出错', '保险', '常规', '稳重', '低调',
             '日常', '基础', '简约一点', '简单'],
}


def _phase1_regex_extract(text: str) -> dict:
    """Phase 1: 正则精确提取 — 零延迟，100% 确定性的信号"""
    result = {
        'explicit_item_ids': [],
        'city_cn': None,
        'city_en': None,
        'date_offset': 0,
        'want_new_items': False,
        'explore_mood_fast': None,
    }

    if not text:
        return result

    # ── 1. 单品 ID 精确匹配（TS-001, SHIRT-005, SHOE-007 等）──
    raw_ids = _ITEM_ID_PATTERN_CN.findall(text)
    # 去重保序
    seen = set()
    result['explicit_item_ids'] = [cid for cid in raw_ids if not (cid in seen or seen.add(cid))]

    # ── 2. 城市提取（中文 → 英文映射）──
    city_match = _CITY_CN_PATTERN.search(text)
    if city_match:
        cn_name = city_match.group(1)
        result['city_cn'] = cn_name
        result['city_en'] = _CITY_CN_TO_EN.get(cn_name, cn_name)

    # ── 3. 日期偏移计算 ──
    # "明天/后天/大后天" 模式
    for kw, offset in sorted(_DATE_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if kw in text:
            result['date_offset'] = offset
            break

    # "下周X" 模式（仅在未匹配到绝对日期时）
    if result['date_offset'] == 0:
        for kw, wd in _WEEKDAY_CN.items():
            for prefix in ('下', '下个', '下周'):
                if f'{prefix}{kw}' in text:
                    today = datetime.date.today()
                    today_wd = today.weekday()
                    days_ahead = (wd - today_wd + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    result['date_offset'] = days_ahead
                    break

    # ── 4. 新入库意图检测 ──
    if any(kw in text for kw in _NEW_ITEM_KEYWORDS):
        result['want_new_items'] = True

    # ── 5. 探索情绪快速检测（高频词走正则，避免 LLM 延迟）──
    for mood, keywords in _EXPLORE_MOOD_FAST.items():
        if any(kw in text for kw in keywords):
            result['explore_mood_fast'] = mood
            break

    return result


# ═══════════════════════════════════════════════════════════
# Phase 2: LLM 语义解析（occasion / activity / vibe / style / mood）
# ═══════════════════════════════════════════════════════════

_INTENT_PARSE_SYSTEM = """你是一个中文穿搭意图解析器。从用户的穿搭请求中提取结构化信息。

输出严格 JSON（无 markdown 标记，无额外文字）：
{
  "occasion": "婚礼/通勤/运动/约会/聚会/度假/户外/居家/日常",
  "activity": "参加朋友婚礼" (具体活动描述，无法判断时 null),
  "vibe": "正式、喜庆" (氛围/情绪关键词，无法判断时 null),
  "style_preference": "日系" (用户明确提到的风格名称，无法判断时 null),
  "explore_mood": "normal" (用户想尝新→"fresh"，想大胆→"bold"，求稳→"safe"，默认→"normal")
}

规则：
- occasion 根据场景词推断：婚礼/婚宴→"婚礼"，开会/面试/商务/签合同/见客户→"通勤"，party/蹦迪/夜店/酒吧→"聚会"，hiking/爬山/徒步/露营→"户外"，网球/跑步/健身/篮球/足球→"运动"，约会/相亲/见面→"约会"，旅行/度假/海边→"度假"，在家/宅→"居家"
- 无法明确判断时 occasion 填 "日常"
- activity 抽取用户描述的具体活动，保留用户原话
- vibe 用 2-4 个中文词概括穿搭应传达的感觉
- style_preference 仅提取用户明确提到的风格（日系/韩系/英伦/美式/街头等）
- explore_mood 根据用户措辞判断：明显想要尝试新颖搭配→"fresh"，想要夸张大胆→"bold"，强调稳妥不出错→"safe"，其他→"normal"
- 不要编造，不确定的字段填 null"""


def _phase2_llm_parse(text: str, explicit_ids: List[str]) -> dict:
    """Phase 2: LLM 语义解析 — 场合、活动、氛围、风格偏好、探索情绪"""
    user_prompt = f'用户说：「{text}」'
    if explicit_ids:
        user_prompt += f'\n（已识别指定单品ID：{", ".join(explicit_ids)}，这些不要在语义字段中重复）'

    try:
        content = call_doubao_chat(
            [
                {'role': 'system', 'content': _INTENT_PARSE_SYSTEM},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=512,
            timeout=30,  # 短超时，不影响管线整体延迟
        )
        parsed = extract_json(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass  # LLM 失败 → 返回空 dict，用 fallback

    return {}


# ═══════════════════════════════════════════════════════════
# Fallback: LLM 失败时的最小关键词兜底
# ═══════════════════════════════════════════════════════════

_FALLBACK_SCENE_KW = [
    (['婚礼', '婚宴', 'wedding', '结婚'], '婚礼'),
    (['面试', '开会', '商务', '签合同', '见客户', '正式场合', '答辩'], '通勤'),
    (['约会', 'date', '相亲', '见面', '聚餐', '吃饭'], '约会'),
    (['网球', 'tennis'], '网球'),
    (['跑步', 'running', '慢跑', '夜跑', '晨跑'], '跑步'),
    (['健身', 'gym', '健身房', '举铁', '力量训练'], '健身'),
    (['篮球', 'basketball'], '篮球'),
    (['足球', 'football', 'soccer'], '足球'),
    (['羽毛球', 'badminton'], '羽毛球'),
    (['运动', '锻炼', '体育', 'sport'], '运动'),
    (['聚会', '派对', 'party', '蹦迪', '夜店', '酒吧'], '聚会'),
    (['旅行', '度假', '旅游', 'vacation', '海边', '沙滩', '海岛', '泳池'], '度假'),
    (['户外', '爬山', '登山', '徒步', '露营', '野餐', 'hiking'], '户外'),
    (['居家', '在家', '宅', '家里', '居家办公'], '居家'),
    (['上班', '工作', '通勤', 'office', '办公室'], '通勤'),
    (['逛街', '购物', '逛商场', '出门'], '日常'),
]


def _fallback_occasion(text: str) -> Optional[str]:
    """最小关键词兜底 — 仅当 LLM 完全失败时使用"""
    text_lower = text.lower()
    for keywords, occasion in _FALLBACK_SCENE_KW:
        for kw in keywords:
            if kw in text_lower:
                return occasion
    return None


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def parse_user_intent(text: str) -> dict:
    """解析用户自然语言穿搭请求 → 结构化意图对象

    Args:
        text: 用户原始输入，如 "明天去上海参加婚礼用SHIRT-005搭配"

    Returns:
        {
            "city_cn": "上海" | None,
            "city_en": "Shanghai" | None,       # wttr.in 使用的英文城市名
            "date_offset": 1,                    # 0=今天, 1=明天, 2=后天...
            "occasion": "婚礼",                  # 场合（来自 LLM 或 fallback）
            "activity": "参加朋友婚礼" | None,   # 具体活动描述
            "vibe": "正式、喜庆" | None,         # 氛围/情绪
            "explicit_item_ids": ["SHIRT-005"],  # 用户显式指定的单品 ID
            "style_preference": None | "日系",   # 用户明确提到的风格
            "explore_mood": "normal",            # normal / fresh / bold / safe
            "want_new_items": False,             # 用户是否想要最新入库的单品
            "_parse_time_ms": 123,               # 解析耗时（毫秒）
        }
    """
    t0 = time.time()

    # ── Phase 1: 正则精确提取（永远执行）──
    p1 = _phase1_regex_extract(text)

    # ── Phase 2: LLM 语义解析 ──
    # 判断是否需要 LLM：如果清洗掉 ID 和城市后还剩有意义的中文文本
    cleaned = text
    for cid in p1['explicit_item_ids']:
        cleaned = cleaned.replace(cid, '')
    if p1['city_cn']:
        cleaned = cleaned.replace(p1['city_cn'], '')
    # 去掉纯功能词
    for noise in ['用', '搭配', '一套', '穿搭', '穿什么', '怎么穿', '推荐',
                  '我想', '想要', '帮我', '给我', '今天', '明天', '后天',
                  '晚上', '早上', '上午', '下午', ' ', '，', '。', '的', '了']:
        cleaned = cleaned.replace(noise, '')
    has_semantic_content = len(cleaned.strip()) >= 2

    p2 = {}
    if has_semantic_content:
        p2 = _phase2_llm_parse(text, p1['explicit_item_ids'])

    # ── 合并结果 ──
    # 场合：LLM > fallback 关键词 > 默认
    occasion = (
        p2.get('occasion')
        or _fallback_occasion(text)
        or '日常'
    )

    # 探索情绪：正则快速检测 > LLM > 默认
    explore_mood = p1.get('explore_mood_fast') or p2.get('explore_mood', 'normal')

    result = {
        'city_cn': p1['city_cn'],
        'city_en': p1['city_en'],
        'date_offset': p1['date_offset'],
        'occasion': occasion,
        'activity': p2.get('activity'),
        'vibe': p2.get('vibe'),
        'explicit_item_ids': p1['explicit_item_ids'],
        'style_preference': p2.get('style_preference'),
        'explore_mood': explore_mood,
        'want_new_items': p1['want_new_items'],
        '_parse_time_ms': int((time.time() - t0) * 1000),
    }
    return result


# ═══════════════════════════════════════════════════════════
# 新入库单品查询
# ═══════════════════════════════════════════════════════════

def load_new_items(user_id: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """读取 new_items.json → [(item_id, added_at, category), ...]

    按入库时间倒序排列。
    """
    from tools.common import resolve_user_dir

    user_dir = resolve_user_dir(user_id)
    path = os.path.join(user_dir, 'config', 'new_items.json')
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(user_dir), 'config', 'new_items.json')
    if not os.path.exists(path):
        # 项目级 fallback
        proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(proj_dir, 'config', 'new_items.json')
    if not os.path.exists(path):
        return []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        items = data.get('items', {})
        sorted_items = sorted(
            items.items(),
            key=lambda kv: kv[1].get('added_at', ''),
            reverse=True,
        )
        return [
            (cid, info.get('added_at', ''), info.get('category', ''))
            for cid, info in sorted_items
        ]
    except Exception:
        return []


def get_recent_new_item_ids(user_id: Optional[str] = None, days: int = 14) -> List[Tuple[str, str]]:
    """获取最近 N 天内入库的单品 ID → [(item_id, category), ...]"""
    new_items = load_new_items(user_id)
    if not new_items:
        return []

    cutoff = time.time() - days * 86400
    recent = []
    for cid, added_at, cat in new_items:
        if not added_at:
            continue
        try:
            # 兼容多种时间格式
            ts_str = added_at[:19]  # '2026-06-24T08:30:00'
            if 'T' in ts_str:
                ts = time.mktime(time.strptime(ts_str, '%Y-%m-%dT%H:%M:%S'))
            else:
                ts = time.mktime(time.strptime(ts_str[:10], '%Y-%m-%d'))
            if ts >= cutoff:
                recent.append((cid, cat))
        except Exception:
            pass
    return recent


# ═══════════════════════════════════════════════════════════
# CLI 测试入口
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    test_cases = [
        "明天去上海参加婚礼用SHIRT-005搭配",
        "下周三去东京见客户，穿正式一点",
        "用新买的衣服做一套日常穿搭",
        "今天打网球，用TS-004和SHOE-001",
        "晚上约会，想要日系温柔风格",
        "周末去杭州爬山，穿得舒服点",
        "我想要一套大胆前卫的混搭",
        "今天穿什么",
        "用大黄鞋做一套穿搭",
    ]

    if len(sys.argv) > 1:
        test_cases = [' '.join(sys.argv[1:])]

    for tc in test_cases:
        print(f"\n{'='*60}")
        print(f"输入: {tc}")
        intent = parse_user_intent(tc)
        for k, v in intent.items():
            if k.startswith('_'):
                continue
            print(f"  {k}: {v!r}")
        print(f"  解析耗时: {intent.get('_parse_time_ms', '?')}ms")
