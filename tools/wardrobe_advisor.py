#!/usr/bin/env python3
"""
衣橱智能顾问 — 品类分析 / 颜色平衡 / 利用率追踪 / 购买建议 / 月度穿搭报告

用法:
  python3 tools/wardrobe_advisor.py --report     衣橱完整分析报告
  python3 tools/wardrobe_advisor.py --monthly    月度穿搭报告（基于历史穿搭记录）
  python3 tools/wardrobe_advisor.py --summary     衣橱简要统计概览
  python3 tools/wardrobe_advisor.py --json        JSON 导出

  --save  附带参数可将报告保存到项目根目录 .txt 文件
"""

import os, sys, json, glob, re, time
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
STATE_FILE = os.path.join(PROJ_DIR, 'config', 'style_lab_state.json')
SNAPSHOT_DIR = os.path.join(PROJ_DIR, 'config')

# ============================================================
# 常量
# ============================================================

IDEAL_RANGES = {
    'TS': (5, 7), 'LS': (3, 4), 'SHIRT': (3, 4), 'TANK': (2, 3),
    'JK': (5, 7), 'PT': (4, 5), 'SH': (3, 4), 'SHOE': (6, 8),
    'BAG': (2, 3), 'HAT': (2, 3), 'SOCK': (3, 4), 'SUN': (1, 2), 'ACC': (2, 3),
}

CATEGORY_NAMES = {
    'TS': 'T恤/短袖', 'LS': '长袖上衣', 'SHIRT': '衬衫', 'TANK': '背心',
    'JK': '外套/夹克', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
    'BAG': '包', 'HAT': '帽子', 'SOCK': '袜子', 'SUN': '太阳镜', 'ACC': '配饰',
}

SHOE_SUBTYPES = {
    '正装鞋/乐福鞋/德比鞋': [],
    '运动鞋/跑鞋/网球鞋': [],
    '帆布鞋/板鞋': [],
    '靴子': [],
    '拖鞋/凉鞋': [],
}

JK_SUBTYPES = {
    '西装外套/Blazer': [],
    '运动/机能夹克': [],
    '休闲外套/牛仔夹克': [],
    '风衣/大衣': [],
    '羽绒/棉服': [],
}

TARGET_HUES = {
    '中性': ['黑色', '白色', '灰色', '米白', '卡其色', '藏青色'],
    '暖色': ['红色', '橙色', '黄色', '棕色', '焦糖色', '酒红色'],
    '冷色': ['蓝色', '绿色', '蓝绿色', '军绿色', '宝蓝色', '天蓝色'],
}

# ============================================================
# 1. 数据加载
# ============================================================

def load_all_clothing():
    """加载所有衣服标签，返回 {clothing_id: tag_dict}"""
    items = {}
    for fpath in sorted(glob.glob(os.path.join(TAGS_DIR, '*.json'))):
        bn = os.path.basename(fpath)
        if bn.startswith('SCORE_CACHE') or bn == 'README.json':
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            item = json.load(f)
            items[item['clothing_id']] = item
    return items


