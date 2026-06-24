#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服装白底提取模块 — Seedream 整件重构到纯白背景 + 程序化去白底

优于旧方案 (complete_clothing.py):
  - 旧方案: 灰底抠图 + 局部 inpainting = 看得出裁剪修补痕迹
  - 新方案: 整件重构到白底 + 阈值去白底 = 专业电商商品图效果

流程:
  1. SegFormer 检测 → 裁剪服装区域
  2. extract_to_white_bg() → Seedream 重构完整服装到纯白背景
  3. remove_white_background() → 阈值去白底 → 透明PNG + 灰底JPG
"""

import os
import json
import base64
import time
import io as _io
import urllib.request
import urllib.error
import numpy as np
from PIL import Image as PILImage, ImageFilter as _PILFilter

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_seedream_config():
    """加载 Seedream API 配置"""
    cfg = {}
    for fname in ['seedream.json', 'seedream.local.json']:
        path = os.path.join(_BASE_DIR, 'config', fname)
        if os.path.exists(path):
            with open(path, 'r') as f:
                cfg.update(json.load(f))
    return cfg


def _encode_image(img_or_path, max_size=1024):
    """将 PIL Image 或路径编码为 base64 data URL"""
    if isinstance(img_or_path, str):
        img = PILImage.open(img_or_path).convert('RGB')
    else:
        img = img_or_path
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)

    buf = _io.BytesIO()
    # RGBA → 白底 RGB（让 Seedream 看到干净的输入）
    if img.mode == 'RGBA':
        bg = PILImage.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img.save(buf, format='JPEG', quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


def extract_to_white_bg(crop_image, category_hint='', max_retries=2, timeout=180):
    """用 Seedream 将服装单品重构到纯白背景。

    与旧 complete_clothing 的区别：
      - 不要求 mask，不依赖 inpainting
      - 让模型从零生成完整服装 + 纯白背景
      - 适用范围：所有 crop（partial 和 full 都走）

    Args:
        crop_image: PIL Image 或路径 — 服装裁剪区域
        category_hint: str — 品类提示（如 'TS', 'PT', 'DRESS'）
        max_retries: int
        timeout: int

    Returns:
        dict: {
            'white_bg_image': PILImage or None,
            'white_bg_bytes': bytes,
            'used': bool,
            'prompt': str,
            'error': str or None,
        }
    """
    cfg = _load_seedream_config()
    api_url = cfg.get('api_url', '')
    api_key = cfg.get('api_key', '')
    model = cfg.get('model', 'doubao-seedream-5.0-lite')

    if not api_key or not api_url:
        return {'white_bg_image': None, 'white_bg_bytes': b'',
                'used': False, 'prompt': '',
                'error': 'Seedream 配置缺失'}

    # 品类中文名
    cat_names = {
        'TS': 'short-sleeve t-shirt', 'LS': 'long-sleeve top', 'SHIRT': 'shirt',
        'TANK': 'tank top', 'JK': 'jacket', 'PT': 'pants', 'SH': 'shorts',
        'SHOE': 'shoes', 'DRESS': 'dress', 'SKIRT': 'skirt', 'JMP': 'jumpsuit',
        'BLOUSE': 'blouse', 'KNIT': 'knitwear', 'HAT': 'hat', 'BAG': 'bag',
        'SUN': 'sunglasses', 'ACC': 'accessory',
    }
    cat_en = cat_names.get(category_hint, 'clothing item')

    # 参考图编码
    ref_b64 = _encode_image(crop_image, max_size=1024)

    # 核心 prompt：提取服装 + 重构到纯白背景
    prompt = f"""Extract and recreate this {cat_en} as a clean, complete product shot.

Place the item centered on a pure white background — the background must be exactly #FFFFFF (RGB 255, 255, 255), no gradients, no shadows on the floor.

Front-facing flat lay, professional fashion product photography, studio lighting.
The item must look complete with proper edges, sleeves, collar, hemline, waistband, etc.
No mannequin, no hanger, no human body parts, no skin visible.
High quality, sharp details, accurate fabric texture and color — match the reference exactly.

