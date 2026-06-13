#!/usr/bin/env python3
"""
ID 重映射脚本
将 Claude 返回的 ID 体系映射到项目标准 ID。

用法:
  python3 tools/tag_remap.py                          # 预览映射
  python3 tools/tag_remap.py --write                  # 写入 remapped JSON
"""

import os, sys, json, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
WARDROBE_MD = os.path.join(PROJ_DIR, 'wardrobe', '服装档案.md')
INPUT_FILE = os.path.join(PROJ_DIR, 'wardrobe', 'tags_claude_raw', 'wardrobe_items.json')
OUTPUT_FILE = os.path.join(PROJ_DIR, 'wardrobe', 'tags_claude_raw', 'wardrobe_remapped.json')

# ============================================================
# 1. 品类代码映射
# ============================================================
CODE_MAP = {
    'TS': 'TS',
    'LS': 'LS', 'HD': 'LS', 'KN': 'LS', 'SW': 'LS',
    'JK': 'JK', 'CT': 'JK', 'BL': 'JK',
    'PT': 'PT',
    'SH': 'SH',
    'SHT': 'SHIRT',
    'TK': 'TANK',
    'FT': 'SHOE',
    'HT': 'HAT', 'HB': 'HAT',
    'BG': 'BAG',
    'GL': 'SUN',
    'JW': 'ACC',
    'SK': 'SOCK',
}

CATEGORY_NAMES = {
    'TS': '短袖上衣', 'LS': '长袖上衣', 'JK': '外套', 'PT': '长裤',
    'SH': '短裤', 'SHIRT': '衬衣', 'TANK': '背心', 'SHOE': '鞋子',
    'HAT': '帽子', 'BAG': '包', 'SUN': '墨镜', 'ACC': '手部配饰', 'SOCK': '袜子',
}

# 每组品类按 服装档案.md 的 ID 顺序
CATEGORY_ORDER = {
    'TS': ['TS-001','TS-002','TS-003','TS-004','TS-005','TS-006','TS-007','TS-008','TS-009','TS-010','TS-011'],
    'LS': ['LS-001','LS-002','LS-003','LS-004'],
    'JK': ['JK-001','JK-002','JK-003','JK-004','JK-005','JK-006'],
    'PT': ['PT-001','PT-002','PT-003','PT-004','PT-005','PT-006'],
    'SH': ['SH-001','SH-002','SH-003','SH-004','SH-005','SH-006','SH-007','SH-008'],
    'SHIRT': ['SHIRT-001','SHIRT-002','SHIRT-003','SHIRT-004'],
    'TANK': ['TANK-001','TANK-002','TANK-003'],
    # Claude 返回顺序: 德训鞋→足球鞋→匡威→Nike板鞋→匡威高帮→大黄靴→Jordan→空军一号→拖鞋→老爹鞋
    'SHOE': ['SHOE-002','SHOE-003','SHOE-004','SHOE-005','SHOE-006','SHOE-007','SHOE-008','SHOE-009','SHOE-010','SHOE-001'],
    'HAT': ['HAT-001','HAT-002','HAT-003','HAT-004','HAT-005'],
    'BAG': ['BAG-001','BAG-002','BAG-003','BAG-004','BAG-005','BAG-006','BAG-007'],
    # Claude 返回顺序: 商务墨镜→复古绿框→运动墨镜
    'SUN': ['SUN-001','SUN-003','SUN-002'],
    'ACC': ['ACC-001','ACC-002','ACC-003'],
    'SOCK': ['SOCK-001','SOCK-002','SOCK-003','SOCK-004','SOCK-005','SOCK-006'],
}