def load_state():
    """加载风格实验室状态（含 items_worn 聚合计数）"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def parse_outfit_items(outfit_dir):
    """从 outfit.md 提取单品 ID 列表（去重）"""
    md_path = os.path.join(outfit_dir, 'outfit.md')
    if not os.path.exists(md_path):
        return []
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    ids = set()
    in_table = False
    for line in content.split('\n'):
        s = line.strip()
        if '单品清单' in s:
            in_table = True
            continue
        if in_table and s.startswith('##'):
            break
        if not in_table or not s.startswith('|') or '---' in s:
            continue
        cells = [c.strip().replace('**', '') for c in s.split('|')]
        if len(cells) < 4:
            continue
        cid = cells[2]
        if re.match(r'^[A-Z]+-\d+', cid):
            ids.add(cid)
    return list(ids)


# ============================================================
# 2. 核心分析
# ============================================================

def analyze_category_gaps(wardrobe):
    """品类数量 vs 理想范围"""
    counts = Counter()
    for item in wardrobe.values():
        counts[item.get('category_code', '?')] += 1

    gaps = {}
    for code, (lo, hi) in IDEAL_RANGES.items():
        n = counts.get(code, 0)
        if n < lo:
            status = 'gap'
            diff = lo - n
        elif n > hi:
            status = 'overstock'
            diff = n - hi
        else:
            status = 'healthy'
            diff = 0
        gaps[code] = {
            'actual': n,
            'ideal': (lo, hi),
            'status': status,
            'diff': diff,
        }

    # 未知品类
    for code, n in sorted(counts.items()):
        if code not in IDEAL_RANGES:
            gaps[code] = {'actual': n, 'ideal': (0, 0), 'status': 'unknown', 'diff': n}

    return gaps


def analyze_subcategory_gaps(wardrobe):
    """子品类缺失检测（SHOE + JK）"""
    shoe_items = []
    jk_items = []
    for cid, item in wardrobe.items():
        code = item.get('category_code', '')
        comment = item.get('meta', {}).get('claude_fit_comment', '')
        name = item.get('category', '') + ' ' + (item.get('brand', {}).get('name', ''))
        fabric = item.get('fabric', {}).get('primary', '')
        combined = comment + name + fabric

        if code == 'SHOE':
            shoe_items.append((cid, combined))
        elif code == 'JK':
            jk_items.append((cid, combined))

    # SHOE 子品类
    shoe_subs = {
        '运动鞋/网球鞋/跑鞋': [],
        '帆布鞋/板鞋': [],
        '皮质休闲鞋/板鞋': [],
        '靴子': [],
        '正装鞋/乐福鞋/德比鞋': [],
        '拖鞋/凉鞋': [],
    }
    for cid, txt in shoe_items:
        if any(kw in txt for kw in ['网球', '跑步', '训练鞋', '运动鞋', '跑鞋']):
            shoe_subs['运动鞋/网球鞋/跑鞋'].append(cid)
        elif any(kw in txt for kw in ['帆布', 'Converse', '匡威']):
            shoe_subs['帆布鞋/板鞋'].append(cid)
        elif any(kw in txt for kw in ['靴', 'Timberland', '大黄靴']):
            shoe_subs['靴子'].append(cid)
        elif any(kw in txt for kw in ['皮质', '皮革']) or '皮质' in txt:
            shoe_subs['皮质休闲鞋/板鞋'].append(cid)
        elif any(kw in txt for kw in ['拖鞋', '凉鞋', '洞洞鞋']):
            shoe_subs['拖鞋/凉鞋'].append(cid)
        else:
            shoe_subs['皮质休闲鞋/板鞋'].append(cid)  # 兜底

    # JK 子品类
    jk_subs = {
        '运动/机能夹克': [],
        '休闲外套/牛仔夹克': [],
        '西装外套/Blazer': [],
        '风衣/大衣': [],
        '羽绒/棉服/其他': [],
    }
    for cid, txt in jk_items:
        if any(kw in txt for kw in ['运动', '机能', '冲锋', '训练']):
            jk_subs['运动/机能夹克'].append(cid)
        elif any(kw in txt for kw in ['西装', 'Blazer', '正装']):
            jk_subs['西装外套/Blazer'].append(cid)
        elif any(kw in txt for kw in ['风衣', '大衣', 'trench']):
            jk_subs['风衣/大衣'].append(cid)
        elif any(kw in txt for kw in ['羽绒', '棉服', '棉衣', 'puffer']):
            jk_subs['羽绒/棉服/其他'].append(cid)
        else:
            jk_subs['休闲外套/牛仔夹克'].append(cid)

    # 短袖品类分析
    ts_variety = {'纯色基础款': 0, '条纹/格纹': 0, '印花/图案': 0, 'Polo领': 0}
    for cid, item in wardrobe.items():
        if item.get('category_code') != 'TS':
            continue
        pattern = item.get('pattern', {}).get('type', '')
        name = item.get('meta', {}).get('claude_fit_comment', '') + item.get('category', '')
        if 'Polo' in name or 'polo' in name:
            ts_variety['Polo领'] += 1
        elif pattern in ('条纹', '格纹'):
            ts_variety['条纹/格纹'] += 1
        elif pattern == '印花':
            ts_variety['印花/图案'] += 1
        else:
            ts_variety['纯色基础款'] += 1

    return {
        'SHOE': {k: v for k, v in shoe_subs.items()},
        'JK': {k: v for k, v in jk_subs.items()},
        'TS_variety': ts_variety,
    }


def analyze_color_balance(wardrobe):
    """颜色分布与缺失色相"""
    by_family = Counter()
    by_hue = Counter()
    by_saturation = Counter()
    by_lightness = Counter()
    palette_risk = 0  # 衬肤风险计数

    for item in wardrobe.values():
        c = item.get('color', {})
        hf = c.get('hue_family', '未知')
        hn = c.get('hue_name', '未知')
        sat = c.get('saturation', '未知')
        light = c.get('lightness', '未知')
        pale_ok = c.get('friendly_for_pale_skin', True)

        by_family[hf] += 1
        by_hue[hn] += 1
        by_saturation[sat] += 1
        by_lightness[light] += 1
        if not pale_ok:
            palette_risk += 1

    # 缺失色相
    missing = {}
    for family, hues in TARGET_HUES.items():
        missing[family] = [h for h in hues if h not in by_hue]

    return {
        'by_family': dict(by_family),
        'by_hue': dict(by_hue),
        'by_saturation': dict(by_saturation),
        'by_lightness': dict(by_lightness),
        'missing_hues': missing,
        'palette_risk_count': palette_risk,
    }


def analyze_brand_diversity(wardrobe):
    """品牌集中度分析"""
    brand_counts = Counter()
    unknown_count = 0
    for item in wardrobe.values():
        b = item.get('brand', {})
        name = b.get('name', '未知')
        brand_counts[name] += 1
        if name == '未知':
            unknown_count += 1

    total = len(wardrobe)
    unknown_ratio = unknown_count / total if total > 0 else 0
    top_brands = brand_counts.most_common(8)

    # 集中度检测
    concentration_warning = None
    for brand, n in top_brands:
        if brand != '未知' and n / total > 0.15:
            concentration_warning = f'{brand} 占 {n/total*100:.0f}%'

    return {
        'total_brands': len([b for b in brand_counts if b != '未知']),
        'unknown_count': unknown_count,
        'unknown_ratio': unknown_ratio,
        'top_brands': top_brands,
        'concentration_warning': concentration_warning,
    }


def analyze_utilization(wardrobe, state=None):
    """利用率追踪：热度榜 + 闲置榜"""
    items_worn = (state or {}).get('items_worn', {})

    worn_list = []
    zero_wear = []
    key_unused = []

    for cid, item in wardrobe.items():
        wc = item.get('meta', {}).get('wear_count', 0)
        name = item.get('meta', {}).get('claude_fit_comment', item.get('category', ''))
        brand = item.get('brand', {}).get('name', '')
        is_key = item.get('meta', {}).get('is_key_piece', False)
        is_statement = item.get('meta', {}).get('is_statement_piece', False)

        entry = {'id': cid, 'wear_count': wc, 'brand': brand, 'name': name[:40]}
        if wc > 0:
            worn_list.append(entry)
        else:
            zero_wear.append(entry)

        if wc == 0 and (is_key or is_statement):
            key_unused.append(entry)

    worn_list.sort(key=lambda x: -x['wear_count'])
    zero_wear.sort(key=lambda x: x['id'])

    total = len(wardrobe)
    utilization_rate = len(worn_list) / total if total > 0 else 0

    return {
        'utilization_rate': utilization_rate,
        'items_worn_count': len(worn_list),
        'items_unworn_count': len(zero_wear),
        'top_worn': worn_list[:10],
        'zero_wear': zero_wear,
        'key_unused': key_unused,
    }


# ============================================================
# 3. 高级分析
# ============================================================

def mine_cp_combinations(base_dir=None):
    """挖掘单品共现配对（CP组合），扫描所有 outfit.md"""
    if base_dir is None:
        base_dir = OUTFITS_DIR

    pairs = Counter()
    outfit_count = 0

    for d in sorted(os.listdir(base_dir)):
        dp = os.path.join(base_dir, d)
        if not os.path.isdir(dp) or d.startswith('.') or d.startswith('_'):
            continue
        items = parse_outfit_items(dp)
        if len(items) < 2:
            continue
        outfit_count += 1
        sitems = sorted(items)
        for i in range(len(sitems)):
            for j in range(i + 1, len(sitems)):
                pairs[(sitems[i], sitems[j])] += 1

    # 过滤 ≥2 次
    top_pairs = [(a, b, n) for (a, b), n in pairs.most_common() if n >= 2]
    return {'total_outfits': outfit_count, 'total_pairs': len(pairs), 'top_pairs': top_pairs[:15]}


def save_monthly_snapshot(wardrobe):
    """保存月度快照，返回是否有上月数据可对比"""
    yyyymm = time.strftime('%Y%m')
    snap_path = os.path.join(SNAPSHOT_DIR, f'wardrobe_snapshot_{yyyymm}.json')

    current = {}
    for cid, item in wardrobe.items():
        current[cid] = {
            'wear_count': item.get('meta', {}).get('wear_count', 0),
            'last_worn': item.get('meta', {}).get('last_worn'),
        }

    prev = None
    if os.path.exists(snap_path):
        with open(snap_path, 'r') as f:
            prev = json.load(f)

    with open(snap_path, 'w') as f:
        json.dump({'date': time.strftime('%Y-%m-%d'), 'items': current}, f, ensure_ascii=False)

    return prev


def compute_monthly_delta(current_wardrobe, prev_snapshot):
    """计算月度穿着变化"""
    if not prev_snapshot:
        return None
    prev_items = prev_snapshot.get('items', {})
    increased = []
    decreased = []
    newly_worn = []
    for cid, item in current_wardrobe.items():
        cur = item.get('meta', {}).get('wear_count', 0)
        old = prev_items.get(cid, {}).get('wear_count', 0) if cid in prev_items else 0
        delta = cur - old
        name = item.get('meta', {}).get('claude_fit_comment', '')[:30]
        if delta > 0 and old == 0:
            newly_worn.append((cid, delta, name))
        elif delta > 0:
            increased.append((cid, delta, name))
        elif delta < 0:
            decreased.append((cid, delta, name))

    increased.sort(key=lambda x: -x[1])
    return {'newly_worn': newly_worn, 'increased': increased, 'decreased': decreased}


# ============================================================
# 4. 购买建议引擎
# ============================================================

def generate_purchase_suggestions(gaps, sub_gaps, color_analysis, brand_analysis):
    """综合所有分析，生成购买建议清单"""
    suggestions = []

    # --- 高优先级：硬缺口 ---
    shoe_subs = sub_gaps.get('SHOE', {})
    missing_shoes = [k for k, v in shoe_subs.items() if len(v) == 0]
    if '正装鞋/乐福鞋/德比鞋' in missing_shoes:
        suggestions.append({
            'priority': 'high', 'item': '1双棕色乐福鞋或德比鞋',
            'reason': '10双鞋中0双正装鞋，无法搭配商务/约会/轻熟风格',
            'category': 'SHOE',
        })
    if '拖鞋/凉鞋' in missing_shoes:
        suggestions.append({
            'priority': 'medium', 'item': '1双凉鞋或勃肯鞋',
            'reason': '夏季高温场景缺少透气便鞋',
            'category': 'SHOE',
        })

    # JK 缺口
    jk_subs = sub_gaps.get('JK', {})
    missing_jk = [k for k, v in jk_subs.items() if len(v) == 0]
    if '西装外套/Blazer' in missing_jk:
        suggestions.append({
            'priority': 'high', 'item': '1件海军蓝或灰色西装外套(Blazer)',
            'reason': '6件外套中0件正装外套，商务/约会场景缺失',
            'category': 'JK',
        })
    if '风衣/大衣' in missing_jk:
        suggestions.append({
            'priority': 'medium', 'item': '1件卡其色风衣或羊毛大衣',
            'reason': '秋冬场景缺少长款外套',
            'category': 'JK',
        })

    # 颜色缺口
    missing = color_analysis.get('missing_hues', {})
    all_missing = []
    for family, hues in missing.items():
        all_missing.extend(hues)
    if '酒红色' in all_missing or '棕色' in all_missing:
        suggestions.append({
            'priority': 'medium', 'item': '1件酒红色或棕色上衣/外套',
            'reason': '暖色系偏少，增加暖色调提升穿搭层次感',
            'category': 'COLOR',
        })
    if '宝蓝色' in all_missing or '天蓝色' in all_missing:
        suggestions.append({
            'priority': 'low', 'item': '1件宝蓝色或天蓝色衬衫/T恤',
            'reason': '冷色系缺失亮色，增加蓝色调丰富配色选择',
            'category': 'COLOR',
        })

    # 过度囤积
    overstock = {k: v for k, v in gaps.items() if v['status'] == 'overstock'}
    ts_over = overstock.get('TS', {})
    if ts_over.get('diff', 0) >= 3:
        suggestions.append({
            'priority': 'low', 'item': '暂停购入短袖T恤',
            'reason': f'已有{ts_over["actual"]}件短袖，超过理想上限{ts_over["ideal"][1]}件',
            'category': 'CTRL',
        })

    # 品牌
    if brand_analysis.get('unknown_ratio', 0) > 0.4:
        suggestions.append({
            'priority': 'medium', 'item': '优先选择有品牌的正装鞋和外套',
            'reason': f'衣橱{brand_analysis["unknown_ratio"]*100:.0f}%为无品牌单品，核心品类建议选有品牌保障的',
            'category': 'BRAND',
        })

    return suggestions


# ============================================================
# 5. 输出格式化
# ============================================================

def build_summary(gaps, utilization, brand_analysis):
    """简要统计概览"""
    total = sum(v['actual'] for v in gaps.values() if v['status'] != 'unknown')
    lines = []

    # 标题行
    overstock = {k: v for k, v in gaps.items() if v['status'] == 'overstock'}
    gap_cats = {k: v for k, v in gaps.items() if v['status'] == 'gap'}
    cats_str = ', '.join(
        f"{CATEGORY_NAMES.get(k, k)}:{v['actual']}⚠️+{v['diff']}"
        for k, v in sorted(overstock.items(), key=lambda x: -x[1]['diff'])
    )
    lines.append(f"👔 衣橱概况  {total}件 | {len(gaps)}品类 | {utilization['items_worn_count']}件有穿着记录")
    lines.append(f"\n📊 品类分布")
    lines.append(f"  {cats_str}")
    healthy = [f"{CATEGORY_NAMES.get(k, k)}:{v['actual']}✅" for k, v in gaps.items() if v['status'] == 'healthy']
    if healthy:
        lines.append(f"  {', '.join(healthy)}")

    lines.append(f"\n🏷️ 品牌")
    lines.append(f"  未知: {brand_analysis['unknown_count']}件({brand_analysis['unknown_ratio']*100:.0f}%)" +
                 (' ⚠️偏高' if brand_analysis['unknown_ratio'] > 0.4 else ''))
    top3 = brand_analysis['top_brands'][:3]
    if top3:
        lines.append(f"  TOP3: {', '.join(f'{b}({n})' for b, n in top3)}")

    lines.append(f"\n📈 利用率")
    top3 = utilization['top_worn'][:3]
    if top3:
        top3_str = ', '.join(f'{t["id"]}({t["wear_count"]}次)' for t in top3)
    lines.append(f'  热度TOP3: {top3_str}')
    lines.append(f"  闲置: {utilization['items_unworn_count']}件({(1-utilization['utilization_rate'])*100:.0f}%)")

    lines.append(f"\n💡 快速建议")
    if overstock:
        lines.append(f"  ⚠️ {len(overstock)}品类超标，建议控制购入")
    if brand_analysis['unknown_ratio'] > 0.4:
        lines.append(f"  ⚠️ 近半无品牌，核心单品建议选有品牌保障的")

    return '\n'.join(lines)


def build_report(gaps, sub_gaps, color_analysis, brand_analysis, utilization,
                 purchase_suggestions, cp_data, monthly_delta, wardrobe):
    """完整分析报告"""
    total = sum(v['actual'] for v in gaps.values() if v['status'] != 'unknown')
    parts = []
    parts.append('━' * 44)
    parts.append('👔 衣橱智能分析报告')
    today = time.strftime('%Y年%m月%d日')
    parts.append(f'📅 {today} | {total}件单品')
    parts.append('━' * 44)

    # ━━━ 品类健康度 ━━━
    parts.append('\n━━━ 📊 品类健康度 ━━━')
    order = ['TS', 'LS', 'SHIRT', 'TANK', 'JK', 'PT', 'SH', 'SHOE', 'BAG', 'HAT', 'SOCK', 'SUN', 'ACC']
    for code in order:
        g = gaps.get(code)
        if not g:
            continue
        icon = '⚠️' if g['status'] == 'overstock' else ('❌' if g['status'] == 'gap' else '✅')
        diff_str = ''
        if g['status'] == 'overstock':
            diff_str = f' ⚠️超标 +{g["diff"]}'
        elif g['status'] == 'gap':
            diff_str = f' ❌缺口 -{g["diff"]}'
        name = CATEGORY_NAMES.get(code, code)
        bar = '█' * min(g['actual'], 15)
        parts.append(f'  {code:5s} {name:10s} {g["actual"]:2d}件 {bar} {icon}{diff_str}')
    for code in sorted(gaps):
        if code not in order:
            g = gaps[code]
            parts.append(f'  {code:5s} {g["actual"]}件 (未知品类)')

    # ━━━ 子品类分析 ━━━
    parts.append('\n━━━ 🔍 子品类分析 ━━━')

    shoe_subs = sub_gaps.get('SHOE', {})
    parts.append('  👟 鞋子子品类:')
    for sub, ids in shoe_subs.items():
        icon = '✅' if ids else '⚠️ 缺失'
        ids_str = '、'.join(ids) if ids else '—'
        parts.append(f'     {icon} {sub}: {ids_str}')

    jk_subs = sub_gaps.get('JK', {})
    parts.append('  🧥 外套子品类:')
    for sub, ids in jk_subs.items():
        icon = '✅' if ids else '⚠️ 缺失'
        ids_str = '、'.join(ids) if ids else '—'
        parts.append(f'     {icon} {sub}: {ids_str}')

    ts_v = sub_gaps.get('TS_variety', {})
    if ts_v:
        parts.append('  👕 短袖品类:')
        for t, n in ts_v.items():
            icon = '⚠️ 过多' if (t == '纯色基础款' and n > 7) else '✅'
            parts.append(f'     {icon} {t}: {n}件')

    # ━━━ 颜色平衡 ━━━
    parts.append('\n━━━ 🎨 颜色平衡 ━━━')
    cf = color_analysis['by_family']
    total_color = sum(cf.values())
    fam_icons = {'中性': '⬜', '暖色': '🟧', '冷色': '🟦'}
    for fam in ['中性', '暖色', '冷色']:
        n = cf.get(fam, 0)
        pct = n / total_color * 100 if total_color > 0 else 0
        bar = '█' * int(pct / 5)
        parts.append(f'  {fam_icons.get(fam,"⬜")} {fam}: {bar} {n}件 ({pct:.0f}%)')

    missing = color_analysis.get('missing_hues', {})
    for fam in ['中性', '暖色', '冷色']:
        m = missing.get(fam, [])
        if m:
            parts.append(f'  ⚠️ {fam}缺失色相: {"、".join(m[:4])}')

    # ━━━ 品牌集中度 ━━━
    parts.append('\n━━━ 🏷️ 品牌集中度 ━━━')
    parts.append(f'  品牌数: {brand_analysis["total_brands"]}个')
    parts.append(f'  未知品牌: {brand_analysis["unknown_count"]}/{total}件 ({brand_analysis["unknown_ratio"]*100:.0f}%)' +
                 (' ⚠️偏高' if brand_analysis['unknown_ratio'] > 0.4 else ''))
    parts.append(f'  TOP品牌: {", ".join(f"{b}({n})" for b, n in brand_analysis["top_brands"][:6])}')
    if brand_analysis.get('concentration_warning'):
        parts.append(f'  ⚠️ {brand_analysis["concentration_warning"]}')

    # ━━━ 利用率追踪 ━━━
    parts.append('\n━━━ 📈 利用率追踪 ━━━')
    parts.append(f'  利用率: {utilization["utilization_rate"]*100:.0f}% ({utilization["items_worn_count"]}/{total}件穿过)')

    top = utilization['top_worn']
    if top:
        parts.append(f'\n  🔥 热度榜 TOP {min(10, len(top))}:')
        for i, t in enumerate(top, 1):
            parts.append(f'     {i:2d}. {t["id"]} — {t["wear_count"]}次  {t["name"][:30]}')

    key_unused = utilization.get('key_unused', [])
    if key_unused:
        parts.append(f'\n  ⚠️ 关键单品闲置:')
        for t in key_unused:
            parts.append(f'     {t["id"]} {t["name"][:30]}')

    # ━━━ 月度变化 ━━━
    if monthly_delta:
        parts.append('\n━━━ 📅 月度变化 ━━━')
        nw = monthly_delta.get('newly_worn', [])
        inc = monthly_delta.get('increased', [])
        if nw:
            parts.append(f'  🆕 新穿着: {", ".join(f"{cid}(+{d})" for cid, d, _ in nw[:5])}')
        if inc:
            parts.append(f'  📈 增加: {", ".join(f"{cid}(+{d})" for cid, d, _ in inc[:5])}')

    # ━━━ CP 组合 ━━━
    if cp_data and cp_data['top_pairs']:
        parts.append('\n━━━ 🔗 CP 组合 TOP 10 ━━━')
        for a, b, n in cp_data['top_pairs'][:10]:
            # 获取简短名称
            na = wardrobe.get(a, {}).get('meta', {}).get('claude_fit_comment', a)[:20]
            nb = wardrobe.get(b, {}).get('meta', {}).get('claude_fit_comment', b)[:20]
            parts.append(f'  {a}+{b} — {n}次  {na} + {nb}')

    # ━━━ 购买建议 ━━━
    parts.append('\n━━━ 🛒 购买建议清单 ━━━')
    by_priority = {'high': [], 'medium': [], 'low': []}
    for s in purchase_suggestions:
        by_priority[s['priority']].append(s)

    for pri, label, icon in [('high', '高优先级', '🔴'), ('medium', '中优先级', '🟡'), ('low', '低优先级', '🟢')]:
        items = by_priority[pri]
        if not items:
            continue
        parts.append(f'\n  【{icon} {label}】')
        for i, s in enumerate(items, 1):
            parts.append(f'  {i}. {s["item"]}')
            parts.append(f'     💡 {s["reason"]}')

    parts.append('\n' + '━' * 44)
    return '\n'.join(parts)


def build_structured_data(gaps, sub_gaps, color_analysis, brand_analysis, utilization,
                          purchase_suggestions, cp_data, monthly_delta, wardrobe):
    """结构化数据（供 JSON 导出）"""
    return {
        'metadata': {
            'total_items': len(wardrobe),
            'categories': len([k for k in gaps if gaps[k]['status'] != 'unknown']),
            'date': time.strftime('%Y-%m-%d'),
        },
        'category_gaps': {k: v for k, v in gaps.items()},
        'subcategory_gaps': sub_gaps,
        'color_balance': {
            'by_family': color_analysis['by_family'],
            'missing_hues': color_analysis['missing_hues'],
        },
        'brand_diversity': {
            'total_brands': brand_analysis['total_brands'],
            'unknown_ratio': brand_analysis['unknown_ratio'],
            'top_brands': brand_analysis['top_brands'],
        },
        'utilization': {
            'utilization_rate': utilization['utilization_rate'],
            'top_worn': utilization['top_worn'],
            'zero_wear_count': utilization['items_unworn_count'],
        },
        'cp_pairs': cp_data['top_pairs'][:10] if cp_data else [],
        'purchase_suggestions': purchase_suggestions,
    }


# ============================================================
# 5b. 月度穿搭报告
# ============================================================

def normalize_style(style_name):
    """归并风格到核心类别"""
    s = style_name.lower()
    if 'city boy' in s or 'cityboy' in s: return '日系 City Boy'
    if 'clean fit' in s or 'cleanfit' in s: return 'Clean Fit'
    if '轻熟' in s: return '轻熟休闲'
    if '街头' in s: return '街头潮流'
    if '运动' in s or 'athleisure' in s or '网球' in s or '跑步' in s: return '运动/网球'
    if '韩系' in s: return '韩系简约'
    if '度假' in s or '热带' in s or '亚麻' in s: return '度假休闲'
    if '大胆' in s or '探索' in s or '突破' in s: return 'B线探索实验'
    if '雾' in s or '雾天' in s: return '日系 City Boy'
    if '日系' in s: return '日系 City Boy'
    return '其他'


def load_all_outfits():
    """加载所有穿搭记录"""
    records = []
    for d in sorted(os.listdir(OUTFITS_DIR)):
        dp = os.path.join(OUTFITS_DIR, d)
        md = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md):
            continue
        with open(md, 'r', encoding='utf-8') as f:
            content = f.read()
        date_m = re.search(r'(\d{4}-\d{2}-\d{2})', d)
        date_str = date_m.group(1) if date_m else d[:10]
        style = ''
        for line in content.split('\n'):
            if 'style:' in line.lower() or '风格' in line:
                m = re.search(r'[：:]\s*(.+)', line)
                if m:
                    style = m.group(1).strip()[:30]
                    break
        ids = set()
        in_table = False
        for line in content.split('\n'):
            s = line.strip()
            if '单品清单' in s:
                in_table = True; continue
            if in_table and s.startswith('##'):
                break
            if not in_table or not s.startswith('|') or '---' in s:
                continue
            cells = [c.strip().replace('**', '') for c in s.split('|')]
            if len(cells) < 4:
                continue
            if re.match(r'^[A-Z]+-\d+', cells[2]):
                ids.add(cells[2])
        rating = None
        rp = os.path.join(dp, 'rating.json')
        if os.path.exists(rp):
            try:
                with open(rp) as f:
                    rating = json.load(f).get('rating')
            except:
                pass
        records.append({
            'date': date_str, 'dir': d, 'style': style,
            'items': sorted(ids), 'count': len(ids), 'rating': rating,
        })
    return records


def build_monthly_report(wardrobe=None):
    """构建月度穿搭报告"""
    records = load_all_outfits()
    if not records:
        return '暂无穿搭记录'

    from collections import Counter, defaultdict

    by_date = defaultdict(list)
    for r in records:
        by_date[r['date']].append(r)

    dates = sorted(by_date)
    total = len(records)
    rated = [r for r in records if r['rating']]

    # 风格归并
    style_groups = defaultdict(list)
    for r in records:
        ns = normalize_style(r['style'])
        style_groups[ns].append(r)

    # 单品频次
    item_freq = Counter()
    for r in records:
        for iid in r['items']:
            item_freq[iid] += 1

    daily_counts = [len(by_date[d]) for d in dates]
    max_count = max(daily_counts) if daily_counts else 1

    parts = []
    parts.append('━' * 44)
    parts.append('📊 穿搭月度报告')
    parts.append(f'📅 {dates[0]} ~ {dates[-1]} ({len(dates)}天) | {total}套穿搭')
    parts.append('━' * 44)

    # 核心数据
    parts.append(f'\n━━━ 📈 核心数据 ━━━')
    parts.append(f'  🧥 总生成穿搭: {total} 套')
    parts.append(f'  📅 活跃天数: {len(dates)} 天')
    parts.append(f'  📊 日均穿搭: {total/len(dates):.1f} 套/天')
    parts.append(f'  ⭐ 有评分: {len(rated)} 套 ({len(rated)/total*100:.0f}%)')
    parts.append(f'  🏷️ 覆盖风格: {len(style_groups)} 种')

    # 每日活跃度
    parts.append(f'\n━━━ 📅 每日活跃度 ━━━')
    for d in dates:
        n = len(by_date[d])
        bar = '█' * n + '░' * (max_count - n)
        rs = by_date[d]
        styles_str = ' | '.join(dict.fromkeys(normalize_style(r['style']) for r in rs))
        parts.append(f'  {d}  {bar} {n}套  {styles_str[:65]}')

    # 风格分布
    parts.append(f'\n━━━ 🎯 风格分布 ━━━')
    total_s = sum(len(v) for v in style_groups.values())
    for ns, rs in sorted(style_groups.items(), key=lambda x: -len(x[1])):
        n = len(rs)
        pct = n / total_s * 100 if total_s else 0
        bar = '█' * max(1, int(pct / 3))
        parts.append(f'  {ns:14s}  {bar} {n}套 ({pct:.0f}%)')

    # 满意度
    parts.append(f'\n━━━ ⭐ 满意度 ━━━')
    if rated:
        by_rating = Counter(r['rating'] for r in rated)
        avg = sum(r['rating'] for r in rated) / len(rated)
        parts.append(f'  ⭐⭐⭐ 满意: {by_rating.get(3,0)}次 ({by_rating.get(3,0)/len(rated)*100:.0f}%)')
        parts.append(f'  ⭐⭐   一般: {by_rating.get(2,0)}次 ({by_rating.get(2,0)/len(rated)*100:.0f}%)')
        parts.append(f'  ⭐     失望: {by_rating.get(1,0)}次 ({by_rating.get(1,0)/len(rated)*100:.0f}%)')
        parts.append(f'  📊 平均分: {avg:.1f}/3')
        if by_rating.get(1, 0) > 0:
            parts.append(f'  ⚠️ 有差评记录，已自动禁用相关单品')
    else:
        parts.append(f'  (暂无评分 — 多评分能帮AI更懂你)')

    # 最爱单品 TOP 15
    parts.append(f'\n━━━ 👟 最爱单品 TOP 15 ━━━')
    for i, (iid, n) in enumerate(item_freq.most_common(15), 1):
        name = ''
        if wardrobe:
            item = wardrobe.get(iid, {})
            name = item.get('meta', {}).get('claude_fit_comment', '')[:25]
        bar = '█' * n
        parts.append(f'  {i:2d}. {iid}  {bar} {n}次  {name}')

    # B线探索
    bline = style_groups.get('B线探索实验', [])
    parts.append(f'\n━━━ 🧪 B线探索报告 ━━━')
    parts.append(f'  探索次数: {len(bline)} 套 ({len(bline)/total*100:.0f}%)')
    if bline:
        bline_dates = sorted(set(r['date'] for r in bline))
        parts.append(f'  探索日期: {", ".join(bline_dates)}')
        for r in bline:
            parts.append(f'    · {r["date"]} {r["style"][:40]}')

    # 搭配习惯 — 品类组合
    cat_combos = Counter()
    for r in records:
        cats = tuple(sorted(set(iid.split('-')[0] for iid in r['items'])))
        cat_combos[cats] += 1
    parts.append(f'\n━━━ 🔄 搭配习惯 ━━━')
    parts.append(f'  品类组合 TOP 5:')
    for cats, n in cat_combos.most_common(5):
        if cats:
            parts.append(f'    {"+".join(cats)}: {n}次')

    # 月度洞察
    parts.append(f'\n━━━ 💡 月度洞察 ━━━')
    if style_groups:
        top_style = max(style_groups, key=lambda x: len(style_groups[x]))
        parts.append(f'  🔍 最常穿风格「{top_style}」({len(style_groups[top_style])}套)')
    if len(rated) < total * 0.3:
        parts.append(f'  ⚠️ 评分率仅{len(rated)/total*100:.0f}%，多评分帮AI更懂你')
    if item_freq:
        top_item = item_freq.most_common(1)[0]
        parts.append(f'  👟 最爱单品 {top_item[0]} ({top_item[1]}次)')
    peak_date = max(dates, key=lambda d: len(by_date[d]))
    parts.append(f'  📈 最活跃日 {peak_date} ({len(by_date[peak_date])}套)')

    # 下月待办
    parts.append(f'\n━━━ 📋 下月待办 ━━━')
    if len(rated) < total * 0.3:
        parts.append(f'  💡 评分率提到50%+可获得个性化偏好报告')
    parts.append(f'  💡 尝试穿一次闲置关键单品（JK-001、LS-004、SHOE-007等）')

    parts.append('\n' + '━' * 44)
    return '\n'.join(parts)


# ============================================================
# 6. CLI
# ============================================================

def main():
    if '--report' in sys.argv:
        wardrobe = load_all_clothing()
        state = load_state()

        gaps = analyze_category_gaps(wardrobe)
        sub_gaps = analyze_subcategory_gaps(wardrobe)
        color_analysis = analyze_color_balance(wardrobe)
        brand_analysis = analyze_brand_diversity(wardrobe)
        utilization = analyze_utilization(wardrobe, state)
        purchase_suggestions = generate_purchase_suggestions(gaps, sub_gaps, color_analysis, brand_analysis)

        cp_data = mine_cp_combinations()
        prev_snap = save_monthly_snapshot(wardrobe)
        monthly_delta = compute_monthly_delta(wardrobe, prev_snap)

        output = build_report(gaps, sub_gaps, color_analysis, brand_analysis, utilization,
                              purchase_suggestions, cp_data, monthly_delta, wardrobe)
        print(output)
        if '--save' in sys.argv:
            path = os.path.abspath(os.path.join(PROJ_DIR, '衣橱分析报告.txt'))
            with open(path, 'w') as f: f.write(output)
            print(f'\n📄 已保存: {path}')

    elif '--monthly' in sys.argv:
        wardrobe = load_all_clothing()
        output = build_monthly_report(wardrobe)
        print(output)
        if '--save' in sys.argv:
            path = os.path.abspath(os.path.join(PROJ_DIR, '穿搭月度报告.txt'))
            with open(path, 'w') as f: f.write(output)
            print(f'\n📄 已保存: {path}')

    elif '--summary' in sys.argv:
        wardrobe = load_all_clothing()
        state = load_state()
        gaps = analyze_category_gaps(wardrobe)
        utilization = analyze_utilization(wardrobe, state)
        brand_analysis = analyze_brand_diversity(wardrobe)
        print(build_summary(gaps, utilization, brand_analysis))

    elif '--json' in sys.argv:
        wardrobe = load_all_clothing()
        state = load_state()
        gaps = analyze_category_gaps(wardrobe)
        sub_gaps = analyze_subcategory_gaps(wardrobe)
        color_analysis = analyze_color_balance(wardrobe)
        brand_analysis = analyze_brand_diversity(wardrobe)
        utilization = analyze_utilization(wardrobe, state)
        purchase_suggestions = generate_purchase_suggestions(gaps, sub_gaps, color_analysis, brand_analysis)
        cp_data = mine_cp_combinations()
        prev_snap = save_monthly_snapshot(wardrobe)
        monthly_delta = compute_monthly_delta(wardrobe, prev_snap)
        data = build_structured_data(gaps, sub_gaps, color_analysis, brand_analysis,
                                     utilization, purchase_suggestions, cp_data, monthly_delta, wardrobe)
        print(json.dumps(data, ensure_ascii=False, indent=2))

    else:
        print("🧥 衣橱智能顾问")
        print("  python3 tools/wardrobe_advisor.py --report     衣橱完整分析报告")
        print("  python3 tools/wardrobe_advisor.py --monthly    月度穿搭报告")
        print("  python3 tools/wardrobe_advisor.py --summary     衣橱简要统计")
        print("  python3 tools/wardrobe_advisor.py --json        JSON 导出")
        print("  加 --save 可将报告保存为 .txt 文件")


if __name__ == '__main__':
    main()
