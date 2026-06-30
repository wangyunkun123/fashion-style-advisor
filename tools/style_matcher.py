#!/usr/bin/env python3
"""
风格匹配引擎
计算服装与风格的兼容度分数。

用法:
  python3 tools/style_matcher.py <style_id>              # 某风格全品类排名
  python3 tools/style_matcher.py <style_id> <cat_code>   # 某风格某品类候选
  python3 tools/style_matcher.py --all                   # 8个风格全部排名
  python3 tools/style_matcher.py --auto 35 晴 运动       # 天气+场合自动推荐
"""

import os, sys, json, glob, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
# 🆕 确保项目根目录在 sys.path
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

# ── 多用户支持 ──
_USER_ID = None
_USER_ARG_IDX = None  # 记录 --user 在 sys.argv 中的位置，用于后续移除
for _i, _arg in enumerate(sys.argv[1:], start=1):
    if _arg == '--user' and _i + 1 < len(sys.argv):
        _USER_ID = sys.argv[_i + 1]
        _USER_ARG_IDX = _i
        break
    elif _arg.startswith('--user='):
        _USER_ID = _arg.split('=', 1)[1]
        _USER_ARG_IDX = _i
        break

# 🆕 从 sys.argv 移除 --user 相关参数，避免干扰 main() 的参数解析
if _USER_ARG_IDX is not None:
    if sys.argv[_USER_ARG_IDX].startswith('--user='):
        del sys.argv[_USER_ARG_IDX]
    else:
        del sys.argv[_USER_ARG_IDX:_USER_ARG_IDX+2]

if _USER_ID:
    from tools.common import resolve_user_dir, resolve_outfits_dir, resolve_wardrobe_dir, set_thread_user
    _USER_DIR = resolve_user_dir(_USER_ID)
    # 🆕 从 registry 获取 gender 并设置线程上下文（使 load_all_clothing 等函数能自动路由）
    from tools.common import get_user_gender
    _USER_GENDER = get_user_gender(_USER_ID)
    set_thread_user(_USER_GENDER, _USER_ID)
    # 🆕 更新模块级 TAGS_DIR 指向用户目录
    TAGS_DIR = os.path.join(resolve_wardrobe_dir(_USER_ID), 'tags')
else:
    _USER_DIR = None
    TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')

STYLES_DIR = os.path.join(PROJ_DIR, 'styles/male')
DEFAULTS_CONFIG = os.path.join(PROJ_DIR, 'config', 'style_defaults.json')  # 旧兼容
DEFAULTS_CONFIG_MALE = os.path.join(PROJ_DIR, 'config', 'style_defaults_male.json')
DEFAULTS_CONFIG_FEMALE = os.path.join(PROJ_DIR, 'config', 'style_defaults_female.json')

# 女性默认 fallback（当配置文件不存在时使用）
FEMALE_DEFAULTS_FALLBACK = {
    'weather_rules': [
        {'temp_high_gte': 35, 'condition': '晴', 'suggest': ['WF-06', 'WF-19', 'WF-37'], 'reason': '酷热天气优先透气轻薄'},
        {'temp_high_between': [28, 34], 'condition': '晴', 'suggest': ['WF-01', 'WF-05', 'WF-08', 'WF-06'], 'reason': '适宜温度适合层次穿搭'},
        {'temp_high_between': [22, 27], 'suggest': ['WF-01', 'WF-05', 'WF-11', 'WF-36'], 'reason': '舒适温度适合多种风格'},
        {'temp_high_lte': 21, 'suggest': ['WF-12', 'WF-17', 'WF-34', 'WF-43'], 'reason': '降温适合外套+叠穿'},
        {'condition': '雨', 'suggest': ['WF-06', 'WF-11', 'WF-33'], 'reason': '雨天优先深色系、不易显脏'},
        {'condition': '阴', 'suggest': ['WF-01', 'WF-36', 'WF-05'], 'reason': '阴天适合灰调/暗色穿搭'},
    ],
    'occasion_rules': [
        {'occasion': '运动', 'suggest': ['WF-08', 'WF-38'], 'reason': '运动场景优先运动休闲'},
        {'occasion': '约会', 'suggest': ['WF-01', 'WF-05', 'WF-15', 'WF-40'], 'reason': '约会需要精致但不刻意'},
        {'occasion': '通勤', 'suggest': ['WF-06', 'WF-17', 'WF-34', 'WF-41'], 'reason': '通勤需要干净利落'},
        {'occasion': '度假', 'suggest': ['WF-37', 'WF-09', 'WF-20'], 'reason': '度假优先放松感'},
        {'occasion': '户外', 'suggest': ['WF-08', 'WF-33', 'WF-05'], 'reason': '户外优先功能性和耐脏'},
        {'occasion': '聚会', 'suggest': ['WF-31', 'WF-10', 'WF-39', 'WF-27'], 'reason': '聚会可以稍微有态度'},
        {'occasion': '居家', 'suggest': ['WF-08', 'WF-06', 'WF-16'], 'reason': '居家优先舒适'},
    ],
}