# ============================================================
# 2. 解析服装档案.md 获取每件衣服的预期描述
# ============================================================
def parse_wardrobe_expected():
    """返回 {new_id: {color, style, features}} 用于校验映射"""
    with open(WARDROBE_MD, 'r', encoding='utf-8') as f:
        content = f.read()

    items = {}
    current_cat = None
    for line in content.split('\n'):
        for cat_name, cat_code in [('短袖上衣','TS'),('长袖上衣','LS'),('外套','JK'),
                                     ('长裤','PT'),('短裤','SH'),('衬衣','SHIRT'),
                                     ('背心','TANK'),('鞋子','SHOE'),('帽子','HAT'),
                                     ('包','BAG'),('墨镜','SUN'),('手部配饰','ACC'),('袜子','SOCK')]:
            if f'## {cat_name}' in line:
                current_cat = cat_code
                break
        m = re.match(r'^\|\s*(\w+-\d+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|', line)
        if m and current_cat:
            cid = m.group(1)
            items[cid] = {
                'color_text': m.group(3).strip(),
                'style_text': m.group(4).strip(),
                'features': m.group(5).strip(),
                'category_code': current_cat,
            }
    return items


# ============================================================
# 3. 主映射逻辑
# ============================================================
def remap():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        claude_data = json.load(f)

    expected = parse_wardrobe_expected()

    # 按目标品类分组 Claude items
    buckets = {}
    for item in claude_data:
        old_code = item['category_code']
        new_code = CODE_MAP.get(old_code, old_code)
        if new_code not in buckets:
            buckets[new_code] = []
        buckets[new_code].append(item)

    # 对每个品类按原顺序分配 ID
    remapped = []
    mapping_log = []
    unmapped = []

    for new_code, id_list in CATEGORY_ORDER.items():
        bucket = buckets.get(new_code, [])

        for i, target_id in enumerate(id_list):
            if i < len(bucket):
                item = bucket[i]
                old_id = item['clothing_id']
                old_code = item['category_code']

                # 更新 ID 和品类
                item['clothing_id'] = target_id
                item['category'] = CATEGORY_NAMES.get(new_code, item['category'])
                item['category_code'] = new_code

                remapped.append(item)

                # 记录映射 + 校验
                exp = expected.get(target_id, {})
                color_match = exp.get('color_text', '?')
                claude_color = item['color']['hue_name']

                status = '✅'
                note = ''
                # 简单校验：检查 Claude 颜色是否与预期大致匹配
                if color_match != '?' and claude_color:
                    if not any(c in claude_color for c in color_match.split('/')[0][:2]) \
                       and not any(c in color_match for c in claude_color[:2]):
                        status = '⚠️'
                        note = f'颜色差异: 预期≈{color_match}, Claude={claude_color}'

                mapping_log.append(f"{status} {old_id}→{target_id} ({old_code}→{new_code}) | {claude_color} | {note}")
            else:
                unmapped.append(f"❌ {target_id}: 无对应 Claude 数据 (品类 {new_code} 仅有 {len(bucket)} 条)")

    # 检查 Claude 中未被映射的额外项
    total_mapped = len(remapped)
    if total_mapped < len(claude_data):
        mapped_old_ids = set()
        for item in remapped:
            # 需要从原始数据中追溯
            pass

    return remapped, mapping_log, unmapped


def main():
    do_write = '--write' in sys.argv

    print("=" * 60)
    print("🔄 ID 重映射")
    print("=" * 60)

    remapped, log, unmapped = remap()

    print(f"\n📊 原始: 75 件")
    print(f"📊 映射: {len(remapped)} 件")

    # 按品类打印映射
    current_cat = None
    for line in log:
        cat = line.split('(')[1].split('→')[0] if '(' in line else ''
        if current_cat != cat:
            current_cat = cat
            cat_name = [k for k,v in CODE_MAP.items() if v == cat.split('→')[0].strip()] if '→' in cat else []
            print()
        print(f"  {line}")

    if unmapped:
        print(f"\n⚠️ 未映射项:")
        for u in unmapped:
            print(f"  {u}")

    if do_write:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(remapped, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已写入: {OUTPUT_FILE}")
    else:
        print(f"\n👉 确认无误后运行: python3 tools/tag_remap.py --write")


if __name__ == '__main__':
    main()
