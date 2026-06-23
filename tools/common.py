#!/usr/bin/env python3
"""共享工具函数 — 消除跨文件重复定义（2026-06-18 增强版）

统一入口：品类映射 / Git+CDN / outfit 解析 / 禁用清单 / 穿着统计
所有工具文件从此单一源获取，不再各自重复定义。
"""
import os, json, glob, re, subprocess, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
STYLES_UNI_DIR = os.path.join(PROJ_DIR, 'styles_universal')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')

# ── 所有品类 ID 正则（消除 7+ 处重复定义）────────────────────
ITEM_ID_PATTERN = re.compile(
    r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+'
    r'|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)'
)

# ── 品类代码统一配置（单一真相源）────────────────────────────
# 所有文件从此获取品类名/emoji/图标/CSS排序，不再各自维护映射表
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

# 衍生快捷函数
def cat_code_to_name(code):
    """品类代码 → 中文名"""
    return CAT_CONFIG.get(code, {}).get('cn', code)

def cat_emoji(code):
    """品类代码 → emoji"""
    return CAT_CONFIG.get(code, {}).get('emoji', '👔')

def cat_icon_key(code):
    """品类代码 → 图标 key（用于前端图标库）"""
    return CAT_CONFIG.get(code, {}).get('icon_key', 'tshirt')

# 核心品类（上衣/下装/鞋子 — 用于选品验证）
CORE_CATS = {'TS', 'LS', 'TANK', 'SHIRT', 'JK', 'SH', 'PT', 'SHOE'}

# 品类代码 → 分类目录映射（用于 wardrobe 目录结构）
CAT_DIR_MAP = {v['cn']: k for k, v in CAT_CONFIG.items()}
# 反向：分类中文名 → 品类代码
for _code, _cfg in CAT_CONFIG.items():
    CAT_DIR_MAP[_cfg['cn']] = _code


# ═══════════════════════════════════════════════════════════════
# Git & CDN（消除 3 处重复）
# ═══════════════════════════════════════════════════════════════

_git_commit_cache = ''

def get_git_commit(short=False):
    """获取当前 Git commit hash（缓存，进程内只算一次）"""
    global _git_commit_cache
    if _git_commit_cache:
        return _git_commit_cache
    try:
        flag = '--short' if short else ''
        args = ['git', 'rev-parse', flag, 'HEAD'] if short else ['git', 'rev-parse', 'HEAD']
        args = [a for a in args if a]
        r = subprocess.run(args, capture_output=True, text=True, cwd=PROJ_DIR, timeout=5)
        _git_commit_cache = r.stdout.strip()
    except Exception:
        _git_commit_cache = 'main'
    return _git_commit_cache

def invalidate_git_commit_cache():
    """清除 git commit 缓存（git push 后调用，确保 CDN URL 使用最新 commit）"""
    global _git_commit_cache
    _git_commit_cache = ''

def get_cdn_base():
    """获取 jsDelivr CDN base URL（自动用最新 commit hash）"""
    h = get_git_commit()
    return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}'

def cdn_url(rel_path):
    """将项目相对路径转为 jsDelivr CDN URL"""
    commit = get_git_commit()
    clean = rel_path.lstrip('./') if rel_path.startswith('..') else rel_path
    return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}/{clean}'

# 兼容旧代码的常量
CDN_BASE = None  # 延迟计算，首次调用 get_cdn_base() 时初始化


# ═══════════════════════════════════════════════════════════════
# Outfit 解析（消除 3+ 处重复的 outfit.md 表格解析）
# ═══════════════════════════════════════════════════════════════

def parse_outfit_md(md_path):
    """解析 outfit.md → {date, style, weather, items: [{id, name, score, reason, cat}]}

    统一 build_prototype / build_push / wechat_control 的解析逻辑。
    """
    if not os.path.exists(md_path):
        return None

    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    data = {'date': '', 'style': '', 'weather': '', 'items': []}

    # 日期（从文件名推断）
    dirname = os.path.basename(os.path.dirname(md_path))
    m = re.search(r'(\d{4}-\d{2}-\d{2})', dirname)
    if m:
        data['date'] = m.group(1)

    # 风格
    m = re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)', text)
    if m:
        data['style'] = (m.group(1) or m.group(2)).strip()

    # 天气
    m = re.search(r'天气.*?[：:]\s*(.+)', text)
    if m:
        data['weather'] = m.group(1).strip()

    # 单品表格
    in_table = False
    for line in text.split('\n'):
        s = line.strip()
        if '单品清单' in s:
            in_table = True
            continue
        if in_table and s.startswith('##'):
            break
        if not in_table or not s.startswith('|') or '---' in s:
            continue
        cells = [c.strip().replace('**', '') for c in s.split('|')]
        if len(cells) < 5:
            continue
        cid = cells[2]
        if not re.match(r'^[A-Z]+-\d+', cid):
            continue
        name = cells[3]
        score = cells[4]
        reason = cells[5] if len(cells) > 5 else ''
        cat = cells[1] if len(cells) > 1 else ''
        data['items'].append({
            'id': cid, 'name': name, 'score': score,
            'reason': reason, 'cat': cat,
        })

    return data


# ═══════════════════════════════════════════════════════════════
# 禁用 / 最近 / 穿着统计（消除 3 处重复）
# ═══════════════════════════════════════════════════════════════