MALE_DEFAULTS_FALLBACK = {
    'weather_rules': [
        {'temp_high_gte': 35, 'condition': '晴', 'suggest': ['resort_vacation', 'clean_fit'], 'reason': '酷热优先透气轻薄'},
        {'temp_high_between': [28, 34], 'condition': '晴', 'suggest': ['japanese_city_boy', 'korean_minimal', 'clean_fit'], 'reason': '适宜温度适合层次穿搭'},
        {'temp_high_between': [22, 27], 'suggest': ['clean_fit', 'smart_casual', 'japanese_city_boy', 'korean_minimal'], 'reason': '舒适温度适合多种风格'},
        {'temp_high_lte': 21, 'suggest': ['smart_casual', 'streetwear', 'chinese_heritage'], 'reason': '降温适合外套+叠穿'},
        {'condition': '雨', 'suggest': ['clean_fit', 'smart_casual', 'streetwear'], 'reason': '雨天优先深色、不易显脏'},
        {'condition': '阴', 'suggest': ['japanese_city_boy', 'clean_fit', 'streetwear'], 'reason': '阴天适合灰调/暗色穿搭'},
    ],
    'occasion_rules': [
        {'occasion': '运动', 'suggest': ['athleisure_sport'], 'reason': '运动场景优先运动休闲'},
        {'occasion': '约会', 'suggest': ['smart_casual', 'korean_minimal', 'chinese_heritage'], 'reason': '约会需要精致但不刻意'},
        {'occasion': '通勤', 'suggest': ['clean_fit', 'smart_casual', 'korean_minimal'], 'reason': '通勤需要干净利落'},
        {'occasion': '度假', 'suggest': ['resort_vacation', 'japanese_city_boy'], 'reason': '度假优先放松感'},
        {'occasion': '户外', 'suggest': ['athleisure_sport', 'streetwear'], 'reason': '户外优先功能性和耐脏'},
        {'occasion': '聚会', 'suggest': ['smart_casual', 'streetwear', 'chinese_heritage'], 'reason': '聚会可以稍微有态度'},
        {'occasion': '居家', 'suggest': ['athleisure_sport', 'clean_fit'], 'reason': '居家优先舒适'},
    ],
}
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')

SAT_ORDER = ['无彩色', '低饱和', '中饱和', '高饱和']
LIGHT_ORDER = ['低明度', '中明度', '高明度']

def _safe_index(order_list, value, default=1):
    """安全查找索引，自动处理复合值（如'中饱和/无彩色'取第一个）"""
    v = str(value).split('/')[0] if value else ''
    return order_list.index(v) if v in order_list else default

# ============================================================
# 1. 数据加载
# ============================================================

def load_style(style_id, gender=None):
    """加载风格指纹 JSON（自动检测性别路径）"""
    # 优先使用 common.load_style_fingerprint（支持 male/female 路径）
    try:
        from tools.common import load_style_fingerprint
        fp = load_style_fingerprint(style_id, gender)
        if fp:
            return fp
    except Exception:
        pass
    # 兜底: 旧路径
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_all_styles(gender=None, recommend_only=False):
    """加载所有风格（自动检测性别路径）

    Args:
        gender: 'male' / 'female' / None(自动检测)
        recommend_only: True 时过滤掉 knowledge-only 和 bold 风格（仅返回 core + explore）
    """
    # 优先使用 common.load_style_fingerprint 的方式扫描
    try:
        from tools.common import get_thread_user, load_style_fingerprint
        g, uid = get_thread_user()
        if not gender:
            gender = g
    except Exception:
        pass
    styles = {}
    if gender == 'female':
        import os as _os
        women_dir = _os.path.join(PROJ_DIR, 'styles/female')
        if _os.path.isdir(women_dir):
            for d in sorted(_os.listdir(women_dir)):
                if d.startswith('.') or d.startswith('_'): continue
                fp_path = _os.path.join(women_dir, d, 'fingerprint.json')
                if _os.path.exists(fp_path):
                    try:
                        with open(fp_path) as f:
                            s = json.load(f)
                        # 推荐模式：跳过 knowledge-only
                        if recommend_only and s.get('tier') == 'knowledge-only':
                            continue
                        styles[s.get('style_id', d)] = s
                    except Exception:
                        pass
    else:
        male_dir = os.path.join(PROJ_DIR, 'styles/male')
        if os.path.isdir(male_dir):
            for fpath in sorted(glob.glob(os.path.join(male_dir, '*.json'))):
                if fpath.endswith('README.json'):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        s = json.load(f)
                    if recommend_only and s.get('tier') == 'knowledge-only':
                        continue
                    styles[s.get('style_id', '')] = s
                except Exception:
                    pass
    if not styles:
        # 最终兜底: 旧路径
        for fpath in sorted(glob.glob(os.path.join(STYLES_DIR, '*.json'))):
            if fpath.endswith('README.json'):
                continue
            with open(fpath, 'r', encoding='utf-8') as f:
                s = json.load(f)
                styles[s['style_id']] = s
    return styles

