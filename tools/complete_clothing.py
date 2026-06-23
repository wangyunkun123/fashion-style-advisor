#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 服装补全模块 — 用 Seedream API 补全部分遮挡/不完整的服装单品

流程:
  1. 输入: 不完整服装裁剪图 + mask (来自 cloth_parser)
  2. 用 Seedream 图生图 API 补全缺失部分
  3. 输出: 完整清洁的服装产品图

API: doubao-seedream-5.0-lite (图片参考 + 文本引导)
"""

import os
import json
import base64
import time
import urllib.request
import io as _io
from PIL import Image as PILImage

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
    """将 PIL Image 或路径编码为 base64 data URL，缩放到 max_size"""
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
    # RGBA → 中性灰底 RGB
    if img.mode == 'RGBA':
        bg = PILImage.new('RGB', img.size, (217, 217, 217))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img.save(buf, format='JPEG', quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


def complete_clothing(crop_image, mask=None, category_hint='', completeness='partial',
                       max_retries=2, timeout=180):
    """用 AI 补全不完整的服装单品。

    Args:
        crop_image: PIL Image 或路径 — 裁剪后的服装区域（建议已抠图去背景）
        mask: PIL Image 或 None — SegFormer 分割 mask
        category_hint: str — 品类提示（如 'TS', 'PT', 'DRESS'），帮助 AI 理解服装类型
        completeness: 'partial' | 'full' — 如果是 'full' 则跳过补全
        max_retries: int — API 调用重试次数
        timeout: int — 单次 API 调用超时秒数

    Returns:
        dict: {
            'completed_image': PILImage or None,  # 补全后的图片
            'completed_url': str,                  # 临时下载 URL（如有）
            'completed_bytes': bytes,              # 图片字节
            'used': bool,                          # 是否实际调用了补全
            'prompt': str,                         # 使用的 prompt
        }
    """
    if completeness == 'full':
        return {'completed_image': None, 'completed_url': '', 'completed_bytes': b'', 'used': False,
                'prompt': ''}

    cfg = _load_seedream_config()
    api_url = cfg.get('api_url', '')
    api_key = cfg.get('api_key', '')
    model = cfg.get('model', 'doubao-seedream-5.0-lite')

    if not api_key or not api_url:
        return {'completed_image': None, 'completed_url': '', 'completed_bytes': b'',
                'used': False, 'prompt': '', 'error': '配置缺失'}

    # 品类中文名
    cat_names = {
        'TS': '短袖T恤', 'LS': '长袖上衣', 'SHIRT': '衬衫', 'TANK': '背心',
        'JK': '外套夹克', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
        'DRESS': '连衣裙', 'SKIRT': '半身裙', 'JMP': '连体裤', 'BLOUSE': '女士衬衫',
        'KNIT': '针织衫', 'HAT': '帽子', 'BAG': '包', 'SUN': '墨镜', 'ACC': '配饰',
    }
    cat_cn = cat_names.get(category_hint, '服装')

    # 参考图：使用已抠图的中性灰底图
    ref_b64 = _encode_image(crop_image, max_size=1024)

    # 构建 inpainting prompt
    prompt = f"""Complete this {cat_cn} that is partially cropped at the edges.
Fill in and reconstruct the missing parts naturally.
The item should look complete with proper edges, sleeves, collar, hemline etc.
Isolated on a clean light gray background (#D9D9D9).
Professional fashion product photography, studio lighting.
Front-facing flat lay, no mannequin, no hanger.
High quality, sharp details, accurate fabric texture.
The completed {cat_cn} should look identical in color, fabric, and style to the visible parts."""

    # 调用 API
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

            # 提取结果
            if 'data' in result and result['data']:
                img_url = result['data'][0].get('url', '')
                if img_url:
                    # 下载补全后的图片
                    try:
                        img_req = urllib.request.Request(img_url)
                        with urllib.request.urlopen(img_req, timeout=30) as img_resp:
                            img_bytes = img_resp.read()
                        completed_img = PILImage.open(_io.BytesIO(img_bytes))
                        return {
                            'completed_image': completed_img,
                            'completed_url': img_url,
                            'completed_bytes': img_bytes,
                            'used': True,
                            'prompt': prompt,
                        }
                    except Exception as _de:
                        if attempt < max_retries:
                            time.sleep(2)
                            continue
                        return {'completed_image': None, 'completed_bytes': b'',
                                'used': True, 'prompt': prompt,
                                'error': f'下载失败: {str(_de)[:100]}'}
            else:
                # 无图片返回
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return {'completed_image': None, 'completed_bytes': b'',
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
            return {'completed_image': None, 'completed_bytes': b'',
                    'used': True, 'prompt': prompt,
                    'error': f'API {e.code}: {err_body}'}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {'completed_image': None, 'completed_bytes': b'',
                    'used': True, 'prompt': prompt,
                    'error': str(e)[:200]}

    return {'completed_image': None, 'completed_bytes': b'',
            'used': True, 'prompt': prompt, 'error': '重试耗尽'}


def complete_and_replace(crop_image, mask, category_hint='', completeness='partial',
                         save_dir=None, item_id=''):
    """补全服装并替换原图。如果补全成功，返回补全后的图片；否则返回原图。

    Returns:
        (result_image, was_completed, metadata)
    """
    if completeness == 'full':
        return (crop_image, False, {'completed': False})

    result = complete_clothing(crop_image, mask, category_hint, completeness)

    if result.get('completed_image'):
        completed = result['completed_image']
        if save_dir and item_id:
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f'{item_id}_completed.jpg')
            completed.save(save_path, 'JPEG', quality=92)
        return (completed, True, {
            'completed': True,
            'prompt': result['prompt'],
            'error': result.get('error', ''),
        })
    else:
        return (crop_image, False, {
            'completed': False,
            'error': result.get('error', '未补全'),
        })


# ── CLI 测试 ──
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 tools/complete_clothing.py <partial_image_path> [category_hint]")
        print("  e.g. python3 tools/complete_clothing.py /tmp/test_cutout_TS.png TS")
        sys.exit(1)

    img_path = sys.argv[1]
    cat_hint = sys.argv[2] if len(sys.argv) > 2 else 'TS'

    print(f"补全: {img_path} (品类: {cat_hint})")
    result = complete_clothing(img_path, category_hint=cat_hint, completeness='partial')

    if result.get('completed_image'):
        out_path = img_path.rsplit('.', 1)[0] + '_completed.jpg'
        result['completed_image'].save(out_path, 'JPEG', quality=92)
        print(f"✅ 补全成功: {out_path}")
    else:
        print(f"❌ 补全失败: {result.get('error', 'unknown')}")
