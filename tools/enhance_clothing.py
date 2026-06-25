#!/usr/bin/env python3
"""
服装照片精修工具
1. AI 抠图去背景（rembg）
2. 自动白平衡 + 色阶 + 锐化
3. 透明 PNG + 增强 JPG 双份输出
"""
import os, sys
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
from rembg import remove

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WARDROBE = os.path.join(BASE_DIR, '..', 'wardrobe')
ENHANCED_DIR = os.path.join(BASE_DIR, '..', 'wardrobe', 'enhanced')


def refine_image(img):
    """精修管线 — 仅亮度校正，不动色相/白平衡"""
    if img.mode != 'RGB': img = img.convert('RGB')
    import numpy as np
    arr = np.array(img).astype(float)
    lum = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
    avg_lum = lum.mean()
    if avg_lum < 100:
        factor = min(1.25, 110 / max(avg_lum, 1))
        arr = np.clip(arr * factor, 0, 255)
        img = Image.fromarray(arr.astype(np.uint8))
    img = ImageEnhance.Sharpness(img).enhance(1.2)
    return img


def enhance_image(src_path, cutout_path, enhanced_jpg_path):
    """
    抠图 + 精修:
    - cutout_path: 透明背景 PNG
    - enhanced_jpg_path: 精修 JPG（保留原背景，备用）
    """
    # 原图
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)

    # 抠图（rembg AI + alpha matting 精细边缘）
    cutout = remove(img)  # 默认参数，不加 alpha_matting（避免侵蚀边缘）
    if cutout.mode != 'RGBA': cutout = cutout.convert('RGBA')
    # 缩放到合理尺寸（最长边 1200px，节省空间）
    w, h = cutout.size
    if max(w, h) > 1200:
        ratio = 1200 / max(w, h)
        cutout = cutout.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)

    os.makedirs(os.path.dirname(cutout_path), exist_ok=True)
    cutout.save(cutout_path, 'PNG')

    # 精修版 JPG
    if img.mode != 'RGB': img = img.convert('RGB')
    enhanced = refine_image(img)
    os.makedirs(os.path.dirname(enhanced_jpg_path), exist_ok=True)
    enhanced.save(enhanced_jpg_path, 'JPEG', quality=95)

    return cutout.size


def enhance_wardrobe(force=False):
    """批量处理衣橱"""
    os.makedirs(ENHANCED_DIR, exist_ok=True)
    total, done, skipped = 0, 0, 0

    for root, dirs, files in os.walk(WARDROBE):
        if 'enhanced' in root: continue
        for f in sorted(files):
            if not f.lower().endswith(('.jpg','.jpeg','.png')) or f.startswith('.'):
                continue
            src = os.path.join(root, f)
            total += 1

            name = os.path.splitext(f)[0]
            cutout_path = os.path.join(ENHANCED_DIR, name + '_cutout.png')
            enhanced_path = os.path.join(ENHANCED_DIR, f)

            if not force and os.path.exists(cutout_path):
                skipped += 1
                continue

            try:
                sz = enhance_image(src, cutout_path, enhanced_path)
                rel = os.path.relpath(src, WARDROBE)
                print(f'  ✨ {rel} → 抠图 {sz[0]}x{sz[1]}')
                done += 1
            except Exception as e:
                print(f'  ❌ {f}: {e}')

    print(f'\n{"="*50}')
    print(f'总计: {total} | 处理: {done} | 已有: {skipped}')
    print(f'目录: {ENHANCED_DIR}')


def get_cutout_path(original_path):
    """获取抠图 PNG 路径"""
    name = os.path.splitext(os.path.basename(original_path))[0]
    cp = os.path.join(ENHANCED_DIR, name + '_cutout.png')
    return cp if os.path.exists(cp) else None


def get_enhanced_path(original_path):
    """获取精修 JPG 路径"""
    ep = os.path.join(ENHANCED_DIR, os.path.basename(original_path))
    return ep if os.path.exists(ep) else None


if __name__ == '__main__':
    force = '--force' in sys.argv
    print("=" * 50)
    print("✨ 服装抠图 + 精修")
    print("=" * 50)
    enhance_wardrobe(force=force)