def load_clothing(clothing_id):
    """加载单件衣服标签（自动路由到当前用户目录）"""
    # 优先使用线程上下文路径
    try:
        from tools.common import get_thread_user, resolve_tags_dir
        gender, uid = get_thread_user()
        if uid and uid != 'default':
            tags_dir = resolve_tags_dir(gender, uid)
            path = os.path.join(tags_dir, f'{clothing_id}.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    except Exception:
        pass
    # 兜底: 模块级常量
    path = os.path.join(TAGS_DIR, f'{clothing_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

from tools.common import load_all_clothing


def get_tag_mtime(clothing_id):
    """获取标签文件的最后修改时间（自动路由到当前用户目录）"""
    # 优先使用线程上下文路径
    try:
        from tools.common import get_thread_user, resolve_tags_dir
        gender, uid = get_thread_user()
        if uid and uid != 'default':
            tags_dir = resolve_tags_dir(gender, uid)
            path = os.path.join(tags_dir, f'{clothing_id}.json')
            if os.path.exists(path):
                return os.path.getmtime(path)
    except Exception:
        pass
    # 兜底
    path = os.path.join(TAGS_DIR, f'{clothing_id}.json')
    if os.path.exists(path):
        return os.path.getmtime(path)
    return 0


from tools.common import load_score_cache


def save_score_cache(cache):
    """保存评分缓存（自动路由到当前用户目录）"""
    cache['_meta'] = cache.get('_meta', {})
    cache['_meta']['last_rebuild'] = time.strftime('%Y-%m-%d %H:%M:%S')
    cache['_meta']['total_entries'] = sum(1 for k in cache if not k.startswith('_'))
    # 使用线程上下文确定用户目录，兜底到模块级常量
    cache_file = CACHE_FILE
    try:
        from tools.common import get_thread_user, resolve_tags_dir
        gender, uid = get_thread_user()
        if uid and uid != 'default':
            tags_dir = resolve_tags_dir(gender, uid)
            cache_file = os.path.join(tags_dir, 'SCORE_CACHE.json')
    except Exception:
        pass
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def is_cache_valid(cid, style_id, cache=None):
    """
    检查缓存是否仍然有效。
    比较标签文件的 mtime 与缓存中的 _tag_mtime。
    如果标签被修改过 → 缓存失效 → 需要重新计算。
    """
    if cache is None:
        cache = load_score_cache()

    item_cache = cache.get(cid, {})
    if style_id not in item_cache:
        return False  # 从未缓存过

    cached_mtime = item_cache[style_id].get('_tag_mtime', 0)
    current_mtime = get_tag_mtime(cid)

    if current_mtime == 0:
        return False  # 标签文件不存在

    return cached_mtime >= current_mtime


def get_cached_or_compute(cid, style_id, cache=None):
    """
    智能获取评分：优先用缓存（若标签未修改），否则实时计算并更新缓存。
    这是所有需要单品-风格评分的代码应该调用的唯一入口。

    返回: (score, details_dict)
    """
    if cache is None:
        cache = load_score_cache()

    # 缓存命中且标签未修改 → 直接返回
    if is_cache_valid(cid, style_id, cache):
        entry = cache[cid][style_id]
        score = entry.get('score', 0)
        details = {
            'raw_score': entry.get('raw_score', 0),
            'breakdown': entry.get('breakdown', {}),
            'passed': entry.get('passed', False),
            '_from_cache': True,
        }
        return score, details

    # 缓存失效 → 实时计算
    score, details = compute_compatibility(cid, style_id)

    # 更新缓存
    if cid not in cache:
        cache[cid] = {}
    cache[cid][style_id] = {
        'score': score,
        'raw_score': details.get('raw_score', 0),
        'breakdown': details.get('breakdown', {}),
        'passed': details.get('passed', False),
        '_tag_mtime': get_tag_mtime(cid),
        '_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    details['_from_cache'] = False

    return score, details


def rebuild_all_cache():
    """全量重建缓存（标签批量修改后调用）"""
    all_clothes = load_all_clothing()
    all_styles = load_all_styles()
    cache = {}

    total = len(all_clothes) * len(all_styles)
    done = 0
    for cid in sorted(all_clothes.keys()):
        cache[cid] = {}
        tag_mtime = get_tag_mtime(cid)
        for sid in sorted(all_styles.keys()):
            score, details = compute_compatibility(cid, sid)
            cache[cid][sid] = {
                'score': score,
                'raw_score': details.get('raw_score', 0),
                'breakdown': details.get('breakdown', {}),
                'passed': details.get('passed', False),
                '_tag_mtime': tag_mtime,
                '_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            done += 1

    save_score_cache(cache)
    return total

def get_nested(d, field_path):
    """获取嵌套字段值 d['a']['b'] → 'a.b'"""
    keys = field_path.split('.')
    val = d
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val

def as_list(v):
    """确保值是列表"""
    if isinstance(v, list):
        return v
    return [v]

# ============================================================
# 2. 评分函数
# ============================================================

def check_hard_constraints(clothing, style):
    """硬约束检查，返回 (passed: bool, violations: list[str])"""
    violations = []
    for c in style.get('hard_constraints', []):
        fv = get_nested(clothing, c['field'])
        op = c['operator']
        cv = c['value']

        if op == 'not_in':
            if fv in cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} 在禁止列表'))
        elif op == 'in':
            if fv not in cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} 不在允许列表'))
        elif op == 'eq':
            if fv != cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} ≠ {cv}'))
        elif op == 'neq':
            if fv == cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} 不应等于 {cv}'))
        elif op == 'lte':
            if isinstance(fv, (int, float)) and fv > cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} > {cv}'))
        elif op == 'gte':
            if isinstance(fv, (int, float)) and fv < cv:
                violations.append(c.get('reason', f'{c["field"]}={fv} < {cv}'))
    return (len(violations) == 0, violations)


