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

import os, sys, json, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
DEFAULTS_CONFIG = os.path.join(PROJ_DIR, 'config', 'style_defaults.json')

SAT_ORDER = ['低饱和', '中饱和', '高饱和']
LIGHT_ORDER = ['低明度', '中明度', '高明度']

# ============================================================
# 1. 数据加载
# ============================================================

def load_style(style_id):
    """加载风格指纹 JSON"""
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_all_styles():
    """加载所有风格"""
    styles = {}
    for fpath in sorted(glob.glob(os.path.join(STYLES_DIR, '*.json'))):
        if fpath.endswith('README.json'):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            s = json.load(f)
            styles[s['style_id']] = s
    return styles

def load_clothing(clothing_id):
    """加载单件衣服标签"""
    path = os.path.join(TAGS_DIR, f'{clothing_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_all_clothing():
    """加载所有衣服标签，返回 {clothing_id: tag_dict}"""
    items = {}
    for fpath in sorted(glob.glob(os.path.join(TAGS_DIR, '*.json'))):
        if os.path.basename(fpath).startswith('SCORE_CACHE'):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            item = json.load(f)
            items[item['clothing_id']] = item
    return items

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
        sat_idx = SAT_ORDER.index(color.get('saturation', '中饱和'))
        max_idx = SAT_ORDER.index(rules['max_saturation'])
        if sat_idx <= max_idx:
            total += 3

    # 明度检查
    if 'min_lightness' in rules:
        lt_idx = LIGHT_ORDER.index(color.get('lightness', '中明度'))
        min_idx = LIGHT_ORDER.index(rules['min_lightness'])
        if lt_idx >= min_idx:
            total += 2
    if 'max_lightness' in rules:
        lt_idx = LIGHT_ORDER.index(color.get('lightness', '中明度'))
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


def score_body_modifier(clothing, style):
    """身形修饰加分"""
    total = 0
    bonuses = style.get('body_modifier_bonus', {})
    for modifier in clothing.get('style_modifiers', []):
        total += bonuses.get(modifier, 0)
    return total


def compute_compatibility(clothing_id, style_id):
    """
    主匹配函数
    流程：硬约束 → 颜色(25) + 软约束(~30) + 关键单品(0~20) + 身形(0~13)
    原始分 max ≈ 88，归一化到 0~100
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

    # 4. 关键单品
    key_bonus = score_key_items(clothing, style)

    # 5. 身形修饰
    body_bonus = score_body_modifier(clothing, style)

    raw = soft + color_score + key_bonus + body_bonus
    max_possible = 88
    normalized = min(round(raw / max_possible * 100), 100)

    return (normalized, {
        'raw_score': raw,
        'breakdown': {
            'soft_constraints': soft,
            'color_compatibility': color_score,
            'key_item_bonus': key_bonus,
            'body_modifier': body_bonus,
        },
        'passed': True,
    })


def rank_items_for_style(style_id, top_n=None, min_score=20):
    """全衣柜按某风格排名"""
    all_clothes = load_all_clothing()
    results = []

    for cid in sorted(all_clothes.keys()):
        score, details = compute_compatibility(cid, style_id)
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

    results.sort(key=lambda x: -x['score'])
    if top_n:
        return results[:top_n]
    return results


def get_candidates_by_category(style_id, category_code, min_score=30):
    """按品类筛选候选单品"""
    all_clothes = load_all_clothing()
    results = []

    for cid, item in all_clothes.items():
        if item.get('category_code') != category_code:
            continue
        score, details = compute_compatibility(cid, style_id)
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

def load_defaults():
    """加载天气-场合-风格默认映射"""
    if not os.path.exists(DEFAULTS_CONFIG):
        # 内置默认规则
        return {
            'weather_rules': [
                {'temp_high_gte': 35, 'condition': '晴', 'suggest': ['resort_vacation', 'clean_fit'], 'reason': '酷热优先透气轻薄'},
                {'temp_high_between': [28, 34], 'condition': '晴', 'suggest': ['japanese_city_boy', 'korean_minimal', 'clean_fit'], 'reason': '适宜温度适合层次穿搭'},
                {'temp_high_between': [22, 27], 'suggest': ['clean_fit', 'smart_casual', 'japanese_city_boy'], 'reason': '舒适温度适合多种风格'},
                {'temp_high_lte': 21, 'suggest': ['smart_casual', 'streetwear', 'chinese_heritage'], 'reason': '降温适合外套+叠穿'},
                {'condition': '雨', 'suggest': ['clean_fit', 'smart_casual'], 'reason': '雨天优先深色、不易显脏'},
            ],
            'occasion_rules': [
                {'occasion': '运动', 'suggest': ['athleisure_sport'], 'reason': '运动场景优先运动休闲'},
                {'occasion': '约会', 'suggest': ['smart_casual', 'korean_minimal', 'chinese_heritage'], 'reason': '约会需要精致但不刻意'},
                {'occasion': '通勤', 'suggest': ['clean_fit', 'smart_casual', 'korean_minimal'], 'reason': '通勤需要干净利落'},
                {'occasion': '度假', 'suggest': ['resort_vacation'], 'reason': '度假优先放松感'},
                {'occasion': '户外', 'suggest': ['athleisure_sport', 'streetwear'], 'reason': '户外优先功能性和耐脏'},
            ],
        }
    with open(DEFAULTS_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)


def auto_suggest_style(temp_high, condition='晴', occasion='日常'):
    """天气+场合自动推荐风格，返回 [(style_id, style_name, reason), ...]"""
    defaults = load_defaults()
    styles = load_all_styles()
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

    # 无匹配时默认
    if not candidates:
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
        print()
        print("风格ID: " + ', '.join(load_all_styles().keys()))


if __name__ == '__main__':
    main()
