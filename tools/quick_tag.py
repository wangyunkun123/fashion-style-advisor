#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速入库 — YOLO品类检测 + 颜色直方图 → 基础标签 JSON（30秒内完成）"""
import os, sys, json, time, argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

parser = argparse.ArgumentParser(description='快速入库')
parser.add_argument('image', help='图片路径')
parser.add_argument('--user', required=True, help='用户 ID')
parser.add_argument('--override-id', default=None, help='指定 ID')
args = parser.parse_args()

# 🆕 从 registry 解析 gender，构建正确路径 users/<gender>/<user_id>/
_registry_path = os.path.join(PROJ_DIR, 'users', '_registry.json')
_gender = None
if os.path.exists(_registry_path):
    with open(_registry_path) as _f:
        _reg = json.load(_f)
    for _g, _users in _reg.items():
        if _g.startswith('_'): continue
        if args.user in _users:
            _gender = _g
            break
if not _gender:
    print(f"❌ 用户 {args.user} 未在 registry 中找到，无法确定 gender")
    sys.exit(1)
user_dir = os.path.join(PROJ_DIR, 'users', _gender, args.user)
tags_dir = os.path.join(user_dir, 'wardrobe', 'tags')
os.makedirs(tags_dir, exist_ok=True)

# ── 1. YOLO 品类检测 ──
CATEGORY_CODE_MAP = {
    't-shirt': 'TS', 'shirt': 'SHIRT', 'tank_top': 'TANK',
    'long_sleeve': 'LS', 'jacket': 'JK', 'coat': 'JK',
    'pants': 'PT', 'shorts': 'SH', 'skirt': 'SH',
    'shoes': 'SHOE', 'bag': 'BAG', 'hat': 'HAT',
    'sunglasses': 'SUN', 'socks': 'SOCK', 'dress': 'SHIRT',
}

def _normalize_image(image_path):
    """预处理图片：修复截断、自动旋转、缩放到合理尺寸，返回临时文件路径"""
    from PIL import Image, ImageFile, ImageOps
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)  # 自动旋转
        img = img.convert('RGB')
        # 缩放到最大边不超过 1280px（YOLO 不需要太高分辨率）
        w, h = img.size
        max_dim = max(w, h)
        if max_dim > 1280:
            scale = 1280 / max_dim
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        # 保存为临时文件
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img.save(tmp.name, 'JPEG', quality=90)
        return tmp.name
    except Exception as e:
        print(f"⚠️ 图片预处理失败: {e}")
        return image_path

def detect_category(image_path):
    """YOLO 检测品类"""
    # 预处理：修复截断 JPEG、自动旋转
    clean_path = _normalize_image(image_path)
    try:
        from ultralytics import YOLO
        model_path = os.path.join(PROJ_DIR, 'yolov8n.pt')
        if not os.path.exists(model_path):
            print(f"⚠️ YOLO 模型不存在: {model_path}，使用默认 TS")
            return 'TS', '短袖上衣', 0.0
        model = YOLO(model_path)
        results = model(clean_path, verbose=False)

        best_cls, best_conf = None, 0.0
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, '')
                conf = float(box.conf[0])
                if cls_name in CATEGORY_CODE_MAP and conf > best_conf:
                    best_cls, best_conf = cls_name, conf

        if best_cls:
            code = CATEGORY_CODE_MAP[best_cls]
            from tools.common import cat_code_to_name
            return code, cat_code_to_name(code), best_conf
    except ImportError:
        print("⚠️ ultralytics 未安装，使用默认 TS")
    except Exception as e:
        print(f"⚠️ YOLO 检测失败: {e}")
    finally:
        # 清理临时文件
        if clean_path != image_path and os.path.exists(clean_path):
            try:
                os.unlink(clean_path)
            except:
                pass

    return 'TS', '短袖上衣', 0.0