def score_soft_constraints(clothing, style):
    """软约束评分，每个匹配项累加 weight"""
    total = 0
    for c in style.get('soft_constraints', []):
        fv = get_nested(clothing, c['field'])
        if fv is None:
            continue
        op = c.get('operator', 'eq')
        cv = c['value']

        if op == 'in':
            if fv in cv:
                total += c.get('weight', 0)
        elif op == 'eq':
            if fv == cv:
                total += c.get('weight', 0)
        elif op == 'neq':
            if fv != cv:
                total += c.get('weight', 0)
        elif op == 'lte':
            if isinstance(fv, (int, float)) and fv <= cv:
                total += c.get('weight', 0)
        elif op == 'gte':
            if isinstance(fv, (int, float)) and fv >= cv:
                total += c.get('weight', 0)
        elif op == 'not_in':
            if fv not in cv:
                total += c.get('weight', 0)
    return total


def score_color_compatibility(clothing, style):
    """颜色兼容性评分"""
    color = clothing.get('color', {})
    rules = style['fingerprint'].get('color_rules', {})
    total = 0

    # 色相族匹配
    if color.get('hue_family') in rules.get('allowed_hue_families', []):
        total += 5

    # 精确色相匹配（权重高）
    if color.get('hue_name') in rules.get('allowed_hues', []):
        total += 8

    # 饱和度检查
    if 'max_saturation' in rules:
        sat_idx = _safe_index(SAT_ORDER, color.get('saturation', '中饱和'))
        max_idx = SAT_ORDER.index(rules['max_saturation'])
        if sat_idx <= max_idx:
            total += 3

    # 明度检查
    if 'min_lightness' in rules:
        lt_idx = _safe_index(LIGHT_ORDER, color.get('lightness', '中明度'))
        min_idx = LIGHT_ORDER.index(rules['min_lightness'])
        if lt_idx >= min_idx:
            total += 2
    if 'max_lightness' in rules:
        lt_idx = _safe_index(LIGHT_ORDER, color.get('lightness', '中明度'))
        max_idx = LIGHT_ORDER.index(rules['max_lightness'])
        if lt_idx <= max_idx:
            total += 2

    # 衬白皮加分
    if color.get('friendly_for_pale_skin'):
        total += 2

    return total


def score_key_items(clothing, style):
    """关键单品加分，取最大匹配 bonus（不叠加）"""
    max_bonus = 0
    cat = clothing.get('category_code', '')
    color = clothing.get('color', {})
    fabric = clothing.get('fabric', {})
    silhouette = clothing.get('silhouette', {})
    pattern = clothing.get('pattern', {})

    for ki in style.get('key_items', []):
        if cat != ki.get('category_code'):
            continue

        matches = True
        if 'fit' in ki:
            if silhouette.get('fit') not in as_list(ki['fit']):
                matches = False
        if 'pattern' in ki:
            if pattern.get('type') not in as_list(ki['pattern']):
                matches = False
        if 'hue' in ki:
            if color.get('hue_name') not in as_list(ki['hue']):
                matches = False
        if 'fabric' in ki:
            if fabric.get('primary') not in as_list(ki['fabric']):
                matches = False

        if matches:
            max_bonus = max(max_bonus, ki.get('bonus', 0))

    return max_bonus