def get_banned_items():
    """获取一星差评禁用的单品清单（统一版，消除 3 处重复定义）

    精准禁用：优先使用 rating.json 中用户标记的 precise banned_items，
    旧数据兼容：fallback 到 outfit 中所有单品。
    """
    banned = []
    if not os.path.exists(OUTFITS_DIR):
        return banned
    for d in os.listdir(OUTFITS_DIR):
        dp = os.path.join(OUTFITS_DIR, d)
        if not os.path.isdir(dp):
            continue
        rating_file = os.path.join(dp, 'rating.json')
        if not os.path.exists(rating_file):
            continue
        try:
            with open(rating_file, 'r') as f:
                rating_data = json.load(f)
            if rating_data.get('rating') != 1:
                continue
            feedback = rating_data.get('feedback', {}) or {}
            precise_banned = feedback.get('banned_items', [])
            if precise_banned and isinstance(precise_banned, list):
                banned.extend(precise_banned)
            else:
                md = os.path.join(dp, 'outfit.md')
                if os.path.exists(md):
                    with open(md, 'r') as f:
                        content = f.read()
                    ids = re.findall(ITEM_ID_PATTERN, content)
                    banned.extend(ids)
        except Exception:
            pass
    return list(set(banned))


def get_recent_outfits(limit=7, include_today=True):
    """获取最近 N 套穿搭的核心单品 → [(label, [core_ids]), ...]

    Args:
        limit: 最大返回数
        include_today: 是否包含今天的 outfit（默认 True，防止同日重复）

    统一 unified_pipeline / wechat_control 的重复逻辑。
    """
    today = time.strftime('%Y-%m-%d')
    recent = []
    if not os.path.exists(OUTFITS_DIR):
        return recent
    for d in sorted(os.listdir(OUTFITS_DIR), reverse=True):
        dp = os.path.join(OUTFITS_DIR, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        if not include_today and d.startswith(today):
            continue
        md = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md):
            continue
        try:
            with open(md, 'r') as f:
                content = f.read()
            ids = list(set(re.findall(ITEM_ID_PATTERN, content)))
            core = [i for i in ids if i.split('-')[0] in CORE_CATS]
            if core:
                label = f'🆕今天 {d}' if d.startswith(today) else d
                recent.append((label, core))
        except Exception:
            pass
        if len(recent) >= limit:
            break
    return recent


def get_wear_counts():
    """统计每件单品的穿着次数（从所有 outfit.md 中统计）"""
    counts = {}
    if not os.path.exists(OUTFITS_DIR):
        return counts
    for d in os.listdir(OUTFITS_DIR):
        dp = os.path.join(OUTFITS_DIR, d)
        md = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md):
            continue
        try:
            with open(md, 'r') as f:
                content = f.read()
            ids = re.findall(ITEM_ID_PATTERN, content)
            for i in set(ids):
                counts[i] = counts.get(i, 0) + 1
        except Exception:
            pass
    return counts


# ═══════════════════════════════════════════════════════════════
# 原有函数（保持不变）
# ═══════════════════════════════════════════════════════════════

def load_all_clothing(include_archived=False):
    """加载所有衣服标签，返回 {clothing_id: tag_dict}

    Args:
        include_archived: 是否包含已归档（旧衣库）单品，默认 False
    """
    # 多用户支持：从线程本地获取用户上下文
    uid = get_thread_user()
    tags_dir = resolve_tags_dir(uid) if uid else TAGS_DIR

    items = {}
    for fpath in sorted(glob.glob(os.path.join(tags_dir, '*.json'))):
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


CDN_BASE_FALLBACK = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'


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
        'encyclopedia_url': f'https://htmlpreview.github.io/?{CDN_BASE_FALLBACK}/styles_universal/{style_id}/encyclopedia.html',
    }


# ═══════════════════════════════════════════════════════════════
# 多用户支持（2026-06-22）
# ═══════════════════════════════════════════════════════════════

def resolve_user_dir(user_id=None):
    """解析用户数据根目录。
    user_id=None 或 'default' → 项目根（现有单用户模式，完全不变）
    user_id='alice'        → users/alice/（多用户模式）
    """
    if not user_id or user_id == 'default':
        return PROJ_DIR
    return os.path.join(PROJ_DIR, 'users', user_id)


def resolve_wardrobe_dir(user_id=None):
    """解析 wardrobe 目录"""
    return os.path.join(resolve_user_dir(user_id), 'wardrobe')


def resolve_outfits_dir(user_id=None):
    """解析 outfits 目录"""
    return os.path.join(resolve_user_dir(user_id), 'outfits')


def resolve_tags_dir(user_id=None):
    """解析 wardrobe/tags 目录"""
    return os.path.join(resolve_user_dir(user_id), 'wardrobe', 'tags')


# ── 线程本地用户上下文（2026-06-22）──
# 允许 deep 调用链中的函数无需显式传 user_id 即可路由到正确用户目录
import threading as _threading
_thread_user = _threading.local()

def set_thread_user(user_id):
    """设置当前线程的用户 ID（无返回值）。API 入口调用一次，后续所有
    load_all_clothing / load_state 等函数自动路由到用户数据目录。"""
    _thread_user.value = user_id

def get_thread_user():
    """获取当前线程的用户 ID，未设置返回 None"""
    return getattr(_thread_user, 'value', None)
