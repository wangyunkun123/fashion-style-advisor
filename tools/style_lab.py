#!/usr/bin/env python3
"""
风格实验室（Style Lab）— B线探索式推荐引擎

从衣橱中被忽视的单品出发，自下而上地探索新搭配可能性。
A线(安全推荐) 与 B线(探索推荐) 以 3:1 比例交替运行。

用法:
  # 测试锚点发现
  python3 tools/style_lab.py --anchors

  # 测试单品解读
  python3 tools/style_lab.py --analyze TS-002

  # 测试舒适区
  python3 tools/style_lab.py --comfort

  # 测试探索方向
  python3 tools/style_lab.py --explore TS-002 32 晴 日常
"""

import os, sys, json, glob, re, urllib.parse
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
STYLES_UNI_DIR = os.path.join(PROJ_DIR, 'styles_universal')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')
STATE_FILE = os.path.join(PROJ_DIR, 'config', 'style_lab_state.json')
DEFAULTS_CONFIG = os.path.join(PROJ_DIR, 'config', 'style_defaults.json')

# CDN base for encyclopedia links
CDN_BASE = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'

# 风格名映射
STYLE_NAMES = {
    'clean_fit': 'Clean Fit', 'japanese_city_boy': '日系City Boy',
    'smart_casual': '轻熟休闲', 'athleisure_sport': '运动休闲',
    'korean_minimal': '韩系简约', 'resort_vacation': '度假休闲',
    'streetwear': '街头潮流', 'chinese_heritage_luxe': '国风质感',
    'chinese_heritage': '国风质感',
}

# ============================================================
# 1. 状态管理
# ============================================================

def load_state():
    """读取风格实验室状态"""
    defaults = {
        'total_recommendations': 0,
        'bline_count': 0,
        'bold_count': 0,
        'last_recommendation_time': None,
        'items_worn': {},
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except:
            pass
    return defaults


def save_state(state):
    """保存风格实验室状态"""
    state['last_recommendation_time'] = datetime.now().isoformat()
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def should_use_bline(state=None):
    """判断是否触发 B线：每 4 次推荐触发 1 次 (total % 4 == 0，且 > 0)"""
    if state is None:
        state = load_state()
    total = state.get('total_recommendations', 0)
    # 第 0 次不走 B线（第一次推荐用 A线打基础）
    return total > 0 and total % 4 == 0


def should_use_bold(state=None):
    """判断是否触发大胆模式：B线内每 4 次触发 1 次 (bline_count % 4 == 0, > 0)"""
    if state is None:
        state = load_state()
    bline = state.get('bline_count', 0)
    return bline > 0 and bline % 4 == 0


def increment_state(state, is_bline=False, is_bold=False, item_ids=None):
    """递增计数并记录穿着"""
    state['total_recommendations'] = state.get('total_recommendations', 0) + 1
    if is_bline:
        state['bline_count'] = state.get('bline_count', 0) + 1
    if is_bold:
        state['bold_count'] = state.get('bold_count', 0) + 1
    if item_ids:
        items_worn = state.setdefault('items_worn', {})
        for iid in item_ids:
            items_worn[iid] = items_worn.get(iid, 0) + 1
    return state


def update_item_wear_count(item_id):
    """回写单品标签文件中的穿着次数"""
    path = os.path.join(TAGS_DIR, f'{item_id}.json')
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            item = json.load(f)
        meta = item.setdefault('meta', {})
        meta['wear_count'] = meta.get('wear_count', 0) + 1
        meta['last_worn'] = datetime.now().isoformat()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
    except:
        pass


# ============================================================
# 2. 数据加载（复用 style_matcher 和 build_push 的模式）
# ============================================================

def load_all_clothing():
    """加载所有衣服标签"""
    items = {}
    for fpath in sorted(glob.glob(os.path.join(TAGS_DIR, '*.json'))):
        fname = os.path.basename(fpath)
        if fname.startswith('SCORE_CACHE') or fname.startswith('.id_to_cutout'):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                item = json.load(f)
            items[item['clothing_id']] = item
        except:
            pass
    return items


def load_all_styles():
    """加载所有风格指纹"""
    styles = {}
    for fpath in sorted(glob.glob(os.path.join(STYLES_DIR, '*.json'))):
        if fpath.endswith('README.json'):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            s = json.load(f)
            styles[s['style_id']] = s
    return styles


def load_style(style_id):
    """加载单个风格指纹"""
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_score_cache():
    """加载评分缓存"""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    cache.pop('_meta', None)
    return cache


def get_item_score(cid, style_id, cache=None):
    """从缓存取单品风格分"""
    if cache is None:
        cache = load_score_cache()
    item_cache = cache.get(cid, {})
    style_cache = item_cache.get(style_id, {})
    return {
        'score': style_cache.get('score', 0),
        'breakdown': style_cache.get('breakdown', {}),
        'passed': style_cache.get('passed', False),
    }


def load_all_ratings():
    """加载所有评分数据"""
    ratings = []
    for d in sorted(os.listdir(OUTFITS_DIR)):
        rpath = os.path.join(OUTFITS_DIR, d, 'rating.json')
        if not os.path.exists(rpath):
            continue
        try:
            with open(rpath, 'r') as f:
                r = json.load(f)
            # 补充 style_id
            if 'style_id' not in r:
                md = os.path.join(OUTFITS_DIR, d, 'outfit.md')
                if os.path.exists(md):
                    with open(md) as f2:
                        txt = f2.read()
                    m = re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)', txt)
                    if m:
                        raw = (m.group(1) or m.group(2)).strip()
                        for kid, kname in STYLE_NAMES.items():
                            if kname.lower().replace(' ', '') in raw.lower().replace(' ', ''):
                                r['style_id'] = kid
                                break
            if 'style_id' not in r:
                r['style_id'] = 'unknown'
            ratings.append(r)
        except:
            pass
    return ratings


def load_encyclopedia(style_id):
    """加载百科数据（复用 build_push 模式）"""
    path = os.path.join(STYLES_UNI_DIR, style_id, 'encyclopedia.md')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    one_liner = ''
    for line in text.split('\n'):
        if '一句话定义' in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m:
                one_liner = m.group(1).strip()
            break

    origin = ''
    in_origin = False
    for line in text.split('\n'):
        if '### 起源' in line or '## 📜' in line:
            in_origin = True
            continue
        if in_origin and line.strip() and not line.startswith('#') and not line.startswith('>'):
            candidate = line.strip().lstrip('- ').strip()
            if len(candidate) > 30:
                origin = candidate[:140] + '...' if len(candidate) > 140 else candidate
                break

    quote = ''
    for line in text.split('\n'):
        if line.strip().startswith('>') and len(line) > 20:
            quote = line.strip().lstrip('> ').strip()
            if '：' in quote or '——' in quote or '"' in quote:
                break

    return {
        'one_liner': one_liner, 'origin': origin, 'quote': quote,
        'encyclopedia_url': f'https://htmlpreview.github.io/?{CDN_BASE}/styles_universal/{style_id}/encyclopedia.html',
    }