# ═══ 身形修饰桥接映射 ═══
# 衣橱标签使用风格感受词（休闲/优雅/运动…），但 body_modifier_bonus 用身形效果词（显腰线/拉长腿部…）
# 这个映射将风格感受翻译为身形效果，让两套词汇体系能互通
_STYLE_TO_BODY_EFFECT = {
    '修身': ['显腰线'],
    '收腰': ['显腰线'],
    '高腰': ['显腰线', '拉长腿部'],
    '法式': ['显腰线', '颜色显白'],
    '优雅': ['显腰线', '颜色显白', '遮盖臀胯'],
    '通勤': ['拉长腿部', '遮盖臀胯'],
    '直筒': ['拉长腿部'],
    '阔腿': ['拉长腿部', '遮盖臀胯'],
    'A字': ['遮盖臀胯', '显腰线'],
    '宽松': ['遮盖臀胯'],
    '慵懒': ['遮盖臀胯'],
    '复古': ['颜色显白'],
    '简约': ['颜色显白'],
    '经典': ['颜色显白', '显腰线'],
    '学院风': ['修饰肩部', '颜色显白'],
    '街头': ['修饰肩部'],
    '街头风': ['修饰肩部'],
    '运动': ['拉长腿部'],
    '运动风': ['拉长腿部'],
    '运动休闲': ['拉长腿部'],
    '度假风': ['颜色显白', '遮盖臀胯'],
    '户外': ['遮盖臀胯'],
    '户外风': ['遮盖臀胯'],
    '可爱': ['颜色显白'],
    '甜酷': ['修饰肩部', '拉长腿部'],
    '清新': ['颜色显白'],
    '商务通勤': ['拉长腿部', '遮盖臀胯', '显腰线'],
    '居家': ['遮盖臀胯'],
    '居家休闲': ['遮盖臀胯'],
    '潮流': ['修饰肩部'],
    '休闲': ['遮盖臀胯'],
    '休闲风': ['遮盖臀胯'],
    '基础款': ['颜色显白'],
    '时尚': ['拉长腿部', '显腰线'],
    '网球鞋': ['拉长腿部'],
    '童趣': ['颜色显白'],
    '紧身': ['显腰线'],
    '复古运动': ['拉长腿部', '颜色显白'],
    '复古风': ['颜色显白'],
    '随性': ['遮盖臀胯'],
}


def score_body_modifier(clothing, style):
    """身形修饰加分 — 🆕 桥接风格感受 → 身形效果"""
    total = 0
    bonuses = style.get('body_modifier_bonus', {})
    modifiers = clothing.get('style_modifiers', [])

    # 🆕 直接匹配（适用于已用身形效果词标注的衣橱）
    for modifier in modifiers:
        total += bonuses.get(modifier, 0)

    # 🆕 桥接匹配：将风格感受词翻译为身形效果
    body_effects_matched = set()
    for modifier in modifiers:
        effects = _STYLE_TO_BODY_EFFECT.get(modifier, [])
        for effect in effects:
            if effect not in body_effects_matched:
                bonus = bonuses.get(effect, 0)
                if bonus:
                    body_effects_matched.add(effect)
                    total += bonus

    return total


# ═══ 🆕 场景匹配 ═══
# 风格 → 典型场景映射（从 encyclopedia 推断）
_STYLE_TYPICAL_OCCASIONS = {
    'WF-01': ['约会', '日常休闲', '职场'],  # 法式慵懒
    'WF-02': ['约会', '日常休闲', '聚会'],  # 韩系少女
    'WF-03': ['日常休闲', '居家', '户外'],  # 日系森系
    'WF-04': ['聚会', '约会', '度假'],    # 新中式
    'WF-05': ['日常休闲', '户外', '运动'],  # 美式休闲
    'WF-06': ['职场', '日常休闲', '居家'],  # 极简
    'WF-07': ['职场', '日常休闲'],         # 学院风
    'WF-08': ['运动', '户外', '日常休闲'],  # 运动休闲
    'WF-09': ['度假', '户外', '聚会'],     # 波西米亚
    'WF-10': ['聚会', '约会', '日常休闲'],  # Y2K
    'WF-11': ['职场', '日常休闲', '约会'],  # 都市通勤
    'WF-12': ['日常休闲', '职场'],         # 暗黑学院
}

# 通用推断：从风格描述关键词推断典型场景
_OCCASION_KEYWORDS = {
    '运动': ['运动', '健身', '网球', '跑步', '户外运动', '机能'],
    '约会': ['约会', '浪漫', '少女', '甜美', '性感', '精致', '晚宴'],
    '职场': ['通勤', '职场', '办公', '商务', '正式', '极简', '干净'],
    '日常休闲': ['休闲', '日常', '随性', '慵懒', '舒适', '基础'],
    '度假': ['度假', '旅行', '海滩', '逃离', '田园', '海岸'],
    '聚会': ['聚会', '派对', '夜店', '街头', '态度', '华丽', '大胆'],
    '户外': ['户外', '自然', '森林', '花园', '草地', '野餐'],
    '居家': ['居家', '慢生活', '烘焙', '手工', '柔软'],
}


