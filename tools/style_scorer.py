#!/usr/bin/env python3
"""
全量风格评分 + 缓存生成
对 76 件衣服 × 8 个风格 = 608 组打分，结果缓存到 wardrobe/tags/SCORE_CACHE.json

用法:
  python3 tools/style_scorer.py              # 全量打分 + 写入缓存
  python3 tools/style_scorer.py --summary    # 打印每件衣服的 Top 3 风格
  python3 tools/style_scorer.py --matrix     # 打印风格×品类热力图
"""

import os, sys, json, glob, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')

# Import matching functions from style_matcher
sys.path.insert(0, os.path.join(BASE_DIR))
from style_matcher import (
    load_all_clothing, load_all_styles, compute_compatibility,
    load_style, SAT_ORDER, LIGHT_ORDER,
)


def score_all(force=False):
    """全量打分，返回 {clothing_id: {style_id: score, ...}}"""
    if os.path.exists(CACHE_FILE) and not force:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        if cache.get('_meta', {}).get('clothing_count') == len(load_all_clothing()):
            print(f"📦 使用缓存: {CACHE_FILE}")
            return cache

    clothes = load_all_clothing()
    styles = load_all_styles()

    total = len(clothes) * len(styles)
    done = 0
    cache = {}

    print(f"🔢 全量打分: {len(clothes)} 件 × {len(styles)} 风格 = {total} 组")
    start = time.time()

    for cid in sorted(clothes.keys()):
        cache[cid] = {}
        for sid in sorted(styles.keys()):
            score, details = compute_compatibility(cid, sid)
            cache[cid][sid] = {
                'score': score,
                'breakdown': details.get('breakdown', {}),
                'passed': details.get('passed', False),
            }
            done += 1
        if done % 50 == 0:
            elapsed = time.time() - start
            eta = elapsed / done * (total - done)
            print(f"  {done}/{total} ({done*100//total}%) | {elapsed:.1f}s | ETA {eta:.0f}s")

    elapsed = time.time() - start
    cache['_meta'] = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'clothing_count': len(clothes),
        'style_count': len(styles),
        'elapsed_seconds': round(elapsed, 1),
    }

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"✅ 完成 {total} 组 ({elapsed:.1f}s) → {CACHE_FILE}")

    return cache


def print_summary(cache):
    """每件衣服的 Top 3 风格"""
    styles = load_all_styles()
    clothes = load_all_clothing()

    print(f"\n{'='*70}")
    print(f"📊 每件衣服的 Top 3 风格归属")
    print(f"{'='*70}")

    cat_order = ['短袖上衣', '长袖上衣', '外套', '衬衣', '背心', '长裤', '短裤', '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
    current_cat = None

    for cid in sorted(cache.keys()):
        if cid.startswith('_'):
            continue
        item = clothes.get(cid, {})
        cat = item.get('category', '?')
        if cat != current_cat:
            current_cat = cat
            print(f"\n── {cat} ──")

        scores = cache[cid]
        top3 = sorted(
            [(sid, v['score']) for sid, v in scores.items() if not sid.startswith('_')],
            key=lambda x: -x[1]
        )[:3]

        top_str = ' | '.join([f"{styles[sid]['name_zh']}={sc}" for sid, sc in top3])
        color = item.get('color', {}).get('hue_name', '?')
        brand = item.get('brand', {}).get('name', '?')
        print(f"  {cid} ({color}, {brand}): {top_str}")


def print_matrix(cache):
    """风格×品类 平均分矩阵"""
    styles = load_all_styles()
    clothes = load_all_clothing()

    categories = ['短袖上衣', '长袖上衣', '外套', '衬衣', '长裤', '短裤', '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子', '背心']
    style_ids = sorted(styles.keys())

    # 计算每个风格×品类的平均分
    matrix = {}
    for sid in style_ids:
        matrix[sid] = {}
        for cat in categories:
            scores = []
            for cid, item in clothes.items():
                if item.get('category') == cat and cid in cache:
                    s = cache[cid].get(sid, {}).get('score', 0)
                    if s > 0:
                        scores.append(s)
            matrix[sid][cat] = round(sum(scores) / len(scores), 1) if scores else 0

    # 打印
    print(f"\n{'='*70}")
    print(f"📊 风格×品类 平均兼容度矩阵")
    print(f"{'='*70}")

    # 表头
    short_cats = [c[:3] for c in categories]
    print(f"{'风格':12s}", end='')
    for sc in short_cats:
        print(f"{sc:>6s}", end='')
    print(f"  {'总均':>5s}")

    for sid in style_ids:
        name = styles[sid]['name_zh']
        print(f"{name:12s}", end='')
        all_scores = []
        for cat in categories:
            s = matrix[sid][cat]
            all_scores.append(s)
            bar = '█' if s >= 50 else ('▓' if s >= 40 else ('▒' if s >= 30 else ('░' if s > 0 else '·')))
            print(f"{s:5.0f}{bar}", end='')
        avg = round(sum(all_scores) / len([s for s in all_scores if s > 0]), 1)
        print(f"  {avg:5.1f}")

    print(f"\n█≥50 ▓≥40 ▒≥30 ░<30 ·无兼容")


def main():
    force = '--force' in sys.argv
    cache = score_all(force=force)

    if '--summary' in sys.argv:
        print_summary(cache)
    elif '--matrix' in sys.argv:
        print_matrix(cache)
    else:
        # Default: score + matrix
        print_matrix(cache)
        print()
        print_summary(cache)

    print(f"\n缓存文件: {CACHE_FILE}")


if __name__ == '__main__':
    main()
