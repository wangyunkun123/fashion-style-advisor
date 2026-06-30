#!/usr/bin/env python3
"""
批量白平衡校正 — 白斑百分位法增强版
专门处理白色服装摄影偏蓝偏青问题。

相比 smart_white_balance，增强：
- 降低饱和度阈值（20 替代 30），确保偏色严重的白色像素不被过滤
- 不使用全局色彩丰富度跳过（白色衣服整体色散低）
- 加大校正力度（默认 0.6）
- 增加亮区采样比例（top 10% 替代 5%）
"""

import numpy as np
from PIL import Image, ImageOps
import os, sys

_LUM_R, _LUM_G, _LUM_B = 0.2126, 0.7152, 0.0722


def correct_white_balance(img, aggressiveness=0.7):
    """
    增强白平衡校正：专为白色服装产品图设计。

    参数:
        img: PIL Image (RGB)
        aggressiveness: 0.0-1.0，默认 0.7（白色服装可更激进）

    返回:
        (corrected_img, did_correct, diagnosis_dict)
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')

    arr = np.array(img).astype(np.float64)
    h, w = arr.shape[:2]
    total_pixels = h * w

    if total_pixels < 100:
        return img, False, {"error": "image too small"}

    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]

    # ── 步骤 1: 亮度排序，取 Top 10% ──
    lum = _LUM_R * r + _LUM_G * g + _LUM_B * b
    threshold = float(np.percentile(lum, 90))
    bright_mask = lum >= threshold
    bright_count = int(bright_mask.sum())

    if bright_count < total_pixels * 0.01:
        return img, False, {"error": f"bright pixels too few: {bright_count}"}

    # ── 步骤 2: 宽松饱和度过滤 ──
    br, bg, bb = r[bright_mask], g[bright_mask], b[bright_mask]

    # 使用更宽松的饱和度阈值 (40 替代 30)，因为严重偏色的白色也有较大通道差
    saturation_map = np.maximum(np.maximum(br, bg), bb) - np.minimum(np.minimum(br, bg), bb)
    low_sat_mask = saturation_map < 40
    neutral_count = int(low_sat_mask.sum())

    # 降级策略：如果 < 1%，降低阈值再试
    if neutral_count < total_pixels * 0.005:
        low_sat_mask = saturation_map < 55
        neutral_count = int(low_sat_mask.sum())

    if neutral_count < total_pixels * 0.003:
        # 最后手段：直接用所有亮区像素
        low_sat_mask = np.ones(bright_count, dtype=bool)
        neutral_count = bright_count

    # ── 步骤 3: 光源色估计 ──
    illum_r = float(br[low_sat_mask].mean())
    illum_g = float(bg[low_sat_mask].mean())
    illum_b = float(bb[low_sat_mask].mean())

    # ── 步骤 4: 中性检查 ──
    max_illum = max(illum_r, illum_g, illum_b)
    min_illum = min(illum_r, illum_g, illum_b)

    if max_illum / min_illum < 1.03:
        return img, False, {
            "illum_r": round(illum_r, 1), "illum_g": round(illum_g, 1), "illum_b": round(illum_b, 1),
            "ratio": round(max_illum / min_illum, 3),
            "reason": "already neutral"
        }

    # ── 步骤 5: 计算校正系数 ──
    illum_gray = (illum_r + illum_g + illum_b) / 3.0
    mul_r = 1.0 + (illum_gray / illum_r - 1.0) * aggressiveness
    mul_g = 1.0 + (illum_gray / illum_g - 1.0) * aggressiveness
    mul_b = 1.0 + (illum_gray / illum_b - 1.0) * aggressiveness

    # 限制校正幅度：白色服装允许更大范围 (0.75-1.30)
    mul_r = np.clip(mul_r, 0.75, 1.30)
    mul_g = np.clip(mul_g, 0.75, 1.30)
    mul_b = np.clip(mul_b, 0.75, 1.30)

    # ── 步骤 6: 应用校正 ──
    arr[:,:,0] = np.clip(arr[:,:,0] * mul_r, 0, 255)
    arr[:,:,1] = np.clip(arr[:,:,1] * mul_g, 0, 255)
    arr[:,:,2] = np.clip(arr[:,:,2] * mul_b, 0, 255)

    return Image.fromarray(arr.astype(np.uint8)), True, {
        "illum_r": round(illum_r, 1), "illum_g": round(illum_g, 1), "illum_b": round(illum_b, 1),
        "ratio": round(max_illum / min_illum, 3),
        "mul_r": round(mul_r, 4), "mul_g": round(mul_g, 4), "mul_b": round(mul_b, 4),
        "neutral_pixels": neutral_count,
        "bright_pixels": bright_count,
    }


def process_item(original_path, output_path=None, aggressiveness=0.7):
    """处理单件服装：加载 → 校正 → 保存"""
    if output_path is None:
        base, ext = os.path.splitext(original_path)
        output_path = f"{base}_wb{ext}"

    img = Image.open(original_path)
    img = ImageOps.exif_transpose(img)

    corrected, did_correct, info = correct_white_balance(img, aggressiveness)

    if did_correct:
        corrected.save(output_path, quality=95)

    return did_correct, info, output_path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/batch_white_balance.py --diagnose <image_path>")
        print("  python3 tools/batch_white_balance.py <image_path> [output_path]")
        print("  python3 tools/batch_white_balance.py --batch")
        sys.exit(0)

    if sys.argv[1] == '--batch':
        # 批量处理 nan 的白色服装
        base = "users/female/nan/wardrobe"
        items = [
            ("短袖上衣/Image_20260630_143049_TS-004.jpg", "TS-004"),
            ("短袖上衣/Image_20260630_142918_TS-002.jpg", "TS-002"),
            ("衬衣/Image_20260630_144108_SHIRT-002.jpg", "SHIRT-002"),
            ("连衣裙/Image_20260624_231022_DRESS-004.jpg", "DRESS-004"),
            ("连衣裙/Image_20260630_143252_DRESS-007.jpg", "DRESS-007"),
            ("连体裤/Image_20260630_143545_JMP-001.jpg", "JMP-001"),
        ]

        print("=" * 72)
        print("🔧 批量白平衡校正 — nan 白色服装")
        print("=" * 72)

        results = []
        for rel_path, item_id in items:
            original = os.path.join(base, rel_path)
            if not os.path.exists(original):
                print(f"❌ {item_id}: 文件不存在")
                continue

            did_correct, info, out_path = process_item(original, aggressiveness=0.7)

            status = "✅ 已校正" if did_correct else "⏭️ 跳过"
            print(f"{status} {item_id}: ", end="")
            if did_correct:
                print(f"光源 R{info['illum_r']} G{info['illum_g']} B{info['illum_b']} "
                      f"比值{info['ratio']} → 修正 R×{info['mul_r']} G×{info['mul_g']} B×{info['mul_b']}")
            else:
                print(info.get('reason', info.get('error', 'unknown')))

            results.append((item_id, did_correct, info, out_path if did_correct else None))

        print()
        print("=" * 72)
        corrected_count = sum(1 for r in results if r[1])
        print(f"📊 处理完成: {corrected_count}/{len(results)} 件已校正")

        if corrected_count > 0:
            print()
            print("已校正文件:")
            for item_id, did, info, path in results:
                if did:
                    print(f"  {item_id}: {path}")

    elif sys.argv[1] == '--diagnose':
        # 诊断模式（测试校正效果）
        img_path = sys.argv[2]
        img = Image.open(img_path)
        img = ImageOps.exif_transpose(img)
        corrected, did_correct, info = correct_white_balance(img, aggressiveness=0.7)

        print(f"📷 {img_path}")
        if did_correct:
            print(f"   🔧 会触发校正")
            print(f"   光源: R={info['illum_r']} G={info['illum_g']} B={info['illum_b']} "
                  f"比值={info['ratio']}")
            print(f"   修正系数: R×{info['mul_r']} G×{info['mul_g']} B×{info['mul_b']}")
            print(f"   采样: {info['neutral_pixels']}/{info['bright_pixels']} 亮区像素")
        else:
            print(f"   ⏭️ 跳过: {info.get('reason', info.get('error', 'unknown'))}")

    else:
        # 单文件校正
        img_path = sys.argv[1]
        out_path = sys.argv[2] if len(sys.argv) > 2 else None
        did_correct, info, saved = process_item(img_path, out_path)

        if did_correct:
            print(f"✅ 已校正 → {saved}")
            print(f"   光源: R={info['illum_r']} G={info['illum_g']} B={info['illum_b']} "
                  f"比值={info['ratio']}")
            print(f"   修正系数: R×{info['mul_r']} G×{info['mul_g']} B×{info['mul_b']}")
        else:
            print(f"⏭️ 跳过: {info.get('reason', info.get('error', 'unknown'))}")