def _infer_style_occasions(style):
    """从风格指纹推断典型场景"""
    sid = style.get('style_id', '')
    if sid in _STYLE_TYPICAL_OCCASIONS:
        return _STYLE_TYPICAL_OCCASIONS[sid]

    # 从描述和名称推断
    desc = style.get('description', '')
    name = style.get('name_zh', '')
    text = desc + ' ' + name

    occasions = []
    for occ, keywords in _OCCASION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            occasions.append(occ)

    return occasions[:3] if occasions else ['日常休闲']


def score_occasion_match(clothing, style):
    """🆕 场景匹配：衣橱单品适用场景 vs 风格典型场景"""
    clothing_occasions = clothing.get('occasions', [])
    if not clothing_occasions:
        return 0

    style_occasions = _infer_style_occasions(style)
    if not style_occasions:
        return 0

    # 计算交集
    matches = set(clothing_occasions) & set(style_occasions)
    if not matches:
        return 0

    # 每个匹配场景 +3 分，最多 9 分
    return min(len(matches) * 3, 9)


# ═══ 🆕 身形档案匹配 ═══
# body_modifier_bonus 对 nan 的启发式匹配
_BODY_PROFILE = None  # 懒加载

def _load_body_profile():
    """加载当前用户身形档案"""
    global _BODY_PROFILE
    if _BODY_PROFILE is not None:
        return _BODY_PROFILE
    try:
        from tools.common import get_thread_user, resolve_user_dir
        import os, json
        _, uid = get_thread_user()
        if uid and uid != 'default':
            profile_path = os.path.join(resolve_user_dir(uid), 'profile.json')
            if os.path.exists(profile_path):
                with open(profile_path) as f:
                    p = json.load(f)
                _BODY_PROFILE = {
                    'height': int(p.get('body', {}).get('height', 0) or 0),
                    'shape': p.get('body', {}).get('shape', ''),
                    'skin_tone': p.get('body', {}).get('skin_tone', ''),
                }
                return _BODY_PROFILE
    except Exception:
        pass
    _BODY_PROFILE = {}
    return _BODY_PROFILE


def score_profile_match(style):
    """🆕 身形档案与风格的身形修饰匹配度 — 体型×风格适配"""
    profile = _load_body_profile()
    if not profile:
        return 0

    bonuses = style.get('body_modifier_bonus', {})
    if not bonuses:
        return 0

    total = 0
    shape = profile.get('shape', '')
    skin = profile.get('skin_tone', '')
    height = profile.get('height', 0)

    # 沙漏型 → 需要显腰线的风格加分
    if '沙漏' in shape and '显腰线' in bonuses:
        total += 3
    # 偏瘦高 → 拉长腿部的风格不用（已经够高了），但遮盖臀胯有用
    if height >= 170 and '拉长腿部' in bonuses:
        total += 0  # 已经高挑，拉长腿部不是刚需
    elif height < 165 and '拉长腿部' in bonuses:
        total += 3
    # 小麦肤色 → 颜色显白的风格加分
    if skin in ('小麦', '偏黄', '暖调') and '颜色显白' in bonuses:
        total += 3

    return min(total, 6)


# ═══ 🆕 面料季节匹配 ═══
_SEASON_WEIGHT = {'春': 3, '夏': 3, '秋': 3, '冬': 3}

def score_seasonality_match(clothing, style):
    """🆕 面料季节性与风格季节性的匹配"""
    clothing_seasons = set(clothing.get('fabric', {}).get('seasonality', []))
    if not clothing_seasons:
        return 0

    # 从面料偏好推断风格季节
    fabric_prefs = style.get('fingerprint', {}).get('fabric', {}).get('preferred', [])
    style_seasons = set()
    season_fabric_map = {
        '春': ['棉', '亚麻', '薄纱', '蕾丝', '真丝', '雪纺'],
        '夏': ['亚麻', '棉', '薄纱', '蕾丝', '真丝', '雪纺', '钩针'],
        '秋': ['羊毛', '羊绒', '针织', '灯芯绒', '皮质', '粗花呢', '毛呢'],
        '冬': ['羊绒', '羊毛', '毛呢', '天鹅绒', '丝绒', '粗花呢', '皮质'],
    }

    for season, fabrics in season_fabric_map.items():
        if any(f in fabric_prefs for f in fabrics):
            style_seasons.add(season)

    if not style_seasons:
        return 0

    match = clothing_seasons & style_seasons
    return min(len(match) * 2, 6)


