#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""布料解析模块 — SegFormer-B2 驱动的服装检测与分割

功能:
  - 从任意照片中检测并分割出服装单品
  - 返回每件单品的裁剪图 + 品类标签 + 遮挡评估
  - 用于 Phase 2 多件检测管线：上传→分割→逐件VLM分析→汇总

模型: mattmdjaga/segformer_b2_clothes (18类, ATR数据集)
推理: CPU ~1-3s/图, 109MB 权重（首次下载后缓存 ~/.cache/huggingface/）
"""

import os
import json
import time
import io as _io
import numpy as np
from PIL import Image as PILImage, ImageDraw as PILDraw

_MODEL = None
_PROCESSOR = None
_MODEL_LOCK = None  # 线程安全锁，延迟初始化


def _get_lock():
    import threading
    global _MODEL_LOCK
    if _MODEL_LOCK is None:
        _MODEL_LOCK = threading.Lock()
    return _MODEL_LOCK


def _load_model():
    """延迟加载模型（线程安全）"""
    global _MODEL, _PROCESSOR
    if _MODEL is not None:
        return _MODEL, _PROCESSOR

    with _get_lock():
        if _MODEL is not None:
            return _MODEL, _PROCESSOR

        from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
        import torch

        model_name = 'mattmdjaga/segformer_b2_clothes'
        _PROCESSOR = SegformerImageProcessor.from_pretrained(model_name)
        _MODEL = SegformerForSemanticSegmentation.from_pretrained(model_name)
        _MODEL.eval()

        return _MODEL, _PROCESSOR


# ── 品类映射：SegFormer class ID → 标准品类代码 ──
# 注意：合并左右鞋/左右腿/左右手臂为单一品类
CLASS_TO_CATEGORY = {
    1:  ('HAT',   '帽子',     '帽子'),
    3:  ('SUN',   '墨镜',     '墨镜'),
    4:  ('TS',    '短袖上衣', '上衣'),   # Upper-clothes → TS（VLM会细分）
    5:  ('SKIRT', '半身裙',   '下装'),
    6:  ('PT',    '长裤',     '下装'),
    7:  ('DRESS', '连衣裙',   '连衣裙'),
    8:  ('ACC',   '腰带',     '配饰'),
    9:  ('SHOE',  '鞋子',     '鞋子'),   # Left-shoe
    10: ('SHOE',  '鞋子',     '鞋子'),   # Right-shoe
    16: ('BAG',   '包',       '包'),
    17: ('ACC',   '围巾',     '配饰'),
}

# 需要合并的类（左右成对）
MERGE_PAIRS = [(9, 10)]   # 左右鞋合并为一双鞋
MERGE_MAP = {10: 9}       # right-shoe → left-shoe

# 最小裁剪面积（过滤噪点）
MIN_CROP_AREA = 2500  # 50x50 pixels


def parse_clothing(image_path_or_pil):
    """解析图片中的服装单品，返回裁剪区域列表。

    Args:
        image_path_or_pil: 图片路径 (str) 或 PIL Image 对象

    Returns:
        list[dict]: 每件服装单品的裁剪信息
            {
                'crop_image': PILImage,       # 裁剪后的单品图（RGB）
                'category_code': str,         # 标准品类代码（如 'SHOE', 'DRESS'）
                'category_name': str,          # 中文品类名
                'prefix': str,                # 品类前缀
                'bbox': (x1, y1, x2, y2),    # 在原图中的边界框（绝对像素）
                'bbox_norm': (x1, y1, x2, y2),  # 归一化边界框（0-1）
                'area_pct': float,            # 占原图面积百分比
                'completeness': 'full' | 'partial',  # 是否完整可见
                'confidence': float,          # 分割置信度 (0-1)
                'seg_class_id': int,          # SegFormer 原始类别 ID
                'mask': PILImage,             # 二值掩码（可选，用于展示）
            }
    """
    model, processor = _load_model()

    # 加载图片
    if isinstance(image_path_or_pil, str):
        img = PILImage.open(image_path_or_pil).convert('RGB')
    else:
        img = image_path_or_pil
        if img.mode != 'RGB':
            img = img.convert('RGB')

    orig_w, orig_h = img.size

    # ── 推理 ──
    import torch
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits  # shape: (1, num_classes, H/4, W/4)

    # 上采样到原始尺寸
    logits_up = torch.nn.functional.interpolate(
        logits, size=(orig_h, orig_w), mode='bilinear', align_corners=False
    )
    pred = logits_up.argmax(dim=1)[0].cpu().numpy()  # shape: (H, W)

    # 概率图（用于 confidence）
    probs = torch.nn.functional.softmax(logits_up, dim=1)[0].cpu().numpy()  # (C, H, W)

    # ── 合并左右成对品类 ──
    pred_merged = pred.copy()
    for src, dst in MERGE_MAP.items():
        pred_merged[pred == src] = dst

    # ── 提取每个品类的连通区域 ──
    from scipy import ndimage as _ndi

    items = []
    processed_classes = set()

    for class_id, (cat_code, cat_name, prefix) in CLASS_TO_CATEGORY.items():
        # 合并后的类（如右鞋已合并到左鞋）
        if class_id in MERGE_MAP:
            continue

        # 找到该类别的所有像素
        mask = (pred_merged == class_id)
        if mask.sum() < MIN_CROP_AREA:
            continue

        # 查找连通区域
        labeled, num_features = _ndi.label(mask)

        for region_id in range(1, num_features + 1):
            region_mask = (labeled == region_id)
            region_area = region_mask.sum()

            if region_area < MIN_CROP_AREA:
                continue

            # 获取边界框
            ys, xs = np.where(region_mask)
            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())

            # 计算置信度（区域内该类的平均概率）
            region_conf = float(probs[class_id][region_mask].mean())

            # 遮挡检测：边界框触及图像边缘
            edge_margin = 5  # pixels
            touches_edge = (
                x1 <= edge_margin or y1 <= edge_margin or
                x2 >= orig_w - edge_margin or y2 >= orig_h - edge_margin
            )
            completeness = 'partial' if touches_edge else 'full'

            # 裁剪区域（略微扩展边界，给 VLM 更多上下文）
            pad = int(min(orig_w, orig_h) * 0.02)  # 2% padding
            crop_x1 = max(0, x1 - pad)
            crop_y1 = max(0, y1 - pad)
            crop_x2 = min(orig_w, x2 + pad)
            crop_y2 = min(orig_h, y2 + pad)

            crop = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

            # 生成二值掩码
            mask_img = PILImage.fromarray((region_mask * 255).astype(np.uint8), mode='L')
            mask_crop = mask_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

            items.append({
                'crop_image': crop,
                'category_code': cat_code,
                'category_name': cat_name,
                'prefix': prefix,
                'bbox': (x1, y1, x2, y2),
                'bbox_norm': (x1/orig_w, y1/orig_h, x2/orig_w, y2/orig_h),
                'area_pct': round(region_area / (orig_w * orig_h) * 100, 1),
                'completeness': completeness,
                'confidence': round(region_conf, 3),
                'seg_class_id': class_id,
                'mask': mask_crop,
            })

    # ── 按面积降序排列（主要单品优先）──
    items.sort(key=lambda x: x['area_pct'], reverse=True)

    return items


def parse_and_save(image_path, output_dir):
    """解析服装单品并保存裁剪图到目录。

    Args:
        image_path: 输入图片路径
        output_dir: 输出目录

    Returns:
        list[dict]: 每件单品的元数据（crop_image 替换为文件路径）
    """
    os.makedirs(output_dir, exist_ok=True)
    items = parse_clothing(image_path)

    results = []
    for i, item in enumerate(items):
        # 保存裁剪图
        crop_filename = f'crop_{i:02d}_{item["category_code"]}_{item["confidence"]:.0f}.jpg'
        crop_path = os.path.join(output_dir, crop_filename)
        item['crop_image'].save(crop_path, 'JPEG', quality=90)

        # 保存掩码
        mask_filename = f'mask_{i:02d}_{item["category_code"]}.png'
        mask_path = os.path.join(output_dir, mask_filename)
        item['mask'].save(mask_path, 'PNG')

        result = {k: v for k, v in item.items() if k not in ('crop_image', 'mask')}
        result['crop_path'] = crop_path
        result['mask_path'] = mask_path
        results.append(result)

    return results


def create_overlay_preview(image_path, items):
    """创建可视化预览：原图上叠加分割区域。

    Returns:
        PILImage: 带彩色遮罩和 bbox 的预览图
    """
    if isinstance(image_path, str):
        img = PILImage.open(image_path).convert('RGB')
    else:
        img = image_path
        if img.mode != 'RGB':
            img = img.convert('RGB')

    # 品类 → 颜色映射
    COLOR_MAP = {
        'HAT':   (255, 200, 50),    # 金色
        'SUN':   (100, 200, 255),   # 浅蓝
        'TS':    (50, 200, 100),    # 绿色
        'SKIRT': (255, 100, 150),   # 粉色
        'PT':    (100, 150, 255),   # 蓝色
        'DRESS': (200, 100, 255),   # 紫色
        'SHOE':  (255, 150, 50),    # 橙色
        'BAG':   (150, 200, 100),   # 黄绿
        'ACC':   (200, 200, 200),   # 灰色
    }

    overlay = img.copy().convert('RGBA')
    draw = PILDraw.Draw(overlay)

    for item in items:
        cat = item['category_code']
        color = COLOR_MAP.get(cat, (255, 255, 0))
        x1, y1, x2, y2 = item['bbox']

        # 绘制边界框
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

        # 绘制标签（用英文代码避免中文 PIL 字体问题）
        label = f"{item['category_code']} {item['confidence']:.0%}"
        tw = len(label) * 7
        draw.rectangle([x1, y1-22, x1+tw+8, y1], fill=(*color, 180))
        try:
            draw.text((x1+4, y1-20), label, fill=(255, 255, 255))
        except UnicodeEncodeError:
            # PIL 默认字体不支持中文，用 ASCII 标签
            ascii_label = f"{item['category_code']} {item['confidence']:.0%}"
            draw.text((x1+4, y1-20), ascii_label, fill=(255, 255, 255))

        # 叠加半透明遮罩
        if 'mask' in item:
            mask = item['mask'].resize((x2-x1, y2-y1))
            mask_rgba = PILImage.new('RGBA', (x2-x1, y2-y1), (*color, 60))
            overlay.paste(mask_rgba, (x1, y1), mask)

    return overlay


# ── CLI 测试 ──
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 tools/cloth_parser.py <image_path> [output_dir]")
        sys.exit(1)

    img_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else '/tmp/cloth_parse_test'

    print(f"解析: {img_path}")
    t0 = time.time()
    items = parse_clothing(img_path)
    elapsed = time.time() - t0

    print(f"耗时: {elapsed:.1f}s, 检测到 {len(items)} 件服装:")
    for item in items:
        status = '⚠️ 部分遮挡' if item['completeness'] == 'partial' else '✅'
        print(f"  {status} {item['category_name']}({item['category_code']}) "
              f"bbox={item['bbox']} area={item['area_pct']}% conf={item['confidence']:.0%}")

    if out_dir:
        results = parse_and_save(img_path, out_dir)
        print(f"\n裁剪结果已保存至: {out_dir}")

        # 生成预览图
        preview = create_overlay_preview(img_path, items)
        preview_path = os.path.join(out_dir, '_preview_overlay.png')
        preview.save(preview_path, 'PNG')
        print(f"预览图: {preview_path}")
