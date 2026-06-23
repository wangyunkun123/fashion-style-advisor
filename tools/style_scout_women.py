#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""女性风格发现 — 根据用户身形+衣橱+偏好搜索相关风格图片（轻量版：仅图片）"""
import os, sys, json, subprocess, argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

parser = argparse.ArgumentParser(description='女性风格发现')
parser.add_argument('--user', required=True, help='用户 ID')
parser.add_argument('--limit', type=int, default=10, help='最多下载图片数')
args = parser.parse_args()

user_dir = os.path.join(PROJ_DIR, 'users', args.user)
profile_path = os.path.join(user_dir, 'profile.json')
tags_dir = os.path.join(user_dir, 'wardrobe', 'tags')
output_dir = os.path.join(user_dir, 'discovered_styles')

if not os.path.exists(profile_path):
    print(f"❌ 用户 {args.user} 不存在（profile.json 未找到）")
    sys.exit(1)

with open(profile_path) as f:
    profile = json.load(f)

# ── 分析身形 ──
body = profile.get('body', {})
shape = body.get('shape', '')

shape_terms = {
    'pear': 'pear shape', 'apple': 'apple shape',
    'hourglass': 'hourglass shape', 'rectangle': 'rectangle body',
    'inverted_triangle': 'inverted triangle body',
}
shape_en = shape_terms.get(shape, 'women')

# ── 分析偏好风格 ──
style_prefs = profile.get('style_prefs', [])
style_names = {
    'WF-01': 'french effortless', 'WF-02': 'korean girlie',
    'WF-03': 'mori kei', 'WF-04': 'new chinese',
    'WF-05': 'american casual', 'WF-06': 'minimalist',
    'WF-07': 'preppy', 'WF-08': 'athleisure',
    'WF-09': 'boho', 'WF-10': 'y2k',
    'WF-11': 'city girl', 'WF-12': 'dark academia',
}
top_style = style_names.get(style_prefs[0], '') if style_prefs else ''

# ── 分析衣橱 ──
dominant_cats = {}
color_counts = {}
total_items = 0
if os.path.isdir(tags_dir):
    for fn in os.listdir(tags_dir):
        if fn.endswith('.json') and fn != 'SCORE_CACHE.json':
            try:
                with open(os.path.join(tags_dir, fn)) as f:
                    tag = json.load(f)
            except Exception:
                continue
            cat = tag.get('category', '')
            dominant_cats[cat] = dominant_cats.get(cat, 0) + 1
            color = (tag.get('color') or {}).get('hue_name', '')
            if color:
                color_counts[color] = color_counts.get(color, 0) + 1
            total_items += 1

top_cats = sorted(dominant_cats, key=dominant_cats.get, reverse=True)[:3]
top_color = max(color_counts, key=color_counts.get) if color_counts else ''

# ── 构建 query ──
query_parts = []
if shape_en:
    query_parts.append(shape_en + ' body type')
if top_cats:
    query_parts.append(' '.join(top_cats[:2]))
if top_color:
    query_parts.append(top_color)
if top_style:
    query_parts.append(top_style + ' style')
query_parts.append('women street style outfit 2025')
query = ' '.join(p for p in query_parts if p)

print(f"👤 用户: {args.user}")
print(f"  身形: {shape or '未知'} ({shape_en})")
print(f"  偏好风格: {top_style or '无'}")
print(f"  衣橱: {total_items}件, 主导品类={top_cats}, 主色={top_color}")
print(f"🔍 搜索: {query}")

# ── 调用 fashion_image_search ──
os.makedirs(output_dir, exist_ok=True)
cmd = [
    'python3', os.path.join(BASE_DIR, 'fashion_image_search.py'),
    '--query', query,
    '--save', output_dir,
    '--count', str(args.limit),
]
result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJ_DIR, timeout=180)

if result.returncode != 0:
    print(f"⚠️ 搜索出错: {result.stderr[:200]}")

# ── 统计结果 ──
img_count = len([f for f in os.listdir(output_dir)
                 if f.endswith(('.jpg','.jpeg','.png','.webp')) and not f.startswith('_')])

# ── 写入 meta ──
meta = {
    'query': query,
    'user_shape': shape,
    'user_top_cats': top_cats,
    'user_top_color': top_color,
    'user_style_pref': top_style,
    'total_wardrobe_items': total_items,
    'images_found': img_count,
    'generated_at': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
}
with open(os.path.join(output_dir, '_meta.json'), 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"✅ 风格发现完成 → {output_dir}/ ({img_count}张图片)")
