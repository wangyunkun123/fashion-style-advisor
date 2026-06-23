#!/usr/bin/env python3
"""
批量校正衣橱图片方向：EXIF 旋转 + 强制竖图（领口在上、衣摆在下）
"""
import os, sys
from PIL import Image, ImageOps

WARDROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wardrobe')

def fix_orientation(path):
    """校正单张图片：EXIF旋转 + 横图转竖"""
    img = Image.open(path)
    original_size = img.size

    # 1. EXIF 自动旋转
    img = ImageOps.exif_transpose(img)

    # 2. 横图转竖（顺时针旋转90度）
    w, h = img.size
    if w > h:
        img = img.transpose(Image.ROTATE_90)
        changed = True
    else:
        changed = original_size != img.size  # 仅 EXIF 改变

    if changed:
        # 保存：保留 EXIF 但清除旋转标记
        img.save(path, quality=95)
        return True
    img.close()
    return False

def main():
    fixed = 0
    skipped = 0
    errors = []

    for root, dirs, files in os.walk(WARDROBE):
        for f in sorted(files):
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            if f.startswith('.'):
                continue
            fpath = os.path.join(root, f)
            try:
                if fix_orientation(fpath):
                    rel = os.path.relpath(fpath, WARDROBE)
                    print(f"  ✅ {rel}")
                    fixed += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append((fpath, str(e)))
                print(f"  ❌ {fpath}: {e}")

    print(f"\n{'='*50}")
    print(f"修复: {fixed} 件 | 无需处理: {skipped} 件 | 错误: {len(errors)} 件")
    if errors:
        for p, e in errors:
            print(f"  ⚠️ {p}: {e}")

if __name__ == '__main__':
    main()
