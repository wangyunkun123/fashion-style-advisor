#!/usr/bin/env python3
"""
智能白平衡 — 白斑百分位法 + 多重保护

替代灰度世界算法。核心思路：
- 灰度世界：假设全图平均色 = 中性灰 → ❌ 彩色衣服被褪色
- 白斑法：只看最亮最白的像素估计光源色 → ✅ 只校正照明偏色

算法步骤：
1. 亮度最高的 5% 像素作为候选白斑
2. 饱和度过滤：只保留低饱和度像素（max-min < 30）
3. 太少则跳过（可能是纯色衣服，没有中性参考区）
4. 计算这些白斑像素的 RGB 均值 → 光源色估计
5. 光源已中性（max/min < 1.08）→ 跳过
6. 全局色彩丰富度 > 30 → 彩色服装，跳过
7. 部分校正（aggressiveness=0.4），避免过度修正
"""

import numpy as np

# 亮度权重 (Rec.709)
_LUM_R, _LUM_G, _LUM_B = 0.2126, 0.7152, 0.0722


def smart_white_balance(img, aggressiveness=0.4):
    """
    智能白平衡：仅在检测到照明偏色时温和校正。

    参数:
        img: PIL Image (RGB 模式)
        aggressiveness: 校正力度 0.0-1.0，默认 0.4（只校正 40%）

    返回:
        PIL Image (RGB 模式)，可能已校正或原样返回
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')

    arr = np.array(img).astype(np.float64)
    h, w = arr.shape[:2]
    total_pixels = h * w
    if total_pixels < 100:
        return img  # 太小，无意义

    # ── 步骤 1: 亮度排序，取 Top 5% ──
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum = _LUM_R * r + _LUM_G * g + _LUM_B * b
    threshold = float(np.percentile(lum, 95))
    bright_mask = lum >= threshold
    bright_count = int(bright_mask.sum())

    if bright_count < total_pixels * 0.01:
        return img  # 亮区太少，不可靠

    # ── 步骤 2: 饱和度过滤 ──
    br, bg, bb = r[bright_mask], g[bright_mask], b[bright_mask]
    saturation = br.max() - br.min() if bright_count > 0 else 0  # 用于后续检查
    low_sat_mask = (np.maximum(np.maximum(br, bg), bb) -
                    np.minimum(np.minimum(br, bg), bb)) < 30
    neutral_bright = low_sat_mask.sum()

    if neutral_bright < total_pixels * 0.02:
        # 亮区中低饱和度像素不足 2% → 纯色衣服，无中性参考
        return img

    # ── 步骤 3: 光源色估计 ──
    illum_r = float(br[low_sat_mask].mean())
    illum_g = float(bg[low_sat_mask].mean())
    illum_b = float(bb[low_sat_mask].mean())

    if illum_r <= 0 or illum_g <= 0 or illum_b <= 0:
        return img

    # ── 步骤 4: 中性检查 ──
    max_illum = max(illum_r, illum_g, illum_b)
    min_illum = min(illum_r, illum_g, illum_b)
    if max_illum / min_illum < 1.08:
        return img  # 光源已足够中性

    # ── 步骤 5: 全局色彩丰富度检查 ──
    global_spread = float((np.maximum(np.maximum(r, g), b) -
                            np.minimum(np.minimum(r, g), b)).mean())
    if global_spread > 35:
        return img  # 彩色服装，不应校正

    # ── 步骤 6: 部分校正 ──
    illum_gray = (illum_r + illum_g + illum_b) / 3.0
    mul_r = 1.0 + (illum_gray / illum_r - 1.0) * aggressiveness
    mul_g = 1.0 + (illum_gray / illum_g - 1.0) * aggressiveness
    mul_b = 1.0 + (illum_gray / illum_b - 1.0) * aggressiveness

    # 限制校正幅度：单通道不超过 15%
    mul_r = np.clip(mul_r, 0.85, 1.15)
    mul_g = np.clip(mul_g, 0.85, 1.15)
    mul_b = np.clip(mul_b, 0.85, 1.15)

    arr[:,:,0] = np.clip(arr[:,:,0] * mul_r, 0, 255)
    arr[:,:,1] = np.clip(arr[:,:,1] * mul_g, 0, 255)
    arr[:,:,2] = np.clip(arr[:,:,2] * mul_b, 0, 255)

    from PIL import Image as _PILImage
    return _PILImage.fromarray(arr.astype(np.uint8))


def diagnose_image(img_path):
    """
    诊断工具：打印图片的 WB 分析信息，不修改图片。
    用法: python3 tools/white_balance.py <image_path>
    """
    from PIL import Image as _PILImage, ImageOps as _ImageOps
    img = _PILImage.open(img_path)
    img = _ImageOps.exif_transpose(img)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    arr = np.array(img).astype(np.float64)
    h, w = arr.shape[:2]
    total = h * w

    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum = _LUM_R * r + _LUM_G * g + _LUM_B * b

    print(f"📷 {img_path}")
    print(f"   尺寸: {w}x{h} ({total} 像素)")
    print(f"   全局 RGB 均值: R={r.mean():.1f} G={g.mean():.1f} B={b.mean():.1f}")
    print(f"   RGB max/min 比值: {max(r.mean(), g.mean(), b.mean()) / min(r.mean(), g.mean(), b.mean()):.3f}")

    threshold = float(np.percentile(lum, 95))
    bright_mask = lum >= threshold
    bright_count = int(bright_mask.sum())
    print(f"   亮度 Top 5% 阈值: {threshold:.1f} ({bright_count} 像素, {100*bright_count/total:.1f}%)")

    br, bg, bb = r[bright_mask], g[bright_mask], b[bright_mask]
    low_sat_mask = (np.maximum(np.maximum(br, bg), bb) -
                    np.minimum(np.minimum(br, bg), bb)) < 30
    neutral_bright = low_sat_mask.sum()
    print(f"   亮区低饱和像素: {neutral_bright} ({100*neutral_bright/total:.1f}%)")

    global_spread = float((np.maximum(np.maximum(r, g), b) -
                            np.minimum(np.minimum(r, g), b)).mean())
    print(f"   全局色彩丰富度: {global_spread:.1f}")

    if neutral_bright >= total * 0.02:
        illum_r = float(br[low_sat_mask].mean())
        illum_g = float(bg[low_sat_mask].mean())
        illum_b = float(bb[low_sat_mask].mean())
        print(f"   光源估计 RGB: R={illum_r:.1f} G={illum_g:.1f} B={illum_b:.1f}")
        print(f"   光源 max/min: {max(illum_r, illum_g, illum_b) / min(illum_r, illum_g, illum_b):.3f}")

        # 判断
        checks = []
        if neutral_bright < total * 0.02:
            checks.append("❌ 中性参考不足 → 跳过")
        if max(illum_r, illum_g, illum_b) / min(illum_r, illum_g, illum_b) < 1.08:
            checks.append("✅ 光源已中性 → 跳过")
        if global_spread > 35:
            checks.append("🎨 彩色服装 → 跳过")
        if not checks:
            checks.append("🔧 会触发校正")
        for ck in checks:
            print(f"   判断: {ck}")
    else:
        print(f"   判断: ⛔ 中性参考像素不足 → 跳过（可能是纯色衣服）")


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python3 tools/white_balance.py <image_path>  — 诊断模式")
        print("      python3 tools/white_balance.py --batch <dir>  — 批量诊断")
        sys.exit(0)
    if sys.argv[1] == '--batch':
        import os
        d = sys.argv[2]
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(('.jpg','.jpeg','.png')):
                diagnose_image(os.path.join(d, f))
                print()
    else:
        diagnose_image(sys.argv[1])
