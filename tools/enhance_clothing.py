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


def auto_white_balance(img):
    if img.mode != 'RGB': img = img.convert('RGB')
    r, g, b = img.split()
    ra = sum(r.getdata()) / max(img.width * img.height, 1)
    ga = sum(g.getdata()) / max(img.width * img.height, 1)
    ba = sum(b.getdata()) / max(img.width * img.height, 1)
    avg = (ra + ga + ba) / 3.0
    if avg > 0:
        r = r.point(lambda x: min(255, int(x * avg / max(ra, 1))))
        g = g.point(lambda x: min(255, int(x * avg / max(ga, 1))))
        b = b.point(lambda x: min(255, int(x * avg / max(ba, 1))))
        return Image.merge('RGB', (r, g, b))
    return img


def refine_image(img):
    """精修管线"""
    if img.mode != 'RGB': img = img.convert('RGB')
    img = auto_white_balance(img)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.06)
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
    cutout = remove(img, alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=4)
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
