#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""衣橱自动分类引擎 — 风格聚类 + 智能分组

Phase 3 核心模块:
  1. 基于 style_modifiers 共现矩阵的风格聚类
  2. 新入库单品自动推荐 matching styles
  3. 衣橱健康度评估（品类分布/利用率/重复度）
"""

import os
import json
import re
from collections import Counter, defaultdict

# 项目路径
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_tags_dir(tags_dir=None, uid=None):
    """加载衣橱所有标签 JSON。

    Returns:
        dict: {clothing_id: tag_data, ...}
    """
    if tags_dir is None:
        if uid and uid != 'default':
            tags_dir = os.path.join(_BASE, 'users', uid, 'wardrobe', 'tags')
        else:
            tags_dir = os.path.join(_BASE, 'wardrobe', 'tags')

    wardrobe = {}
    if not os.path.isdir(tags_dir):
        return wardrobe

    for fn in sorted(os.listdir(tags_dir)):
        if fn == 'SCORE_CACHE.json' or not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(tags_dir, fn), 'r') as f:
                data = json.load(f)
            cid = data.get('clothing_id', fn.replace('.json', ''))
            if data.get('meta', {}).get('archived'):
                continue
            wardrobe[cid] = data
        except Exception:
            continue

    return wardrobe


def build_style_cooccurrence(wardrobe):
    """构建风格标签共现矩阵。

    遍历所有单品的 style_modifiers，统计标签对的共现次数。
    style_modifiers 是 list，如 ["运动休闲", "复古", "条纹"]。

    Returns:
        cooc: {(tag1, tag2): count}  共现矩阵
        tag_freq: {tag: count}        标签频率
    """
    cooc = Counter()
    tag_freq = Counter()

    for cid, item in wardrobe.items():
        tags = item.get('style_modifiers', [])
        if not tags:
            tags = ['基础款']
        for tag in tags:
            tag_freq[tag] += 1
        # 两两共现
        for i in range(len(tags)):
            for j in range(i+1, len(tags)):
                pair = tuple(sorted([tags[i], tags[j]]))
                cooc[pair] += 1

    return cooc, tag_freq


def compute_style_clusters(wardrobe, min_cluster_size=2):
    """基于共现矩阵，将单品聚类到风格群组。

    算法：
    1. 找到最高频标签作为种子
    2. 对该标签下的单品，计算与其他标签的 Jaccard 相似度
    3. 合并相似度 > 0.3 的标签为群组
    4. 未归类的单品放入「其他风格」

    Returns:
        list[dict]: [
            {
                'name': str,           # 群组名（如「运动休闲风」）
                'tags': [str],          # 群组包含的风格标签
                'items': [str],         # 单品 ID 列表
                'item_count': int,
                'coverage_pct': float,  # 占衣橱比例
                'representative': str,  # 代表性单品 ID
            },
            ...
        ]
    """
    cooc, tag_freq = build_style_cooccurrence(wardrobe)

    if not tag_freq:
        return []

    # Step 1: 按频率排序标签
    sorted_tags = sorted(tag_freq.items(), key=lambda x: -x[1])

    # Step 2: 贪心聚类
    assigned_tags = set()
    clusters_raw = []

    for seed_tag, seed_freq in sorted_tags:
        if seed_tag in assigned_tags:
            continue

        # 收集与 seed_tag 高度共现的标签
        cluster_tags = {seed_tag}
        for other_tag, _ in sorted_tags:
            if other_tag == seed_tag or other_tag in assigned_tags:
                continue
            pair = tuple(sorted([seed_tag, other_tag]))
            pair_count = cooc.get(pair, 0)
            # Jaccard: |A ∩ B| / |A ∪ B|
            union = tag_freq[seed_tag] + tag_freq[other_tag] - pair_count
            jaccard = pair_count / union if union > 0 else 0
            if jaccard > 0.3:
                cluster_tags.add(other_tag)

        assigned_tags.update(cluster_tags)
        clusters_raw.append(cluster_tags)

    # Step 3: 将单品分配到群组
    item_to_cluster = {}
    for cid, item in wardrobe.items():
        tags = set(item.get('style_modifiers', []))
        if not tags:
            tags = {'基础款'}

        best_cluster = -1
        best_score = 0
        for ci, ctags in enumerate(clusters_raw):
            overlap = len(tags & ctags)
            score = overlap / len(tags | ctags) if tags | ctags else 0
            if score > best_score:
                best_score = score
                best_cluster = ci

        if best_cluster >= 0 and best_score > 0:
            item_to_cluster[cid] = best_cluster

    # Step 4: 构建结果
    clusters = []
    for ci, ctags in enumerate(clusters_raw):
        items_in = [cid for cid, c in item_to_cluster.items() if c == ci]
        if len(items_in) >= min_cluster_size:
            # 选代表性单品（style_modifiers 匹配最多的）
            best_item = items_in[0]
            best_match = 0
            for iid in items_in:
                item_tags = set(wardrobe[iid].get('style_modifiers', []))
                match = len(item_tags & ctags)
                if match > best_match:
                    best_match = match
                    best_item = iid
            clusters.append({
                'name': '、'.join(sorted(ctags, key=lambda t: -tag_freq[t])[:3]),
                'tags': sorted(ctags, key=lambda t: -tag_freq[t]),
                'items': sorted(items_in),
                'item_count': len(items_in),
                'coverage_pct': round(len(items_in) / len(wardrobe) * 100, 1),
                'representative': best_item,
            })

    # 未被分配的单品 → 「其他风格」
    all_assigned = set()
    for c in clusters:
        all_assigned.update(c['items'])
    unassigned = [cid for cid in wardrobe if cid not in all_assigned]
    if unassigned:
        clusters.append({
            'name': '其他风格',
            'tags': ['基础款'],
            'items': sorted(unassigned),
            'item_count': len(unassigned),
            'coverage_pct': round(len(unassigned) / len(wardrobe) * 100, 1),
            'representative': unassigned[0] if unassigned else '',
        })

    # 按单品数量降序
    clusters.sort(key=lambda c: -c['item_count'])
    return clusters


def recommend_styles_for_item(item_tags, wardrobe=None):
    """根据新单品的标签，推荐匹配的风格 ID 列表。

    Args:
        item_tags: dict with 'style_modifiers', 'occasions', 'category_code', 'color', etc.
        wardrobe: optional full wardrobe for co-occurrence context

    Returns:
        list[str]: 风格 ID 列表（如 ['american_ivy_league', 'clean_fit']）
    """
    modifiers = item_tags.get('style_modifiers', [])
    occasions = item_tags.get('occasions', [])
    cat_code = item_tags.get('category_code', '')
    color = item_tags.get('color', {})
    formality = item_tags.get('formality', 3)

    # 风格映射规则（基于标签 → 风格 ID）
    # 这是从 styles/ 目录和 styles_universal/ 中提取的映射
    STYLE_RULES = [
        # (条件, 风格ID)
        (lambda: any(t in modifiers for t in ['运动休闲', '运动', '速干']), 'athleisure_sport'),
        (lambda: any(t in modifiers for t in ['复古', 'vintage', '90s']), 'retro_casual'),
        (lambda: any(t in modifiers for t in ['极简', '简约', 'minimal']), 'clean_fit'),
        (lambda: any(t in modifiers for t in ['街头', 'street', 'hiphop']), 'streetwear'),
        (lambda: any(t in modifiers for t in ['商务', '正装', 'formal']), 'business_casual'),
        (lambda: any(t in modifiers for t in ['法式', 'french', 'effortless']), 'french_effortless'),
        (lambda: any(t in modifiers for t in ['设计师', '暗黑', '先锋']), 'avant_garde'),
        (lambda: any(t in modifiers for t in ['户外', '机能', '工装']), 'gorpcore_techwear'),
        (lambda: any(t in modifiers for t in ['学院', 'ivy', 'preppy']), 'american_ivy_league'),
        (lambda: any(t in modifiers for t in ['日系', 'japanese', 'wabi']), 'japanese_minimal'),
        (lambda: any(t in modifiers for t in ['针织', '毛衣', '羊绒']), 'knitwear_cashmere'),
        (lambda: any(t in modifiers for t in ['丹宁', '牛仔', 'denim']), 'denim_culture'),
        (lambda: any(t in modifiers for t in ['度假', '海滩', '热带']), 'resort_vacation'),
        (lambda: any(t in modifiers for t in ['性感', '妩媚', '蕾丝']), 'feminine_romantic'),
        # 场合驱动
        (lambda: '运动' in occasions, 'athleisure_sport'),
        (lambda: '网球' in occasions, 'tennis_core'),
        (lambda: '商务' in occasions or formality >= 4, 'business_casual'),
        # 颜色驱动
        (lambda: color.get('is_neutral') and color.get('saturation') == '无彩色',
         'clean_fit' if formality >= 3 else 'minimalist_monochrome'),
    ]

    recommended = []
    for condition, style_id in STYLE_RULES:
        try:
            if condition() and style_id not in recommended:
                recommended.append(style_id)
        except Exception:
            continue

    return recommended[:5]  # 最多 5 个


def compute_wardrobe_health(wardrobe, outfit_records=None):
    """评估衣橱健康度。

    Returns:
        dict: {
            'total_items': int,
            'total_categories': int,
            'category_distribution': {cat_code: count},
            'utilization': {cid: wear_count},
            'orphans': [cid],  # 从未穿过的单品
            'overlap': [(cid1, cid2, similarity)],  # 功能重叠单品
        }
    """
    total = len(wardrobe)
    cat_dist = Counter()
    utilization = {}
    for cid, item in wardrobe.items():
        cc = item.get('category_code', '?')
        cat_dist[cc] += 1
        utilization[cid] = item.get('meta', {}).get('wear_count', 0)

    orphans = [cid for cid, n in utilization.items() if n == 0]

    # 检测功能重叠（同品类 + 同颜色家族 + 同风格）
    overlap = []
    items_list = list(wardrobe.items())
    for i in range(len(items_list)):
        for j in range(i+1, len(items_list)):
            cid1, item1 = items_list[i]
            cid2, item2 = items_list[j]
            if item1.get('category_code') != item2.get('category_code'):
                continue
            c1 = item1.get('color', {})
            c2 = item2.get('color', {})
            if (c1.get('hue_family') == c2.get('hue_family') and
                c1.get('hue_name') == c2.get('hue_name')):
                s1 = set(item1.get('style_modifiers', []))
                s2 = set(item2.get('style_modifiers', []))
                sim = len(s1 & s2) / len(s1 | s2) if s1 | s2 else 0
                if sim > 0.5:
                    overlap.append((cid1, cid2, round(sim, 2)))

    return {
        'total_items': total,
        'total_categories': len(cat_dist),
        'category_distribution': dict(cat_dist.most_common()),
        'utilization': utilization,
        'orphans': orphans,
        'orphan_count': len(orphans),
        'overlap_count': len(overlap),
        'overlap': overlap[:10],  # Top 10
    }


# ── CLI ──
if __name__ == '__main__':
    import sys
    wardrobe = load_tags_dir()

    if '--clusters' in sys.argv:
        clusters = compute_style_clusters(wardrobe)
        print(f"\n{'='*50}")
        print(f"风格聚类 — {len(clusters)} 个群组")
        print(f"{'='*50}")
        for c in clusters:
            print(f"\n🎯 {c['name']} ({c['item_count']}件, {c['coverage_pct']}%)")
            print(f"  代表: {c['representative']}")
            print(f"  单品: {', '.join(c['items'][:8])}{'...' if len(c['items'])>8 else ''}")

    elif '--health' in sys.argv:
        health = compute_wardrobe_health(wardrobe)
        print(f"\n{'='*50}")
        print(f"衣橱健康报告")
        print(f"{'='*50}")
        print(f"总单品: {health['total_items']}")
        print(f"品类数: {health['total_categories']}")
        print(f"闲置单品: {health['orphan_count']}")
        print(f"功能重叠: {health['overlap_count']} 对")
        print(f"\n品类分布:")
        for cat, n in health['category_distribution'].items():
            bar = '█' * n
            print(f"  {cat}: {bar} ({n})")

    else:
        # 默认：对新单品 TS-014 做风格推荐测试
        test_item = {
            'style_modifiers': ['运动休闲', '复古'],
            'occasions': ['运动', '日常休闲'],
            'category_code': 'TS',
            'color': {'hue_family': '冷色', 'hue_name': '深绿色', 'is_neutral': False},
            'formality': 3,
        }
        styles = recommend_styles_for_item(test_item)
        print(f"测试单品: {test_item}")
        print(f"推荐风格: {styles}")