# ── 2. 颜色直方图分析 ──
def analyze_color(image_path):
    """分析主色"""
    try:
        from PIL import Image, ImageOps, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
        # 缩放到 100x100 加速
        img = img.resize((100, 100))
        pixels = list(img.getdata())

        r = sum(p[0] for p in pixels) / len(pixels)
        g = sum(p[1] for p in pixels) / len(pixels)
        b = sum(p[2] for p in pixels) / len(pixels)
    except Exception as e:
        print(f"⚠️ 颜色分析失败: {e}")
        return {'hue_family': '中性色', 'hue_name': '灰', 'saturation': '低饱和',
                'lightness': '中明度', 'is_neutral': True}

    # RGB → 颜色名
    color_refs = [
        ((180, 30, 30), (255, 80, 80), '红', '暖色'),
        ((180, 80, 30), (255, 160, 80), '橙', '暖色'),
        ((160, 140, 30), (255, 230, 130), '黄', '暖色'),
        ((30, 130, 30), (80, 220, 80), '绿', '冷色'),
        ((30, 80, 180), (80, 160, 255), '蓝', '冷色'),
        ((80, 30, 130), (160, 80, 220), '紫', '冷色'),
        ((80, 40, 20), (160, 100, 60), '棕', '暖色'),
        ((180, 130, 130), (255, 210, 210), '粉', '暖色'),
        ((200, 170, 130), (255, 240, 210), '米', '暖色'),
        ((200, 200, 200), (240, 240, 240), '白', '中性色'),
        ((100, 100, 100), (170, 170, 170), '灰', '中性色'),
        ((0, 0, 0), (60, 60, 60), '黑', '中性色'),
    ]

    best_name, best_family = '灰', '中性色'
    min_dist = float('inf')
    for (lo_r, lo_g, lo_b), (hi_r, hi_g, hi_b), name, family in color_refs:
        cr, cg, cb = (lo_r + hi_r) / 2, (lo_g + hi_g) / 2, (lo_b + hi_b) / 2
        dist = ((r - cr)**2 + (g - cg)**2 + (b - cb)**2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            best_name, best_family = name, family

    max_rgb = max(r, g, b)
    min_rgb = min(r, g, b)
    saturation = '低饱和' if (max_rgb - min_rgb) < 50 else ('高饱和' if (max_rgb - min_rgb) > 120 else '中饱和')
    lightness = '高明度' if (r + g + b) / 3 > 180 else ('低明度' if (r + g + b) / 3 < 80 else '中明度')

    return {
        'hue_family': best_family,
        'hue_name': best_name,
        'saturation': saturation,
        'lightness': lightness,
        'is_neutral': best_family == '中性色',
    }


# ── 3. ID 分配 ──
def get_next_id(category_code, tags_dir):
    existing = []
    if os.path.isdir(tags_dir):
        for fn in os.listdir(tags_dir):
            if fn.startswith(f'{category_code}-') and fn.endswith('.json'):
                import re
                m = re.search(rf'{category_code}-(\d+)', fn)
                if m:
                    existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    return f'{category_code}-{next_num:03d}'


# ── 主流程 ──
print(f"🔍 分析: {os.path.basename(args.image)}")

cat_code, cat_name, cat_conf = detect_category(args.image)
print(f"   品类: {cat_name} ({cat_code}) 置信度={cat_conf:.0%}")

color = analyze_color(args.image)
print(f"   颜色: {color['hue_name']} ({color['hue_family']}, {color['saturation']}, {color['lightness']})")

cid = args.override_id or get_next_id(cat_code, tags_dir)

tag_data = {
    'clothing_id': cid,
    'category': cat_name,
    'category_code': cat_code,
    'color': color,
    'fabric': {'primary': '未知', 'texture': '未知', 'weight': '适中', 'seasonality': ['春', '秋']},
    'silhouette': {'fit': '合身', 'shoulder_effect': '无特殊效果', 'torso_effect': '无特殊效果', 'length_ratio': '标准'},
    'pattern': {'type': '纯色', 'density': '无', 'logo_visible': False},
    'brand': {'name': '未知', 'collection': '', 'confidence': '未知'},
    'style_modifiers': [],
    'occasions': ['日常休闲'],
    'formality': 3,
    'meta': {
        'is_key_piece': False, 'is_statement_piece': False,
        'wear_count': 0, 'last_worn': None, 'claude_fit_comment': '',
    },
    'reviewed': False,
    'reviewed_by_human': None,
    'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
}

tag_path = os.path.join(tags_dir, f'{cid}.json')
with open(tag_path, 'w', encoding='utf-8') as f:
    json.dump(tag_data, f, ensure_ascii=False, indent=2)

print(f"✅ 标签已生成: {tag_path}")
# 输出 JSON 供调用方解析
print(json.dumps({'id': cid, 'category': cat_name, 'color': color['hue_name']}, ensure_ascii=False))