def compute_compatibility(clothing_id, style_id):
    """
    主匹配函数 🆕 七维评分引擎
    硬约束 → 颜色(22) + 软约束(20) + 关键单品(15) + 身形(13)
           + 场景(9) + 身形档案(6) + 面料季节(6)
    原始分 max ≈ 91，归一化到 0~100
    """
    clothing = load_clothing(clothing_id)
    style = load_style(style_id)

    if not clothing or not style:
        return (0, {'error': 'clothing or style not found'})

    # 1. 硬约束
    passed, violations = check_hard_constraints(clothing, style)
    if not passed:
        return (0, {'passed': False, 'violations': violations})

    # 2. 软约束
    soft = score_soft_constraints(clothing, style)

    # 3. 颜色
    color_score = score_color_compatibility(clothing, style)

    # 4. 关键单品 (🆕 收紧：品类不对直接0分)
    key_bonus = score_key_items(clothing, style)

    # 5. 身形修饰 (🆕 桥接：风格感受→身形效果)
    body_bonus = score_body_modifier(clothing, style)

    # 6. 🆕 场景匹配
    occasion_score = score_occasion_match(clothing, style)

    # 7. 🆕 身形档案 × 风格适配
    profile_score = score_profile_match(style)

    # 8. 🆕 面料季节匹配
    season_score = score_seasonality_match(clothing, style)

    raw = soft + color_score + key_bonus + body_bonus + occasion_score + profile_score + season_score
    max_possible = 91
    normalized = min(round(raw / max_possible * 100), 100)

    return (normalized, {
        'raw_score': raw,
        'breakdown': {
            'soft_constraints': soft,
            'color_compatibility': color_score,
            'key_item_bonus': key_bonus,
            'body_modifier': body_bonus,
            'occasion_match': occasion_score,
            'profile_match': profile_score,
            'season_match': season_score,
        },
        'passed': True,
    })


def rank_items_for_style(style_id, top_n=None, min_score=20):
    """全衣柜按某风格排名（自动检测标签变更，过期缓存实时重算）"""
    all_clothes = load_all_clothing()
    cache = load_score_cache()
    results = []
    cache_updated = False

    for cid in sorted(all_clothes.keys()):
        score, details = get_cached_or_compute(cid, style_id, cache)
        if not details.get('_from_cache', True):
            cache_updated = True
        if score >= min_score:
            item = all_clothes[cid]
            results.append({
                'clothing_id': cid,
                'category': item.get('category', ''),
                'color': item['color']['hue_name'],
                'brand': item.get('brand', {}).get('name', '?'),
                'score': score,
                'breakdown': details.get('breakdown', {}),
            })

    # 如果有标签变更导致重新计算，保存更新后的缓存
    if cache_updated:
        save_score_cache(cache)

    results.sort(key=lambda x: -x['score'])
    if top_n:
        return results[:top_n]
    return results


def get_candidates_by_category(style_id, category_code, min_score=30):
    """按品类筛选候选单品（自动检测标签变更）"""
    all_clothes = load_all_clothing()
    cache = load_score_cache()
    results = []

    for cid, item in all_clothes.items():
        if item.get('category_code') != category_code:
            continue
        score, details = get_cached_or_compute(cid, style_id, cache)
        if score >= min_score:
            results.append({
                'clothing_id': cid,
                'color': item['color']['hue_name'],
                'brand': item.get('brand', {}).get('name', '?'),
                'score': score,
            })

    results.sort(key=lambda x: -x['score'])
    return results


# ============================================================
# 3. 自动风格推荐
# ============================================================

def load_defaults(gender=None):
    """加载天气-场合-风格默认映射。gender='male'/'female'/None → 自动从线程上下文获取"""
    # 自动检测性别
    if not gender:
        try:
            from tools.common import get_thread_user as _gtu
            _g, _uid = _gtu()
            if _g:
                gender = _g
        except Exception:
            pass
    # 选择配置文件
    if gender == 'female':
        cfg_path = DEFAULTS_CONFIG_FEMALE
        fallback = FEMALE_DEFAULTS_FALLBACK
    elif gender == 'male':
        cfg_path = DEFAULTS_CONFIG_MALE
        fallback = MALE_DEFAULTS_FALLBACK
    else:
        cfg_path = DEFAULTS_CONFIG
        fallback = MALE_DEFAULTS_FALLBACK

    if not os.path.exists(cfg_path):
        return fallback
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def auto_suggest_style(temp_high, condition='晴', occasion='日常', gender=None):
    """天气+场合自动推荐风格，返回 [(style_id, style_name, reason), ...]
    gender: 'male'/'female'/None → 自动从线程上下文获取
    """
    defaults = load_defaults(gender=gender)
    styles = load_all_styles(gender=gender, recommend_only=True)
    candidates = {}

    # 天气规则
    for rule in defaults.get('weather_rules', []):
        matched = False
        if 'temp_high_gte' in rule and temp_high >= rule['temp_high_gte']:
            if rule.get('condition', condition) == condition:
                matched = True
        elif 'temp_high_between' in rule:
            lo, hi = rule['temp_high_between']
            if lo <= temp_high <= hi:
                matched = True
        elif 'temp_high_lte' in rule and temp_high <= rule['temp_high_lte']:
            matched = True

        if matched:
            for sid in rule.get('suggest', []):
                if sid not in candidates:
                    candidates[sid] = rule['reason']

    # 场合规则
    for rule in defaults.get('occasion_rules', []):
        if rule['occasion'] in occasion or occasion in rule['occasion']:
            for sid in rule.get('suggest', []):
                if sid not in candidates:
                    candidates[sid] = rule['reason']

    # 无匹配时默认（按性别）
    if not candidates:
        if gender == 'female':
            candidates = {'WF-01': '默认日常风格', 'WF-05': '默认日常风格', 'WF-06': '默认日常风格'}
        else:
            candidates = {'clean_fit': '默认日常风格', 'japanese_city_boy': '默认日常风格'}

    # 格式化为结果
    results = []
    for sid, reason in candidates.items():
        s = styles.get(sid, {})
        results.append({
            'style_id': sid,
            'name_zh': s.get('name_zh', sid),
            'reason': reason,
        })
    return results


