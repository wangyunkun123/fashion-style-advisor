# -*- coding: utf-8 -*-
"""图片内存 LRU 缓存 — 避免每次请求都读磁盘，缓存最近访问的图片 bytes

总容量 ~25MB（约 30-50 张 600px 缩图或 15-20 张原图）
"""

import io
import os
import threading
import collections
from PIL import Image as PILImage

_IMG_CACHE_MAX = 25 * 1024 * 1024
_IMG_CACHE_SIZE = 0
_IMG_CACHE = {}  # key: (file_abs, width, mtime) → bytes
_IMG_CACHE_ORDER = collections.OrderedDict()  # LRU 顺序
_IMG_CACHE_LOCK = threading.Lock()


def _cache_key(file_abs, req_w):
    """用文件 mtime 做 key 的一部分，文件更新后自动失效"""
    try:
        mtime = os.path.getmtime(file_abs)
    except OSError:
        mtime = 0
    return (file_abs, req_w, mtime)


def image_cache_get(file_abs, req_w):
    """从 LRU 缓存获取图片 bytes，未命中返回 None"""
    key = _cache_key(file_abs, req_w)
    with _IMG_CACHE_LOCK:
        if key in _IMG_CACHE:
            _IMG_CACHE_ORDER.move_to_end(key)
            return _IMG_CACHE[key]
    return None


def image_cache_put(file_abs, req_w, data):
    """将图片 bytes 放入 LRU 缓存，自动淘汰最旧条目"""
    global _IMG_CACHE_SIZE
    key = _cache_key(file_abs, req_w)
    size = len(data)
    with _IMG_CACHE_LOCK:
        if key in _IMG_CACHE:
            _IMG_CACHE_SIZE -= len(_IMG_CACHE[key])
            del _IMG_CACHE[key]
        while _IMG_CACHE_SIZE + size > _IMG_CACHE_MAX and _IMG_CACHE_ORDER:
            old_key = next(iter(_IMG_CACHE_ORDER))
            _IMG_CACHE_SIZE -= len(_IMG_CACHE[old_key])
            del _IMG_CACHE[old_key]
            del _IMG_CACHE_ORDER[old_key]
        _IMG_CACHE[key] = data
        _IMG_CACHE_ORDER[key] = None
        _IMG_CACHE_SIZE += size


def resize_image_bytes(data, target_w, content_type=None):
    """将图片 bytes 缩放到指定宽度，返回 bytes。失败返回原图。"""
    try:
        img = PILImage.open(io.BytesIO(data))
        w, h = img.size
        if w <= target_w:
            return data
        ratio = target_w / w
        new_h = int(h * ratio)
        img = img.resize((target_w, new_h), PILImage.LANCZOS)
        if img.mode == 'RGBA':
            fmt = 'PNG'
        else:
            fmt = 'JPEG'
            if img.mode != 'RGB':
                img = img.convert('RGB')
        buf = io.BytesIO()
        save_kw = {'format': fmt, 'optimize': True}
        if fmt == 'JPEG':
            save_kw['quality'] = 85
        img.save(buf, **save_kw)
        return buf.getvalue()
    except Exception:
        return data


# ── 管线预压缩 ────────────────────────────────────────────
# 生图完成后立即生成压缩版，避免手机首次请求时实时缩放全尺寸原图

def pre_compress_image(src_path, widths=(900,), quality=85, force=False):
    """从源图生成指定宽度的 JPEG 压缩版，返回生成的文件路径列表。

    Args:
        src_path: 原始图片绝对路径
        widths: 目标宽度元组，默认 (900,) 覆盖手机 3x retina
        quality: JPEG 质量 1-100，默认 85
        force: 即使已存在也强制重新生成

    Returns:
        [compressed_path, ...] 生成的压缩版路径列表
    """
    import os as _os
    created = []
    src_dir = _os.path.dirname(src_path)
    src_base = _os.path.splitext(_os.path.basename(src_path))[0]
    src_mtime = _os.path.getmtime(src_path)

    try:
        img = PILImage.open(src_path)
    except Exception:
        return created

    # 转 RGB（AI 生图通常是 RGB 的 PNG，JPEG 不需要 RGBA）
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        # 用白色背景替换透明区域
        bg = PILImage.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img.convert('RGBA'), mask=img.convert('RGBA').split()[3])
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    for w in widths:
        out_name = f'{src_base}_{w}w.jpg'
        out_path = _os.path.join(src_dir, out_name)

        # 跳过已存在且比源图新的压缩版
        if not force and _os.path.exists(out_path):
            if _os.path.getmtime(out_path) >= src_mtime:
                created.append(out_path)
                continue

        if img.width <= w:
            # 原图已经够小，直接保存为 JPEG
            out_img = img.copy()
        else:
            ratio = w / img.width
            new_h = int(img.height * ratio)
            out_img = img.resize((w, new_h), PILImage.LANCZOS)

        out_img.save(out_path, 'JPEG', quality=quality, optimize=True)
        created.append(out_path)

    return created


def pre_compress_dir(dir_path, widths=(900,), quality=85, force=False):
    """对目录下所有图片执行预压缩（跳过已压缩版本自身）。
    返回成功压缩的文件数量。
    """
    import os as _os
    count = 0
    if not _os.path.isdir(dir_path):
        return 0
    for fname in _os.listdir(dir_path):
        # 跳过已压缩版本、非图片文件
        if '_900w' in fname or '_600w' in fname or '_300w' in fname:
            continue
        if fname.startswith('.'):
            continue
        ext = _os.path.splitext(fname)[1].lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.webp'):
            continue
        src = _os.path.join(dir_path, fname)
        try:
            created = pre_compress_image(src, widths=widths, quality=quality, force=force)
            count += len(created)
        except Exception:
            pass
    return count