The final image should look like a professional e-commerce product photo: isolated {cat_en} on pure white."""

    for attempt in range(max_retries + 1):
        try:
            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "image": [ref_b64],
                "size": cfg.get('size', '1024x1024'),
                "response_format": "url",
                "watermark": False,
                "max_images": 1,
            }).encode('utf-8')

            req = urllib.request.Request(api_url, data=payload, headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            })

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            if 'data' in result and result['data']:
                img_url = result['data'][0].get('url', '')
                if img_url:
                    try:
                        img_req = urllib.request.Request(img_url)
                        with urllib.request.urlopen(img_req, timeout=30) as img_resp:
                            img_bytes = img_resp.read()
                        white_bg_img = PILImage.open(_io.BytesIO(img_bytes))
                        return {
                            'white_bg_image': white_bg_img,
                            'white_bg_bytes': img_bytes,
                            'used': True,
                            'prompt': prompt,
                            'error': None,
                        }
                    except Exception as _de:
                        if attempt < max_retries:
                            time.sleep(2)
                            continue
                        return {'white_bg_image': None, 'white_bg_bytes': b'',
                                'used': True, 'prompt': prompt,
                                'error': f'下载失败: {str(_de)[:100]}'}
            else:
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return {'white_bg_image': None, 'white_bg_bytes': b'',
                        'used': True, 'prompt': prompt,
                        'error': f'API 未返回图片: {str(result)[:200]}'}

        except urllib.error.HTTPError as e:
            err_body = ''
            try:
                err_body = e.read().decode('utf-8')[:300]
            except Exception:
                pass
            if attempt < max_retries and e.code >= 500:
                time.sleep(3)
                continue
            return {'white_bg_image': None, 'white_bg_bytes': b'',
                    'used': True, 'prompt': prompt,
                    'error': f'API {e.code}: {err_body}'}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {'white_bg_image': None, 'white_bg_bytes': b'',
                    'used': True, 'prompt': prompt,
                    'error': str(e)[:200]}

    return {'white_bg_image': None, 'white_bg_bytes': b'',
            'used': True, 'prompt': prompt,
            'error': '重试耗尽'}


def remove_white_background(image, threshold=240, feather_radius=2,
                            bg_color=(217, 217, 217)):
    """移除纯白背景，输出透明 PNG + 中性灰底 JPG。

    原理：Seedream 输出是白底(#FFFFFF)商品图，白像素可精确识别。
    相比之下，旧方案从复杂背景抠图 → 边缘不准。白底去底几乎零人工痕迹。

    Args:
        image: PIL Image — 白底商品图 (RGB)
        threshold: int — 白色阈值 (0-255)，三通道都 > 此值视为白色
        feather_radius: int — 边缘羽化像素
        bg_color: tuple — JPG 中性灰底色

    Returns:
        dict: {
            'cutout_png': PILImage (RGBA),
            'cutout_jpg': PILImage (RGB),
            'cutout_bytes_png': bytes,
            'cutout_bytes_jpg': bytes,
        }
    """
    img = image
    if img.mode != 'RGB':
        img = img.convert('RGB')

    arr = np.array(img, dtype=np.float32)

    # 白色检测：RGB 三通道都 > threshold
    is_white = np.all(arr > threshold, axis=2)

    # alpha 通道：白色→0（透明），非白色→255（不透明）
    alpha = np.where(is_white, 0, 255).astype(np.uint8)

    # 转换 alpha → PIL Image 并羽化（避免硬边）
    alpha_img = PILImage.fromarray(alpha, mode='L')
    if feather_radius > 0:
        alpha_img = alpha_img.filter(_PILFilter.GaussianBlur(radius=feather_radius))

    # 透明 PNG
    img_rgba = img.copy().convert('RGBA')
    img_rgba.putalpha(alpha_img)

    png_buf = _io.BytesIO()
    img_rgba.save(png_buf, format='PNG', optimize=True)
    png_buf.seek(0)

    # 中性灰底 JPG（给 VLM 看 / 兼容旧流程）
    bg = PILImage.new('RGB', img.size, bg_color)
    bg.paste(img_rgba, mask=img_rgba.split()[3])
    jpg_buf = _io.BytesIO()
    bg.save(jpg_buf, format='JPEG', quality=90)
    jpg_buf.seek(0)

    return {
        'cutout_png': img_rgba,
        'cutout_jpg': bg,
        'cutout_bytes_png': png_buf.read(),
        'cutout_bytes_jpg': jpg_buf.read(),
    }


# ── CLI 测试 ──
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 tools/extract_clothing.py <crop_image_path> [category_hint]")
        print("  e.g. python3 tools/extract_clothing.py /tmp/crop_ts.jpg TS")
        sys.exit(1)

    img_path = sys.argv[1]
    cat_hint = sys.argv[2] if len(sys.argv) > 2 else 'TS'

    print(f"白底提取: {img_path} (品类: {cat_hint})")

    # Step 1: Seedream 重构到白底
    print("→ Seedream 重构到白底...")
    result = extract_to_white_bg(img_path, category_hint=cat_hint)

    if result.get('white_bg_image'):
        out_dir = os.path.dirname(img_path) or '/tmp'
        base = os.path.splitext(os.path.basename(img_path))[0]

        # 保存白底原图
        white_path = os.path.join(out_dir, f'{base}_white_bg.jpg')
        result['white_bg_image'].save(white_path, 'JPEG', quality=92)
        print(f"✅ 白底图: {white_path}")

        # Step 2: 去白底
        print("→ 去白底...")
        cleaned = remove_white_background(result['white_bg_image'])

        # 保存透明 PNG
        png_path = os.path.join(out_dir, f'{base}_clean.png')
        cleaned['cutout_png'].save(png_path, 'PNG', optimize=True)
        print(f"✅ 透明PNG: {png_path}")

        # 保存灰底 JPG
        jpg_path = os.path.join(out_dir, f'{base}_clean.jpg')
        cleaned['cutout_jpg'].save(jpg_path, 'JPEG', quality=92)
        print(f"✅ 灰底JPG: {jpg_path}")
    else:
        print(f"❌ 白底提取失败: {result.get('error', 'unknown')}")
