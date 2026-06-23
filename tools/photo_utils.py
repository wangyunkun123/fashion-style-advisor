# -*- coding: utf-8 -*-
"""用户照片处理 — 加载/抠图/构图选择"""

import json
import os

_PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_person_photos():
    """根据 config/user_profile.json 获取用户个人照片路径列表
    返回: [photo_path, ...] 或空列表（无照片/关闭形象）
    """
    up_path = os.path.join(_PROJ_DIR, 'config', 'user_profile.json')
    if not os.path.exists(up_path):
        old = os.path.join(_PROJ_DIR, 'profile', 'photos', 'IMG_8493.jpg')
        return [old] if os.path.exists(old) else []

    try:
        with open(up_path) as f:
            up = json.load(f)
    except Exception:
        return []

    if up.get('use_my_image') is False:
        return []

    photos = up.get('photos', {})
    result = []

    slot_order = ['full_body_front', 'face_closeup', 'full_body_side']
    for slot in slot_order:
        rel_path = photos.get(slot, '')
        if rel_path:
            abs_path = os.path.join(_PROJ_DIR, rel_path)
            if os.path.exists(abs_path):
                result.append(abs_path)

    if not result:
        old = os.path.join(_PROJ_DIR, 'profile', 'photos', 'IMG_8493.jpg')
        if os.path.exists(old):
            result.append(old)

    return result


def remove_person_background(src_path):
    """对人物照片 AI 去背景，保存为透明 PNG 抠图。
    返回: cutout_path（与源文件同目录，_cutout 后缀）
    如果抠图已存在且比源文件新，跳过。
    """
    base = os.path.splitext(src_path)[0]
    dst_path = base + '_cutout.png'

    if os.path.exists(dst_path):
        if os.path.getmtime(dst_path) >= os.path.getmtime(src_path):
            return dst_path

    try:
        from rembg import remove
        from PIL import Image as _PILImg, ImageOps as _PILOps
    except ImportError:
        return src_path

    img = _PILImg.open(src_path)
    img = _PILOps.exif_transpose(img)

    cutout = remove(img, alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=4)
    if cutout.mode != 'RGBA':
        cutout = cutout.convert('RGBA')

    w, h = cutout.size
    if max(w, h) > 1024:
        ratio = 1024 / max(w, h)
        cutout = cutout.resize((int(w * ratio), int(h * ratio)), _PILImg.LANCZOS)

    cutout.save(dst_path, 'PNG')
    return dst_path


def select_person_photos_for_prompt(person_photos, seedream_prompt):
    """根据 prompt 构图角度选择匹配的人物参考图。
    person_photos: [全身正面, 面部近照, 侧面全身]
    seedream_prompt: 英文生图提示词

    规则:
    - 侧面构图 → 侧面照 + 面部近照
    - 正面/默认构图 → 全身正面 + 面部近照
    - 面部近照永远保留（锁定五官）
    """
    if len(person_photos) <= 1:
        return person_photos

    prompt_lower = seedream_prompt.lower()

    side_keywords = [
        'side profile', 'looking back', 'over shoulder', 'side view',
        'side angle', 'side shot', 'profile view', 'turning away',
        'mid-laugh', 'looking over', 'glancing back'
    ]
    is_side = any(kw in prompt_lower for kw in side_keywords)

    face_photo = person_photos[1] if len(person_photos) > 1 else None

    if is_side:
        result = []
        if len(person_photos) > 2:
            result.append(person_photos[2])
        if face_photo:
            result.append(face_photo)
        return result or person_photos

    result = [person_photos[0]]
    if face_photo:
        result.append(face_photo)
    return result
