#!/usr/bin/env python3
"""
同步抠图到穿搭 items/ 目录
从 wardrobe/enhanced/ 复制抠图，自动按 {ID}_{名称}_cutout.png 格式命名。

用法:
  python3 tools/sync_items.py <outfit_dir>
"""

import os, sys, re, glob, shutil, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
ENHANCED_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'enhanced')
WARDROBE_MD = os.path.join(PROJ_DIR, 'wardrobe', '服装档案.md')
MAPPING_FILE = os.path.join(PROJ_DIR, 'wardrobe', 'tags', '.id_to_cutout.json')


def build_mapping():
    """从服装档案.md 建立 ID → enhanced cutout 文件名映射，缓存到 JSON"""
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, 'r') as f:
            cached = json.load(f)
        # 验证缓存有效性
        if len(cached) >= 70:
            return cached

    mapping = {}
    with open(WARDROBE_MD, 'r', encoding='utf-8') as f:
        content = f.read()

    for line in content.split('\n'):
        m = re.match(r'^\|\s*(\w+-\d+)\s*\|\s*([^\|]+)\s*\|', line)
        if not m:
            continue
        cid = m.group(1)
        fname = m.group(2).strip()

        # 在 enhanced/ 中找到对应的 cutout 文件
        base = os.path.splitext(fname)[0]
        cutout_name = f'{base}_cutout.png'
        cutout_path = os.path.join(ENHANCED_DIR, cutout_name)

        if os.path.exists(cutout_path):
            mapping[cid] = cutout_name
        else:
            # 模糊匹配：找包含相近日期的文件
            date_match = re.search(r'(\d{8})_(\d{4})_(\d{2})_(\d{3})', fname)
            if date_match:
                pattern = f"{date_match.group(1)}_{date_match.group(2)}"
                candidates = [f for f in os.listdir(ENHANCED_DIR)
                              if pattern in f and f.endswith('_cutout.png')]
                if candidates:
                    mapping[cid] = candidates[0]
                else:
                    mapping[cid] = None
            else:
                mapping[cid] = None

    # 缓存
    with open(MAPPING_FILE, 'w') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    return mapping


def parse_outfit_items(outfit_dir):
    """解析 outfit.md 获取单品列表 [{id, name}]"""
    md = os.path.join(outfit_dir, 'outfit.md')
    if not os.path.exists(md):
        return []
    with open(md, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    items = []
    in_section = False
    for line in lines:
        s = line.strip()
        if '单品清单' in s:
            in_section = True
            continue
        if in_section and s.startswith('##'):
            break
        if not in_section or not s.startswith('|') or '---' in s:
            continue
        cells = [c.strip().replace('**', '') for c in s.split('|')]
        if len(cells) < 4:
            continue
        cid = cells[2]
        if not re.match(r'^[A-Z]+-\d+', cid):
            continue
        items.append({'id': cid, 'name': cells[3]})
    return items


def sync(outfit_dir):
    """主同步逻辑"""
    items_dir = os.path.join(outfit_dir, 'items')
    os.makedirs(items_dir, exist_ok=True)

    items = parse_outfit_items(outfit_dir)
    if not items:
        print("❌ outfit.md 未找到单品清单")
        return

    mapping = build_mapping()

    # 清理旧格式文件
    for f in os.listdir(items_dir):
        if f.startswith('Image_') or f.startswith('IMG_'):
            os.remove(os.path.join(items_dir, f))

    synced, missing = 0, 0
    for item in items:
        cid = item['id']
        name = item['name'].replace('/', '_')  # 安全文件名
        target = os.path.join(items_dir, f'{cid}_{name}_cutout.png')

        if os.path.exists(target):
            synced += 1
            continue

        src_name = mapping.get(cid)
        if src_name:
            src = os.path.join(ENHANCED_DIR, src_name)
            if os.path.exists(src):
                shutil.copy2(src, target)
                print(f'  ✅ {cid} ← {src_name}')
                synced += 1
            else:
                print(f'  ❌ {cid}: 映射文件不存在 {src_name}')
                missing += 1
        else:
            print(f'  ⚠️  {cid}: 无抠图映射')
            missing += 1

    print(f'\n✅ {synced} 件 | ⚠️ {missing} 件缺失')
    return synced


if __name__ == '__main__':
    if len(sys.argv) > 1:
        d = sys.argv[1]
        if not os.path.isabs(d):
            d = os.path.join(BASE_DIR, '..', d)
        d = os.path.abspath(d)
    else:
        # 找最新穿搭
        ob = os.path.join(BASE_DIR, '..', 'outfits')
        dirs = sorted([x for x in os.listdir(ob) if os.path.isdir(os.path.join(ob, x)) and not x.startswith('.')],
                      key=lambda x: os.path.getctime(os.path.join(ob, x)))
        d = os.path.join(ob, dirs[-1]) if dirs else None

    if not d or not os.path.exists(d):
        print('❌ 未找到穿搭目录')
        sys.exit(1)

    print(f'📁 {os.path.basename(d)}')
    sync(d)
