#!/usr/bin/env python3
"""为所有衣橱单品生成缩略图（从原始图片居中裁剪 + 缩放）
映射规则：品类目录下图片按文件名排序 ↔ 标签文件按ID排序 → 一一对应
"""
import os, json, glob
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')
TAGS_DIR = os.path.join(PROJ, 'wardrobe', 'tags')
WARDROBE_DIR = os.path.join(PROJ, 'wardrobe')
ENHANCED_DIR = os.path.join(PROJ, 'wardrobe', 'enhanced')
THUMB_SIZE = (200, 200)  # 缩略图尺寸

# 品类代码 → 中文目录名
CAT_DIRS = {
    'LS': '长袖上衣', 'TS': '短袖上衣', 'SHIRT': '衬衣', 'TANK': '背心',
    'JK': '外套', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
    'BAG': '包', 'HAT': '帽子', 'SOCK': '袜子', 'SUN': '墨镜', 'ACC': '手部配饰',
}


def generate_thumb(src_path, dst_path, size=THUMB_SIZE):
    """从原始图片生成居中裁剪缩略图"""
    img = Image.open(src_path).convert('RGB')
    # 居中裁剪为正方形
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
    # 缩放到目标尺寸
    img = img.resize(size, Image.LANCZOS)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    img.save(dst_path, 'PNG', optimize=True)
    return dst_path


def main():
    # 1. 收集所有标签文件，按品类分组
    tag_files = sorted(glob.glob(os.path.join(TAGS_DIR, '*.json')))
    tag_files = [f for f in tag_files
                 if not os.path.basename(f).startswith('SCORE_CACHE')
                 and os.path.basename(f) != 'README.json']

    cats = {}  # {category_code: [(clothing_id, tag_path), ...]}
    for tf in tag_files:
        with open(tf) as f:
            data = json.load(f)
        cid = data.get('clothing_id')
        cat_code = data.get('category_code', '?')
        if cat_code not in cats:
            cats[cat_code] = []
        cats[cat_code].append((cid, tf))

    # 2. 确保 enhanced 目录存在
    os.makedirs(ENHANCED_DIR, exist_ok=True)

    generated = 0
    skipped = 0
    errors = []

    for cat_code, items in sorted(cats.items()):
        cat_dir_name = CAT_DIRS.get(cat_code)
        if not cat_dir_name:
            print(f"  ⚠️ 未知品类 {cat_code}，跳过")
            continue

        cat_dir = os.path.join(WARDROBE_DIR, cat_dir_name)
        if not os.path.exists(cat_dir):
            print(f"  ⚠️ 目录不存在: {cat_dir}")
            continue

        # 获取品类目录下所有图片，按文件名排序
        images = sorted([
            f for f in os.listdir(cat_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
            and not f.startswith('.')
        ])

        if len(images) != len(items):
            print(f"  ⚠️ {cat_code} ({cat_dir_name}): 图片 {len(images)} ≠ 标签 {len(items)}，跳过")
            errors.append(f"{cat_code}: 数量不匹配")
            continue

        # 按标签 ID 排序（保证 LS-001, LS-002, ... 顺序）
        items.sort(key=lambda x: x[0])

        print(f"  {cat_code} ({cat_dir_name}): {len(items)} 件")

        for (cid, tag_path), img_name in zip(items, images):
            # 检查是否已有缩略图
            existing = glob.glob(os.path.join(ENHANCED_DIR, f'{cid}_thumb.*'))
            if existing:
                skipped += 1
                continue

            src_path = os.path.join(cat_dir, img_name)
            dst_path = os.path.join(ENHANCED_DIR, f'{cid}_thumb.png')

            try:
                generate_thumb(src_path, dst_path)
                generated += 1
                print(f"    ✅ {cid} ← {img_name}")
            except Exception as e:
                errors.append(f"{cid}: {e}")
                print(f"    ❌ {cid}: {e}")

    print(f"\n{'='*50}")
    print(f"✅ 生成: {generated} 张")
    print(f"⏭️ 已存在跳过: {skipped} 张")
    if errors:
        print(f"❌ 错误: {len(errors)}")
        for e in errors:
            print(f"   - {e}")

    # 3. 更新 _find_item_thumb 能识别的文件名
    print(f"\n缩略图保存在: {ENHANCED_DIR}")
    print("命名格式: {ID}_thumb.png (如 LS-001_thumb.png)")


def rename_cutout_for_item(clothing_id):
    """为重命名抠图文件为 ID 格式（如 LS-005_cutout.png）"""
    # 读取标签
    tag_path = os.path.join(TAGS_DIR, f'{clothing_id}.json')
    if not os.path.exists(tag_path):
        return None

    with open(tag_path) as f:
        data = json.load(f)

    cat_code = data.get('category_code', '?')
    cat_dir_name = CAT_DIRS.get(cat_code)
    if not cat_dir_name:
        return None

    cat_dir = os.path.join(WARDROBE_DIR, cat_dir_name)
    if not os.path.exists(cat_dir):
        return None

    # 获取该品类所有图片，最新的一张对应该衣服
    images = sorted([
        f for f in os.listdir(cat_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
        and not f.startswith('.')
    ])
    if not images:
        return None

    # 取最新图片
    img_name = images[-1]
    base_name = os.path.splitext(img_name)[0]
    src = os.path.join(ENHANCED_DIR, f'{base_name}_cutout.png')
    dst = os.path.join(ENHANCED_DIR, f'{clothing_id}_cutout.png')

    if os.path.exists(src) and not os.path.exists(dst):
        import shutil
        shutil.copy2(src, dst)
        return dst
    elif os.path.exists(dst):
        return dst
    return None


def generate_single_thumb(clothing_id):
    """为单件衣服生成缩略图（用于新衣服入库流程）
    按品类目录中时间最新的图片作为该衣服的原始图
    """
    # 读取标签
    tag_path = os.path.join(TAGS_DIR, f'{clothing_id}.json')
    if not os.path.exists(tag_path):
        print(f"  ❌ 标签文件不存在: {tag_path}")
        return None

    with open(tag_path) as f:
        data = json.load(f)

    cat_code = data.get('category_code', '?')
    cat_dir_name = CAT_DIRS.get(cat_code)
    if not cat_dir_name:
        print(f"  ❌ 未知品类: {cat_code}")
        return None

    cat_dir = os.path.join(WARDROBE_DIR, cat_dir_name)
    if not os.path.exists(cat_dir):
        print(f"  ❌ 目录不存在: {cat_dir}")
        return None

    # 获取该品类所有图片，取最新的一张
    images = sorted([
        f for f in os.listdir(cat_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
        and not f.startswith('.')
    ])
    if not images:
        print(f"  ❌ 品类目录无图片")
        return None

    src_path = os.path.join(cat_dir, images[-1])  # 最新图片
    dst_path = os.path.join(ENHANCED_DIR, f'{clothing_id}_thumb.png')

    try:
        generate_thumb(src_path, dst_path)
        print(f"  ✅ {clothing_id} ← {images[-1]}")
        return dst_path
    except Exception as e:
        print(f"  ❌ {clothing_id}: {e}")
        return None


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        # 单件模式：python3 tools/generate_thumbnails.py LS-005
        for cid in sys.argv[1:]:
            rename_cutout_for_item(cid)
            generate_single_thumb(cid)
    else:
        # 批量模式
        main()
