#!/usr/bin/env python3
"""共享工具函数 — 消除跨文件重复定义"""
import os, json, glob, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')

# 所有品类 ID 正则（消除 7 处重复定义）
ITEM_ID_PATTERN = re.compile(
    r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+'
    r'|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)'
)

# 品类代码统一配置
CAT_CONFIG = {
    'TS':    {'emoji': '👕', 'icon_key': 'tshirt',  'cn': '短袖上衣', 'sort':  5},
    'LS':    {'emoji': '👔', 'icon_key': 'tshirt',  'cn': '长袖上衣', 'sort':  4},
    'SHIRT': {'emoji': '👔', 'icon_key': 'tshirt',  'cn': '衬衣',     'sort':  3},
    'TANK':  {'emoji': '🎽', 'icon_key': 'tshirt',  'cn': '背心',     'sort':  6},
    'JK':    {'emoji': '🧥', 'icon_key': 'tshirt',  'cn': '外套',     'sort':  1},
    'PT':    {'emoji': '👖', 'icon_key': 'pants',   'cn': '长裤',     'sort':  7},
    'SH':    {'emoji': '🩳', 'icon_key': 'pants',   'cn': '短裤',     'sort':  8},
    'SHOE':  {'emoji': '👟', 'icon_key': 'shoe',    'cn': '鞋子',     'sort': 12},
    'BAG':   {'emoji': '🎒', 'icon_key': 'bag',     'cn': '包',       'sort': 10},
    'HAT':   {'emoji': '🧢', 'icon_key': 'hat',     'cn': '帽子',     'sort':  0},
    'SOCK':  {'emoji': '🧦', 'icon_key': 'sock',    'cn': '袜子',     'sort': 13},
    'SUN':   {'emoji': '🕶', 'icon_key': 'sun',     'cn': '墨镜',     'sort':  2},
    'ACC':   {'emoji': '⌚', 'icon_key': 'acc',     'cn': '手部配饰', 'sort': 11},
}
CAT_SORT_ORDER = sorted(CAT_CONFIG.keys(), key=lambda k: CAT_CONFIG[k]['sort'])


def load_all_clothing(include_archived=False):
    """加载所有衣服标签，返回 {clothing_id: tag_dict}

    Args:
        include_archived: 是否包含已归档（旧衣库）单品的，默认 False
    """
    items = {}
    for fpath in sorted(glob.glob(os.path.join(TAGS_DIR, '*.json'))):
        fname = os.path.basename(fpath)
        if fname.startswith('SCORE_CACHE') or fname == 'README.json' or fname.startswith('.id_to_cutout'):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                item = json.load(f)
            cid = item.get('clothing_id', '')
            if not cid:
                continue
            if not include_archived and (item.get('meta') or {}).get('archived'):
                continue
            items[cid] = item
        except Exception:
            pass
    return items


def load_score_cache():
    """加载评分缓存，返回 dict（已剥离 _meta）"""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    cache.pop('_meta', None)
    return cache


def load_style_fingerprint(style_id):
    """加载风格指纹 JSON"""
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


STYLES_UNI_DIR = os.path.join(PROJ_DIR, 'styles_universal')
CDN_BASE = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'


def load_encyclopedia(style_id):
    """从百科中提取冷知识、名人、品牌信息"""
    path = os.path.join(STYLES_UNI_DIR, style_id, 'encyclopedia.md')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 一句话定义
    one_liner = ''
    for line in text.split('\n'):
        if '一句话定义' in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m:
                one_liner = m.group(1).strip()
            break

    # 起源/冷知识
    origin = ''
    in_origin = False
    for line in text.split('\n'):
        if '### 起源' in line or '## 📜' in line:
            in_origin = True
            continue
        if in_origin and line.strip() and not line.startswith('#') and not line.startswith('>'):
            candidate = line.strip().lstrip('- ').strip()
            if len(candidate) > 30:
                origin = candidate[:140] + '...' if len(candidate) > 140 else candidate
                break

    # 名人引用
    quote = ''
    for line in text.split('\n'):
        if line.strip().startswith('>') and len(line) > 20:
            quote = line.strip().lstrip('> ').strip()
            if '：' in quote or '——' in quote or '"' in quote:
                break

    # 品牌代表（前3个）
    brands = []
    in_brands = False
    for line in text.split('\n'):
        if '## 🏷️' in line or '代表品牌' in line:
            in_brands = True
            continue
        if in_brands and line.startswith('##'):
            break
        if in_brands:
            m = re.match(r'^- \*\*(.+?)\*\*.*?[—]\s*(.+)$', line)
            if m:
                brands.append({'name': m.group(1).strip(), 'desc': m.group(2).strip()[:60]})
            if len(brands) >= 3:
                break

    # 风格偶像（前2个）
    icons = []
    in_icons = False
    for line in text.split('\n'):
        if '## 👤' in line or '风格偶像' in line:
            in_icons = True
            continue
        if in_icons and line.startswith('##'):
            break
        if in_icons:
            m = re.match(r'^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
            if m:
                icons.append({'name': m.group(1).strip(), 'role': m.group(2).strip(), 'why': m.group(3).strip()[:60]})
            if len(icons) >= 2:
                break

    return {
        'one_liner': one_liner, 'origin': origin, 'quote': quote,
        'brands': brands, 'icons': icons,
        'encyclopedia_url': f'https://htmlpreview.github.io/?{CDN_BASE}/styles_universal/{style_id}/encyclopedia.html',
    }