# ============================================================
# 4. 命令行接口
# ============================================================

def print_ranking(style_id, results):
    """格式化打印排名"""
    style = load_style(style_id)
    name = style['name_zh'] if style else style_id

    print(f"\n{'='*60}")
    print(f"🎯 {name} ({style_id})")
    if style:
        print(f"   {style['description'][:80]}...")
    print(f"{'='*60}")

    # 分数分布
    if results:
        scores = [r['score'] for r in results]
        print(f"📊 {len(results)} 件 | 最高{max(scores)}分 | 最低{min(scores)}分 | 平均{sum(scores)//len(scores)}分")
        print()

    current_cat = None
    for r in results:
        cat = r['category']
        if cat != current_cat:
            current_cat = cat
            print(f"  ── {cat} ──")
        bar = '█' * (r['score'] // 5)
        bd = r.get('breakdown', {})
        detail = f"soft={bd.get('soft_constraints',0)} col={bd.get('color_compatibility',0)} key={bd.get('key_item_bonus',0)} body={bd.get('body_modifier',0)}"
        print(f"  {r['score']:3d} {bar:20s} {r['clothing_id']} | {r['color']} | {r['brand']} | {detail}")


def main():
    if '--rebuild' in sys.argv:
        print(f"🔄 重建评分缓存（76件 × 8风格 = 608组）...")
        total = rebuild_all_cache()
        print(f"✅ 缓存重建完成: {total} 组评分")
        return

    if '--all' in sys.argv:
        styles = load_all_styles()
        for sid in sorted(styles.keys()):
            results = rank_items_for_style(sid, top_n=15)
            print_ranking(sid, results)

    elif '--auto' in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith('--')]
        if len(args) >= 1:
            temp = int(args[0])
            cond = args[1] if len(args) > 1 else '晴'
            occasion = args[2] if len(args) > 2 else '日常'
        else:
            temp, cond, occasion = 30, '晴', '日常'

        print(f"🌤 天气: {temp}°C {cond} | 📋 场合: {occasion}")
        suggestions = auto_suggest_style(temp, cond, occasion)
        print(f"\n推荐风格:")
        for s in suggestions:
            print(f"  🎯 {s['name_zh']} ({s['style_id']}) — {s['reason']}")

        # 对推荐风格做快速排名
        if suggestions:
            sid = suggestions[0]['style_id']
            candidates = rank_items_for_style(sid, top_n=20)
            print_ranking(sid, candidates)

    elif len(sys.argv) >= 2:
        style_id = sys.argv[1]
        cat_code = sys.argv[2] if len(sys.argv) > 2 else None

        if cat_code:
            candidates = get_candidates_by_category(style_id, cat_code)
            style = load_style(style_id)
            name = style['name_zh'] if style else style_id
            print(f"\n🎯 {name} → {cat_code} 候选")
            for c in candidates:
                print(f"  {c['score']:3d}分 | {c['clothing_id']} | {c['color']} | {c['brand']}")
        else:
            results = rank_items_for_style(style_id)
            print_ranking(style_id, results)

    else:
        print("用法:")
        print("  python3 tools/style_matcher.py <style_id>              # 某风格全品类排名")
        print("  python3 tools/style_matcher.py <style_id> <cat_code>   # 某风格某品类候选")
        print("  python3 tools/style_matcher.py --all                   # 8个风格全部排名")
        print("  python3 tools/style_matcher.py --auto <温度> <天气> <场合>  # 自动推荐")
        print("  python3 tools/style_matcher.py --rebuild               # 重建评分缓存")
        print()
        print("风格ID: " + ', '.join(load_all_styles().keys()))
        print()
        print("💡 提示：修改 wardrobe/tags/{ID}.json 后缓存自动失效，无需手动 --rebuild")
        print("   只有批量修改标签后才需要 --rebuild 一次性刷新全部缓存")


if __name__ == '__main__':
    main()