def load_defaults_config():
    """加载天气-场合默认映射"""
    if not os.path.exists(DEFAULTS_CONFIG):
        return {
            'weather_rules': [
                {'temp_high_gte': 35, 'condition': '晴', 'suggest': ['resort_vacation', 'clean_fit']},
                {'temp_high_between': [28, 34], 'condition': '晴', 'suggest': ['japanese_city_boy', 'korean_minimal', 'clean_fit']},
                {'temp_high_between': [22, 27], 'suggest': ['clean_fit', 'smart_casual', 'japanese_city_boy', 'korean_minimal']},
                {'temp_high_lte': 21, 'suggest': ['smart_casual', 'streetwear', 'chinese_heritage']},
                {'condition': '雨', 'suggest': ['clean_fit', 'smart_casual', 'streetwear']},
                {'condition': '阴', 'suggest': ['japanese_city_boy', 'clean_fit', 'streetwear']},
            ],
            'occasion_rules': [
                {'occasion': '运动', 'suggest': ['athleisure_sport']},
                {'occasion': '约会', 'suggest': ['smart_casual', 'korean_minimal', 'chinese_heritage']},
                {'occasion': '通勤', 'suggest': ['clean_fit', 'smart_casual', 'korean_minimal']},
                {'occasion': '度假', 'suggest': ['resort_vacation', 'japanese_city_boy']},
                {'occasion': '户外', 'suggest': ['athleisure_sport', 'streetwear']},
                {'occasion': '聚会', 'suggest': ['smart_casual', 'streetwear', 'chinese_heritage']},
                {'occasion': '居家', 'suggest': ['athleisure_sport', 'clean_fit']},
            ],
        }
    with open(DEFAULTS_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 3. 单品表现力计算
# ============================================================

def compute_statement_score(item):
    """
    计算单品的"表现力"分数（0.0 ~ 1.0）
    越高 = 越有个性 = 越有可能成为锚点单品
    """
    score = 0.0
    pattern = item.get('pattern', {}).get('type', '纯色')

    # 图案独特程度 (+0.05 ~ +0.30)
    pattern_bonus = {
        '印花': 0.30, '格纹': 0.25, '条纹': 0.20,
        '拼接': 0.25, 'Logo': 0.15, '纯色': 0.0,
        '几何': 0.25, '迷彩': 0.30, '扎染': 0.30,
        '文字': 0.20, '其他(核雕)': 0.25,
    }
    score += pattern_bonus.get(pattern, 0.05)

    color = item.get('color', {})
    # 饱和度 (+0.20 for 高饱和)
    if color.get('saturation') == '高饱和':
        score += 0.20
    elif color.get('saturation') == '中饱和':
        score += 0.10
    # 非中性色 (+0.10)
    if not color.get('is_neutral', True):
        score += 0.10
    # 罕见色相 (+0.10)
    unusual_hues = {'荧光橙', '正红色', '姜黄色', '砖红色', '草绿', '焦糖色', '薄荷绿', '紫红色', '亮橙色', '亮绿色'}
    if color.get('hue_name') in unusual_hues:
        score += 0.10

    fabric = item.get('fabric', {}).get('primary', '棉')
    # 罕见面料 (+0.05 ~ +0.20)
    fabric_bonus = {
        '皮质': 0.20, '灯芯绒': 0.15, '亚麻': 0.20,
        '麻': 0.10, '羊毛混纺': 0.10, '木质': 0.10,
        '其他(核雕)': 0.10, '棉': 0.0, '涤纶': 0.0,
    }
    score += fabric_bonus.get(fabric, 0.05)

    # 品牌辨识度 (+0.05)
    distinctive_brands = {'COMME des GARCONS PLAY', 'Lululemon', 'Jordan', 'Timberland', 'Wilson'}
    brand_name = item.get('brand', {}).get('name', '')
    if brand_name in distinctive_brands:
        score += 0.05

    # 配饰类天然有表现力 (+0.05)
    acc_codes = {'ACC', 'SUN', 'HAT'}
    if item.get('category_code') in acc_codes:
        score += 0.05

    return min(score, 1.0)


# ============================================================
# 4. 锚点发现
# ============================================================

def find_anchor_items(state=None, min_statement_score=0.20, max_wear_count=2, count=5, strategy='micro', comfort_zone=None):
    """
    寻找被埋没的「锚点单品」：低穿着率 + 高表现力

    strategy='micro': 偏好与舒适区高度匹配的单品（安全探索）
    strategy='bold':  偏好与舒适区格格不入的单品（大胆跨越）
    """
    if state is None:
        state = load_state()

    all_clothing = load_all_clothing()
    items_worn = state.get('items_worn', {})
    score_cache = load_score_cache()

    if comfort_zone is None:
        comfort_zone = get_user_comfort_zone()
    comfort_styles = set(comfort_zone.get('comfort_styles', []))

    results = []

    for cid, item in all_clothing.items():
        wear_count = items_worn.get(cid, 0)
        if wear_count > max_wear_count:
            continue

        statement_score = compute_statement_score(item)
        if statement_score < min_statement_score:
            continue

        # 计算该单品在 8 风格中的得分
        all_scores = []
        comfort_scores = []
        for sid in score_cache.get(cid, {}):
            sc = score_cache[cid][sid].get('score', 0)
            all_scores.append(sc)
            if sid in comfort_styles:
                comfort_scores.append(sc)
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        max_comfort = max(comfort_scores) if comfort_scores else 0

        # 找最高分和最低分风格
        best_style = None
        best_score = 0
        worst_style = None
        worst_score = 100
        for sid, sdata in score_cache.get(cid, {}).items():
            sc = sdata.get('score', 0)
            if sc > best_score:
                best_score = sc
                best_style = sid
            if sc < worst_score:
                worst_score = sc
                worst_style = sid

        score_range = best_score - worst_score

        results.append({
            'item': item,
            'statement_score': round(statement_score, 2),
            'wear_count': wear_count,
            'avg_score': round(avg_score, 1),
            'max_comfort': max_comfort,
            'best_style': best_style,
            'best_score': best_score,
            'worst_style': worst_style,
            'worst_score': worst_score,
            'score_range': score_range,
            # 大胆策略加分：得分范围越大 + 舒适区得分越低 = 越适合大胆尝试
            'bold_score': round(statement_score * 0.3 + (1 - max_comfort/100) * 0.4 + (score_range/100) * 0.3, 2),
        })

    if strategy == 'bold':
        # 大胆模式：按 bold_score 降序——偏好表现力高、舒适区低分、跨风格幅度大的单品
        results.sort(key=lambda x: (-x['bold_score'], x['wear_count']))
    else:
        # 微调模式：按 statement_score 降序，同分按穿着次数升序
        results.sort(key=lambda x: (-x['statement_score'], x['wear_count']))

    return results[:count]


# ============================================================
# 5. 单品深度解读
# ============================================================

def analyze_item_appeal(item):
    """深度解读单品的「吸引力基因」"""
    item_id = item['clothing_id']
    color = item.get('color', {})
    silhouette = item.get('silhouette', {})
    fabric = item.get('fabric', {})
    pattern = item.get('pattern', {})
    style_modifiers = item.get('style_modifiers', [])
    meta = item.get('meta', {})

    # 视觉签名
    color_name = color.get('hue_name', '?')
    pattern_type = pattern.get('type', '纯色')
    if pattern_type in ('纯色', 'Logo'):
        visual = f"{color_name}{pattern_type}" if pattern_type == 'Logo' else f"{color_name}纯色"
    else:
        visual = f"{color_name}{pattern_type}"

    # 廓形态度
    fit = silhouette.get('fit', '标准')
    shoulder = silhouette.get('shoulder_effect', '无特殊效果')
    torso = silhouette.get('torso_effect', '无特殊效果')
    if shoulder != '无特殊效果':
        silhouette_desc = f"{fit}版型 · {shoulder}"
    elif torso != '无特殊效果':
        silhouette_desc = f"{fit}版型 · {torso}"
    else:
        silhouette_desc = f"{fit}版型"

    # 材质语言
    fabric_primary = fabric.get('primary', '?')
    fabric_texture = fabric.get('texture', '?')
    if fabric_texture and fabric_texture != fabric_primary:
        fabric_desc = f"{fabric_primary} · {fabric_texture}质感"
    else:
        fabric_desc = fabric_primary

    # 风格亲和度（从评分缓存获取）
    style_affinity = {'strong': [], 'moderate': [], 'weak': []}
    score_cache = load_score_cache()
    item_scores = score_cache.get(item_id, {})
    for sid, sdata in item_scores.items():
        sc = sdata.get('score', 0)
        if sc >= 60:
            style_affinity['strong'].append(sid)
        elif sc >= 40:
            style_affinity['moderate'].append(sid)
        elif sc >= 20:
            style_affinity['weak'].append(sid)

    # 非框架内潜力风格（得分低于40但在49百科中有可能相关的风格）
    untapped = []
    all_styles = load_all_styles()
    for sid in style_affinity['moderate'] + style_affinity['weak']:
        if sid in all_styles:
            related = all_styles[sid].get('related_styles', [])
            for rs in related:
                if rs not in style_affinity['strong'] and rs not in style_affinity['moderate'] and rs not in untapped:
                    untapped.append(rs)

    return {
        'clothing_id': item_id,
        'category': item.get('category', ''),
        'visual_signature': visual,
        'silhouette_story': silhouette_desc,
        'fabric_story': fabric_desc,
        'brand': item.get('brand', {}).get('name', ''),
        'formality': item.get('formality', 0),
        'style_affinity': style_affinity,
        'untapped_styles': untapped[:5],
        'modifiers': style_modifiers,
        'claude_comment': meta.get('claude_fit_comment', ''),
        'is_statement_piece': meta.get('is_statement_piece', False),
    }


# ============================================================
# 6. 用户舒适区分析
# ============================================================

def get_user_comfort_zone():
    """从评分历史推导用户舒适区"""
    ratings = load_all_ratings()
    all_styles = load_all_styles()
    all_style_ids = set(all_styles.keys())

    comfort = set()    # 3星满意的风格
    explored = set()   # 所有被评价过的风格
    disliked = set()   # 1星不满意的风格

    for r in ratings:
        sid = r.get('style_id', 'unknown')
        if sid == 'unknown' or sid not in all_style_ids:
            continue
        explored.add(sid)
        rating = r.get('rating', 0)
        if rating >= 3:
            comfort.add(sid)
        elif rating <= 1:
            disliked.add(sid)

    # 如果没有任何评分数据，用天气-场合默认推荐作为舒适区
    if not comfort and not explored:
        defaults = load_defaults_config()
        for rule in defaults.get('weather_rules', []):
            for sid in rule.get('suggest', []):
                if sid in all_style_ids:
                    comfort.add(sid)
        for rule in defaults.get('occasion_rules', []):
            for sid in rule.get('suggest', []):
                if sid in all_style_ids:
                    comfort.add(sid)

    unexplored = all_style_ids - explored - {'athleisure_sport'}  # 排除运动风（非日常）

    return {
        'comfort_styles': list(comfort),
        'explored_styles': list(explored),
        'unexplored_styles': list(unexplored),
        'disliked_styles': list(disliked),
    }


# ============================================================
# 7. 探索方向生成
# ============================================================

def generate_exploration_directions(anchor_item, weather_temp=None,
                                     weather_cond='晴', occasion='日常',
                                     boldness='micro', comfort_zone=None):
    """
    为锚点单品生成 2-3 个探索方向

    boldness='micro': 从舒适区 related_styles 出发，微调
    boldness='bold': 从 unexplored + conflicting_styles 出发，大胆跨越
    """
    if comfort_zone is None:
        comfort_zone = get_user_comfort_zone()

    all_styles = load_all_styles()
    score_cache = load_score_cache()
    appeal = analyze_item_appeal(anchor_item)

    comfort_styles = set(comfort_zone.get('comfort_styles', []))
    explored = set(comfort_zone.get('explored_styles', []))
    unexplored = set(comfort_zone.get('unexplored_styles', []))
    disliked = set(comfort_zone.get('disliked_styles', []))

    candidates = []

    if boldness == 'micro':
        # 微调：从舒适区 + related_styles 出发，保持锚点中高匹配分
        candidate_styles = set()
        for cs in comfort_styles:
            style = all_styles.get(cs, {})
            candidate_styles.add(cs)
            for rs in style.get('related_styles', []):
                if rs not in disliked:
                    candidate_styles.add(rs)

        # 也加入 style_affinity 中 moderate 的风格
        for sid in appeal['style_affinity'].get('moderate', []):
            if sid not in disliked:
                candidate_styles.add(sid)

        min_score = 30

    else:  # bold
        # 大胆：严格排除舒适区及其 related_styles，专注未探索 + conflicting
        excluded = set(comfort_styles)
        for cs in comfort_styles:
            style = all_styles.get(cs, {})
            for rs in style.get('related_styles', []):
                excluded.add(rs)

        # 候选源 1：未探索区（排除舒适区相关）
        candidate_styles = set(unexplored) - excluded

        # 候选源 2：舒适区的 conflicting_styles
        for cs in comfort_styles:
            style = all_styles.get(cs, {})
            for cs2 in style.get('conflicting_styles', []):
                if cs2 not in disliked and cs2 not in excluded:
                    candidate_styles.add(cs2)

        # 候选源 3：锚点在所有风格中得分最低的几个（真正的跨风格挑战）
        # 取锚点得分 15-35 的风格——有基本可行性但高度非常规
        item_scores_all = score_cache.get(anchor_item['clothing_id'], {})
        low_score_styles = [sid for sid, sdata in item_scores_all.items()
                           if 15 <= sdata.get('score', 0) <= 35 and sid not in disliked and sid not in excluded]
        for sid in low_score_styles:
            candidate_styles.add(sid)

        # 如果候选太少，降低排除门槛
        if len(candidate_styles) < 2:
            candidate_styles = set(unexplored) | set(comfort_zone.get('explored_styles', [])) - disliked
            candidate_styles -= set(comfort_styles)  # 至少排除核心舒适区

        min_score = 15

    # 排除已在厌恶区的风格
    candidate_styles -= disliked

    # 为每个候选计算 anchor 匹配分
    for sid in candidate_styles:
        if sid not in all_styles:
            continue
        anchor_score = 0
        item_scores = score_cache.get(anchor_item['clothing_id'], {})
        if sid in item_scores:
            anchor_score = item_scores[sid].get('score', 0)

        # 确认过滤：至少要有最低分
        if anchor_score < min_score:
            continue

        style = all_styles[sid]

        # 判定舒适距离
        if sid in comfort_styles:
            distance = 'adjacent'
        elif any(sid in all_styles.get(cs, {}).get('related_styles', []) for cs in comfort_styles):
            distance = 'step'
        else:
            distance = 'leap'

        # 探索理由
        if distance == 'adjacent':
            rationale = f"锚点单品「{appeal['visual_signature']}」在{style['name_zh']}中意外适应，为惯常风格注入新意"
        elif distance == 'step':
            rationale = f"从你喜欢的风格延伸而来，「{appeal['visual_signature']}」作为桥梁单品带你探索{style['name_zh']}"
        else:
            rationale = f"大胆跨界！「{appeal['visual_signature']}」的{appeal['fabric_story']}与{style['name_zh']}碰撞，可能诞生你的专属风格"

        # 综合分：anchor匹配分 + 新颖度加成
        novelty_bonus = 0
        if distance == 'leap':
            novelty_bonus = 15
        elif distance == 'step':
            novelty_bonus = 8

        composite = anchor_score + novelty_bonus

        candidates.append({
            'target_style_id': sid,
            'target_style_name': style['name_zh'],
            'anchor_score': anchor_score,
            'novelty_bonus': novelty_bonus,
            'composite': composite,
            'exploration_rationale': rationale,
            'comfort_distance': distance,
        })

    # 按综合分降序，取 2-3 个
    candidates.sort(key=lambda x: -x['composite'])
    return candidates[:3]


# ============================================================
# 8. 同伴匹配
# ============================================================

def check_color_harmony(item_a, item_b):
    """
    检查两件单品的颜色协调度（0.0 ~ 1.0）
    """
    ca = item_a.get('color', {})
    cb = item_b.get('color', {})

    hue_a = ca.get('hue_family', '')
    hue_b = cb.get('hue_family', '')

    # 同色系 = 高度协调
    if hue_a == hue_b:
        return 1.0

    # 都是中性色 = 高协调
    neutral_hues = {'中性', '黑白灰'}
    if hue_a in neutral_hues and hue_b in neutral_hues:
        return 0.9

    # 一个中性 + 另一个任意 = 中高协调
    if hue_a in neutral_hues or hue_b in neutral_hues:
        return 0.75

    # 互补色（冷+暖）= 冲突中带态度
    warm = {'橙', '红', '黄', '棕'}
    cold = {'蓝', '绿', '紫', '青'}
    if (hue_a in warm and hue_b in cold) or (hue_a in cold and hue_b in warm):
        return 0.4

    return 0.6


def check_weather_appropriateness(item, weather_temp=None, weather_cond='晴'):
    """
    检查单品是否适合当前天气（0.0 ~ 1.0）
    """
    fabric = item.get('fabric', {})
    seasonality = fabric.get('seasonality', [])

    if not seasonality:
        return 0.7  # 无数据时默认适中

    if weather_temp is None:
        return 0.8

    # 高温偏好轻薄
    if weather_temp >= 30:
        if '夏' in seasonality:
            return 1.0
        if '春' in seasonality or '秋' in seasonality:
            return 0.5
        return 0.2

    # 低温偏好厚实
    if weather_temp <= 15:
        if '冬' in seasonality:
            return 1.0
        if '秋' in seasonality:
            return 0.7
        return 0.2

    # 适中温度
    return 0.8


def find_companions(anchor_item, direction, wardrobe=None, weather_temp=None,
                     weather_cond='晴', count_per_category=None):
    """
    为锚点单品找同伴：基于风格兼容 + 锚点和谐 + 天气适配
    """
    if wardrobe is None:
        wardrobe = load_all_clothing()
    if count_per_category is None:
        count_per_category = {'TS': 1, 'PT': 1, 'SHOE': 1}

    target_style_id = direction['target_style_id']
    score_cache = load_score_cache()
    style = load_style(target_style_id)
    anchor_id = anchor_item['clothing_id']
    anchor_cat = anchor_item.get('category_code', '')

    results = []

    for cid, item in wardrobe.items():
        if cid == anchor_id:
            continue
        cat = item.get('category_code', '')
        if cat == anchor_cat:
            continue  # 跳过锚点同品类

        # 1. 风格匹配度（从缓存）
        style_score = 0
        if cid in score_cache and target_style_id in score_cache[cid]:
            style_score = score_cache[cid][target_style_id].get('score', 0)

        # 2. 锚点和谐度
        harmony = check_color_harmony(anchor_item, item)

        # 3. 天气适配度
        weather_score = check_weather_appropriateness(item, weather_temp, weather_cond)

        # 综合分：60%风格 + 25%和谐 + 15%天气
        composite = style_score * 0.6 + harmony * 100 * 0.25 + weather_score * 100 * 0.15

        results.append({
            'item': item,
            'style_score': style_score,
            'harmony_score': round(harmony, 2),
            'weather_score': round(weather_score, 2),
            'composite': round(composite, 1),
            'category': item.get('category', ''),
        })

    # 按品类分组，每组取 Top N
    results.sort(key=lambda x: -x['composite'])
    by_cat = defaultdict(list)
    for r in results:
        cat_prefix = r['item'].get('category_code', '')
        # 映射到需要的品类
        for need_cat, need_count in count_per_category.items():
            if cat_prefix.startswith(need_cat) or cat_prefix == need_cat:
                if len(by_cat[need_cat]) < need_count:
                    by_cat[need_cat].append(r)
                break

    # 展开结果
    companions = []
    for need_cat in count_per_category:
        companions.extend(by_cat.get(need_cat, []))

    return companions


# ============================================================
# 9. 方案组装与叙事生成
# ============================================================

def assemble_exploratory_outfit(direction, anchor_item, companions):
    """组装探索穿搭方案"""
    return {
        'line': 'B',
        'boldness': direction.get('comfort_distance', 'step'),
        'anchor_item': anchor_item,
        'companions': companions,
        'target_style_id': direction['target_style_id'],
        'target_style_name': direction['target_style_name'],
        'direction': direction,
    }


def generate_exploration_narrative(direction, anchor, companions):
    """生成探索穿搭的详细叙事"""
    anchor_name = f"{anchor['clothing_id']} {anchor.get('brand', {}).get('name', '')}"
    anchor_color = anchor.get('color', {}).get('hue_name', '')
    anchor_fabric = anchor.get('fabric', {}).get('primary', '')

    appeal = analyze_item_appeal(anchor)
    style_name = direction['target_style_name']
    distance = direction['comfort_distance']

    parts = []

    # 锚点介绍
    parts.append(f"🔍 **探索基点**：{anchor_name}")
    parts.append(f"   {anchor_color} | {anchor_fabric} | {appeal['visual_signature']}")
    parts.append(f"   发现它的价值：{appeal['claude_comment'] or appeal['silhouette_story']}")

    # 探索方向
    if distance == 'leap':
        emoji = '🚀'
        tag = '大胆跨界'
    elif distance == 'step':
        emoji = '🔭'
        tag = '渐进探索'
    else:
        emoji = '🪞'
        tag = '微妙变奏'

    parts.append(f"\n{emoji} **探索方向**：{style_name}（{tag}）")
    parts.append(f"   {direction['exploration_rationale']}")

    # 同伴搭配逻辑
    parts.append(f"\n🎯 **搭配逻辑**：")
    category_emojis = {
        'TS': '👕', 'LS': '🧥', 'SHIRT': '👔', 'JK': '🧥',
        'PT': '👖', 'SH': '🩳', 'SHOE': '👟', 'HAT': '🧢',
        'BAG': '🎒', 'SUN': '🕶️', 'ACC': '💍', 'TANK': '🎽',
    }
    for comp in companions[:6]:
        item = comp['item']
        cid = item['clothing_id']
        cat_prefix = item.get('category_code', '')[:2]
        emoji = category_emojis.get(item.get('category_code', ''), '👔')
        name = item.get('brand', {}).get('name', cid)
        harmony = comp.get('harmony_score', 0)
        if harmony >= 0.8:
            rel = '和谐呼应'
        elif harmony >= 0.5:
            rel = '中性平衡'
        else:
            rel = '冲突张力'
        parts.append(f"   {emoji} **{cid}** {item['color']['hue_name']} — {rel}（风格匹配 {comp.get('style_score', 0)}分）")

    # 风格溯源（如果有百科数据）
    encyc = load_encyclopedia(direction['target_style_id'])
    if encyc and encyc.get('origin'):
        parts.append(f"\n📖 **风格溯源**：{encyc['origin'][:120]}")
    if encyc and encyc.get('one_liner'):
        parts.append(f"   💡 {encyc['one_liner']}")

    # 穿法建议
    silhouette = anchor.get('silhouette', {})
    if silhouette.get('fit') == '宽松':
        tip = '锚点单品偏宽松，下装可选直筒/锥形保持上下平衡'
    elif silhouette.get('fit') == '合身':
        tip = '锚点合身剪裁，可用宽松外套制造层次对比'
    else:
        tip = '尝试将锚点单品作为视觉焦点，其他单品做减法'

    parts.append(f"\n💬 **穿法建议**：{tip}")

    return '\n'.join(parts)


# ============================================================
# 10. 「今天也适合」动态生成
# ============================================================

def generate_alt_section(primary_line='A', is_bline=False, is_bold=False,
                          primary_style_id=None, weather_temp=None,
                          weather_cond='晴', occasion='日常',
                          comfort_zone=None):
    """
    动态生成「今天也适合」的 3 个替代方案

    规则：
    - A线推送：2个A线安全风格 + 1个B线微调
    - B线微调：1个A线 + 1个B线微调 + 1个B线大胆
    - B线大胆：3个A线安全风格
    """
    if comfort_zone is None:
        comfort_zone = get_user_comfort_zone()

    all_styles = load_all_styles()
    defaults = load_defaults_config()

    # 获取 A线安全风格（从天气-场合映射）
    safe_styles = []
    for rule in defaults.get('weather_rules', []):
        matched = False
        if 'condition' in rule and rule.get('condition') == weather_cond:
            matched = True
        elif 'condition' not in rule:
            matched = True
        if matched:
            for sid in rule.get('suggest', []):
                if sid in all_styles and sid not in safe_styles:
                    safe_styles.append(sid)

    for rule in defaults.get('occasion_rules', []):
        if rule['occasion'] in occasion or occasion in rule['occasion']:
            for sid in rule.get('suggest', []):
                if sid in all_styles and sid not in safe_styles:
                    safe_styles.append(sid)

    if not safe_styles:
        safe_styles = ['clean_fit', 'japanese_city_boy', 'korean_minimal']

    alt_items = []

    if is_bold:
        # B线大胆：2个安全风格 + 1个微调
        for sid in safe_styles:
            if sid != primary_style_id and len(alt_items) < 2:
                style = all_styles.get(sid, {})
                alt_items.append({
                    'style_id': sid,
                    'style_name': style.get('name_zh', sid),
                    'why': '回到舒适区，换换心情',
                })
        # 加1个微调
        anchors = find_anchor_items(count=3)
        if anchors:
            micro_dirs = generate_exploration_directions(
                anchors[0]['item'], weather_temp, weather_cond, occasion,
                boldness='micro', comfort_zone=comfort_zone
            )
            for md in micro_dirs:
                if md['target_style_id'] != primary_style_id and not any(a['style_id'] == md['target_style_id'] for a in alt_items):
                    alt_items.append({
                        'style_id': md['target_style_id'],
                        'style_name': md['target_style_name'],
                        'why': '🧪 微调探索 · 尝试新方向',
                    })
                    break

    elif is_bline:
        # B线微调：1个A线 + 1个B线微调 + 1个B线大胆
        # 1个A线
        for sid in safe_styles:
            if sid != primary_style_id and len(alt_items) < 1:
                style = all_styles.get(sid, {})
                alt_items.append({
                    'style_id': sid,
                    'style_name': style.get('name_zh', sid),
                    'why': '回到舒适区，换换心情',
                })

        # 1个B线微调方向
        anchors = find_anchor_items(count=3)
        if anchors:
            micro_dirs = generate_exploration_directions(
                anchors[0]['item'], weather_temp, weather_cond, occasion,
                boldness='micro', comfort_zone=comfort_zone
            )
            for md in micro_dirs:
                if md['target_style_id'] != primary_style_id and len([a for a in alt_items if a['style_id'] == md['target_style_id']]) == 0:
                    alt_items.append({
                        'style_id': md['target_style_id'],
                        'style_name': md['target_style_name'],
                        'why': f"微调探索 · {md['comfort_distance']}",
                    })
                    break

        # 1个B线大胆方向
        if anchors:
            bold_dirs = generate_exploration_directions(
                anchors[0]['item'], weather_temp, weather_cond, occasion,
                boldness='bold', comfort_zone=comfort_zone
            )
            for bd in bold_dirs:
                if bd['target_style_id'] != primary_style_id and len([a for a in alt_items if a['style_id'] == bd['target_style_id']]) == 0:
                    alt_items.append({
                        'style_id': bd['target_style_id'],
                        'style_name': bd['target_style_name'],
                        'why': '🚀 大胆尝试 · 风格跨界',
                    })
                    break

    else:
        # A线推送：2个A线 + 1个B线微调
        # 2个A线
        for sid in safe_styles:
            if sid != primary_style_id and len([a for a in alt_items if not a.get('why', '').startswith('微调')]) < 2:
                style = all_styles.get(sid, {})
                alt_items.append({
                    'style_id': sid,
                    'style_name': style.get('name_zh', sid),
                    'why': '今天也适合的百搭风格',
                })

        # 1个B线微调
        anchors = find_anchor_items(count=3)
        if anchors:
            micro_dirs = generate_exploration_directions(
                anchors[0]['item'], weather_temp, weather_cond, occasion,
                boldness='micro', comfort_zone=comfort_zone
            )
            for md in micro_dirs:
                if md['target_style_id'] != primary_style_id:
                    alt_items.append({
                        'style_id': md['target_style_id'],
                        'style_name': md['target_style_name'],
                        'why': f"🧪 风格实验 · {md['comfort_distance']}",
                    })
                    break

    # 补充：如果不够 3 个，从 safe_styles 补齐
    for sid in safe_styles:
        if len(alt_items) >= 3:
            break
        if sid != primary_style_id and not any(a['style_id'] == sid for a in alt_items):
            style = all_styles.get(sid, {})
            alt_items.append({
                'style_id': sid,
                'style_name': style.get('name_zh', sid),
                'why': '经典日常选择',
            })

    return alt_items[:3]


# ============================================================
# 11. B线排版图生成
# ============================================================

def compose_bline_outfit(anchor_item, companions, output_name='bline_composite'):
    """
    为 B线穿搭快速生成排版图（纯单品抠图拼合，不需要 AI 效果图）
    返回 (image_path, cdn_url) 或 (None, None)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None, None

    WARDROBE_ENHANCED = os.path.join(PROJ_DIR, 'wardrobe', 'enhanced')
    OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')

    # 收集所有需要展示的单品和它们的抠图路径
    items_to_show = [anchor_item] + [c['item'] for c in companions[:5]]
    img_paths = []

    def find_cutout(item):
        cid = item['clothing_id']
        # 1. 先找 wardrobe/enhanced/
        for fname in os.listdir(WARDROBE_ENHANCED) if os.path.exists(WARDROBE_ENHANCED) else []:
            if fname.startswith(cid + '_') and fname.endswith('_cutout.png'):
                return os.path.join(WARDROBE_ENHANCED, fname)
        # 2. 遍历所有 outfit 的 items/ 目录
        for od in os.listdir(OUTFITS_DIR):
            items_dir = os.path.join(OUTFITS_DIR, od, 'items')
            if not os.path.isdir(items_dir):
                continue
            for fname in os.listdir(items_dir):
                if fname.startswith(cid + '_') and fname.endswith('_cutout.png'):
                    return os.path.join(items_dir, fname)
        return None

    for item in items_to_show:
        path = find_cutout(item)
        if path:
            img_paths.append((item, path))

    if not img_paths:
        return None, None

    # 排版参数
    BG_COLOR = (250, 249, 246)  # 温暖米白底
    CARD_W, CARD_H = 400, 500
    PADDING = 24
    GAP = 16
    LABEL_H = 60
    COLS = min(len(img_paths), 4)
    ROWS = (len(img_paths) + COLS - 1) // COLS

    canvas_w = PADDING * 2 + COLS * CARD_W + (COLS - 1) * GAP
    canvas_h = PADDING * 2 + ROWS * (CARD_H + LABEL_H) + (ROWS - 1) * GAP

    canvas = Image.new('RGB', (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # 加载字体
    font_label = None
    font_title = None
    for fp in ['/System/Library/Fonts/STHeiti Medium.ttc',
                '/System/Library/Fonts/Supplemental/Songti.ttc',
                '/System/Library/Fonts/STHeiti Light.ttc']:
        if os.path.exists(fp):
            try:
                font_label = ImageFont.truetype(fp, 16)
                font_title = ImageFont.truetype(fp, 22)
                break
            except:
                pass

    for idx, (item, img_path) in enumerate(img_paths):
        row, col = idx // COLS, idx % COLS
        x = PADDING + col * (CARD_W + GAP)
        y = PADDING + row * (CARD_H + LABEL_H + GAP)

        # 加载并处理单品图
        try:
            img = Image.open(img_path)
            if img.mode == 'RGBA':
                # 白色背景合成
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert('RGB')

            # 缩放适配卡片
            iw, ih = img.size
            scale = min(CARD_W / iw, CARD_H / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = img.resize((nw, nh), Image.LANCZOS)

            # 居中贴入
            px = x + (CARD_W - nw) // 2
            py = y + (CARD_H - nh) // 2
            canvas.paste(img, (px, py))
        except:
            pass

        # 卡片边框
        draw.rectangle([x, y, x + CARD_W, y + CARD_H], outline=(220, 218, 213), width=1)

        # 标签
        cid = item['clothing_id']
        is_anchor = (cid == anchor_item['clothing_id'])
        label_text = f"⭐ {cid}" if is_anchor else cid
        if font_label:
            bbox = draw.textbbox((0, 0), label_text, font=font_label)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x + (CARD_W - tw) // 2, y + CARD_H + 10), label_text, fill=(80, 80, 80), font=font_label)

    # 保存
    output_dir = os.path.join(PROJ_DIR, 'outfits', '_bline_temp')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{output_name}.jpg')
    canvas.save(output_path, 'JPEG', quality=90)

    # CDN URL
    CDN_BASE = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'
    rel = os.path.relpath(output_path, PROJ_DIR)
    cdn_url = f'{CDN_BASE}/{rel}'

    return output_path, cdn_url


# ============================================================
# 12. B线完整生图管线
# ============================================================

# 品类 → 目录映射（用于找参考图）
CATEGORY_DIR_MAP = {
    '短袖上衣': '短袖上衣', '长袖上衣': '长袖上衣',
    '外套': '外套', '长裤': '长裤', '短裤': '短裤',
    '衬衣': '衬衣', '背心': '背心', '鞋子': '鞋子',
    '帽子': '帽子', '包': '包', '墨镜': '墨镜',
    '手部配饰': '手部配饰', '袜子': '袜子',
}
CATEGORY_PREFIX_MAP = {
    '短袖上衣': '上衣', '长袖上衣': '上衣', '衬衣': '上衣', '背心': '上衣',
    '外套': '外搭', '长裤': '下装', '短裤': '下装', '鞋子': '鞋子',
}


def _load_wardrobe_index():
    """从服装档案.md 建立 ID → filename 索引"""
    wardrobe_md = os.path.join(PROJ_DIR, 'wardrobe', '服装档案.md')
    index = {}
    if not os.path.exists(wardrobe_md):
        return index
    with open(wardrobe_md, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'\|\s*([A-Z]+-\d+)\s*\|\s*(\S+\.(jpg|png|jpeg|JPG))\s*\|', line)
            if m:
                index[m.group(1)] = m.group(2)
    return index


def _generate_seedream_image(outfit_dir, shengtu_dir, shangao_dir):
    """直调 Seedream API 生图，不依赖 generate.py 的关键词查找"""
    import base64, urllib.request

    # 加载提示词
    prompt_file = os.path.join(shengtu_dir, '豆包提示词.txt')
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(f"提示词文件不存在: {prompt_file}")
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt = f.read().strip()

    # 收集参考图（人物 + 上衣/外搭 + 下装 + 鞋子）
    ref_images = []
    for prefix in ['人物_', '上衣_', '外搭_', '下装_', '鞋子_']:
        for fname in sorted(os.listdir(shengtu_dir)):
            if fname.startswith(prefix) and fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                path = os.path.join(shengtu_dir, fname)
                try:
                    from PIL import Image
                    img = Image.open(path)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.thumbnail((1024, 1024), Image.LANCZOS)
                    import io
                    buf = io.BytesIO()
                    img.save(buf, 'JPEG', quality=70)
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    ref_images.append(f'data:image/jpeg;base64,{b64}')
                except Exception:
                    pass
                break  # 每种前缀只取一张
        if len(ref_images) >= 4:
            break

    # 加载 API 配置
    cfg_path = os.path.join(PROJ_DIR, 'config', 'seedream.local.json')
    with open(cfg_path, 'r') as f:
        api_key = json.load(f)['api_key']

    seedream_cfg_path = os.path.join(PROJ_DIR, 'config', 'seedream.json')
    if os.path.exists(seedream_cfg_path):
        with open(seedream_cfg_path, 'r') as f:
            seedream_cfg = json.load(f)
    else:
        seedream_cfg = {'model': 'doubao-seedream-5.0-lite', 'size': '2048x2048', 'max_images': 4}

    # 调用 API
    payload = {
        'model': seedream_cfg.get('model', 'doubao-seedream-5.0-lite'),
        'prompt': prompt,
        'size': seedream_cfg.get('size', '2048x2048'),
        'response_format': 'url',
        'watermark': False,
        'max_images': 1,
    }
    if ref_images:
        payload['reference_images'] = ref_images[:4]

    req = urllib.request.Request(
        'https://ark.cn-beijing.volces.com/api/plan/v3/images/generations',
        data=json.dumps(payload).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
    )

    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    img_url = resp['data'][0]['url']

    # 下载结果
    img_data = urllib.request.urlopen(img_url, timeout=60).read()
    output_path = os.path.join(shangao_dir, '上身效果_1.png')
    with open(output_path, 'wb') as f:
        f.write(img_data)

    print(f"  [B线] Seedream 生图完成: {len(img_data)} bytes")


def prepare_bline_outfit(anchor_item, companions, direction, weather_temp=30, weather_cond='晴'):
    """
    为 B线探索穿搭创建完整的 outfit 目录结构，运行生图+排版管线。
    返回: (outfit_dir, composite_jpg_path, cdn_url) 或 (None, None, None)
    """
    import shutil
    import subprocess

    anchor_id = anchor_item['clothing_id']
    style_id = direction['target_style_id']
    style_name = direction['target_style_name']
    boldness = direction.get('comfort_distance', 'step')
    bold_tag = '\U0001f680' if boldness == 'leap' else '\U0001f9ea'

    today = datetime.now().strftime('%Y-%m-%d')
    dir_name = f"{today}_{style_name}B线探索"
    outfit_dir = os.path.join(PROJ_DIR, 'outfits', dir_name)

    if os.path.exists(outfit_dir):
        for i in range(2, 100):
            alt = f"{today}_{style_name}B线探索_{i}"
            if not os.path.exists(os.path.join(PROJ_DIR, 'outfits', alt)):
                outfit_dir = os.path.join(PROJ_DIR, 'outfits', alt)
                dir_name = alt
                break

    shengtu_dir = os.path.join(outfit_dir, '豆包生图')
    items_dir = os.path.join(outfit_dir, 'items')
    shangao_dir = os.path.join(outfit_dir, '上身效果')

    for d in [shengtu_dir, items_dir, shangao_dir]:
        os.makedirs(d, exist_ok=True)

    all_items = [anchor_item] + [c['item'] for c in companions[:5]]
    wardrobe_index = _load_wardrobe_index()
    appeal = analyze_item_appeal(anchor_item)

    # ── 1. outfit.md ──
    items_table_lines = []
    for item in all_items:
        cid = item['clothing_id']
        cat = item.get('category', '')
        color = item.get('color', {}).get('hue_name', '')
        brand = item.get('brand', {}).get('name', '')
        if brand and brand != '未知':
            item_name = f'{brand} {color}{cat}'
        else:
            item_name = f'{color}{cat}'
        # ⚠️ ⭐ 不能放在 ID 列，否则 composite_v2 的 parse() 会把 ⭐ 读入 ID → 找不到文件
        marker = ' ⭐锚点' if cid == anchor_id else ''
        items_table_lines.append(
            f"| {cat} | **{cid}** | {item_name} | {appeal['visual_signature'][:30]}{marker} |"
        )

    # 风格笔记（composite_v2 parse_style_info 读取每行作为 STYLE NOTES）
    # 从探索叙事中提取关键信息
    encyc = load_encyclopedia(style_id) if style_id else None
    style_desc = encyc.get('one_liner', '') if encyc else ''
    if not style_desc:
        style_desc = f'{style_name}风格穿搭'

    anchor_color = anchor_item.get('color', {}).get('hue_name', '')
    anchor_cat = anchor_item.get('category', '')
    claude_tip = anchor_item.get('meta', {}).get('claude_fit_comment', '')
    if len(claude_tip) > 30:
        claude_tip = claude_tip[:28] + '..'

    silhouette = anchor_item.get('silhouette', {})
    if silhouette.get('fit') == '宽松':
        wear_tip = '上宽下窄，直筒/锥形下装'
    elif silhouette.get('fit') == '合身':
        wear_tip = '外搭宽松层次，制造对比'
    else:
        wear_tip = '以锚点单品为视觉焦点'

    style_notes_lines = [
        f'- {style_name}：{style_desc[:26]}',
        f'- 锚点 {anchor_id}：{claude_tip}' if claude_tip else f'- 锚点：{anchor_color}{anchor_cat}',
        f'- 穿法：{wear_tip}',
        f'- {bold_tag} {"大胆跨界尝试" if boldness == "leap" else "微调探索新方向"}',
    ]

    outfit_md = f"""# {style_name} B线探索穿搭

- **日期**: {today}
- **天气**: {weather_cond} {weather_temp}°C
- **风格**: {style_name}（风格实验室探索）
- **探索模式**: {bold_tag} {'大胆跨界' if boldness == 'leap' else '微调探索'}

## 单品清单
| 品类 | ID | 单品 | 选品理由 |
|------|-----|------|----------|
{chr(10).join(items_table_lines)}

## 探索叙事

{generate_exploration_narrative(direction, anchor_item, companions)}

## 风格笔记

{chr(10).join(style_notes_lines)}
"""
    with open(os.path.join(outfit_dir, 'outfit.md'), 'w', encoding='utf-8') as f:
        f.write(outfit_md)

    # ── 2. Seedream 提示词 ──
    item_descs = []
    for item in all_items:
        cid = item['clothing_id']
        color = item.get('color', {}).get('hue_name', '')
        fabric = item.get('fabric', {}).get('primary', '')
        fit = item.get('silhouette', {}).get('fit', '')
        cat = item.get('category', '')
        item_descs.append(f"- {cat}：{color}{fabric}{fit}款")

    prompt = f"""一位30岁亚洲男性全身穿搭照，身高179cm偏瘦体型，肤色偏白，短发干净。

【穿搭风格】{style_name}，探索式推荐。

【穿搭描述】
{chr(10).join(item_descs)}

【场景】城市户外或艺术街区，{weather_cond}天自然光，全身构图。
【摄影风格】fujifilm胶片质感，街拍风格，自然姿态。"""
    with open(os.path.join(shengtu_dir, '豆包提示词.txt'), 'w', encoding='utf-8') as f:
        f.write(prompt)

    # ── 3. 人物照片 ──
    person_photo = os.path.join(PROJ_DIR, 'profile', 'photos', 'IMG_8493.jpg')
    if os.path.exists(person_photo):
        shutil.copy2(person_photo, os.path.join(shengtu_dir, '人物_IMG_8493.jpg'))

    # ── 4. 参考图 → 豆包生图/ ──
    copied_prefixes = set()
    for item in all_items:
        cid = item['clothing_id']
        cat = item.get('category', '')
        cat_dir = CATEGORY_DIR_MAP.get(cat, '')
        prefix = CATEGORY_PREFIX_MAP.get(cat, '')
        if not cat_dir or not prefix or prefix in copied_prefixes:
            continue
        filename = wardrobe_index.get(cid)
        if not filename:
            continue
        src = os.path.join(PROJ_DIR, 'wardrobe', cat_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(shengtu_dir, f'{prefix}_{filename}'))
            copied_prefixes.add(prefix)

    # ── 5. 抠图 → items/（使用服装档案 ID 映射）──
    ENHANCED_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'enhanced')
    # 构建 ID → enhanced cutout 文件名映射（与 sync_items.py 相同逻辑）
    id_to_cutout = {}
    for cid, filename in wardrobe_index.items():
        base = os.path.splitext(filename)[0]
        cutout_name = f'{base}_cutout.png'
        cutout_path = os.path.join(ENHANCED_DIR, cutout_name)
        if os.path.exists(cutout_path):
            id_to_cutout[cid] = cutout_name
        else:
            # 模糊匹配：日期模式
            date_match = re.search(r'(\d{8})_(\d{4})_(\d{2})_(\d{3})', filename)
            if date_match:
                pattern = f"{date_match.group(1)}_{date_match.group(2)}"
                for fname in os.listdir(ENHANCED_DIR) if os.path.exists(ENHANCED_DIR) else []:
                    if pattern in fname and fname.endswith('_cutout.png'):
                        id_to_cutout[cid] = fname
                        break

    for item in all_items:
        cid = item['clothing_id']
        cat = item.get('category', '')
        found = False

        # a. 用 ID 映射从 enhanced/ 复制抠图
        if cid in id_to_cutout:
            cutout_name = id_to_cutout[cid]
            src = os.path.join(ENHANCED_DIR, cutout_name)
            if os.path.exists(src):
                # 保持原名但加 ID 前缀
                dst_name = f"{cid}_{cutout_name}"
                shutil.copy2(src, os.path.join(items_dir, dst_name))
                found = True

        if not found:
            # b. 从已有 outfits 中找
            for od in os.listdir(os.path.join(PROJ_DIR, 'outfits')):
                odir = os.path.join(PROJ_DIR, 'outfits', od, 'items')
                if not os.path.isdir(odir):
                    continue
                for fname in os.listdir(odir):
                    if fname.startswith(cid + '_') and fname.endswith('_cutout.png'):
                        shutil.copy2(os.path.join(odir, fname), os.path.join(items_dir, fname))
                        found = True
                        break
                if found:
                    break

        if not found:
            # c. 回退：用原始 wardrobe 图片
            filename = wardrobe_index.get(cid)
            if filename:
                cat_dir = CATEGORY_DIR_MAP.get(cat, '')
                src = os.path.join(PROJ_DIR, 'wardrobe', cat_dir, filename)
                if os.path.exists(src):
                    base = os.path.splitext(filename)[0]
                    ext = os.path.splitext(filename)[1]
                    dst_name = f"{cid}_{base}{ext}"
                    shutil.copy2(src, os.path.join(items_dir, dst_name))
                    found = True

    # ── 6. 豆包生图（直调 API，不依赖 generate.py 的关键词查找）──
    try:
        _generate_seedream_image(outfit_dir, shengtu_dir, shangao_dir)
    except Exception as e:
        print(f"  [B线] 生图失败: {e}")
        img_path, cdn_url = compose_bline_outfit(anchor_item, companions, dir_name[:30])
        return outfit_dir, img_path, cdn_url

    # ── 7. 排版合成 ──
    try:
        subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, 'composite_v2.py'), outfit_dir],
            cwd=PROJ_DIR, capture_output=True, text=True, timeout=60
        )
    except Exception as e:
        print(f"  [B线] 排版失败: {e}")

    # ── 8. 找排版图 ──
    composite_jpg = None
    for fname in sorted(os.listdir(shangao_dir) if os.path.exists(shangao_dir) else [], reverse=True):
        if '方案' in fname and fname.endswith('.jpg'):
            composite_jpg = os.path.join(shangao_dir, fname)
            break

    if not composite_jpg:
        img_path, cdn_url = compose_bline_outfit(anchor_item, companions, dir_name[:30])
        return outfit_dir, img_path, cdn_url

    # ── 9. Git push ──
    commit_hash = None
    try:
        subprocess.run(['git', 'add', '-A'], cwd=PROJ_DIR, capture_output=True, timeout=30)
        subprocess.run(['git', 'commit', '-m', f'{bold_tag} B线探索: {style_name} ({today})'],
                       cwd=PROJ_DIR, capture_output=True, timeout=30)
        subprocess.run(['git', 'push'], cwd=PROJ_DIR, capture_output=True, timeout=60)
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=PROJ_DIR, capture_output=True, text=True, timeout=10)
        commit_hash = result.stdout.strip()[:7]
    except Exception as e:
        print(f"  [B线] Git push 失败: {e}")

    rel = os.path.relpath(composite_jpg, PROJ_DIR)
    # URL 编码中文路径
    encoded_rel = urllib.parse.quote(rel, safe='/')
    if commit_hash:
        cdn_url = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit_hash}/{encoded_rel}'
    else:
        cdn_url = f'{CDN_BASE}/{encoded_rel}'

    return outfit_dir, composite_jpg, cdn_url


# ============================================================
# 13. 命令行接口
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/style_lab.py --anchors              # 列出锚点单品")
        print("  python3 tools/style_lab.py --analyze <item_id>    # 深度解读单品")
        print("  python3 tools/style_lab.py --comfort              # 查看用户舒适区")
        print("  python3 tools/style_lab.py --explore <item_id> <temp> <cond> <occasion>  # 探索方向")
        print("  python3 tools/style_lab.py --alt <style_id> <cond> <occasion>  # 今天也适合")
        return

    cmd = sys.argv[1]

    if cmd == '--anchors':
        state = load_state()
        anchors = find_anchor_items(state, min_statement_score=0.15, count=10)
        print("\n🧲 锚点单品 Top 10（低穿着率 + 高表现力）\n")
        print(f"{'ID':12s} {'品类':8s} {'表现力':6s} {'穿着':4s} {'均分':5s} {'最佳风格':20s} {'最佳分':5s}")
        print("-" * 70)
        for a in anchors:
            item = a['item']
            print(f"{item['clothing_id']:12s} {item['category']:8s} {a['statement_score']:.2f}   "
                  f"{a['wear_count']:3d}  {a['avg_score']:4.1f}  "
                  f"{STYLE_NAMES.get(a['best_style'], a['best_style'] or '?'):20s} {a['best_score']:4d}")

    elif cmd == '--analyze':
        if len(sys.argv) < 3:
            print("请指定单品 ID，如: python3 tools/style_lab.py --analyze TS-002")
            return
        item_id = sys.argv[2]
        wardrobe = load_all_clothing()
        if item_id not in wardrobe:
            print(f"❌ 未找到单品: {item_id}")
            return
        appeal = analyze_item_appeal(wardrobe[item_id])
        print(f"\n🔍 {item_id} 深度解读")
        print(f"   视觉签名: {appeal['visual_signature']}")
        print(f"   廓形态度: {appeal['silhouette_story']}")
        print(f"   材质语言: {appeal['fabric_story']}")
        print(f"   正式度: {appeal['formality']}/5")
        print(f"   表现力单品: {'是' if appeal['is_statement_piece'] else '否'}")
        print(f"   强亲和风格: {[STYLE_NAMES.get(s, s) for s in appeal['style_affinity']['strong']]}")
        print(f"   中亲和风格: {[STYLE_NAMES.get(s, s) for s in appeal['style_affinity']['moderate']]}")
        print(f"   未开发潜力: {[STYLE_NAMES.get(s, s) for s in appeal['untapped_styles']]}")
        print(f"   Claude 点评: {appeal['claude_comment']}")

    elif cmd == '--comfort':
        cz = get_user_comfort_zone()
        print("\n🛋️ 用户舒适区")
        print(f"   舒适风格: {[STYLE_NAMES.get(s, s) for s in cz['comfort_styles']]}")
        print(f"   已探索: {[STYLE_NAMES.get(s, s) for s in cz['explored_styles']]}")
        print(f"   未探索: {[STYLE_NAMES.get(s, s) for s in cz['unexplored_styles']]}")
        print(f"   不喜欢: {[STYLE_NAMES.get(s, s) for s in cz['disliked_styles']]}")

    elif cmd == '--explore':
        if len(sys.argv) < 3:
            print("用法: python3 tools/style_lab.py --explore <item_id> [temp] [cond] [occasion]")
            return
        item_id = sys.argv[2]
        temp = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        cond = sys.argv[4] if len(sys.argv) > 4 else '晴'
        occasion = sys.argv[5] if len(sys.argv) > 5 else '日常'

        wardrobe = load_all_clothing()
        if item_id not in wardrobe:
            print(f"❌ 未找到单品: {item_id}")
            return
        anchor = wardrobe[item_id]
        cz = get_user_comfort_zone()

        for boldness in ['micro', 'bold']:
            label = '🔭 微调' if boldness == 'micro' else '🚀 大胆'
            print(f"\n{label} 探索方向")
            dirs = generate_exploration_directions(anchor, temp, cond, occasion, boldness, cz)
            for d in dirs:
                print(f"   🎯 {d['target_style_name']} ({d['target_style_id']})")
                print(f"      锚点匹配: {d['anchor_score']}分 | 新颖加成: +{d['novelty_bonus']} | 综合: {d['composite']}")
                print(f"      距离: {d['comfort_distance']} | {d['exploration_rationale']}")

            # 也展示同伴
            if dirs:
                d = dirs[0]
                companions = find_companions(anchor, d, wardrobe, temp, cond)
                print(f"\n   🤝 同伴搭配（{d['target_style_name']}）：")
                for c in companions[:5]:
                    item = c['item']
                    print(f"      {item['clothing_id']} {item['color']['hue_name']} | "
                          f"风格{c['style_score']}分 | 和谐{c['harmony_score']:.0%} | 天气{c['weather_score']:.0%}")

    elif cmd == '--alt':
        style_id = sys.argv[2] if len(sys.argv) > 2 else 'clean_fit'
        cond = sys.argv[3] if len(sys.argv) > 3 else '晴'
        occasion = sys.argv[4] if len(sys.argv) > 4 else '日常'
        cz = get_user_comfort_zone()

        for scenario in [('A线推送', 'A', False, False), ('B线微调', 'B', True, False), ('B线大胆', 'B', True, True)]:
            label, line, is_bl, is_bd = scenario
            print(f"\n📋 {label} → 今天也适合")
            alts = generate_alt_section(line, is_bl, is_bd, style_id, 30, cond, occasion, cz)
            for a in alts:
                print(f"   [{a['style_name']}] — {a['why']}")

    else:
        print(f"未知命令: {cmd}")


if __name__ == '__main__':
    main()
