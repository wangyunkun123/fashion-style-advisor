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
    r'|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+'
    r'|DRESS-\d+|SKIRT-\d+|JMP-\d+|BLOUSE-\d+|KNIT-\d+)'
)

# ── 品类代码统一配置（单一真相源）────────────────────────────
# 所有文件从此获取品类名/emoji/图标/CSS排序，不再各自维护映射表
# 🔧 2026-06-24: 新增女性品类 DRESS/SKIRT/JMP/BLOUSE/KNIT
CAT_CONFIG = {
    # ── 中性/男装品类 ──
    'TS':    {'emoji': '👕', 'icon_key': 'tshirt',  'cn': '短袖上衣', 'sort':  5, 'gender': 'both'},
    'LS':    {'emoji': '👔', 'icon_key': 'tshirt',  'cn': '长袖上衣', 'sort':  4, 'gender': 'both'},
    'SHIRT': {'emoji': '👔', 'icon_key': 'tshirt',  'cn': '衬衣',     'sort':  3, 'gender': 'both'},
    'TANK':  {'emoji': '🎽', 'icon_key': 'tshirt',  'cn': '背心',     'sort':  6, 'gender': 'both'},
    'JK':    {'emoji': '🧥', 'icon_key': 'tshirt',  'cn': '外套',     'sort':  1, 'gender': 'both'},
    'PT':    {'emoji': '👖', 'icon_key': 'pants',   'cn': '长裤',     'sort':  7, 'gender': 'both'},
    'SH':    {'emoji': '🩳', 'icon_key': 'pants',   'cn': '短裤',     'sort':  8, 'gender': 'both'},
    'SHOE':  {'emoji': '👟', 'icon_key': 'shoe',    'cn': '鞋子',     'sort': 12, 'gender': 'both'},
    'BAG':   {'emoji': '🎒', 'icon_key': 'bag',     'cn': '包',       'sort': 10, 'gender': 'both'},
    'HAT':   {'emoji': '🧢', 'icon_key': 'hat',     'cn': '帽子',     'sort':  0, 'gender': 'both'},
    'SOCK':  {'emoji': '🧦', 'icon_key': 'sock',    'cn': '袜子',     'sort': 13, 'gender': 'both'},
    'SUN':   {'emoji': '🕶', 'icon_key': 'sun',     'cn': '墨镜',     'sort':  2, 'gender': 'both'},
    'ACC':   {'emoji': '⌚', 'icon_key': 'acc',     'cn': '手部配饰', 'sort': 11, 'gender': 'both'},
    # ── 女性专属品类 ──
    'DRESS': {'emoji': '👗', 'icon_key': 'tshirt',  'cn': '连衣裙',   'sort': 14, 'gender': 'female'},
    'SKIRT': {'emoji': '🩰', 'icon_key': 'pants',   'cn': '半身裙',   'sort': 15, 'gender': 'female'},
    'JMP':   {'emoji': '🪭', 'icon_key': 'tshirt',  'cn': '连体裤',   'sort': 16, 'gender': 'female'},
    'SUIT':  {'emoji': '👗', 'icon_key': 'tshirt',  'cn': '套装',     'sort': 17, 'gender': 'female'},
    'BLOUSE':{'emoji': '👚', 'icon_key': 'tshirt',  'cn': '女士衬衫', 'sort':  3, 'gender': 'female'},
    'KNIT':  {'emoji': '🧶', 'icon_key': 'tshirt',  'cn': '针织衫',   'sort':  4, 'gender': 'both'},
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
CORE_CATS = {'TS', 'LS', 'TANK', 'SHIRT', 'JK', 'SH', 'PT', 'SHOE', 'DRESS', 'SKIRT', 'JMP', 'BLOUSE', 'KNIT'}

# 品类代码 → 分类目录映射（用于 wardrobe 目录结构）
CAT_DIR_MAP = {v['cn']: k for k, v in CAT_CONFIG.items()}
# 反向：分类中文名 → 品类代码
for _code, _cfg in CAT_CONFIG.items():
    CAT_DIR_MAP[_cfg['cn']] = _code


# ── 品类别名解析（fuzzy dedup）────────────────────────────────
# VLM 输出的品类名可能五花八门，此函数做标准化映射
# 数据源: config/category_aliases.json（用户修正时自动追加）
_alias_cache = None
_alias_load_time = 0

def _load_aliases():
    """加载品类别名配置（60s 缓存）"""
    global _alias_cache, _alias_load_time
    now = time.time()
    if _alias_cache is not None and now - _alias_load_time < 60:
        return _alias_cache
    alias_path = os.path.join(PROJ_DIR, 'config', 'category_aliases.json')
    try:
        with open(alias_path, 'r') as f:
            data = json.load(f)
        _alias_cache = data.get('aliases', {})
        _alias_load_time = now
        return _alias_cache
    except Exception:
        return {}


def resolve_category_code(raw_name, gender='male'):
    """将 VLM 输出的原始品类名映射到标准品类代码。

    Args:
        raw_name: VLM 输出的品类名称（如 "短袖T恤"、"midi dress"、"连身裙"）
        gender: 用户性别，用于优先匹配对应性别的品类

    Returns:
        (standard_code, standard_cn_name, confidence)
        如 ('TS', '短袖上衣', 'fuzzy') 或 ('TS', '短袖上衣', 'exact')
        无法匹配时返回 (None, raw_name, 'unknown')
    """
    if not raw_name:
        return (None, '', 'unknown')

    raw = raw_name.strip()

    # Step 1: 直接匹配品类代码
    if raw.upper() in CAT_CONFIG:
        code = raw.upper()
        return (code, CAT_CONFIG[code]['cn'], 'exact')

    # Step 2: 精确匹配中文标准名
    for code, cfg in CAT_CONFIG.items():
        if cfg['cn'] == raw:
            return (code, cfg['cn'], 'exact')

    # Step 3: Fuzzy match via aliases
    aliases = _load_aliases()
    best_code = None
    best_len = 0

    for code, alias_list in aliases.items():
        if code not in CAT_CONFIG:
            continue
        for alias in alias_list:
            # 完全匹配别名
            if alias.lower() == raw.lower():
                return (code, CAT_CONFIG[code]['cn'], 'alias_exact')
            # 包含匹配（取最长匹配）
            if alias.lower() in raw.lower() or raw.lower() in alias.lower():
                if len(alias) > best_len:
                    best_len = len(alias)
                    best_code = code

    if best_code and best_len >= 2:
        return (best_code, CAT_CONFIG[best_code]['cn'], 'fuzzy')

    # Step 4: 根据性别偏好猜测
    if gender == 'female':
        if any(kw in raw for kw in ['裙', 'dress', 'skirt']):
            if '半身' in raw or '短裙' in raw or 'skirt' in raw.lower():
                return ('SKIRT', '半身裙', 'keyword')
            return ('DRESS', '连衣裙', 'keyword')
        if any(kw in raw for kw in ['连体', 'jumpsuit', 'romper']):
            return ('JMP', '连体裤', 'keyword')
        if any(kw in raw for kw in ['雪纺', '真丝', 'blouse', '女士衬衫', '荷叶边', '飘带']):
            return ('BLOUSE', '女士衬衫', 'keyword')

    if any(kw in raw for kw in ['针织', '毛衣', '毛衫', 'knit', 'sweater', 'cardigan', '羊绒', '羊毛']):
        return ('KNIT', '针织衫', 'keyword')

    # Step 5: 无法匹配，返回原始名称供人工确认
    return (None, raw, 'unknown')


def add_category_alias(code, alias_name):
    """用户修正品类后，将别名追加到映射表（数据飞轮）"""
    if code not in CAT_CONFIG:
        return False
    alias_path = os.path.join(PROJ_DIR, 'config', 'category_aliases.json')
    try:
        with open(alias_path, 'r') as f:
            data = json.load(f)
        aliases = data.get('aliases', {})
        if code not in aliases:
            aliases[code] = []
        if alias_name not in aliases[code]:
            aliases[code].append(alias_name)
            data['aliases'] = aliases
            data['_last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(alias_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 清除缓存强制重新加载
            global _alias_cache
            _alias_cache = None
            return True
    except Exception:
        pass
    return False


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

def _get_active_outfits_dir():
    """多用户感知：返回当前活跃用户的 outfits 目录"""
    uid = get_thread_user()
    if uid and uid != 'default':
        return resolve_outfits_dir(uid)
    return OUTFITS_DIR


def get_banned_items():
    """获取一星差评禁用的单品清单（统一版，消除 3 处重复定义）

    精准禁用：优先使用 rating.json 中用户标记的 precise banned_items，
    旧数据兼容：fallback 到 outfit 中所有单品。
    """
    banned = []
    outfits_dir = _get_active_outfits_dir()
    if not os.path.exists(outfits_dir):
        return banned
    for d in os.listdir(outfits_dir):
        dp = os.path.join(outfits_dir, d)
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
    outfits_dir = _get_active_outfits_dir()
    if not os.path.exists(outfits_dir):
        return recent
    for d in sorted(os.listdir(outfits_dir), reverse=True):
        dp = os.path.join(outfits_dir, d)
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
    outfits_dir = _get_active_outfits_dir()
    if not os.path.exists(outfits_dir):
        return counts
    for d in os.listdir(outfits_dir):
        dp = os.path.join(outfits_dir, d)
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
