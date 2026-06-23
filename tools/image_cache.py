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
