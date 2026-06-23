#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build mobile-v2.html prototype with proper icons from icon library"""
import re, os, sys, json, time, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')
OUTFITS_DIR = os.path.join(PROJ, 'outfits')
WARDROBE_DIR = os.path.join(PROJ, 'wardrobe')

# 确保项目根目录在 sys.path 中（支持直接运行和模块导入两种方式）
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

# ── 多用户支持 ──
from tools.common import resolve_outfits_dir, resolve_wardrobe_dir, resolve_user_dir

USER_ID = None
args = sys.argv[1:]
for i, arg in enumerate(args):
    if arg == '--user' and i + 1 < len(args):
        USER_ID = args[i + 1]
        break
    elif arg.startswith('--user='):
        USER_ID = arg.split('=', 1)[1]
        break

# 如果是多用户模式，切换 OUTFITS_DIR
if USER_ID:
    OUTFITS_DIR = resolve_outfits_dir(USER_ID)
    WARDROBE_DIR = resolve_wardrobe_dir(USER_ID)

# 标签质量过滤器 — 去除日期/指令类噪音
JUNK_PATTERNS = [r'^\d{4}-\d{2}-\d{2}', r'^\d+月\d+', r'^今日', r'^推荐', r'^穿搭',
                 r'^第\d+', r'^请', r'^帮我', r'^我想', r'^需要', r'^场景', r'^。$', r'^$']

# CDN — 从 common 统一导入
from tools.common import get_git_commit, cdn_url

# ═════════════════════════════════════════════════════════
# 服装显示名称 — 从 tag JSON 结构化数据构造
# 规则: 品牌 + 服装名城 + (空间允许时)颜色/风格词
# ═════════════════════════════════════════════════════════

CAT_SHORT = {
    '短袖上衣': '短袖', '长袖上衣': '长袖', '衬衣': '衬衫',
    '短裤': '短裤', '长裤': '长裤', '鞋子': '鞋', '帽子': '帽',
    '袜子': '袜', '外套': '外套', '包': '包', '墨镜': '墨镜',
    '背心': '背心', '手部配饰': '手链'
}

_GOOD_FABRICS = {'速干', '棉', '皮质', '帆布', '牛仔', '亚麻', '羊毛混纺', '针织', '金属', '尼龙', '木质', '棉混纺', '聚酯纤维'}

# 风格词 → 命名缩写
_STYLE_SHORT = {
    '跑鞋': '跑鞋', '拖鞋': '拖鞋', '渔夫帽': '渔夫帽', '棒球帽': '棒球帽',
    '机能风格': '机能', '复古运动感': '复古', '网球配件': '网球', '网球运动': '网球',
    '休闲遮阳': '休闲', '复古训练': '复古', '澳洲休闲': '休闲', '日系宽松': '宽松',
    '高端训练': '训练', '科技运动': '运动', '运动休闲': '运动', '入门网球': '网球',
    '休闲运动': '运动', '夏日度假': '度假', '休闲偏精致': '精致', '帆布经典': '经典',
    '篮球文化': '篮球', '足球文化': '足球', '美式校园': '校园', '复古街头': '街头',
    '工装风': '工装', '户外机能': '户外', '意式运动': '运动', '嘻哈文化': '嘻哈',
    '摇滚文化': '摇滚', '美式复古': '复古', '朋克': '朋克', '潮流': '潮流',
    '夏威夷风情': '夏威夷', '度假休闲': '度假', '勇士队联名': '勇士',
    'AJ基因': 'AJ', '高帮': '高帮', '防水': '防水', '速干运动': '运动',
    '休闲居家': '居家', '运动潮流': '潮流', '内搭': '打底', '夏季必备': '夏',
    '椰树印花': '印花', '休闲基础': '休闲', '网眼轻便': '轻便', '学院休闲': '学院',
    '醒目': '亮色', '工装感': '工装', '通勤实用': '通勤',
}

# 不参与命名的填充词
_STYLE_SKIP = {
    '颜色显白', '增加肩宽', '增加上半身体量感', '增加下半身体量感',
    '厚底增加视觉比例', '视觉清新', '视觉轻盈', '视觉利落', '无明显修饰',
    'Silverescent抗菌', 'HIIT/跑步', '基础百搭', '休闲日常', '日常休闲',
    '松紧抽绳腰', '百搭基础', '通勤百搭', '极简', '简约', '基本款', '基础',
    '视觉吸睛', '视觉鲜艳吸睛', '视觉吸睛加分', '视觉亮点', '可爱图案点缀',
    '花纹点缀视觉趣味', '小格纹增添细节感', '横向条纹略增宽视感', '视觉肌理增加层次',
    '防滑设计实用', '罗纹细节增添质感', '视觉个性表达', '经典百搭', '时尚个性',
    '束脚收紧脚踝显比例', '束脚显比例', '遮盖小肚子', '遮盖纤细小腿', '修身显腿型纤细',
    '长款拉长比例', '视觉重心上移', '简约实用', '经典Logo', '质感', '亮面',
    '舒适耐穿', '高性价比', '日常百搭', '通勤休闲', '简约百搭',
    '拉链口袋分层置物', '多物包容性强', '拉杆箱固定带', '木质温润感',
    '科技感', '功能性', '实用', '质感优雅', '多功能收纳', '分层置物',
    '机能户外风', '运动机能感', '休闲实用', '节日点缀', '视觉点缀',
    '密集印花', '大雪橇纹针织', '东南亚', '球迷潮流',
}

_TYPE_WORDS = {'跑鞋', '拖鞋', '渔夫帽', '棒球帽'}

def _clean_brand(brand):
    """清理品牌名：去系列后缀/品类噪音，未知→空"""
    if not brand or brand == '未知':
        return ''
    # 去掉 …系列 / …健身衣 / …拖鞋 等后缀噪音
    brand = re.sub(r'\S*(?:系列|健身衣|跑步|运动服|复古运动|潮流|拖鞋|帽子|袜子|包|鞋子|短袖|长袖|短裤|长裤|外套).*$', '', brand).strip()
    brand = re.sub(r'\s+', ' ', brand).strip()
    return brand

def get_display_name(iid):
    """从 wardrobe/tags/{iid}.json 构造显示名称：品牌 + 服装名城"""
    tag_path = os.path.join(PROJ, 'wardrobe', 'tags', f'{iid}.json')
    if not os.path.exists(tag_path):
        return iid

    try:
        with open(tag_path) as f:
            tag = json.load(f)
    except Exception:
        return iid

    brand = _clean_brand(tag.get('brand', {}).get('name', ''))
    category = tag.get('category', '')
    cat = CAT_SHORT.get(category, category)
    fabric = tag.get('fabric', {}).get('primary', '')
    style_mods = tag.get('style_modifiers', [])

    # ── 收集描述词（缩简 + 去重）──
    descs = []
    seen = set()
    for sm in style_mods:
        if sm in _STYLE_SKIP:
            continue
        short = _STYLE_SHORT.get(sm)
        if short is None:
            if len(sm) <= 3 and sm not in _STYLE_SKIP:
                short = sm
            else:
                continue
        if short and short not in seen:
            # 子串去重
            if not any(short in d for d in seen) and not any(d in short for d in seen):
                descs.append(short)
                seen.add(short)

    # 面料描述
    if fabric and fabric in _GOOD_FABRICS and fabric not in seen:
        if not any(fabric in d for d in seen):
            descs.append(fabric)
            seen.add(fabric)

    # ── 检测完整类型词 ──
    item_core = cat
    for d in descs[:]:
        if d in _TYPE_WORDS:
            item_core = d
            descs.remove(d)
            break

    # ── 构建：{品牌} {描述词…}{品类} ──
    chosen = descs[:3]
    core = ''.join(chosen) + item_core

    if brand:
        name = f'{brand} {core}'
    else:
        name = core

    return name[:24].strip()

def scan_outfits(date_filter=None, rating_filter=None, limit=20):
    """Scan outfits directory, return list of outfit dicts"""
    results = []
    # Sort by date prefix in directory name (newest first).
    # Dir names start with YYYY-MM-DD, reverse alphabetical = newest first.
    # NOT by mtime — rating.json writes would reorder today's list.
    if not os.path.isdir(OUTFITS_DIR):
        return []
    dirs = [d for d in os.listdir(OUTFITS_DIR)
            if os.path.isdir(os.path.join(OUTFITS_DIR, d))
            and not d.startswith('.') and not d.startswith('_')]
    dirs.sort(key=lambda d: os.path.getctime(os.path.join(OUTFITS_DIR, d)), reverse=True)
    for d in dirs:
        dp = os.path.join(OUTFITS_DIR, d)
        md_path = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md_path):
            continue
        date_str = d[:10]
        if date_filter and date_str != date_filter:
            continue
        # Rating check
        rating = None
        rp = os.path.join(dp, 'rating.json')
        if os.path.exists(rp):
            try:
                with open(rp) as f:
                    rating = json.load(f).get('rating')
            except: pass
        if rating_filter is not None:
            if rating != rating_filter: continue

        with open(md_path) as f: content = f.read()
        # Extract items
        items = []
        in_table = False
        for line in content.split('\n'):
            s = line.strip()
            if '单品清单' in s: in_table = True; continue
            if in_table and s.startswith('##'): break
            if not in_table or not s.startswith('|') or '---' in s: continue
            cells = [c.strip().replace('**','') for c in s.split('|')]
            if len(cells) < 4: continue
            if re.match(r'^[A-Z]+-\d+', cells[2]):
                full_name = cells[3]
                items.append({'id': cells[2], 'name': get_display_name(cells[2]),
                              'full_name': full_name, 'cat': cells[1] if len(cells)>1 else ''})
        style = ''
        weather = ''
        for line in content.split('\n'):
            if 'style:' in line.lower() and not style:
                m = re.search(r'[：:]\s*(.+)', line)
                if m: style = m.group(1).strip()[:40]
            if 'weather' in line.lower() or '天气' in line:
                m = re.search(r'[：:]\s*(.+)', line)
                if m: weather = m.group(1).strip()[:60]
        scene = d.split('_',1)[-1] if '_' in d else style
        # Find character image: 900w预压缩 > 上身效果_1.png (AI原图) > 人物*.jpg > 排版图 > any
        char_img = ''
        char_thumb = ''  # 缩略图（300px宽，用于历史卡片，10-25KB vs 原图500KB-1MB）
        for sub in ['上身效果','豆包生图']:
            sd = os.path.join(dp, sub)
            if not os.path.exists(sd): continue
            # 🆕 最高优先：900w 预压缩 JPEG（100-250KB，比 PNG 原图小 70-92%）
            for f in sorted(os.listdir(sd)):
                if '_900w' in f and '上身效果_1' in f and '方案' not in f:
                    char_img = cdn_url('../outfits/{}/{}/{}'.format(d, sub, f))
                    break
            if char_img: break
            # First: 上身效果_1.png (raw AI gen, first stored)
            for f in sorted(os.listdir(sd)):
                if f == '上身效果_1.png':
                    char_img = cdn_url('../outfits/{}/{}/{}'.format(d, sub, f))
                    break
            if char_img: break
            # Second: 人物_*.jpg
            for f in sorted(os.listdir(sd)):
                if '人物' in f and f.endswith(('.jpg','.png')) and not f.startswith('.'):
                    char_img = cdn_url('../outfits/{}/{}/{}'.format(d, sub, f))
                    break
            if char_img: break
            # Third: *_方案*.jpg (composite)
            for f in sorted(os.listdir(sd)):
                if '方案' in f and f.endswith('.jpg') and not f.startswith('.'):
                    char_img = cdn_url('../outfits/{}/{}/{}'.format(d, sub, f))
                    break
            if char_img: break
            # Last: any image
            for f in sorted(os.listdir(sd)):
                if f.endswith(('.jpg','.png')) and not f.startswith('.') and not f.startswith('_') and not f.startswith('.'):
                    char_img = cdn_url('../outfits/{}/{}/{}'.format(d, sub, f))
                    break
            if char_img: break
        # 缩略图：优先 300px 宽 JPEG（10-25KB），fallback 到原图
        if char_img:
            thumb_file = os.path.join(dp, '上身效果', 'thumb_300w.jpg')
            if os.path.exists(thumb_file):
                char_thumb = cdn_url('../outfits/{}/上身效果/thumb_300w.jpg'.format(d))
            else:
                char_thumb = char_img
        # Build item thumbnails — 衣橱增强版优先（用户调整版为准）
        items_dir = os.path.join(dp, 'items')
        enhanced_dir = os.path.join(PROJ, 'wardrobe', 'enhanced')
        for it in items:
            thumb_found = False
            # 🆕 同时确定 thumb（卡片缩略图）和 cutout（弹窗大图）
            cutout_png = os.path.join(enhanced_dir, f"{it['id']}_cutout.png")
            cutout_thumb_png = os.path.join(enhanced_dir, f"{it['id']}_cutout_thumb.png")
            # cutout 大图优先：用于弹窗查看细节
            if os.path.exists(cutout_png):
                it['cutout'] = os.path.join('..', 'wardrobe', 'enhanced', f"{it['id']}_cutout.png")
            # thumb 缩略图：用于卡片网格展示
            for pat in [f"{it['id']}_cutout_thumb.png", f"{it['id']}_cutout.png"]:
                ep = os.path.join(enhanced_dir, pat)
                if os.path.exists(ep):
                    it['thumb'] = os.path.join('..', 'wardrobe', 'enhanced', pat)
                    thumb_found = True
                    break
            if thumb_found:
                continue
            # 兜底：outfit 历史副本
            if os.path.exists(items_dir):
                for f in os.listdir(items_dir):
                    if f.startswith(it['id']+'_') and f.endswith('.png'):
                        it['thumb'] = os.path.join('..', 'outfits', d, 'items', f)
                        break
        # Parse weather: temp range + UV
        temp_str = ''
        uv_str = ''
        if weather:
            tm = re.search(r'(\d+)[-\s~~]+(\d+)\s*[°度]?C', weather)
            if tm: temp_str = '{}~{}°C'.format(tm.group(1), tm.group(2))
            if '紫外线' in weather:
                um = re.search(r'紫外线\s*(\S+)', weather)
                if um: uv_str = um.group(1)
            elif '晴' in weather: uv_str = '强'
            elif '多云' in weather: uv_str = '中等'
            elif '雾' in weather or '阴' in weather: uv_str = '弱'
        # Parse 推荐理由 and 穿搭技巧
        rationale = ''
        dressing_tips = []
        in_section = None  # 'rationale' or 'tips'
        for line in content.split('\n'):
            s = line.strip()
            if s.startswith('## 推荐理由'):
                in_section = 'rationale'
                m = re.search(r'[：:]\s*(.+)', s)
                if m: rationale = m.group(1).strip()
                continue
            if s.startswith('## 穿搭技巧'):
                in_section = 'tips'
                continue
            if s.startswith('##'):
                in_section = None
                continue
            if in_section == 'rationale' and s:
                rationale = (rationale + ' ' + s).strip()
            elif in_section == 'tips' and s:
                if s.startswith('- '):
                    dressing_tips.append(s[2:].strip())
                else:
                    dressing_tips.append(s)
        results.append({'dir': d, 'date': date_str, 'style': style or scene[:30], 'items': items, 'rating': rating, 'char_img': char_img, 'char_thumb': char_thumb, 'weather': weather, 'temp': temp_str, 'uv': uv_str,
            'rationale': rationale, 'dressing_tips': dressing_tips})
        if len(results) >= limit: break
    return results

# ── Load Clothing-Icons ──
with open(os.path.join(PROJ, 'node_modules/clothing-icons/dist/index.js')) as f:
    ci_js = f.read()

def ci(name):
    i = ci_js.find('Svg'+name)
    if i == -1: return None
    ps = re.findall(r'd:\s*"([^"]+)"', ci_js[i:i+4000])[:10]
    if not ps: return None
    inner = ''.join('<path d="{}"/>'.format(p) for p in ps)
    return '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{}</svg>'.format(inner)

def lu(name):
    p = os.path.join(PROJ, 'node_modules/lucide-static/icons/{}.svg'.format(name))
    if not os.path.exists(p): return None
    with open(p) as f: svg = f.read()
    inner = re.sub(r'<svg[^>]*>|</svg>|<!--.*?-->', '', svg, flags=re.DOTALL).strip()
    inner = inner.replace('stroke-width="2"', 'stroke-width="1.5"')
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{}</svg>'.format(inner)

# ── Tab icons (Lucide) ──
tab = {
    'recommend': lu('shirt'), 'explore': lu('crosshair'), 'wardrobe': lu('layout-grid'),
    'add': lu('camera'), 'profile': lu('user'),
}

# ── Clothing item icons (CI for clothing, Lucide for shoes) ──
item_icons = {
    'tshirt': ci('TShirt') or lu('shirt'),
    'pants': ci('PantsMans') or '',
    'shoe': lu('sport-shoe'),
    'hat': ci('BaseballCap') or '',
    'bag': lu('shopping-bag'),
    'sock': ci('Socks') or lu('shirt'),
    'acc': lu('watch'),
    'sun': lu('glasses'),
}
# Fallback for CI if missing
if not item_icons['pants']:
    item_icons['pants'] = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 2h10v4l-3 4v12h-4V10L7 6V2z"/></svg>'
if not item_icons['hat']:
    item_icons['hat'] = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 17h20v2a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-2z"/><path d="M5 17v-6a7 7 0 0 1 14 0v6"/></svg>'

# ── Inline small icons (Lucide) ──
ico = {
    'cal': lu('calendar'), 'cloud': lu('cloud'), 'search': lu('search'),
    'shirt_sm': lu('shirt'),  # for mini cards
}

# ── Add page icons ──
add_icons = {
    'camera_lg_icon': lu('camera'),     # camera icon
    'image_icon': lu('image'),          # album/image icon
    'lock_icon': lu('lock'),            # privacy lock
}

# ── Rating UI icons ──
star_filled_svg = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'
star_outline_svg = lu('star') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'
check_svg = lu('check') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 6L9 17l-5-5"/></svg>'
x_svg = lu('x') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 6L6 18M6 6l12 12"/></svg>'
style_icon_svg = lu('palette') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>'
scene_icon_svg = lu('map-pin') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>'
combo_icon_svg = lu('shirt') or '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20.38 3.46L16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/></svg>'

# ── Build HTML ──
def tab_btn(key, label, active=False):
    cls = 'tab active' if active else 'tab'
    svg = tab.get(key, '')
    return '<div class="{}" data-page="{}"><div class="t-icon">{}</div><span class="t-label">{}</span></div>'.format(cls, key, svg, label)

def item_row(icon_svg, cat, iid, name, thumb='', cutout=''):
    thumb_html = ''
    if thumb:
        # 缩略图用 CDN，点开放大走 /api/image（享受 600px 缩图 + ETag 缓存）
        if cutout:
            from urllib.parse import quote
            cp = cutout
            if cp.startswith('..'):
                cp = cp[3:]  # strip ../
            elif cp.startswith('/'):
                cp = cp[1:]
            cutout_src = '/api/image?f=' + quote(cp)
        else:
            cutout_src = thumb
        thumb_html = '<img class="item-thumb" src="{}" data-cutout="{}" onclick="event.stopPropagation();showImg(this.dataset.cutout)" loading="lazy">'.format(thumb, cutout_src)
    return '<div class="item-row"><span class="item-emoji">{}</span><span class="item-cat">{}</span><span class="item-id">{}</span><span class="item-name">{}</span>{}</div>'.format(icon_svg, cat, iid, name, thumb_html)

# ── Chinese color → hex mapping ──
COLOR_MAP = {
    '黑色':'#2a2a2a','深黑':'#1a1a1a','纯黑':'#000',
    '白色':'#f5f3ef','米白':'#f5f0e8','乳白':'#faf8f5','本白':'#fefdfb',
    '深灰':'#4a4a4a','灰色':'#9e9e9e','浅灰':'#d0d0d0','银灰':'#bdbdbd','灰白':'#e0ded8',
    '灰绿':'#8a9a82','灰绿色':'#8a9a82',
    '卡其':'#c4b5a0','卡其色':'#c4b5a0','卡其驼色':'#c4b098','驼色':'#b8976e',
    '深棕':'#5c3d2e','棕色':'#7a5230','浅棕':'#b8956a',
    '深蓝':'#1e3a5f','藏蓝':'#1e3a6f','藏青':'#1e3a5f','海军蓝':'#1e3a5f','蓝色':'#4a7eb5','浅蓝':'#7ea3c8','天蓝':'#8bb8d6',
    '军绿':'#5c6e4a','军绿色':'#5c6e4a','深军绿':'#4a5c3a','墨绿':'#3c5032','绿色':'#6b8c5c','浅绿':'#9cba8c',
    '红色':'#c4523c','暗红':'#8b2e3e','酒红':'#8b2e3e','深红':'#7a2a2a','亮红':'#d4453c',
    '橙色':'#e88a3c','亮橙':'#f0983c','橘色':'#e88030',
    '黄色':'#d4a84b','姜黄':'#c49a3c','亮黄':'#e8c84b','米黄':'#e8d8b0',
    '紫色':'#8b6b9e','浅紫':'#b89ac8',
    '粉色':'#e8b4b8','浅粉':'#f0c8cc',
    '米色':'#e8dcc8','沙色':'#d8ccb0',
    '深牛仔蓝':'#2a4a6c','牛仔蓝':'#4a6a8c','浅牛仔蓝':'#7a9ab8',
    '条纹':'#c0c0c0','印花':'#c0c0c0',
}
def color_to_hex(name):
    """Convert Chinese color name to approximate hex code"""
    if not name: return None
    name = name.strip()
    if name in COLOR_MAP: return COLOR_MAP[name]
    # Partial match
    for cname, chex in COLOR_MAP.items():
        if cname in name or name in cname: return chex
    return None

def extract_palette(outfit):
    """Extract color palette from .color_cache.json (same source as WeChat push).
    Falls back to Chinese color name mapping if cache unavailable."""
    dp = os.path.join(OUTFITS_DIR, outfit['dir'])
    # Strategy 1: Read from .color_cache.json (generated by composite_v2, used by build_push)
    for sub in ['上身效果', '豆包生图']:
        cache_file = os.path.join(dp, sub, '.color_cache.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file) as f:
                    colors = [tuple(c) for c in json.load(f)]
                # Convert (R,G,B) tuples to hex, deduplicate
                seen = set()
                hex_colors = []
                for rgb in colors[:5]:
                    hex_c = '#{:02x}{:02x}{:02x}'.format(*rgb)
                    if hex_c not in seen:
                        hex_colors.append(hex_c)
                        seen.add(hex_c)
                if hex_colors:
                    return hex_colors
            except: pass
    # Strategy 2: Fallback to Chinese color name mapping
    colors = []
    seen = set()
    md_path = os.path.join(dp, 'outfit.md')
    if os.path.exists(md_path):
        with open(md_path) as f: content = f.read()
        for it in outfit.get('items', []):
            for line in content.split('\n'):
                if it['id'] in line and line.strip().startswith('|'):
                    cells = [c.strip().replace('**','') for c in line.split('|')]
                    if len(cells) >= 5:
                        color_text = cells[4].split('，')[0].split(',')[0].strip()
                        hex_c = color_to_hex(color_text)
                        if hex_c and hex_c not in seen:
                            colors.append(hex_c)
                            seen.add(hex_c)
                    break
    return colors[:5]

def _escape_html(text):
    """Escape HTML special characters"""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def build_rationale_html(outfit):
    """Build rationale + dressing tips HTML block"""
    rationale = outfit.get('rationale', '')
    tips = outfit.get('dressing_tips', [])

    if not rationale and not tips:
        return ''

    parts = ['<div class="rationale-box">']

    if rationale:
        parts.append('<div class="ra-title">推荐理由</div>')
        parts.append('<div class="ra-text">{}</div>'.format(_escape_html(rationale)))

    if tips:
        parts.append('<div class="rationale-tips">')
        for tip in tips:
            parts.append('<div class="rt-item"><span class="rt-dot"></span>{}</div>'.format(_escape_html(tip)))
        parts.append('</div>')

    parts.append('</div>')
    return '\n'.join(parts)


def build_palette_html(outfit):
    """Build palette strip HTML from outfit colors"""
    colors = extract_palette(outfit)
    if not colors:
        return ''
    dots = ''.join('<span class="pal-dot" style="background:{}"></span>'.format(c) for c in colors)
    return '<div class="palette-strip"><span class="pal-label">COLOR PALETTE</span>{}</div>'.format(dots)

def split_brand_desc(name):
    """Split a simplified item name into (brand, description)"""
    brands = ['COMME des GARÇONS PLAY','COMME des GARCONS','Decathlon Artengo',
              'Decathlon Kiprun','FUR SPEED','Cotton On','H FOREST','DAN JOHN',
              'LIBERTY SHINE','Apple Watch','Lululemon','Champion','Converse',
              'Timberland','Artengo','Decathlon','Merrell','Adidas','Jordan',
              'Wilson','Kiprun','Uniqlo','FILA','SHINO','YASCIQ','Puma','NBA',
              'HLA','Nike','CDG']
    for b in brands:
        if b.lower() in name.lower():
            desc = name.replace(b, '').strip()
            return (b, desc)
    return ('', name)

def mini_card(style_name, all_items):
    # Show first 3 items collapsed, rest in detail
    preview = all_items[:3]
    detail = all_items[3:]
    prev_html = ''.join('<div>{}</div>'.format(p) for p in preview)
    detail_html = ''.join('<div class="rci">{}</div>'.format(d) for d in detail)
    arrow = '<div class="rc-arrow">▾</div>' if detail else ''
    return '<div class="rec-card" onclick="this.classList.toggle(\'open\')"><div class="rc-style-name">{name}</div><div class="rc-items">{prev}</div>{detail_block}{arrow}</div>'.format(name=style_name, prev=prev_html, detail_block=('<div class="rc-detail">'+detail_html+'</div>') if detail else '', arrow=arrow)

html = '''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no,viewport-fit=cover">
<title>穿搭助手</title>
<link rel="dns-prefetch" href="https://cdn.jsdelivr.net">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<script>var __CDN__='';</script>
<style>
:root{{--navy:#1e3a5f;--navy-light:#2a5080;--text:#1a2838;--sub:#6b7d94;
  --muted:#94a3b5;--border:#e6ecf3;--bg:#f8fafc;--white:#fff;
  --shadow:0 2px 8px rgba(30,58,95,.04);--radius:14px;--radius-sm:10px}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#e2e6ec;display:flex;justify-content:center;min-height:100vh;-webkit-font-smoothing:antialiased}}
#app{{max-width:500px;width:100%;background:var(--bg);min-height:100vh;display:flex;flex-direction:column;position:relative;overflow:hidden;padding-bottom:80px}}
.header{{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:var(--white);border-bottom:1px solid var(--border)}}
.header h1{{font-size:17px;font-weight:700;color:var(--text);letter-spacing:-.4px}}
.header .avatar{{width:34px;height:34px;background:var(--navy);border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600}}
.segmented{{display:flex;background:#eef2f7;border-radius:12px;padding:3px;margin:14px 20px;gap:2px}}
.seg-btn{{flex:1;text-align:center;padding:9px 0;font-size:13px;font-weight:600;color:var(--sub);border-radius:10px;cursor:pointer;transition:all .25s;-webkit-tap-highlight-color:transparent}}
.seg-btn.active{{background:var(--navy);color:#fff;box-shadow:0 2px 8px rgba(30,58,95,.25)}}
.page{{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0}}
.page.active{{display:flex}}
.scroll-area{{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 14px 16px;min-height:0}}
.page-bottom{{flex-shrink:0;padding:10px 20px;background:var(--bg);border-top:1px solid var(--border);z-index:5;display:flex;align-items:center}}
.page-bottom input{{width:100%;padding:14px 18px;border:none;border-radius:var(--radius-sm);background:var(--white);font-size:14px;color:var(--text);box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);outline:none;-webkit-appearance:none}}
.page-bottom input:focus{{border-color:var(--navy);box-shadow:0 0 0 3px rgba(30,58,95,.08)}}
.page-bottom input::placeholder{{color:var(--muted)}}

/* Hero card */
.hero-card{{background:var(--white);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);margin:16px 0 14px;border:1px solid rgba(30,58,95,.05)}}
.hero-img{{width:100%;background:#f8fafc;overflow:hidden}}
.hero-img img{{width:100%;display:block}}
.hero-body{{padding:18px}}
.hero-style{{font-size:22px;font-weight:800;color:var(--text);letter-spacing:-.5px;margin-bottom:6px}}
.hero-meta{{font-size:12px;color:var(--sub);margin-bottom:14px}}
/* Style tags */
.style-tags{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}}
.style-tags span{{font-size:11px;color:#fff;background:var(--navy);padding:4px 10px;border-radius:10px;font-weight:500}}
/* Item grid — 3 cols */
.item-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}}
.item-grid .item-row{{flex-direction:column;align-items:flex-start;gap:4px;padding:8px;background:#f8fafc;border-radius:8px;border:none}}
.item-grid .item-emoji{{width:16px;height:16px}}
.item-grid .item-cat{{font-size:9px;width:auto}}
.item-grid .item-id{{font-size:8px}}
.item-grid .item-name{{font-size:9px;white-space:normal}}
.item-thumb{{width:28px;height:28px;object-fit:cover;border-radius:4px;cursor:pointer;flex-shrink:0;margin-left:auto}}
/* Lightbox */
.lightbox{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.9);z-index:200;align-items:center;justify-content:center}}
.lightbox.show{{display:flex}}
.lightbox img{{max-width:90%;max-height:80%;object-fit:contain;border-radius:8px}}
.lightbox .close{{position:absolute;top:20px;right:24px;color:#fff;font-size:32px;cursor:pointer;z-index:201}}
/* Palette strip */
.palette-strip{{display:flex;align-items:center;gap:4px;padding:10px 0;border-top:1px solid var(--border)}}
.pal-label{{font-size:9px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-right:6px}}
.pal-dot{{width:16px;height:16px;border-radius:4px;border:1px solid var(--border);flex-shrink:0}}
/* Rationale */
.rationale-box{{padding:10px 0;border-top:1px solid var(--border)}}
.rationale-box .ra-title{{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:1px;margin-bottom:6px}}
.rationale-box .ra-text{{font-size:12px;color:var(--text);line-height:1.75}}
.rationale-tips{{margin-top:8px;display:flex;flex-direction:column;gap:3px}}
.rationale-tips .rt-item{{font-size:11px;color:var(--sub);line-height:1.6;padding-left:12px;position:relative}}
.rt-dot{{position:absolute;left:0;top:5px;width:5px;height:5px;border-radius:50%;background:var(--navy)}}

/* Hero item grid — 2 cols */
.hero-item-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:14px}}
.hero-item{{background:#f8fafc;border-radius:8px;padding:8px;display:flex;flex-wrap:wrap;align-items:flex-start;gap:1px 5px;position:relative}}
.hero-item .item-emoji{{width:14px;height:14px;flex-shrink:0;color:var(--navy)}}
.hero-item .ir-id{{font-size:7px;color:var(--muted);font-family:monospace;flex-shrink:0;line-height:14px}}
.hero-item .ir-brand{{font-size:11px;font-weight:700;color:var(--text);width:100%;text-align:left;line-height:1.3}}
.hero-item .ir-desc{{font-size:10px;color:var(--sub);width:100%;text-align:left;line-height:1.4}}
.hero-item .item-thumb{{width:28px;height:28px;object-fit:cover;border-radius:4px;cursor:pointer;flex-shrink:0;margin-left:auto;order:99}}
/* Item rows */
.item-list{{display:flex;flex-direction:column}}
.item-row{{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f2f5f9}}
.item-row:last-child{{border-bottom:none}}
.item-emoji{{width:17px;height:17px;flex-shrink:0;color:var(--navy)}}
.item-emoji svg{{width:100%;height:100%;display:block}}
.item-cat{{font-size:10px;color:var(--muted);width:22px;flex-shrink:0;font-weight:500}}
.item-id{{font-size:10px;color:var(--sub);font-family:monospace;background:#f0f4f8;padding:2px 5px;border-radius:4px;flex-shrink:0}}
.item-name{{font-size:12px;color:var(--text);flex:1;min-width:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word;line-height:1.35}}

/* Section */
.section-header{{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:1.5px;margin:0 0 12px}}

/* Mini rec cards — horizontal, square-ish */
.rec-cards{{display:flex;gap:10px;margin-bottom:16px}}
.rec-card{{flex:1;min-width:0;background:var(--white);border-radius:var(--radius-sm);padding:14px 12px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;text-align:center}}
.rec-card:active{{transform:scale(.97)}}
.rec-card .rc-style-name{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px}}
.rec-card .rc-items{{font-size:11px;color:var(--sub);line-height:1.8}}
.rec-card .rc-items div{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.rec-card .rc-detail{{display:none;margin-top:6px;padding-top:6px;border-top:1px solid #f0f4f8}}
.rec-card.open .rc-detail{{display:block}}
.rec-card .rc-detail .rci{{font-size:11px;color:var(--sub);line-height:1.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.rec-card .rc-arrow{{text-align:center;font-size:9px;color:var(--muted);margin-top:6px;transition:transform .25s;cursor:pointer}}
.rec-card.open .rc-arrow{{transform:rotate(180deg)}}
.rec-card.dashed{{background:transparent;border:2px dashed #dce3ed;display:flex;align-items:center;justify-content:center}}
.rec-card.dashed .dash-text{{color:var(--muted);font-size:12px}}

/* Tab Bar */
.tab-bar{{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(30,58,95,.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:18px;padding:6px 8px;display:flex;gap:2px;z-index:100;box-shadow:0 8px 32px rgba(30,58,95,.25);max-width:440px;width:calc(100% - 32px);pointer-events:auto}}
.tab{{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;cursor:pointer;padding:8px 0;border-radius:14px;transition:all .25s;-webkit-tap-highlight-color:transparent;min-width:56px}}
.tab .t-icon{{width:22px;height:22px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5);transition:color .25s}}
.tab .t-icon svg{{width:100%;height:100%}}
.tab .t-label{{font-size:10px;color:rgba(255,255,255,.55);font-weight:500;transition:color .25s}}
.tab.active{{background:rgba(255,255,255,.15)}}
.tab.active .t-icon{{color:#fff}}
.tab.active .t-label{{color:#fff;font-weight:600}}

/* Favorites */
.fav-list{{display:flex;flex-direction:column;gap:8px}}
.fav-card{{display:flex;align-items:center;gap:12px;background:var(--white);border-radius:var(--radius-sm);padding:14px 16px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);cursor:pointer;flex-wrap:wrap}}
.fav-card.expanded{{flex-direction:column;align-items:stretch}}
.fav-num{{width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.fav-info{{flex:1;min-width:0}}
.fav-style{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:3px}}
.fav-meta{{font-size:11px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.fav-expand{{display:none}}
.fav-card.expanded .fav-expand{{display:block;width:100%;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}}
.fav-expand .item-grid{{margin-bottom:0}}
.fav-card .fav-arrow{{font-size:9px;color:var(--muted);transition:transform .25s;flex-shrink:0}}
.fav-card.expanded .fav-arrow{{transform:rotate(180deg)}}
.fav-card.expanded .h-thumb-sm{{display:none}}
.fav-card.filtered{{display:none}}
.h-char-img{{width:80px;height:80px;border-radius:8px;object-fit:cover;flex-shrink:0;cursor:pointer}}
.h-thumb-sm{{width:42px;height:42px;border-radius:6px;object-fit:cover;flex-shrink:0;margin-left:8px}}
.h-tags{{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}}
.h-tags span{{font-size:9px;background:var(--navy);color:#fff;padding:2px 7px;border-radius:8px;font-weight:500}}
.h-expand-row{{display:flex;gap:14px;align-items:flex-start}}
.h-head-palette{{display:flex;align-items:center;gap:4px;margin-top:6px}}
.h-head-palette .pal-dot{{width:14px;height:14px;border-radius:3px;border:1px solid var(--border)}}
.h-char-img-lg{{width:170px;height:226px;border-radius:10px;object-fit:cover;flex-shrink:0;cursor:pointer}}
/* 2x4 square grid */
.h-square-grid{{flex:1;display:grid;grid-template-columns:repeat(2,1fr);gap:5px;align-content:start;grid-auto-rows:53px}}
.h-square-grid .item-row{{display:flex;flex-direction:column;gap:0;padding:3px 5px;background:#f8fafc;border-radius:6px;cursor:pointer;position:relative;overflow:hidden;min-height:53px;justify-content:flex-start;align-items:flex-start}}
.h-square-grid .item-row .ir-top{{display:flex;align-items:center;gap:2px}}
.h-square-grid .item-row.clickable:active{{background:#eef2f7}}
.h-square-grid .item-emoji{{width:13px;height:13px;flex-shrink:0}}
.h-square-grid .item-id{{font-size:7px;flex-shrink:0}}
.h-square-grid .ir-brand{{font-size:7px;font-weight:700;color:var(--text);line-height:1.15;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;text-align:left}}
.h-square-grid .ir-desc{{font-size:7px;color:var(--sub);line-height:1.2;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;text-align:left}}
.h-square-grid .item-row.expanded{{grid-column:1 / -1;grid-row:span 2;padding:4px;z-index:2}}
.h-square-grid .item-row.expanded .ir-top,.h-square-grid .item-row.expanded .ir-brand,.h-square-grid .item-row.expanded .ir-desc{{display:none}}
.h-square-grid .item-row.expanded .item-img{{display:block;border-radius:6px}}
.h-exp-bottom{{display:flex;align-items:center;justify-content:space-between;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}}
.h-exp-palette{{display:flex;align-items:center;gap:4px}}
.h-exp-palette .pal-dot{{width:16px;height:16px;border-radius:3px;border:1px solid var(--border)}}
.pin-btn{{padding:5px 12px;background:var(--white);border:1px solid var(--navy);border-radius:16px;color:var(--navy);font-size:11px;font-weight:600;cursor:pointer;transition:all .2s;-webkit-tap-highlight-color:transparent;flex-shrink:0}}
.pin-btn:active{{background:var(--navy);color:#fff}}
.h-square-grid .item-img{{display:none;width:100%;height:100%;object-fit:contain;position:absolute;top:0;left:0;padding:4px}}
.h-square-grid .item-row.showing-img .item-img{{display:block}}
.placeholder{{text-align:center;padding:60px 20px;cursor:pointer}}
.placeholder .ph-icon{{width:56px;height:56px;margin:0 auto 16px;color:var(--navy);opacity:.5}}
.placeholder .ph-icon svg{{width:100%;height:100%}}
.placeholder .ph-text{{font-size:14px;line-height:1.7;color:var(--sub)}}
/* Progress overlay */
.progress-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(26,40,56,.55);z-index:160;align-items:center;justify-content:center;-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}}
.progress-overlay.show{{display:flex}}
.progress-card{{background:var(--white);border-radius:var(--radius);padding:32px 24px;max-width:340px;width:calc(100% - 48px);text-align:center;box-shadow:0 12px 48px rgba(0,0,0,.18);animation:fadeInUp .3s ease}}
@keyframes fadeInUp{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}
.progress-spinner{{width:38px;height:38px;border:3px solid var(--border);border-top-color:var(--navy);border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 18px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.progress-title{{font-size:16px;font-weight:700;color:var(--text);margin-bottom:14px;min-height:22px}}
.progress-steps{{text-align:left;font-size:12px;color:var(--sub);line-height:2.2;max-height:200px;overflow-y:auto}}
.progress-steps .step-done{{color:#5a7d3a}}
.progress-steps .step-active{{color:var(--navy);font-weight:600}}
.progress-steps .step-pending{{color:var(--muted)}}
.progress-dot{{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:8px;vertical-align:middle}}
.progress-dot.done{{background:#5a7d3a}}
.progress-dot.active{{background:var(--navy);animation:pulse 1s ease infinite}}
.step-estimate{{font-size:11px;color:var(--muted);padding:2px 0 8px 0;font-style:italic}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.progress-result-img{{width:100%;border-radius:10px;margin-top:14px;box-shadow:var(--shadow)}}
.progress-close{{display:inline-block;margin-top:18px;padding:10px 28px;background:var(--navy);color:#fff;border:none;border-radius:20px;font-size:14px;font-weight:600;cursor:pointer}}
/* Wardrobe page */
.wrd-stats{{display:flex;gap:10px;margin:16px 0 12px}}
.wrd-stat-card{{flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)}}
.wrd-stat-num{{font-size:26px;font-weight:800;color:var(--navy)}}
.wrd-stat-label{{font-size:10px;color:var(--muted);margin-top:2px}}
.wrd-stat-card.warn .wrd-stat-num{{color:#c4523c}}
.skeleton-text{{animation:skeleton-pulse 1.5s ease infinite;border-radius:6px}}
@keyframes skeleton-pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
/* Category rows + horizontal scroll */
.wrd-cat-row{{margin-bottom:22px}}
.wrd-cat-header{{display:flex;align-items:center;gap:8px;padding:0 4px 10px}}
.wrd-cat-header-icon{{font-size:18px}}
.wrd-cat-header-name{{font-size:14px;font-weight:700;color:var(--text)}}
.wrd-cat-header-count{{font-size:12px;color:var(--muted)}}
.wrd-cat-scroll{{display:flex;gap:10px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-top:6px;padding-bottom:8px;scrollbar-width:none}}
.wrd-cat-scroll::-webkit-scrollbar{{display:none}}
/* Horizontal item card */
.wrd-item-card-h{{flex:0 0 auto;width:100px;scroll-snap-align:start;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:transform .15s}}
.wrd-item-card-h:active{{transform:scale(.96)}}
.wrd-item-card-img-wrap{{position:relative;width:100px;height:120px;background:#f0f4f8;border-radius:var(--radius-sm);overflow:hidden}}
.wrd-item-card-img{{width:100%;height:100%;object-fit:cover;display:block}}
.wrd-item-card-id{{position:absolute;bottom:4px;left:4px;font-size:8px;font-family:monospace;color:#fff;background:rgba(0,0,0,.55);padding:2px 5px;border-radius:4px;letter-spacing:.3px;line-height:1}}
/* Item detail modal — bottom sheet */
.item-modal-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(26,40,56,.6);z-index:180;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);justify-content:center;align-items:flex-end;-webkit-transform:translateZ(0);transform:translateZ(0)}}
.item-modal-overlay.show{{display:flex}}
.item-modal{{background:var(--white);border-radius:var(--radius) var(--radius) 0 0;width:100%;max-width:500px;max-height:92vh;display:flex;flex-direction:column;animation:slideUp .3s ease}}
@keyframes slideUp{{from{{transform:translateY(100%)}}to{{transform:translateY(0)}}}}
.item-modal-close{{position:absolute;top:12px;right:16px;font-size:26px;color:var(--muted);cursor:pointer;z-index:5;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:rgba(255,255,255,.85)}}
.item-modal-scroll{{flex:1;overflow-y:auto;padding:24px 0 20px;min-height:0}}
/* Hero image + rotate */
.im-hero{{position:relative;width:100%;height:50vh;max-height:420px;background:#f0f4f8;overflow:hidden;box-sizing:border-box}}
.im-hero-img{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);max-width:calc(100% - 32px);max-height:calc(100% - 48px);width:auto;height:auto;display:block;object-fit:contain;transition:transform .3s ease}}
.im-rotate-btn{{position:absolute;bottom:12px;width:36px;height:36px;border-radius:50%;background:rgba(0,0,0,.45);color:#fff;border:none;font-size:18px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:3;-webkit-tap-highlight-color:transparent}}
.im-rotate-btn:active{{background:rgba(0,0,0,.7)}}
.im-rotate-left{{left:16px}}
.im-rotate-right{{right:16px}}
.im-hero-id{{position:absolute;top:12px;left:12px;font-size:11px;font-family:monospace;color:#fff;background:rgba(0,0,0,.6);padding:4px 8px;border-radius:6px;z-index:2}}
/* Info header */
.im-info{{padding:16px 16px 0}}
.im-info-name{{font-size:13px;color:var(--text);line-height:1.5;margin-bottom:4px}}
.im-info-brand{{font-size:12px;color:var(--sub)}}
/* Tag chips */
.im-tags-title{{font-size:12px;font-weight:700;color:var(--muted);padding:14px 16px 8px;letter-spacing:.5px}}
.im-tags{{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px}}
.im-tag{{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:12px;font-size:11px;font-weight:500;cursor:pointer;-webkit-tap-highlight-color:transparent;background:#eef2f7;color:var(--sub);border:1px solid transparent;transition:all .15s}}
.im-tag:active{{transform:scale(.96)}}
.im-tag.editing{{background:var(--white);border-color:var(--navy);color:var(--text)}}
.im-tag .im-tag-del{{font-size:14px;line-height:1;opacity:.4;cursor:pointer;margin-left:2px}}
.im-tag .im-tag-del:hover{{opacity:1;color:#c4523c}}
.im-tag-add{{background:transparent;border:1px dashed var(--border);color:var(--muted)}}
.im-tag-input{{width:80px;border:none;outline:none;font-size:11px;background:transparent;color:var(--text);padding:0}}
/* Tag detail modal (nested) */
.im-tag-detail{{padding:12px 16px;border-top:1px solid var(--border);margin-top:8px}}
.im-tag-detail input{{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;color:var(--text);margin-bottom:8px}}
.im-tag-detail textarea{{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;color:var(--text);resize:vertical;min-height:60px;margin-bottom:8px}}
.im-tag-detail-btns{{display:flex;gap:8px}}
.im-tag-detail-btns button{{flex:1;padding:10px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;border:none}}
.im-btn-save{{background:var(--navy);color:#fff}}
.im-btn-cancel{{background:#eef2f7;color:var(--sub)}}
/* Explore style cards */
.exp-style-card{{background:var(--white);border-radius:var(--radius);padding:18px 16px;margin-bottom:10px;box-shadow:var(--shadow);cursor:pointer;transition:all .2s;-webkit-tap-highlight-color:transparent;border:1px solid rgba(30,58,95,.04);display:flex;flex-direction:column;gap:8px}}
.exp-style-card:active{{transform:scale(.98);background:#f8fafc}}
.es-header{{display:flex;align-items:flex-start;gap:12px}}
.es-icon{{width:56px;height:72px;border-radius:8px;background:var(--navy);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;font-weight:700;overflow:hidden;position:relative}}
.es-icon img{{width:100%;height:100%;object-fit:cover;display:block;position:absolute;top:0;left:0}}
.es-icon.has-img{{background:#f0f4f8}}
.es-info{{flex:1;min-width:0}}
.es-name{{font-size:15px;font-weight:700;color:var(--text);line-height:1.3;margin-bottom:1px}}
.es-en{{font-size:11px;color:var(--muted);font-weight:400}}
.es-desc{{font-size:12px;color:var(--sub);line-height:1.55;margin-top:2px}}
.es-footer{{display:flex;justify-content:space-between;align-items:center}}
.es-fusion{{text-align:center;font-size:16px;font-weight:700;color:var(--navy);padding:14px;background:linear-gradient(135deg,#f0f4ff,#faf5ff);border-radius:var(--radius-sm);margin-bottom:14px;border:1px solid #e0e4f8}}
/* Style card bottom: items + try */
.es-bottom{{display:flex;align-items:flex-end;justify-content:space-between;gap:8px;margin-top:6px}}
.es-items{{display:flex;gap:6px;flex:1;flex-wrap:wrap;align-items:flex-end}}
.es-item-chip{{background:#f0f4f8;border-radius:7px;padding:2px}}
.es-item-chip img{{width:28px;height:28px;border-radius:5px;object-fit:cover;display:block;cursor:pointer}}
.es-try-btn{{flex-shrink:0;padding:7px 14px;background:var(--navy);color:#fff;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;transition:all .2s;-webkit-tap-highlight-color:transparent}}
.es-try-btn:active{{background:var(--navy-light);transform:scale(.96)}}
.es-try-btn.loading{{opacity:.6;pointer-events:none}}
/* Action buttons */
.im-actions{{display:flex;gap:10px;padding:16px}}
.im-actions button{{flex:1;padding:12px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;border:none;-webkit-tap-highlight-color:transparent}}
.im-btn-save-tags{{background:var(--navy);color:#fff}}
.im-btn-archive{{background:transparent;color:#c4523c;border:1px solid #fce4ec!important}}
.im-btn-restore{{background:transparent;color:#2e7d32;border:1px solid #e8f5e9!important}}
.im-btn-boost{{background:transparent;color:#e88a3c;border:1px solid #fff3e0!important}}
/* Add clothing page */
.add-action-cards{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:20px 16px}}
.add-action-card{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:36px 16px;min-height:150px;background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);cursor:pointer;transition:all .2s;border:2px solid transparent;-webkit-tap-highlight-color:transparent}}
.add-action-card:active{{transform:scale(.97);background:#f8fafc}}
.add-action-icon{{width:52px;height:52px;color:var(--navy);opacity:.85}}
.add-action-icon svg{{width:100%;height:100%}}
.add-action-label{{font-size:18px;font-weight:700;color:var(--text)}}
.add-action-hint{{font-size:12px;color:var(--muted)}}
/* Image strip */
.add-image-strip{{display:flex;gap:10px;overflow-x:auto;padding:16px 14px;scrollbar-width:none;align-items:center}}
.add-image-strip::-webkit-scrollbar{{display:none}}
.add-image-thumb{{flex:0 0 88px;width:88px;height:88px;border-radius:10px;overflow:hidden;position:relative;background:#f0f4f8}}
.add-image-thumb img{{width:100%;height:100%;object-fit:cover}}
.add-image-thumb .thumb-remove{{position:absolute;top:2px;right:2px;width:22px;height:22px;background:rgba(0,0,0,.55);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;line-height:1;cursor:pointer;z-index:2}}
.add-more-btn{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;border:2px dashed #dce3ed;background:transparent;cursor:pointer}}
.add-more-plus{{font-size:28px;color:var(--muted);line-height:1}}
.add-more-label{{font-size:10px;color:var(--muted)}}
/* Review cards */
.add-review-card{{background:var(--white);border-radius:var(--radius);padding:14px 16px;margin-bottom:10px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.05)}}
.add-review-card .ar-header{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.add-review-card .ar-id{{font-size:12px;font-family:monospace;font-weight:700;color:var(--navy);background:#eef2f7;padding:2px 8px;border-radius:4px}}
.add-review-card .ar-cat{{font-size:11px;color:var(--sub);font-weight:500}}
.add-review-card .ar-fields{{display:flex;flex-direction:column;gap:6px}}
.add-review-card .ar-field{{display:flex;align-items:center;gap:8px;font-size:12px}}
.add-review-card .ar-label{{color:var(--muted);width:36px;flex-shrink:0;font-weight:500}}
.add-review-card .ar-value{{color:var(--text);flex:1}}
/* 🆕 衣橱匹配卡片 */
.match-section{{margin:16px 0}}
.match-section-title{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.match-section-title .ms-icon{{font-size:16px}}
.match-cat-group{{margin-bottom:14px}}
.match-cat-label{{font-size:11px;font-weight:600;color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:6px;letter-spacing:.3px}}
.match-cat-label .mcl-count{{font-weight:400;color:var(--sub)}}
.match-scroll{{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-bottom:4px;scrollbar-width:none}}
.match-scroll::-webkit-scrollbar{{display:none}}
.match-card{{flex:0 0 105px;scroll-snap-align:start;background:var(--white);border-radius:10px;padding:10px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.05);cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;gap:5px;position:relative}}
.match-card:active{{transform:scale(.96)}}
.match-card .mc-score{{position:absolute;top:4px;right:6px;font-size:9px;font-weight:700;color:var(--navy);background:#eef2f7;padding:1px 6px;border-radius:6px}}
.match-card .mc-thumb{{width:56px;height:56px;border-radius:8px;object-fit:cover;background:#f8fafc}}
.match-card .mc-id{{font-size:9px;font-family:monospace;color:var(--sub);font-weight:600}}
.match-card .mc-brand{{font-size:10px;color:var(--text);text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}}
.match-card .mc-color{{font-size:9px;color:var(--muted)}}
.match-card .mc-reasons{{display:flex;flex-wrap:wrap;gap:2px;justify-content:center}}
.match-card .mc-reason{{font-size:7px;background:#eef7f0;color:#2e7d32;padding:1px 5px;border-radius:4px;white-space:nowrap}}
.match-card.selected{{border:2px solid var(--navy);box-shadow:0 0 0 3px rgba(30,58,95,.1)}}
.match-card.selected .mc-score{{background:var(--navy);color:#fff}}
/* 🆕 生图预览 CTA */
.preview-cta{{text-align:center;padding:16px 0}}
.preview-cta-btn{{display:inline-flex;align-items:center;gap:8px;padding:13px 28px;background:linear-gradient(135deg,#1e3a5f,#2a5080);color:#fff;border:none;border-radius:24px;font-size:15px;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(30,58,95,.25);transition:all .2s;-webkit-tap-highlight-color:transparent}}
.preview-cta-btn:active{{transform:scale(.96)}}
.preview-cta-btn:disabled{{opacity:.5;transform:none}}
.preview-cta-hint{{font-size:11px;color:var(--muted);margin-top:8px}}
/* 🆕 穿搭预览结果 */
.outfit-preview{{margin:16px 0;background:var(--white);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.05)}}
.outfit-preview .op-hero{{position:relative;background:#f8fafc}}
.outfit-preview .op-hero img{{width:100%;display:block}}
.outfit-preview .op-body{{padding:16px}}
.outfit-preview .op-title{{font-size:15px;font-weight:700;color:var(--text);margin-bottom:12px}}
.outfit-preview .op-items{{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}}
.outfit-preview .op-item{{display:flex;align-items:center;gap:10px;padding:8px 10px;background:#f8fafc;border-radius:8px;font-size:12px}}
.outfit-preview .op-item .opi-badge{{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;flex-shrink:0}}
.opi-badge.new{{background:#fff3e0;color:#e67e22}}
.opi-badge.existing{{background:#eef2f7;color:var(--sub)}}
.outfit-preview .op-item .opi-name{{flex:1;color:var(--text);font-weight:500}}
.outfit-preview .op-item .opi-color{{color:var(--muted);font-size:11px}}
.outfit-preview .op-actions{{display:flex;gap:10px}}
.outfit-preview .op-actions button{{flex:1;padding:12px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;border:none}}
.op-btn-retry{{background:#eef2f7;color:var(--text)}}
.op-btn-confirm{{background:var(--navy);color:#fff}}
/* New badge */
.new-badge{{position:absolute;top:-3px;right:-3px;background:linear-gradient(135deg,#ff6b6b,#ee5a24);color:#fff;font-size:7px;font-weight:700;padding:2px 5px;border-radius:5px;z-index:2;letter-spacing:.5px;box-shadow:0 1px 4px rgba(238,90,36,.35);animation:badgePulse 2s ease infinite;pointer-events:none}}
@keyframes badgePulse{{{{0%,100%{{{{transform:scale(1)}}}}50%{{{{transform:scale(1.1)}}}}}}}}
.im-tag-group{{padding:8px 16px}}
.im-tag-group-title{{font-size:11px;font-weight:700;color:var(--muted);margin-bottom:6px;letter-spacing:.5px}}
.im-tag-ro{{opacity:.8;pointer-events:none}}
.im-tag-group-hl{{background:linear-gradient(135deg,#f0f4ff,#faf5ff);border-radius:12px;padding:12px 16px;margin:4px 8px;border:1px solid #e0e4f8}}
.im-tag-group-hl .im-tag{{background:var(--white);border-color:#d0d4f0;color:var(--navy);font-weight:600}}
.im-tag-group-hl .im-tag-group-title{{color:var(--navy-light)}}
/* Keep old detail for cold-items backward compat */
.wrd-monthly{{margin:12px 0 16px}}
.wrd-monthly .wm-card{{background:var(--white);border-radius:10px;padding:16px;box-shadow:var(--shadow);margin-bottom:10px}}
.wrd-monthly .wm-title{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:10px}}
.wrd-monthly .wm-stat-row{{display:flex;gap:12px;margin-bottom:8px}}
.wrd-monthly .wm-stat-item{{flex:1;text-align:center}}
.wrd-monthly .wm-stat-val{{font-size:22px;font-weight:800;color:var(--navy)}}
.wrd-monthly .wm-stat-lbl{{font-size:9px;color:var(--muted)}}
.wrd-monthly .wm-bar-row{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.wrd-monthly .wm-bar-label{{font-size:11px;color:var(--sub);width:72px;flex-shrink:0;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.wrd-monthly .wm-bar-track{{flex:1;height:8px;background:#eef2f7;border-radius:4px;overflow:hidden}}
.wrd-monthly .wm-bar-fill{{height:100%;background:var(--navy);border-radius:4px;transition:width .4s ease}}
.wrd-monthly .wm-bar-num{{font-size:10px;color:var(--muted);width:28px;flex-shrink:0}}
.wrd-cold-item{{background:var(--white);border-radius:10px;padding:12px;box-shadow:var(--shadow);display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.wrd-cold-item .cold-badge{{font-size:9px;background:#fce4ec;color:#c62828;padding:3px 8px;border-radius:6px;font-weight:600;flex-shrink:0}}
.wrd-cold-item .cold-badge.key{{background:#fff3e0;color:#e65100}}
.wrd-item-thumb{{width:44px;height:44px;object-fit:cover;border-radius:8px;flex-shrink:0;background:#f0f4f8}}
.wrd-item-info{{flex:1;min-width:0}}
.wi-name{{font-size:12px;font-weight:600;color:var(--text);line-height:1.35}}
.wi-meta{{font-size:10px;color:var(--sub);margin-top:3px}}
.wi-usage{{font-size:9px;color:var(--muted);margin-top:2px}}
.wrd-gap-card{{background:var(--white);border-radius:10px;padding:14px;box-shadow:var(--shadow);margin-bottom:8px;border-left:3px solid transparent}}
.wrd-gap-card.priority-high{{border-left-color:#c62828}}
.wrd-gap-card.priority-medium{{border-left-color:#e65100}}
.wrd-gap-card.priority-low{{border-left-color:#2e7d32}}
.wrd-gap-card .gap-item{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:4px}}
.wrd-gap-card .gap-reason{{font-size:11px;color:var(--sub);line-height:1.5}}
.wrd-gap-card .gap-priority{{font-size:9px;font-weight:600;padding:2px 8px;border-radius:4px;display:inline-block;margin-bottom:6px}}
.gap-priority.high{{background:#fce4ec;color:#c62828}}
.gap-priority.medium{{background:#fff3e0;color:#e65100}}
.gap-priority.low{{background:#e8f5e9;color:#2e7d32}}
.wrd-sub{{margin:12px 0 16px}}
.wrd-loading{{text-align:center;padding:40px 20px;color:var(--muted);font-size:13px}}
.wrd-loading::before{{content:'⏳';display:block;font-size:32px;margin-bottom:10px}}
.wrd-empty{{text-align:center;padding:30px 20px;color:var(--muted);font-size:12px}}
.filtered{{display:none!important}}
/* ── Rating buttons ── */
.hero-rate{{text-align:center;margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}}
.rate-label{{font-size:12px;color:var(--sub);margin-bottom:10px}}
.star-row{{display:inline-flex;gap:2px;align-items:center;vertical-align:middle}}
.star-row .sr-btn{{width:24px;height:24px;padding:0;background:transparent;border:none;cursor:pointer;color:var(--border);transition:all .15s;-webkit-tap-highlight-color:transparent}}
.star-row .sr-btn svg{{width:100%;height:100%;display:block}}
.star-row .sr-btn.filled{{color:#e88a3c}}
.star-row .sr-btn:active{{transform:scale(.9)}}
.hero-rate .star-row{{gap:4px}}
.hero-rate .sr-btn{{width:30px;height:30px}}
.rate-tip{{font-size:10px;color:var(--sub);margin-top:4px}}
.cancel-rating{{font-size:10px;color:var(--muted);cursor:pointer;margin-left:6px;text-decoration:underline;-webkit-tap-highlight-color:transparent;display:none}}
.cancel-rating.visible{{display:inline}}
.hist-stars{{display:inline-flex;gap:1px;vertical-align:middle;margin-left:4px}}
.hist-stars .sr-btn{{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;cursor:default;pointer-events:none}}
/* Feedback modal — reason cards (Step 1) */
.reason-cards{{display:flex;flex-direction:column;gap:10px;padding:0 20px 16px}}
.reason-card{{display:flex;align-items:center;gap:14px;padding:16px;border-radius:12px;border:1.5px solid var(--border);cursor:pointer;transition:all .15s;-webkit-tap-highlight-color:transparent;background:var(--white)}}
.reason-card:active{{transform:scale(.98);border-color:var(--navy);background:#f4f7fb}}
.reason-card .rc-icon{{width:36px;height:36px;border-radius:10px;background:#f0f4f8;display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--navy)}}
.reason-card .rc-icon svg{{width:20px;height:20px}}
.reason-card .rc-text{{flex:1;min-width:0}}
.reason-card .rc-title{{font-size:14px;font-weight:600;color:var(--text)}}
.reason-card .rc-desc{{font-size:11px;color:var(--sub);margin-top:2px}}
/* Feedback modal (bottom sheet for 1-star item selection) */
.feedback-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(26,40,56,.6);z-index:185;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);justify-content:center;align-items:flex-end}}
.feedback-overlay.show{{display:flex}}
.feedback-modal{{background:var(--white);border-radius:var(--radius) var(--radius) 0 0;width:100%;max-width:500px;max-height:85vh;display:flex;flex-direction:column;animation:slideUp .3s ease}}
.feedback-header{{display:flex;align-items:center;justify-content:space-between;padding:16px 20px 12px;border-bottom:1px solid var(--border)}}
.feedback-title{{font-size:16px;font-weight:700;color:var(--text)}}
.feedback-close{{width:28px;height:28px;border-radius:50%;background:#f0f4f8;color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;-webkit-tap-highlight-color:transparent}}
.feedback-close svg{{width:16px;height:16px}}
.feedback-body{{padding:0 0 16px;flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch}}
.feedback-hint{{font-size:12px;color:var(--sub);padding:12px 20px 8px;line-height:1.5}}
.feedback-items{{display:flex;flex-direction:column;gap:2px;padding:0 16px}}
.feedback-item{{display:flex;align-items:center;gap:10px;padding:12px 8px;border-radius:10px;cursor:pointer;transition:all .15s;-webkit-tap-highlight-color:transparent;border:1.5px solid transparent}}
.feedback-item:active{{transform:scale(.98)}}
.feedback-item.selected{{background:#fef9f2;border-color:#e88a3c}}
.feedback-item .fi-check{{width:20px;height:20px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}}
.feedback-item.selected .fi-check{{background:#e88a3c;border-color:#e88a3c;color:#fff}}
.feedback-item .fi-check svg{{width:12px;height:12px;display:none}}
.feedback-item.selected .fi-check svg{{display:block}}
.feedback-item .fi-icon{{width:16px;height:16px;color:var(--navy);flex-shrink:0}}
.feedback-item .fi-icon svg{{width:100%;height:100%}}
.feedback-item .fi-id{{font-size:9px;font-family:monospace;color:var(--muted);background:#f0f4f8;padding:2px 5px;border-radius:4px;flex-shrink:0}}
.feedback-item .fi-name{{font-size:12px;color:var(--text);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.feedback-footer{{padding:12px 20px 20px;display:flex;gap:10px}}
.feedback-footer button{{flex:1;padding:12px;border-radius:20px;font-size:14px;font-weight:600;cursor:pointer;border:none;-webkit-tap-highlight-color:transparent;transition:all .2s}}
.feedback-btn-cancel{{background:#f0f4f8;color:var(--sub)}}
.feedback-btn-confirm{{background:var(--navy);color:#fff}}
.feedback-btn-confirm:disabled{{opacity:.5;pointer-events:none}}
/* ═══ 我的形象页 ═══ */
.profile-section{{padding:16px 20px}}
.profile-section-title{{font-size:15px;font-weight:700;color:var(--navy);margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.profile-privacy{{font-size:11px;color:var(--muted);background:#f8fafb;border-radius:10px;padding:10px 14px;margin:12px 20px 0;line-height:1.5;display:flex;align-items:flex-start;gap:6px}}
.profile-privacy svg{{width:14px;height:14px;color:var(--navy);flex-shrink:0;margin-top:1px}}
/* 照片上传区 */
.photo-slots{{display:flex;gap:10px;padding:0 20px;margin-bottom:4px}}
.photo-slot{{flex:1;text-align:center;background:#f8fafb;border-radius:14px;padding:10px 6px 12px;border:2px dashed #dde3ea;transition:border-color .25s;position:relative;min-width:0}}
.photo-slot.has-photo{{border-color:var(--navy);border-style:solid;background:#eef5fb}}
.photo-slot-label{{font-size:11px;font-weight:700;color:var(--navy);margin-bottom:4px}}
.photo-slot-badge{{display:inline-block;font-size:9px;padding:1px 7px;border-radius:8px;margin-bottom:6px;font-weight:600}}
.photo-slot-badge.required{{background:#fce4ec;color:#c0392b}}
.photo-slot-badge.recommended{{background:#e8f5e9;color:#2e7d32}}
.photo-slot-badge.optional{{background:#f0f4f8;color:var(--muted)}}
.photo-slot-preview{{width:100%;height:80px;border-radius:8px;object-fit:cover;margin-bottom:6px;background:#eef2f7;display:none}}
.photo-slot.has-photo .photo-slot-preview{{display:block}}
.photo-slot.has-photo .photo-slot-empty{{display:none}}
.photo-slot-empty{{padding:12px 0;color:var(--muted);font-size:20px}}
.photo-slot-actions{{display:flex;gap:4px;justify-content:center;flex-wrap:wrap}}
.photo-slot-btn{{width:28px;height:28px;border-radius:50%;border:1.5px solid #c5cdd5;background:#fff;color:var(--sub);font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center;-webkit-tap-highlight-color:transparent;transition:all .2s;padding:0}}
.photo-slot-btn:active{{background:var(--navy);color:#fff;border-color:var(--navy)}}
.photo-hint{{font-size:10px;color:var(--muted);text-align:center;padding:4px 20px 0;line-height:1.4}}
/* 开关 */
.toggle-row{{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;margin:12px 20px;background:#f8fafb;border-radius:12px;gap:12px}}
.toggle-label{{font-size:14px;font-weight:600;color:var(--text);flex:1}}
.toggle-switch{{width:48px;height:28px;background:#c5cdd5;border-radius:14px;cursor:pointer;position:relative;transition:background .3s;flex-shrink:0;-webkit-tap-highlight-color:transparent}}
.toggle-switch.on{{background:var(--navy)}}
.toggle-switch::after{{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;background:#fff;border-radius:50%;transition:transform .3s;box-shadow:0 1px 3px rgba(0,0,0,.15)}}
.toggle-switch.on::after{{transform:translateX(20px)}}
/* 分析按钮 */
.analyze-row{{padding:0 20px;margin-bottom:14px}}
.analyze-btn{{width:100%;padding:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:12px;font-size:14px;font-weight:600;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:6px}}
.analyze-btn:active{{opacity:.85;transform:scale(.98)}}
.analyze-btn:disabled{{opacity:.5;pointer-events:none}}
/* 表单 */
.profile-form{{padding:0 20px}}
.profile-form-group{{margin-bottom:12px}}
.profile-form-label{{font-size:12px;font-weight:600;color:var(--sub);margin-bottom:5px;display:block}}
.profile-form-label .optional-tag{{font-size:10px;color:var(--muted);font-weight:400;margin-left:4px}}
.profile-form-input{{width:100%;padding:10px 14px;border:1.5px solid #e2e7ec;border-radius:10px;font-size:14px;color:var(--text);background:#fff;outline:none;-webkit-appearance:none;box-sizing:border-box;transition:border-color .2s}}
.profile-form-input:focus{{border-color:var(--navy)}}
.profile-form-input::placeholder{{color:#bcc4cd}}
/* 分段选择 */
.seg-choice-row{{display:flex;gap:6px;flex-wrap:wrap}}
.seg-choice{{padding:8px 14px;border-radius:20px;font-size:12px;font-weight:500;cursor:pointer;border:1.5px solid #e2e7ec;background:#fff;color:var(--sub);transition:all .2s;-webkit-tap-highlight-color:transparent;white-space:nowrap}}
.seg-choice.selected{{background:var(--navy);color:#fff;border-color:var(--navy)}}
/* 引导语 */
.profile-guide{{font-size:12px;color:var(--muted);text-align:center;padding:8px 20px;line-height:1.6;font-style:italic}}
.profile-guide svg{{width:14px;height:14px;vertical-align:-2px;color:#e67e22}}
/* 预览 */
.profile-preview{{margin:8px 20px;padding:12px 16px;background:#fef9e7;border-radius:10px;font-size:12px;color:#8d6e00;line-height:1.6}}
.profile-preview-title{{font-weight:600;margin-bottom:4px;font-size:11px;color:#b8860b}}
/* 保存按钮 */
.profile-save-row{{padding:12px 20px 20px;display:flex;gap:10px;align-items:center}}
.profile-save-btn{{flex:1;padding:14px;background:var(--navy);color:#fff;border:none;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:all .2s}}
.profile-save-btn:active{{opacity:.85;transform:scale(.98)}}
.profile-save-btn:disabled{{opacity:.5;pointer-events:none}}
.profile-save-btn.saved{{background:#27ae60}}
.profile-reset-link{{font-size:11px;color:var(--muted);cursor:pointer;text-align:center;display:block;padding-bottom:24px;-webkit-tap-highlight-color:transparent}}
.daily-warning{{background:linear-gradient(135deg,#fff8e1,#fff3cd);border:1px solid #ffcc02;border-radius:16px;padding:28px 20px;text-align:center;margin:0 0 12px 0;animation:fadeInUp .4s ease}}
.daily-warning-icon{{font-size:42px;margin-bottom:8px}}
.daily-warning-title{{font-size:16px;font-weight:700;color:#5c3d1a;margin-bottom:4px}}
.daily-warning-msg{{font-size:13px;color:#8b6d3a;margin-bottom:16px}}
.daily-warning-btn{{display:inline-block;background:var(--navy);color:#fff;border:none;border-radius:24px;padding:10px 28px;font-size:15px;font-weight:600;cursor:pointer;-webkit-tap-highlight-color:transparent;box-shadow:0 4px 12px rgba(30,58,95,.25);transition:transform .15s,opacity .15s}}
.daily-warning-btn:active{{transform:scale(.96);opacity:.85}}
.daily-warning-btn:disabled{{opacity:.5;pointer-events:none}}
.daily-loading{{display:flex;align-items:center;justify-content:center;gap:8px;padding:20px;color:var(--navy);font-size:14px;font-weight:500}}
.daily-loading-dot{{width:8px;height:8px;background:var(--navy);border-radius:50%;animation:dailyBounce 1.2s infinite ease-in-out}}
.daily-loading-dot:nth-child(2){{animation-delay:.15s}}
.daily-loading-dot:nth-child(3){{animation-delay:.3s}}
.funnel-warning{{background:#fff0f0;border:1px solid #e8c8c8;border-radius:10px;padding:8px 14px;margin:0 0 8px 0;font-size:12px;color:#a05050;display:flex;align-items:center;gap:6px;animation:fadeInUp .4s ease}}
.funnel-warning-icon{{font-size:16px}}
@keyframes dailyBounce{{0%,80%,100%{{transform:scale(.6);opacity:.4}}40%{{transform:scale(1);opacity:1}}}}
@keyframes fadeInUp{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}
.report-item-card{{display:flex;align-items:center;gap:12px;background:var(--white);border-radius:10px;padding:12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}}
.report-item-thumb{{width:56px;height:56px;border-radius:8px;object-fit:contain;background:#f5f0eb;flex-shrink:0}}
.report-item-info{{flex:1;min-width:0}}
.report-item-name{{font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px}}
.report-item-desc{{font-size:11px;color:var(--muted)}}
.report-item-count{{font-size:11px;color:var(--navy);font-weight:600;margin-top:2px}}
.report-style-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}}
.report-style-card{{background:var(--white);border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05)}}
.report-style-img{{width:100%;aspect-ratio:4/3;object-fit:cover;background:#eef2f7}}
.report-style-placeholder{{width:100%;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;background:var(--navy);color:#fff;font-size:13px;font-weight:600;text-align:center;padding:8px}}
.report-style-info{{padding:8px 10px}}
.report-style-name{{font-size:12px;font-weight:600;color:var(--text)}}
.report-style-meta{{font-size:10px;color:var(--muted)}}
.report-toggle-btn{{display:block;width:100%;padding:14px;margin-top:12px;background:var(--white);border:1.5px dashed var(--navy);border-radius:12px;color:var(--navy);font-size:14px;font-weight:600;text-align:center;cursor:pointer}}
.report-toggle-btn:active{{background:#f0edf5}}
.report-section-title{{font-size:13px;font-weight:700;color:var(--text);margin:16px 0 8px}}
.report-section-title:first-child{{margin-top:0}}
.report-empty{{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}}
</style></head><body><div id="app">

<!-- ═══ 推荐页 ═══ -->
<div class="page active" id="page-recommend">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented" id="seg-recommend">
<div class="seg-btn active" data-sub="today">今日推荐</div>
<div class="seg-btn" data-sub="history">历史推荐</div>
</div>

<!-- 今日推荐 -->
<div class="subpage active" id="sub-today" style="display:flex;flex-direction:column;flex:1;overflow:hidden">
<div class="scroll-area">
<div class="funnel-warning" id="funnel-warning" style="display:none">
<span class="funnel-warning-icon">🔗</span><span>外网隧道未连接，手机端可能无法访问</span>
</div>
<div class="daily-warning" id="daily-warning" style="display:none">
<div class="daily-warning-icon">⏳</div>
<div class="daily-warning-title" id="daily-warning-title">今日穿搭未生成</div>
<div class="daily-warning-msg" id="daily-warning-msg">凌晨自动生成未能完成，点击下方按钮立即生成</div>
<button class="daily-warning-btn" id="daily-warning-btn" onclick="generateDaily()">⚡ 立即生成</button>
</div>
<div class="daily-loading" id="daily-loading" style="display:none">
<div class="daily-loading-dot"></div><div class="daily-loading-dot"></div><div class="daily-loading-dot"></div>
<span id="daily-loading-text">正在生成今日穿搭...</span>
</div>
<div class="hero-card">
<div class="hero-img"><img src="{hero_img}" alt="" onerror="this.onerror=null;this.src=__CDN__+'wardrobe/enhanced/_placeholder.png'"></div>
<div class="hero-body">
<div class="style-tags">{hero_tags_html}</div>
<div class="hero-style">{hero_style}</div>
<div class="hero-meta">{hero_meta}</div>
<div class="item-list">{hero_items_html}</div>
{palette_html}
{rationale_html}
<div class="hero-rate" data-oid="{hero_outfit_id}">
<div class="rate-label">给这套穿搭评分</div>
<div class="star-row" id="hero-star-row">{hero_star_html}</div>
<div class="rate-tip">多多评价，让 AI 更懂你的风格 ✨</div>
<span class="cancel-rating{cancel_visible}" id="hero-cancel" onclick="cancelRating('{hero_outfit_id}')">取消评分</span>
</div>
</div></div>

<div class="section-header">其他推荐</div>
<div class="rec-cards" id="alt-cards">
{card1}
{card2}
{card3}
</div>
<div style="text-align:center;padding:4px 0 12px"><span style="font-size:12px;color:var(--navy);cursor:pointer;font-weight:600" onclick="refreshAlts()">⟳ 换一批</span></div>
</div>
<div class="page-bottom"><input type="text" id="today-input" placeholder="描述穿搭需求，如「今天要去约会」..." onkeydown="if(event.key==='Enter')sendOutfit()"><button style="width:44px;height:44px;background:var(--navy);color:#fff;border:none;border-radius:50%;font-size:16px;cursor:pointer;flex-shrink:0;margin-left:8px" onclick="sendOutfit()">▶</button></div>
</div>

<!-- 历史推荐 -->
<div class="subpage" id="sub-history" style="display:none;flex-direction:column;flex:1;overflow:hidden">
<div class="scroll-area" id="history-scroll">
<div class="section-header" style="margin-top:4px">今日穿搭</div>
<div class="fav-list" id="today-list" style="margin-bottom:16px">{today_cards}</div>
<div class="section-header">历史最爱</div>
<div class="fav-list" id="fav-list" style="margin-bottom:16px">{fav_cards}</div>
</div>
<div class="page-bottom"><input type="text" id="history-search" placeholder="搜索历史推荐..." oninput="filterHistory()"></div>
</div>
</div>

<!-- ═══ 探索页 ═══ -->
<div class="page" id="page-explore">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented" id="exp-seg"><div class="seg-btn active" data-sub="tweak">日常穿搭</div><div class="seg-btn" data-sub="transform">改变自己</div><div class="seg-btn" data-sub="cross">大胆跨界</div><div class="seg-btn" data-sub="trends">时尚圈子</div></div>
<div class="scroll-area">
<div class="exp-sub" id="sub-tweak" style="display:block">
<div id="exp-tweak-content"><div class="wrd-loading">加载中...</div></div>
</div>
<div class="exp-sub" id="sub-transform" style="display:none">
<div id="exp-transform-content"><div class="wrd-loading">加载中...</div></div>
</div>
<div class="exp-sub" id="sub-cross" style="display:none">
<div id="exp-cross-content"><div class="wrd-loading">加载中...</div></div>
</div>
<div class="exp-sub" id="sub-trends" style="display:none">
<div id="exp-trends-content"><div class="wrd-loading">加载中...</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" id="exp-input" placeholder="描述你想尝试的风格..." onkeydown="if(event.key==='Enter')tryExplore()"></div>
</div>

<!-- ═══ 衣橱页 ═══ -->
<div class="page" id="page-wardrobe">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented" id="wrd-seg"><div class="seg-btn active" data-sub="my">我的衣橱</div><div class="seg-btn" data-sub="monthly">穿搭报告</div><div class="seg-btn" data-sub="cold">冷门单品</div><div class="seg-btn" data-sub="gaps">购买建议</div></div>
<div class="scroll-area">
<!-- 统计卡片（JS动态填充） -->
<div class="wrd-stats" id="wrd-stats">
<div class="wrd-stat-card"><div class="wrd-stat-num skeleton-text" id="wrd-total">—</div><div class="wrd-stat-label">总件数</div></div>
<div class="wrd-stat-card"><div class="wrd-stat-num skeleton-text" id="wrd-util">—</div><div class="wrd-stat-label">利用率</div></div>
<div class="wrd-stat-card"><div class="wrd-stat-num skeleton-text" id="wrd-over">—</div><div class="wrd-stat-label">超标品类</div></div>
</div>

<!-- 子页：我的衣橱 -->
<div class="wrd-sub" id="sub-my" style="display:block">
<div id="wrd-rows"><div class="wrd-loading">加载中...</div></div>
</div>

<!-- 子页：月度报告 -->
<div class="wrd-sub" id="sub-monthly" style="display:none">
<div id="wrd-report-content"><div class="wrd-loading">加载中...</div></div>
</div>

<!-- 子页：冷门单品 -->
<div class="wrd-sub" id="sub-cold" style="display:none">
<div id="wrd-cold-list"><div class="wrd-loading">加载中...</div></div>
</div>

<!-- 子页：购买建议 -->
<div class="wrd-sub" id="sub-gaps" style="display:none">
<div id="wrd-gaps-content"><div class="wrd-loading">加载中...</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" id="wrd-search" placeholder="搜索衣服..." oninput="filterWardrobe()"></div>
</div>

<!-- ═══ 添加页 ═══ -->
<div class="page" id="page-add">
<div class="header"><h1>添加单品</h1><div class="avatar">K</div></div>
<div class="scroll-area">
<div class="add-action-cards" id="add-action-cards">
<div class="add-action-card" onclick="triggerAddCamera()">
<div class="add-action-icon">{camera_lg_icon}</div>
<div class="add-action-label">拍照</div>
<div class="add-action-hint">打开相机拍摄</div>
</div>
<div class="add-action-card" onclick="triggerAddAlbum()">
<div class="add-action-icon">{image_icon}</div>
<div class="add-action-label">上传</div>
<div class="add-action-hint">从相册选择多张</div>
</div>
</div>
<input type="file" id="add-camera-input" accept="image/*" capture="environment" style="display:none" onchange="handleAddImages(this)">
<input type="file" id="add-album-input" accept="image/*" multiple style="display:none" onchange="handleAddImages(this)">

<!-- 图片缩略条 -->
<div class="add-image-strip" id="add-image-strip" style="display:none"></div>

<!-- 进度 -->
<div id="add-progress" style="display:none">
<div id="add-progress-text" style="text-align:center;padding:40px 20px;color:var(--muted);font-size:13px">识别中...</div>
</div>

<!-- 审核结果 -->
<div id="add-result" style="display:none"></div>
</div>
<div class="page-bottom" style="display:flex;gap:10px" id="add-buttons">
<button style="flex:1;padding:14px;background:var(--navy);color:#fff;border:none;border-radius:24px;font-size:15px;font-weight:600" id="add-confirm-btn" onclick="submitAddImages()" disabled>确认分析</button>
<button style="flex:1;padding:14px;background:#eef2f7;color:var(--sub);border:none;border-radius:24px;font-size:15px" onclick="clearAddImages()">清空</button>
</div>
</div>

<!-- ═══ 我的页 ═══ -->
<div class="page" id="page-profile">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="scroll-area">
<div class="profile-privacy"><span>{lock_icon}</span><span>照片仅存本地，生图时通过 API 传给 Seedream，不会公开</span></div>

<div class="toggle-row">
<span class="toggle-label">🪄 使用我的形象生成效果图</span>
<div class="toggle-switch on" id="toggle-use-image" onclick="toggleUseImage()"></div>
</div>

<div id="profile-detail" style="display:block">
<div class="profile-section">
<div class="profile-section-title">📷 我的照片</div>
<div class="photo-slots">
<div class="photo-slot" id="slot-full">
<div class="photo-slot-label">⭐ 正面全身</div>
<div class="photo-slot-badge required">必须</div>
<img class="photo-slot-preview" id="preview-full" src="">
<div class="photo-slot-empty">📷</div>
<div class="photo-slot-actions">
<button class="photo-slot-btn" onclick="capturePhoto('full_body_front')" title="拍照">📷</button>
<button class="photo-slot-btn" onclick="pickPhoto('full_body_front')" title="上传">⬆</button>
</div>
</div>
<div class="photo-slot" id="slot-face">
<div class="photo-slot-label">半身面部</div>
<div class="photo-slot-badge recommended">推荐</div>
<img class="photo-slot-preview" id="preview-face" src="">
<div class="photo-slot-empty">📷</div>
<div class="photo-slot-actions">
<button class="photo-slot-btn" onclick="capturePhoto('face_closeup')" title="拍照">📷</button>
<button class="photo-slot-btn" onclick="pickPhoto('face_closeup')" title="上传">⬆</button>
</div>
</div>
<div class="photo-slot" id="slot-side">
<div class="photo-slot-label">侧面全身</div>
<div class="photo-slot-badge optional">可选</div>
<img class="photo-slot-preview" id="preview-side" src="">
<div class="photo-slot-empty">📷</div>
<div class="photo-slot-actions">
<button class="photo-slot-btn" onclick="capturePhoto('full_body_side')" title="拍照">📷</button>
<button class="photo-slot-btn" onclick="pickPhoto('full_body_side')" title="上传">⬆</button>
</div>
</div>
</div>
<div class="photo-hint">💡 不上传照片将使用亚洲标准脸型与身形作为生图参考</div>
<input type="file" id="profile-camera-input" accept="image/*" capture="environment" style="display:none" onchange="handleProfilePhoto(this,'camera')">
<input type="file" id="profile-album-input" accept="image/*" style="display:none" onchange="handleProfilePhoto(this,'album')">
</div>

<div class="analyze-row"><button class="analyze-btn" id="analyze-btn" onclick="analyzeProfilePhotos()">🔍 AI 分析照片中的身形</button></div>
</div><!-- #profile-detail -->

<div class="profile-section">
<div class="profile-section-title">📏 基本信息</div>

<div class="profile-form">

<div class="profile-form-group">
<label class="profile-form-label">性别</label>
<div class="seg-choice-row" id="seg-gender">
<div class="seg-choice selected" data-val="男" onclick="selectSeg(this,'seg-gender','__genderVal')">男</div>
<div class="seg-choice" data-val="女" onclick="selectSeg(this,'seg-gender','__genderVal')">女</div>
</div>
</div>

<div class="profile-form-group">
<label class="profile-form-label">身高 · cm（自由填写）</label>
<input class="profile-form-input" id="pf-height" type="text" placeholder="如 179" inputmode="numeric">
</div>

<div class="profile-form-group">
<label class="profile-form-label">体重 · kg（自由填写）</label>
<input class="profile-form-input" id="pf-weight" type="text" placeholder="如 68" inputmode="numeric">
</div>

<div class="profile-form-group">
<label class="profile-form-label">年龄（自由填写）</label>
<input class="profile-form-input" id="pf-age" type="text" placeholder="如 30" inputmode="numeric">
</div>

<div class="profile-form-group">
<label class="profile-form-label">体型</label>
<div class="seg-choice-row" id="seg-body-male">
<div class="seg-choice" data-val="偏瘦" onclick="selectSeg(this,'seg-body','__bodyVal')">偏瘦</div>
<div class="seg-choice" data-val="标准" onclick="selectSeg(this,'seg-body','__bodyVal')">标准</div>
<div class="seg-choice" data-val="偏胖" onclick="selectSeg(this,'seg-body','__bodyVal')">偏胖</div>
<div class="seg-choice" data-val="肌肉型" onclick="selectSeg(this,'seg-body','__bodyVal')">肌肉型</div>
</div>
<div class="seg-choice-row" id="seg-body-female" style="display:none">
<div class="seg-choice" data-val="沙漏型" onclick="selectSeg(this,'seg-body','__bodyVal')">⌛ 沙漏型</div>
<div class="seg-choice" data-val="梨型" onclick="selectSeg(this,'seg-body','__bodyVal')">🍐 梨型</div>
<div class="seg-choice" data-val="苹果型" onclick="selectSeg(this,'seg-body','__bodyVal')">🍎 苹果型</div>
<div class="seg-choice" data-val="矩形" onclick="selectSeg(this,'seg-body','__bodyVal')">📏 矩形</div>
<div class="seg-choice" data-val="倒三角" onclick="selectSeg(this,'seg-body','__bodyVal')">🔻 倒三角</div>
<div class="seg-choice" data-val="小个子" onclick="selectSeg(this,'seg-body','__bodyVal')">🌸 小个子</div>
</div>
</div>

<div class="profile-form-group">
<label class="profile-form-label">肤色</label>
<div class="seg-choice-row" id="seg-skin">
<div class="seg-choice" data-val="白皙" onclick="selectSeg(this,'seg-skin','__skinVal')">白皙</div>
<div class="seg-choice" data-val="偏白" onclick="selectSeg(this,'seg-skin','__skinVal')">偏白</div>
<div class="seg-choice" data-val="自然" onclick="selectSeg(this,'seg-skin','__skinVal')">自然</div>
<div class="seg-choice" data-val="小麦" onclick="selectSeg(this,'seg-skin','__skinVal')">小麦</div>
<div class="seg-choice" data-val="偏黄" onclick="selectSeg(this,'seg-skin','__skinVal')">偏黄</div>
<div class="seg-choice" data-val="偏黑" onclick="selectSeg(this,'seg-skin','__skinVal')">偏黑</div>
</div>
</div>

<div class="profile-form-group">
<label class="profile-form-label">肩型</label>
<div class="seg-choice-row" id="seg-shoulder">
<div class="seg-choice" data-val="窄肩" onclick="selectSeg(this,'seg-shoulder','__shoulderVal')">窄肩</div>
<div class="seg-choice" data-val="标准" onclick="selectSeg(this,'seg-shoulder','__shoulderVal')">标准</div>
<div class="seg-choice" data-val="宽肩" onclick="selectSeg(this,'seg-shoulder','__shoulderVal')">宽肩</div>
<div class="seg-choice" data-val="溜肩" onclick="selectSeg(this,'seg-shoulder','__shoulderVal')">溜肩</div>
</div>
</div>

<div class="profile-form-group">
<label class="profile-form-label">脸型</label>
<div class="seg-choice-row" id="seg-face">
<div class="seg-choice" data-val="圆脸" onclick="selectSeg(this,'seg-face','__faceVal')">圆脸</div>
<div class="seg-choice" data-val="方脸" onclick="selectSeg(this,'seg-face','__faceVal')">方脸</div>
<div class="seg-choice" data-val="长脸" onclick="selectSeg(this,'seg-face','__faceVal')">长脸</div>
<div class="seg-choice" data-val="瓜子脸" onclick="selectSeg(this,'seg-face','__faceVal')">瓜子脸</div>
<div class="seg-choice" data-val="椭圆脸" onclick="selectSeg(this,'seg-face','__faceVal')">椭圆脸</div>
</div>
</div>

<div class="profile-form-group">
<label class="profile-form-label">职业 <span class="optional-tag">选填 ✨</span></label>
<input class="profile-form-input" id="pf-occupation" type="text" placeholder="如 自媒体">
</div>

<div class="profile-form-group">
<label class="profile-form-label">风格偏好 <span class="optional-tag">选填 ✨</span></label>
<input class="profile-form-input" id="pf-style-pref" type="text" placeholder="如 日系/Clean Fit">
</div>

<div class="profile-form-group">
<label class="profile-form-label">穿搭困扰 <span class="optional-tag">选填 ✨</span></label>
<input class="profile-form-input" id="pf-pain-points" type="text" placeholder="如 不够时尚，不知如何搭配">
</div>

<div class="profile-guide" id="profile-guide" style="display:none"></div>

<div class="profile-form-group">
<label class="profile-form-label">🔒 身材秘密 <span class="optional-tag">选填</span></label>
<textarea class="profile-form-input" id="pf-body-secrets" rows="3" placeholder="如 小肚子、大腿粗、肩膀窄、平胸…&#10;勇敢说出你的身材劣势，AI 才能更好地帮你扬长避短 ✨" style="resize:vertical;min-height:72px;line-height:1.6"></textarea>
<div style="font-size:10px;color:var(--muted);margin-top:4px;line-height:1.5">💬 这不是缺点，是你的独特身材特征。告诉 AI 才知道该用上宽下窄遮肚子、还是用落肩剪裁修饰窄肩</div>
</div>

</div><!-- .profile-form -->
</div>

<div class="profile-preview" id="profile-preview" style="display:none">
<div class="profile-preview-title">💬 AI 将这样描述你：</div>
<div id="profile-preview-text"></div>
</div>

<a class="profile-reset-link" onclick="resetProfile()">· 恢复默认 ·</a>

<div class="profile-save-row">
<button class="profile-save-btn" id="profile-save-btn" onclick="saveProfile()">保存形象信息</button>
</div>

</div><!-- .scroll-area -->
</div>

</div>

<!-- Tab Bar -->
<div class="lightbox" id="lightbox" onclick="this.classList.remove('show')"><span class="close">&times;</span><img id="lightbox-img" src=""></div>

<!-- Feedback Modal (1-star: Step1 reason → Step2 items) -->
<div class="feedback-overlay" id="feedback-overlay" onclick="if(event.target===this)closeFeedbackModal()">
<div class="feedback-modal">
<div class="feedback-header">
<span class="feedback-title" id="feedback-title">为什么不满意？</span>
<span class="feedback-close" onclick="closeFeedbackModal()">__X_SVG__</span>
</div>
<!-- Step 1: 选择原因 -->
<div class="feedback-body" id="feedback-step1">
<div class="feedback-hint">告诉我们哪里不满意，AI 会针对性优化</div>
<div class="reason-cards">
<div class="reason-card" onclick="selectReason('style_mismatch')">
<div class="rc-icon">__STYLE_ICON__</div>
<div class="rc-text">
<div class="rc-title">风格不喜欢</div>
<div class="rc-desc">减少此类风格的推荐频率</div>
</div>
</div>
<div class="reason-card" onclick="selectReason('scene_mismatch')">
<div class="rc-icon">__SCENE_ICON__</div>
<div class="rc-text">
<div class="rc-title">场景不适合</div>
<div class="rc-desc">在此场景下不再推荐类似穿搭</div>
</div>
</div>
<div class="reason-card" onclick="showItemStep()">
<div class="rc-icon">__COMBO_ICON__</div>
<div class="rc-text">
<div class="rc-title">搭配有问题</div>
<div class="rc-desc">选择不满意的单品，减少一起出现的概率</div>
</div>
</div>
</div>
</div>
<!-- Step 2: 选择单品（仅搭配有问题） -->
<div class="feedback-body" id="feedback-step2" style="display:none">
<div class="feedback-hint">选择你觉得不满意的单品（可多选），系统将减少它们一起出现的概率</div>
<div class="feedback-items" id="feedback-items"></div>
<div class="feedback-footer">
<button class="feedback-btn-cancel" onclick="closeFeedbackModal()">取消</button>
<button class="feedback-btn-confirm" id="feedback-confirm-btn" onclick="confirmFeedback()" disabled>确认</button>
</div>
</div>
</div></div>

<!-- Progress Overlay -->
<div class="progress-overlay" id="progress-overlay">
<div class="progress-card">
<div class="progress-spinner" id="progress-spinner"></div>
<div class="progress-title" id="progress-title">正在生成穿搭...</div>
<div class="progress-steps" id="progress-steps"></div>
<button class="progress-close" id="progress-close" style="display:none" onclick="dismissProgress()">好的</button>
</div>
</div>

<!-- Item Detail Modal -->
<div class="item-modal-overlay" id="item-modal" onclick="if(event.target===this)closeItemModal()">
<div class="item-modal">
<div class="item-modal-close" onclick="closeItemModal()">&times;</div>
<div class="item-modal-scroll" id="item-modal-scroll">
<div class="wrd-loading">加载中...</div>
</div>
</div>
</div>

<div class="tab-bar" id="tab-bar">
{tabs}
</div>

<script>
var __sf__='__SF_T__';var __so__='__SO_T__';
function showImg(src){{if(src.indexOf('/api/image')!==-1&&src.indexOf('&w=')===-1)src+='&w=600';document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').classList.add('show')}}
function showItemImg(el){{var t=el.dataset.thumb;if(t)showImg(t)}}
/* ═══ 图片懒加载 — Intersection Observer ═══ */
var _imgObserver=new IntersectionObserver(function(entries){{entries.forEach(function(e){{if(e.isIntersecting){{var imgs=e.target.querySelectorAll('img[data-src]');if(!imgs.length&&e.target.tagName==='IMG'&&e.target.dataset.src)imgs=[e.target];imgs.forEach(function(img){{if(img.dataset.src){{img.src=img.dataset.src;img.removeAttribute('data-src');img.classList.add('loaded')}}}});e.target.classList.remove('lazy-img');_imgObserver.unobserve(e.target)}}}})}},{{rootMargin:'200px'}});
function observeLazyImages(container){{if(!container)container=document;(container.querySelectorAll||function(s){{return[]}}).call(container,'.lazy-img').forEach(function(el){{_imgObserver.observe(el)}})}}
/* ═══ 导航状态 ═══ */
var currentPage='recommend';
document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{var p=this.dataset.page;if(p===currentPage)return;currentPage=p;document.querySelectorAll('#tab-bar .tab').forEach(function(t){{t.classList.remove('active')}});this.classList.add('active');document.querySelectorAll('.page').forEach(function(pg){{pg.classList.remove('active')}});document.getElementById('page-'+p).classList.add('active')}})}});
document.querySelectorAll('.segmented').forEach(function(seg){{seg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;seg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;if(!sub)return;var parent=seg.parentElement;parent.querySelectorAll('.subpage').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='flex'}})}});
function filterHistory(){{var q=document.getElementById('history-search').value.toLowerCase();document.querySelectorAll('#today-list .fav-card, #fav-list .fav-card').forEach(function(c){{var t=c.textContent.toLowerCase();c.classList.toggle('filtered',q&&!t.includes(q))}})}}
function filterTodayCards(){{var t=new Date();var ds=t.getFullYear()+'-'+('0'+(t.getMonth()+1)).slice(-2)+'-'+('0'+t.getDate()).slice(-2);var list=document.getElementById('today-list');if(!list)return;var cards=list.querySelectorAll('.fav-card');var n=0;for(var i=0;i<cards.length;i++){{var d=cards[i].getAttribute('data-date');if(d!==ds){{cards[i].style.display='none'}}else{{cards[i].style.display='';n++}}}}if(!n&&cards.length){{var p=document.createElement('div');p.className='today-empty';p.style.cssText='padding:16px;color:var(--muted);font-size:13px';p.textContent='今日暂无推荐';list.appendChild(p)}}}}
function checkDailyStatus(){{var now=new Date();var hour=now.getHours();fetch('/health').then(function(r){{return r.json()}}).then(function(d){{var warn=document.getElementById('daily-warning');var load=document.getElementById('daily-loading');var hero=document.querySelector('.hero-card');var fw=document.getElementById('funnel-warning');if(fw){{fw.style.display=d.funnel_active?'none':'flex'}}if(!warn)return;if(d.today_ok){{warn.style.display='none';load.style.display='none';if(hero)hero.style.opacity='1';return}}if(d.running){{warn.style.display='none';load.style.display='block';if(hero)hero.style.opacity='0.4';document.getElementById('daily-loading-text').textContent='正在生成今日穿搭...';setTimeout(checkDailyStatus,5000);return}}if(hour>=10){{warn.style.display='none';load.style.display='none';if(hero)hero.style.opacity='1';return}}warn.style.display='block';load.style.display='none';if(hero)hero.style.opacity='0.4'}}).catch(function(e){{console.log('Health check failed:',e)}})}}
function generateDaily(){{var warn=document.getElementById('daily-warning');var load=document.getElementById('daily-loading');var btn=document.getElementById('daily-warning-btn');warn.style.display='none';load.style.display='block';if(btn)btn.disabled=true;document.getElementById('daily-loading-text').textContent='正在生成今日穿搭...';fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:'今天穿什么'}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.task_id){{__dailyPollId=d.task_id;pollDailyTask(d.task_id)}}else{{load.style.display='none';setTimeout(function(){{location.reload()}},1500)}}}}).catch(function(e){{warn.style.display='block';load.style.display='none';if(btn)btn.disabled=false;document.getElementById('daily-warning-msg').textContent='生成失败: '+e.message}})}}
function pollDailyTask(tid){{fetch('/api/task/'+tid).then(function(r){{return r.json()}}).then(function(d){{if(tid!==__dailyPollId)return;if(d.status==='done'){{document.getElementById('daily-loading-text').textContent='✅ 完成，刷新页面...';setTimeout(function(){{location.reload()}},1000)}}else if(d.status==='error'){{var warn=document.getElementById('daily-warning');var load=document.getElementById('daily-loading');var btn=document.getElementById('daily-warning-btn');warn.style.display='block';load.style.display='none';if(btn)btn.disabled=false;document.getElementById('daily-warning-msg').textContent='生成失败，请重试'}}else{{document.getElementById('daily-loading-text').textContent=d.message||'生成中...';setTimeout(function(){{pollDailyTask(tid)}},3000)}}}}).catch(function(){{setTimeout(function(){{pollDailyTask(tid)}},3000)}})}}
document.addEventListener('DOMContentLoaded',function(){{filterTodayCards();checkDailyStatus()}});
function escHtml(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}}
function showProgress(){{var o=document.getElementById('progress-overlay');o.classList.add('show');document.getElementById('progress-title').textContent='正在分析...';document.getElementById('progress-steps').innerHTML='';document.getElementById('progress-spinner').style.display='block';document.getElementById('progress-close').style.display='none'}}
function dismissProgress(){{location.href=location.href.split('#')[0]+'?t='+Date.now()}}
function closeProgress(){{var o=document.getElementById('progress-overlay');o.classList.remove('show');document.getElementById('progress-spinner').style.display='block';document.getElementById('progress-close').style.display='none'}}
function sendOutfit(){{var inp=document.getElementById('today-input');var msg=inp.value.trim()||'推荐穿搭';inp.value='';inp.placeholder='描述穿搭需求...';showProgress();fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg}})}}).then(r=>r.json()).then(d=>{{if(d.result){{document.getElementById('progress-title').textContent=d.result;document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block';if(d.image_url){{document.getElementById('progress-steps').innerHTML='<img class=\"progress-result-img\" src=\"'+d.image_url+'\" loading=\"lazy\">'}}}}else if(d.task_id){{__activePollId=d.task_id;pollTask(d.task_id)}}else{{document.getElementById('progress-title').textContent='已发送';setTimeout(dismissProgress,2000)}}}}).catch(function(e){{document.getElementById('progress-title').textContent='网络错误: '+e.message;document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block'}})}}
function pollTask(tid){{fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){{if(tid!==__activePollId)return;var title=document.getElementById('progress-title');var steps=document.getElementById('progress-steps');var spinner=document.getElementById('progress-spinner');var closeBtn=document.getElementById('progress-close');if(d.status==='done'){{spinner.style.display='none';closeBtn.style.display='inline-block';title.textContent='✅ 穿搭完成';var log=d.log||'';var lines=log.split('\\n').filter(function(l){{return l.trim()}});steps.innerHTML=lines.map(function(l){{if(l.indexOf('📊')===0)return'<div class=\"step-estimate\">'+escHtml(l)+'</div>';return'<div class=\"step-done\"><span class=\"progress-dot done\"></span>'+escHtml(l)+'</div>'}}).join('');if(d.image_url){{steps.innerHTML+='<img class=\"progress-result-img\" src=\"'+escHtml(d.image_url)+'\" loading=\"lazy\">'}}}}else if(d.status==='error'){{spinner.style.display='none';closeBtn.style.display='inline-block';title.textContent='❌ 生成失败';steps.innerHTML='<div style=\"color:#c4523c\">'+escHtml(d.message||'未知错误')+'</div>'}}else{{title.textContent=d.message||'生成中...';var log=d.log||'';if(log){{var lines=log.split('\\n').filter(function(l){{return l.trim()}});steps.innerHTML=lines.map(function(l,i){{if(l.indexOf('📊')===0)return'<div class=\"step-estimate\">'+escHtml(l)+'</div>';var isLast=i===lines.length-1;var cls=isLast?'step-active':'step-done';var dot=isLast?'active':'done';return'<div class=\"'+cls+'\"><span class=\"progress-dot '+dot+'\"></span>'+escHtml(l)+'</div>'}}).join('')}}setTimeout(function(){{pollTask(tid)}},2000)}}}}).catch(function(){{setTimeout(function(){{pollTask(tid)}},2000)}})}}
function refreshAlts(){{var alts=__ALT_DATA__;var pool=alts.sort(function(){{return Math.random()-0.5}}).slice(0,3);var h='';pool.forEach(function(a){{var items=a[1].map(function(i){{return'<div>'+i+'</div>'}}).join('');h+='<div class=\"rec-card\" onclick=\"this.classList.toggle(\\'open\\')\"><div class=\"rc-style-name\">'+a[0]+'</div><div class=\"rc-items\">'+items+'</div><div class=\"rc-arrow\">▾</div></div>'}});var el=document.getElementById('alt-cards');if(el)el.innerHTML=h}}
/* ═══ 衣橱页 ═══ */
var __wrdData=null,__wrdStats=null,__newItemIds=[],__wardrobeNeedsReload=false;
/* ── 智能缓存层 ── */
var __apiCache={{}};
var __CACHE_TTL=300000; // 5分钟缓存
function cachedFetch(key,url,renderFn,alwaysFetch){{alwaysFetch=alwaysFetch||false;var now=Date.now();var entry=__apiCache[key];if(entry&&(now-entry.ts<__CACHE_TTL)){{renderFn(entry.data,true);if(!alwaysFetch)return}};fetch(url).then(function(r){{return r.json()}}).then(function(d){{var isSame=entry&&JSON.stringify(d)===JSON.stringify(entry.data);if(!isSame){{__apiCache[key]={{data:d,ts:now}};renderFn(d,false)}}}}).catch(function(e){{if(!entry)renderFn(null,false)}})}}
function invalidateCache(pattern){{Object.keys(__apiCache).forEach(function(k){{if(k.indexOf(pattern)>=0)delete __apiCache[k]}})}};if(!__wrdLoaded){{var __wrdLoaded=false}};
function loadWardrobe(){{var needFetch=!__wrdData||__wardrobeNeedsReload;__wardrobeNeedsReload=false;if(__wrdData){{renderCatRows(__wrdData)}}if(!needFetch)return;fetch('/api/wardrobe').then(r=>r.json()).then(d=>{{__wrdStats=d;var elTotal=document.getElementById('wrd-total'),elUtil=document.getElementById('wrd-util'),elOver=document.getElementById('wrd-over');if(elTotal){{elTotal.textContent=d.metadata.total_items;elTotal.classList.remove('skeleton-text')}}if(elUtil){{var pct=Math.round((d.utilization||{{}}).utilization_rate*100)||0;elUtil.textContent=pct+'%';elUtil.classList.remove('skeleton-text');if(pct<30)elUtil.parentElement.classList.add('warn')}}if(elOver){{var over=Object.values(d.category_gaps||{{}}).filter(function(g){{return g.status==='overstock'}}).length;elOver.textContent=over;elOver.classList.remove('skeleton-text');if(over>2)elOver.parentElement.classList.add('warn')}}}}).catch(function(e){{console.error('Wardrobe stats error:',e)}});fetch('/api/wardrobe/items').then(r=>r.json()).then(d=>{{__wrdData=d.items;renderCatRows(d.items)}}).catch(function(e){{console.error('Wardrobe items error:',e)}});fetch('/api/wardrobe/new-items').then(r=>r.json()).then(function(d){{__newItemIds=(d.new_items||[]).map(function(it){{return it.id}});if(__wrdData)renderCatRows(__wrdData)}}).catch(function(){{}})}}
var COLOR_MAP={{'黑色':'#2a2a2a','白色':'#f5f3ef','米白':'#f5f0e8','乳白':'#faf8f5','深灰':'#4a4a4a','灰色':'#9e9e9e','浅灰':'#d0d0d0','银灰':'#bdbdbd','灰绿':'#8a9a82','卡其':'#c4b5a0','卡其色':'#c4b5a0','驼色':'#b8976e','深棕':'#5c3d2e','棕色':'#7a5230','浅棕':'#b8956a','深蓝':'#1e3a5f','藏蓝':'#1e3a6f','藏青':'#1e3a5f','海军蓝':'#1e3a5f','蓝色':'#4a7eb5','浅蓝':'#7ea3c8','天蓝':'#8bb8d6','军绿':'#5c6e4a','军绿色':'#5c6e4a','墨绿':'#3c5032','绿色':'#6b8c5c','浅绿':'#9cba8c','正红色':'#c4523c','红色':'#c4523c','暗红':'#8b2e3e','酒红':'#8b2e3e','橙色':'#e88a3c','亮橙':'#f0983c','橘色':'#e88030','黄色':'#d4a84b','姜黄':'#c49a3c','米黄':'#e8d8b0','紫色':'#8b6b9e','浅紫':'#b89ac8','粉色':'#e8b4b8','浅粉':'#f0c8cc','米色':'#e8dcc8','沙色':'#d8ccb0','深牛仔蓝':'#2a4a6c','牛仔蓝':'#4a6a8c','浅牛仔蓝':'#7a9ab8','牛油果绿':'#7a9a5c','条纹':'#c0c0c0','印花':'#c0c0c0'}};function colorHex(name){{var c=COLOR_MAP[name];if(c)return c;for(var k in COLOR_MAP){{if(k.indexOf(name)!=-1||name.indexOf(k)!=-1)return COLOR_MAP[k]}}return'#bdbdbd'}}
	var CAT_ORDER=['TS','LS','SHIRT','TANK','JK','PT','SH','SHOE','BAG','HAT','SOCK','SUN','ACC'];
var CAT_ICONS={{'TS':'👕','LS':'👔','SHIRT':'👔','TANK':'🎽','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','BAG':'🎒','HAT':'🧢','SOCK':'🧦','SUN':'🕶️','ACC':'⌚'}};
function renderCatRows(items){{var cats={{}};var archived=[];items.forEach(function(it){{if(it._archived){{archived.push(it);return}}var c=it.category_code;if(!cats[c])cats[c]=[];cats[c].push(it)}});var html='';CAT_ORDER.forEach(function(code){{var list=cats[code]||[];if(!list.length)return;var icon=CAT_ICONS[code]||'📦';var name=list[0].category;html+='<div class=\"wrd-cat-row\"><div class=\"wrd-cat-header\"><span class=\"wrd-cat-header-icon\">'+icon+'</span><span class=\"wrd-cat-header-name\">'+escHtml(name)+'</span><span class=\"wrd-cat-header-count\">'+list.length+'件</span></div><div class=\"wrd-cat-scroll\">'+list.map(function(it){{return renderItemCardH(it)}}).join('')+'</div></div>'}});if(archived.length){{html+='<div class=\"wrd-cat-row\" style=\"opacity:.7\"><div class=\"wrd-cat-header\"><span class=\"wrd-cat-header-icon\">🗄️</span><span class=\"wrd-cat-header-name\">旧衣库</span><span class=\"wrd-cat-header-count\">'+archived.length+'件</span></div><div class=\"wrd-cat-scroll\">'+archived.map(function(it){{return renderItemCardH(it)}}).join('')+'</div></div>'}}document.getElementById('wrd-rows').innerHTML=html||'<div class=\"wrd-empty\">暂无数据</div>'}}
function renderItemCardH(it){{var inner='';if(it.thumb){{inner='<img class=\"wrd-item-card-img\" src=\"../'+escHtml(it.thumb)+'\" loading=\"lazy\" onerror=\"this.style.display=\\'none\\';this.parentElement.innerHTML=\\'<span style=font-size:11px;color:var(--muted)>'+escHtml(it.id)+'</span>\\'\">'}}else{{inner='<span style=\"font-size:11px;color:var(--muted)\">'+escHtml(it.id)+'</span>'}}var badgeHtml='';if(__newItemIds&&__newItemIds.indexOf(it.id)!==-1){{badgeHtml='<span class=\"new-badge\">NEW</span>'}}return'<div class=\"wrd-item-card-h\" onclick=\"openItemModal(\\''+escHtml(it.id)+'\\')\" style=\"position:relative\"><div class=\"wrd-item-card-img-wrap\">'+inner+'<span class=\"wrd-item-card-id\">'+escHtml(it.id)+'</span></div>'+badgeHtml+'</div>'}}
function filterWardrobe(){{var q=document.getElementById('wrd-search').value.toLowerCase();document.querySelectorAll('.wrd-cat-row').forEach(function(row){{var cards=row.querySelectorAll('.wrd-item-card-h');var anyVisible=false;cards.forEach(function(c){{var t=(c.querySelector('.wrd-item-card-id')||{{}}).textContent||'';var visible=!q||t.toLowerCase().includes(q);c.style.display=visible?'':'none';if(visible)anyVisible=true}});row.style.display=anyVisible?'':'none'}})}}
var __currentItemId=null,__currentItemData=null,__imgRotation=0,__editingTagIdx=-1,__editingTagGroup='',__editingTagField='';
function openItemModal(itemId){{__currentItemId=itemId;__imgRotation=0;__editingTagIdx=-1;__editingTagField='';var overlay=document.getElementById('item-modal');var scroll=document.getElementById('item-modal-scroll');overlay.classList.add('show');scroll.innerHTML='<div class=\"wrd-loading\">加载中...</div>';if(__newItemIds&&__newItemIds.indexOf(itemId)!==-1){{fetch('/api/wardrobe/new-items/dismiss',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{clothing_id:itemId}})}}).then(function(){{__newItemIds=__newItemIds.filter(function(id){{return id!==itemId}});if(__wrdData)renderCatRows(__wrdData)}})}}fetch('/api/wardrobe/item/'+encodeURIComponent(itemId)).then(function(r){{return r.json()}}).then(function(data){{if(data.error){{scroll.innerHTML='<div class=\"wrd-empty\">加载失败</div>';return}}__currentItemData=data;if(!data.recommended_styles||!data.recommended_styles.length){{data.recommended_styles=matchStyles(data)}}renderItemCard(data);scroll.scrollTop=0}}).catch(function(){{scroll.innerHTML='<div class=\"wrd-empty\">网络错误</div>'}})}}
function closeItemModal(){{document.getElementById('item-modal').classList.remove('show');__currentItemId=null;__currentItemData=null}}
function rotateImg(dir){{__imgRotation+=dir*90;var img=document.getElementById('im-hero-img');if(img)img.style.transform='translate(-50%,-50%) rotate('+__imgRotation+'deg)'}}
function matchStyles(data){{var styles=[];var allTags=[];if(data.brand&&data.brand.name)allTags.push(data.brand.name);var c=data.color||{{}};if(c.hue_family)allTags.push(c.hue_family);if(c.hue_name)allTags.push(c.hue_name);var f=data.fabric||{{}};if(f.primary)allTags.push(f.primary);if(f.texture)allTags.push(f.texture);var s=data.silhouette||{{}};if(s.fit)allTags.push(s.fit);var p=data.pattern||{{}};if(p.type)allTags.push(p.type);var sm=data.style_modifiers||[];allTags=allTags.concat(sm);var occ=data.occasions||[];allTags=allTags.concat(occ);var str=allTags.join(' ').toLowerCase();var rules=[{{k:'日系简约',m:['uniqlo','日系','简约','基本','基础百搭']}},{{k:'韩系潮流',m:['韩','韩流','街头','潮流','oversize']}},{{k:'City Boy',m:['宽松','落肩','city','boy','日系']}},{{k:'Clean Fit',m:['合身','clean','简约','基本','纯色']}},{{k:'街头潮流',m:['街头','潮流','logo','印花','oversize','棒球']}},{{k:'轻熟商务',m:['商务','通勤','正式','衬衫','西裤','牛津','polo']}},{{k:'运动休闲',m:['运动','速干','nike','adidas','跑步','健身','网球']}},{{k:'复古工装',m:['工装','复古','军绿','卡其','帆布','牛仔']}},{{k:'意式运动',m:['意式','fila','italia','运动','复古']}},{{k:'高街暗黑',m:['黑色','暗黑','高街','cdg','comme']}},{{k:'户外机能',m:['户外','机能','冲锋','防风','防水','登山','徒步']}},{{k:'夏日度假',m:['度假','海滩','亚麻','短裤','凉鞋','夏日']}},{{k:'极简主义',m:['极简','纯色','基本','无logo','单色']}}];rules.forEach(function(r){{var hit=r.m.some(function(kw){{return str.indexOf(kw)!=-1}});if(hit&&styles.indexOf(r.k)==-1)styles.push(r.k)}});if(!styles.length)styles.push('基础百搭');return styles.slice(0,5)}}
function getTagGroups(data){{var g=[];var rs=data.recommended_styles||matchStyles(data);g.push({{id:'recommended_styles',title:'🤖 AI 适合风格',tags:rs.slice().map(function(s){{return{{l:s,f:''}}}}),readonly:true,highlight:true}});var b=data.brand||{{}};if(b.name)g.push({{id:'brand',title:'品牌',tags:[{{l:b.name+(b.collection?' · '+b.collection:''),f:'name'}}]}});var c=data.color||{{}};var colorTags=[];if(c.hue_family)colorTags.push({{l:c.hue_family,f:'hue_family'}});if(c.hue_name)colorTags.push({{l:c.hue_name,f:'hue_name'}});if(c.saturation)colorTags.push({{l:c.saturation,f:'saturation'}});if(c.lightness)colorTags.push({{l:c.lightness,f:'lightness'}});if(c.is_neutral)colorTags.push({{l:'中性色',f:'is_neutral'}});if(c.friendly_for_pale_skin)colorTags.push({{l:'显白',f:'friendly_for_pale_skin'}});var cExt=(c.extra||[]).slice();for(var ei=0;ei<cExt.length;ei++)colorTags.push({{l:cExt[ei],f:'extra_'+ei}});if(colorTags.length)g.push({{id:'color',title:'色彩',tags:colorTags}});var f=data.fabric||{{}};var fabTags=[];if(f.primary)fabTags.push({{l:f.primary,f:'primary'}});if(f.texture)fabTags.push({{l:f.texture,f:'texture'}});if(f.weight)fabTags.push({{l:f.weight,f:'weight'}});if(fabTags.length)g.push({{id:'fabric',title:'面料',tags:fabTags}});var s=data.silhouette||{{}};var silTags=[];if(s.fit)silTags.push({{l:s.fit,f:'fit'}});if(s.shoulder_effect&&s.shoulder_effect!='无特殊效果')silTags.push({{l:s.shoulder_effect,f:'shoulder_effect'}});if(s.torso_effect&&s.torso_effect!='无特殊效果')silTags.push({{l:s.torso_effect,f:'torso_effect'}});if(silTags.length)g.push({{id:'silhouette',title:'版型',tags:silTags}});var p=data.pattern||{{}};var patTags=[];if(p.type&&p.type!='纯色')patTags.push({{l:p.type,f:'type'}});if(p.density&&p.density!='无')patTags.push({{l:p.density,f:'density'}});if(p.logo_visible)patTags.push({{l:'Logo',f:'logo_visible'}});var pExt=(p.extra||[]).slice();for(var pi=0;pi<pExt.length;pi++)patTags.push({{l:pExt[pi],f:'extra_'+pi}});if(patTags.length)g.push({{id:'pattern',title:'图案',tags:patTags}});var season=(f.seasonality||[]).slice();if(season.length)g.push({{id:'season',title:'季节',tags:season.map(function(s,i){{return{{l:s,f:'season_'+i}}}})}});var occ=data.occasions||[];g.push({{id:'occasions',title:'场景',tags:occ.slice().map(function(s,i){{return{{l:s,f:'occ_'+i}}}})}});var sm=(data.style_modifiers||[]).slice();g.push({{id:'style_modifiers',title:'风格修饰',tags:sm.map(function(s,i){{return{{l:s,f:'sm_'+i}}}})}});return g}}
function renderItemCard(data,forceRefresh){{var isArchived=data.meta&&data.meta.archived;var boost=(data.meta&&data.meta.boost_score)||0;var thumbRaw=data._thumb||'';var thumbPath=thumbRaw.split('?')[0];var imgSrc=thumbPath?'/api/image?f='+encodeURIComponent(thumbPath)+'&w=600':'';var groups=getTagGroups(data);var groupsHtml=groups.map(function(grp){{var wrapCls=grp.highlight?'im-tag-group im-tag-group-hl':'im-tag-group';var chips=grp.tags.map(function(t,i){{var label=t.l||t;var cls=grp.readonly?'im-tag im-tag-ro':'im-tag';var del=grp.readonly?'':'<span class=\"im-tag-del\" onclick=\"event.stopPropagation();removeChip(\\''+grp.id+'\\','+i+')\">×</span>';return'<span class=\"'+cls+'\" onclick=\"'+(grp.readonly?'':'editChip(\\''+grp.id+'\\','+i+')')+'\">'+escHtml(label)+del+'</span>'}}).join('');var canAdd=!grp.readonly&&(!grp.maxSlots||grp.tags.length<grp.maxSlots);if(canAdd)chips+='<span class=\"im-tag im-tag-add\" onclick=\"addChip(\\''+grp.id+'\\')\">+</span>';return'<div class=\"'+wrapCls+'\"><div class=\"im-tag-group-title\">'+escHtml(grp.title)+'</div><div class=\"im-tags\">'+chips+'</div></div>'}}).join('');var archiveLabel=isArchived?'↩️ 移回衣橱':'🗑️ 移入旧衣库';var archiveBtnClass=isArchived?'im-btn-restore':'im-btn-archive';var archiveFn=isArchived?'restoreItem()':'archiveItem()';var deleteBtn=isArchived?'<button class=\"im-btn-archive\" onclick=\"deleteItem()\" style=\"color:#c62828;border-color:#fce4ec!important\">🗑️ 彻底扔掉</button>':'';var boostLabel=boost>0?'⭐ 已推荐('+boost+')':'⭐ 多推荐';var actionsHtml=isArchived?'<div class=\"im-actions\"><button class=\"'+archiveBtnClass+'\" onclick=\"'+archiveFn+'\">'+archiveLabel+'</button>'+deleteBtn+'</div>':'<div class=\"im-actions\"><button class=\"im-btn-save-tags\" onclick=\"saveAllChanges()\">💾 保存修改</button><button class=\"im-btn-boost\" onclick=\"boostItem()\">'+boostLabel+'</button><button class=\"'+archiveBtnClass+'\" onclick=\"'+archiveFn+'\">'+archiveLabel+'</button></div>';var scroll=document.getElementById('item-modal-scroll');scroll.innerHTML='<div class=\"im-hero\"><img class=\"im-hero-img\" id=\"im-hero-img\" src=\"'+imgSrc+'\" onerror=\"this.style.display=\\'none\\'\" style=\"transform:translate(-50%,-50%) rotate('+__imgRotation+'deg)\"><span class=\"im-hero-id\">'+escHtml(data.clothing_id)+'</span><button class=\"im-rotate-btn im-rotate-left\" onclick=\"rotateImg(-1)\">↺</button><button class=\"im-rotate-btn im-rotate-right\" onclick=\"rotateImg(1)\">↻</button></div><div class=\"im-info\"><div class=\"im-info-name\">'+escHtml(data.meta&&data.meta.claude_fit_comment||data.category)+'</div><div class=\"im-info-brand\">'+escHtml(data.clothing_id)+' · '+escHtml(data.category)+' · 穿着'+escHtml(String(data.meta&&data.meta.wear_count||0))+'次</div></div>'+groupsHtml+'<div id=\"im-chip-editor\" style=\"display:none\"></div><div class=\"im-actions\">'+actionsHtml+'</div>'}}
function editChip(groupId,idx){{var data=__currentItemData;if(!data)return;var grp=getTagGroups(data).find(function(g){{return g.id===groupId}});if(!grp||idx<0||idx>=grp.tags.length)return;var tag=grp.tags[idx];__editingTagGroup=groupId;__editingTagIdx=idx;__editingTagField=tag.f||'';var label=tag.l||tag;var el=document.getElementById('im-chip-editor');el.style.display='block';el.innerHTML='<div class=\"im-tag-detail\"><input id=\"im-chip-input\" value=\"'+escHtml(label)+'\"><div class=\"im-tag-detail-btns\"><button class=\"im-btn-save\" onclick=\"saveChipEdit()\">确认</button><button class=\"im-btn-cancel\" onclick=\"cancelChipEdit()\">取消</button></div></div>';var inp=document.getElementById('im-chip-input');inp.focus();inp.select()}}
function saveChipEdit(){{var val=document.getElementById('im-chip-input').value.trim();if(!val||!__editingTagGroup)return cancelChipEdit();var data=__currentItemData;var gid=__editingTagGroup;var fld=__editingTagField;if(gid==='brand'){{if(!data.brand)data.brand={{}};data.brand.name=val}}else if(gid==='color'){{var c=data.color||{{}};if(fld==='is_neutral')c.is_neutral=val!=='false';else if(fld==='friendly_for_pale_skin')c.friendly_for_pale_skin=val!=='false';else if(fld&&fld.indexOf('extra_')===0){{if(!c.extra)c.extra=[];var ei=parseInt(fld.split('_')[1]);if(!isNaN(ei)&&ei>=0)c.extra[ei]=val}}else if(fld)c[fld]=val;data.color=c}}else if(gid==='fabric'){{var f=data.fabric||{{}};if(fld)f[fld]=val;data.fabric=f}}else if(gid==='silhouette'){{var s=data.silhouette||{{}};if(fld)s[fld]=val;data.silhouette=s}}else if(gid==='pattern'){{var p=data.pattern||{{}};if(fld==='logo_visible')p.logo_visible=val!=='false';else if(fld&&fld.indexOf('extra_')===0){{if(!p.extra)p.extra=[];var pi=parseInt(fld.split('_')[1]);if(!isNaN(pi)&&pi>=0)p.extra[pi]=val}}else if(fld)p[fld]=val;data.pattern=p}}else if(gid==='season'){{if(!data.fabric)data.fabric={{}};if(!data.fabric.seasonality)data.fabric.seasonality=[];var si=parseInt(fld.split('_')[1]);if(!isNaN(si)&&si>=0)data.fabric.seasonality[si]=val}}else if(gid==='occasions'){{if(!data.occasions)data.occasions=[];var oi=parseInt(fld.split('_')[1]);if(!isNaN(oi)&&oi>=0)data.occasions[oi]=val}}else if(gid==='style_modifiers'){{if(!data.style_modifiers)data.style_modifiers=[];var mi=parseInt(fld.split('_')[1]);if(!isNaN(mi)&&mi>=0)data.style_modifiers[mi]=val}}cancelChipEdit();renderItemCard(data)}}
function cancelChipEdit(){{__editingTagIdx=-1;__editingTagGroup='';__editingTagField='';document.getElementById('im-chip-editor').style.display='none'}}
function addChip(groupId){{var data=__currentItemData;if(!data)return;var grp=getTagGroups(data).find(function(g){{return g.id===groupId}});if(!grp||grp.readonly)return;var newVal='新标签';if(groupId==='brand'){{if(!data.brand)data.brand={{}};if(!data.brand.name){{data.brand.name=newVal;__editingTagField='name'}}else{{newVal=data.brand.name;__editingTagField='name'}}}}else if(groupId==='color'){{if(!data.color)data.color={{}};var _c=data.color;if(!_c.hue_family){{_c.hue_family=newVal;__editingTagField='hue_family'}}else if(!_c.hue_name){{_c.hue_name=newVal;__editingTagField='hue_name'}}else if(!_c.saturation){{_c.saturation=newVal;__editingTagField='saturation'}}else if(!_c.lightness){{_c.lightness=newVal;__editingTagField='lightness'}}else{{if(!_c.extra)_c.extra=[];_c.extra.push(newVal);__editingTagField='extra_'+(_c.extra.length-1)}}}}else if(groupId==='fabric'){{if(!data.fabric)data.fabric={{}};var _f=data.fabric;if(!_f.primary){{_f.primary=newVal;__editingTagField='primary'}}else if(!_f.texture){{_f.texture=newVal;__editingTagField='texture'}}else if(!_f.weight){{_f.weight=newVal;__editingTagField='weight'}}else{{_f.primary=newVal;__editingTagField='primary'}}}}else if(groupId==='silhouette'){{if(!data.silhouette)data.silhouette={{}};var _s=data.silhouette;if(!_s.fit){{_s.fit=newVal;__editingTagField='fit'}}else if(!_s.shoulder_effect||_s.shoulder_effect==='无特殊效果'){{_s.shoulder_effect=newVal;__editingTagField='shoulder_effect'}}else if(!_s.torso_effect||_s.torso_effect==='无特殊效果'){{_s.torso_effect=newVal;__editingTagField='torso_effect'}}else{{_s.fit=newVal;__editingTagField='fit'}}}}else if(groupId==='pattern'){{if(!data.pattern)data.pattern={{}};var _p=data.pattern;if(!_p.type||_p.type==='纯色'){{_p.type=newVal;__editingTagField='type'}}else if(!_p.density||_p.density==='无'){{_p.density=newVal;__editingTagField='density'}}else{{if(!_p.extra)_p.extra=[];_p.extra.push(newVal);__editingTagField='extra_'+(_p.extra.length-1)}}}}else if(groupId==='season'){{if(!data.fabric)data.fabric={{}};if(!data.fabric.seasonality)data.fabric.seasonality=[];data.fabric.seasonality.push(newVal);__editingTagField='season_'+(data.fabric.seasonality.length-1)}}else if(groupId==='occasions'){{if(!data.occasions)data.occasions=[];data.occasions.push(newVal);__editingTagField='occ_'+(data.occasions.length-1)}}else if(groupId==='style_modifiers'){{if(!data.style_modifiers)data.style_modifiers=[];data.style_modifiers.push(newVal);__editingTagField='sm_'+(data.style_modifiers.length-1)}}renderItemCard(data);__editingTagGroup=groupId;var el=document.getElementById('im-chip-editor');el.style.display='block';el.innerHTML='<div class=\"im-tag-detail\"><input id=\"im-chip-input\" value=\"'+escHtml(newVal)+'\"><div class=\"im-tag-detail-btns\"><button class=\"im-btn-save\" onclick=\"saveChipEdit()\">确认</button><button class=\"im-btn-cancel\" onclick=\"cancelChipEdit()\">取消</button></div></div>';var inp=document.getElementById('im-chip-input');inp.focus();inp.select()}}
function removeChip(groupId,idx){{var data=__currentItemData;if(!data)return;var grp=getTagGroups(data).find(function(g){{return g.id===groupId}});var tag=grp&&idx<grp.tags.length?grp.tags[idx]:null;var fld=tag?tag.f:'';if(groupId==='brand'){{if(data.brand)data.brand.name=''}}else if(groupId==='color'){{var c=data.color||{{}};if(fld==='is_neutral')c.is_neutral=false;else if(fld==='friendly_for_pale_skin')c.friendly_for_pale_skin=false;else if(fld&&fld.indexOf('extra_')===0){{var ri=parseInt(fld.split('_')[1]);if(!isNaN(ri)&&ri>=0&&c.extra)c.extra.splice(ri,1)}}else if(fld)c[fld]='';data.color=c}}else if(groupId==='fabric'){{var f=data.fabric||{{}};if(fld)f[fld]='';data.fabric=f}}else if(groupId==='silhouette'){{var s=data.silhouette||{{}};if(fld)s[fld]=(fld==='fit'?'':'无特殊效果');data.silhouette=s}}else if(groupId==='pattern'){{var p=data.pattern||{{}};if(fld==='logo_visible')p.logo_visible=false;else if(fld&&fld.indexOf('extra_')===0){{var rj=parseInt(fld.split('_')[1]);if(!isNaN(rj)&&rj>=0&&p.extra)p.extra.splice(rj,1)}}else if(fld)p[fld]=(fld==='type'?'纯色':(fld==='density'?'无':''));data.pattern=p}}else if(groupId==='season'){{if(data.fabric&&data.fabric.seasonality)data.fabric.seasonality.splice(idx,1)}}else if(groupId==='occasions'){{if(data.occasions)data.occasions.splice(idx,1)}}else if(groupId==='style_modifiers'){{if(data.style_modifiers)data.style_modifiers.splice(idx,1)}}renderItemCard(data)}}
function showToast(msg,color){{var t=document.createElement('div');t.textContent=msg;t.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:'+(color||'#1e3a5f')+';color:#fff;padding:14px 28px;border-radius:12px;font-size:15px;font-weight:600;z-index:300;box-shadow:0 8px 32px rgba(0,0,0,.25);animation:fadeInUp .3s ease';document.body.appendChild(t);setTimeout(function(){{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(function(){{t.remove()}},300)}},1800)}}
function rateOutfit(btn,n,isHist){{var oid,stars,cancelEl;if(isHist){{var ss=btn.closest('.hist-stars');oid=ss?ss.dataset.oid:'';stars=ss?ss.querySelectorAll('.sr-btn'):[];cancelEl=ss?ss.querySelector('.cancel-rating'):null}}else{{var heroRate=btn.closest('.hero-rate');oid=heroRate?heroRate.dataset.oid:'';stars=document.querySelectorAll('#hero-star-row .sr-btn');cancelEl=document.getElementById('hero-cancel')}}
if(!oid){{showToast('无法获取穿搭ID','#c4523c');return}}
var currentFilled=0;stars.forEach(function(s,i){{if(s.classList.contains('filled'))currentFilled=i+1}});
if(n===currentFilled&&currentFilled>0){{if(confirm('确定取消评分吗？'))cancelRating(oid,stars,cancelEl);return}}
if(n===1){{showReasonModal(oid,stars,cancelEl,isHist);return}}
doRate(oid,n,stars,cancelEl,isHist)}}
var __feedbackOid='',__feedbackStars=null,__feedbackCancelEl=null,__feedbackIsHist=false,__selectedFeedbackItems=[];
function showReasonModal(oid,stars,cancelEl,isHist){{__feedbackOid=oid;__feedbackStars=stars;__feedbackCancelEl=cancelEl;__feedbackIsHist=isHist;
document.getElementById('feedback-title').textContent='为什么不满意？';
document.getElementById('feedback-step1').style.display='block';
document.getElementById('feedback-step2').style.display='none';
document.getElementById('feedback-overlay').classList.add('show')}}
function selectReason(reason){{if(!__feedbackOid)return;
var fb={{reason:reason,detail:''}};
var msgs={{style_mismatch:'已记录，将减少此类风格推荐',scene_mismatch:'已记录，此场景不再推荐类似穿搭',item_issue:'已记录'}};
var msg=msgs[reason]||'已记录';
doRate(__feedbackOid,1,__feedbackStars,__feedbackCancelEl,__feedbackIsHist,fb);
closeFeedbackModal();
showToast(msg,'#c4523c')}}
function showItemStep(){{if(!__feedbackOid)return;
document.getElementById('feedback-title').textContent='哪些单品不满意？';
document.getElementById('feedback-step1').style.display='none';
document.getElementById('feedback-step2').style.display='block';
fetch('/api/outfit/'+encodeURIComponent(__feedbackOid)).then(function(r){{return r.json()}}).then(function(d){{var itemsHtml='';var items=d.items||[];
items.forEach(function(it){{itemsHtml+='<div class="feedback-item" data-item-id="'+escHtml(it.id)+'" onclick="toggleFeedbackItem(this)"><span class="fi-check">__CHECK_SVG__</span><span class="fi-icon">__TSHIRT_SVG__</span><span class="fi-id">'+escHtml(it.id)+'</span><span class="fi-name">'+escHtml(it.name||it.id)+'</span></div>'}});
document.getElementById('feedback-items').innerHTML=itemsHtml||'<div style="padding:20px;text-align:center;color:var(--muted)">暂无单品数据</div>';
__selectedFeedbackItems=[];updateFeedbackConfirmBtn()}}).catch(function(){{showToast('加载单品失败','#c4523c')}})}}
function toggleFeedbackItem(el){{el.classList.toggle('selected');var iid=el.dataset.itemId;var idx=__selectedFeedbackItems.indexOf(iid);if(idx>=0)__selectedFeedbackItems.splice(idx,1);else __selectedFeedbackItems.push(iid);updateFeedbackConfirmBtn()}}
function updateFeedbackConfirmBtn(){{var btn=document.getElementById('feedback-confirm-btn');if(btn){{btn.textContent='确认('+(__selectedFeedbackItems.length?'选'+__selectedFeedbackItems.length+'项':'跳过')+')';btn.disabled=false}}}}
function closeFeedbackModal(){{document.getElementById('feedback-overlay').classList.remove('show');__feedbackOid='';__selectedFeedbackItems=[]}}
function confirmFeedback(){{if(!__feedbackOid){{closeFeedbackModal();return}}
var fb=__selectedFeedbackItems.length?{{reason:'item_issue',banned_items:__selectedFeedbackItems}}:{{reason:'item_issue',detail:''}};
doRate(__feedbackOid,1,__feedbackStars,__feedbackCancelEl,__feedbackIsHist,fb);closeFeedbackModal()}}
function syncAllStars(oid,n){{var allRows=document.querySelectorAll('.hist-stars[data-oid="'+oid+'"]');allRows.forEach(function(row){{var btns=row.querySelectorAll('.sr-btn');btns.forEach(function(b,i){{b.classList.toggle('filled',i<n);b.innerHTML=(i<n)?__sf__:__so__}})}});var heroRate=document.querySelector('.hero-rate[data-oid="'+oid+'"]');if(heroRate){{var heroStars=heroRate.querySelectorAll('.sr-btn');heroStars.forEach(function(b,i){{b.classList.toggle('filled',i<n);b.innerHTML=(i<n)?__sf__:__so__}})}}var heroCancel=document.getElementById('hero-cancel');if(heroCancel)heroCancel.classList.toggle('visible',n>0)}}
function insertCardSorted(dst,card){{var cardDate=card.getAttribute('data-date')||'';var children=dst.querySelectorAll(':scope > .fav-card');var inserted=false;for(var i=0;i<children.length;i++){{if(cardDate>(children[i].getAttribute('data-date')||'')){{dst.insertBefore(card,children[i]);inserted=true;break}}}}if(!inserted)dst.appendChild(card)}}
function moveCardToSection(oid,targetId){{var card=document.querySelector('.fav-card[data-oid="'+oid+'"]');if(!card)return;var parent=card.parentElement;if(!parent||parent.id===targetId)return;var dst=document.getElementById(targetId);if(!dst)return;var ph=dst.querySelector(':scope > div:not(.fav-card)');if(ph)ph.remove();insertCardSorted(dst,card)}}
function cloneCardToSection(oid,targetId){{if(document.querySelector('#'+targetId+' .fav-card[data-oid="'+oid+'"]'))return;var card=document.querySelector('.fav-card[data-oid="'+oid+'"]');if(!card)return;var clone=card.cloneNode(true);var dst=document.getElementById(targetId);if(!dst)return;var ph=dst.querySelector(':scope > div:not(.fav-card)');if(ph)ph.remove();insertCardSorted(dst,clone)}}
function doRate(oid,n,stars,cancelEl,isHist,feedback){{var body={{outfit_id:oid,rating:n,rated_at:new Date().toISOString()}};if(feedback)body.feedback=feedback;
fetch('/rate',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}}).then(function(r){{return r.json()}}).then(function(d){{if(d.status==='ok'){{if(stars)stars.forEach(function(s,i){{s.classList.toggle('filled',i<n);s.innerHTML=(i<n)?__sf__:__so__}});if(cancelEl)cancelEl.classList.toggle('visible',true);syncAllStars(oid,n);try{{var rc=JSON.parse(localStorage.getItem('rc')||'{{}}');rc[oid]=n;localStorage.setItem('rc',JSON.stringify(rc))}}catch(e){{}}var card=document.querySelector('.fav-card[data-oid="'+oid+'"]');var inToday=card&&card.parentElement&&card.parentElement.id==='today-list';if(n===3){{if(inToday){{cloneCardToSection(oid,'fav-list')}}else{{moveCardToSection(oid,'fav-list')}}}}else if(n>=0&&n<3&&card&&card.parentElement&&card.parentElement.id==='fav-list'){{moveCardToSection(oid,'today-list')}}showToast({{1:'已记录，会减少此类推荐',2:'已记录一般',3:'感谢好评！✨'}}[n]||'评分已记录',n===1?'#c4523c':'#2e7d32')}}}}).catch(function(){{showToast('网络错误','#c4523c')}})}}
function cancelRating(oid,stars,cancelEl){{fetch('/rate/cancel',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{outfit_id:oid}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.status==='ok'){{if(stars)stars.forEach(function(s){{s.classList.remove('filled');s.innerHTML=__so__}});if(cancelEl)cancelEl.classList.remove('visible');syncAllStars(oid,0);try{{var rc=JSON.parse(localStorage.getItem('rc')||'{{}}');delete rc[oid];localStorage.setItem('rc',JSON.stringify(rc))}}catch(e){{}}var card=document.querySelector('.fav-card[data-oid="'+oid+'"]');var inToday=card&&card.parentElement&&card.parentElement.id==='today-list';var favClone=document.querySelector('#fav-list .fav-card[data-oid="'+oid+'"]');if(favClone&&inToday){{favClone.remove();var fl=document.getElementById('fav-list');if(fl&&!fl.querySelector('.fav-card'))fl.innerHTML='<div style="padding:16px;color:var(--muted);font-size:13px">暂无三星好评 · 给穿搭点 ⭐⭐⭐ 后会出现在这里</div>'}}else if(card&&card.parentElement&&card.parentElement.id==='fav-list'){{moveCardToSection(oid,'today-list')}}showToast('评分已取消','#1e3a5f')}}}}).catch(function(){{showToast('网络错误','#c4523c')}})}}
function saveAllChanges(){{if(!__currentItemId||!__currentItemData)return;var data=__currentItemData;var btn=document.querySelector('.im-btn-save-tags');if(btn){{btn.textContent='保存中...';btn.disabled=true}}var hasRotation=__imgRotation%360!==0;var doSave=function(){{var newStyles=matchStyles(data);data.recommended_styles=newStyles;var updates={{}};if(data.brand)updates.brand=data.brand;if(data.color)updates.color=data.color;if(data.fabric)updates.fabric=data.fabric;if(data.silhouette)updates.silhouette=data.silhouette;if(data.pattern)updates.pattern=data.pattern;if(data.occasions!==undefined)updates.occasions=data.occasions;if(data.style_modifiers!==undefined)updates.style_modifiers=data.style_modifiers;updates.recommended_styles=newStyles;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(updates)}}).then(function(r){{return r.json()}}).then(function(d){{if(btn)btn.disabled=false;if(d.ok){{showToast('✅ 保存成功','#2e7d32');var hadRotation=hasRotation;__imgRotation=0;renderItemCard(data,!!hadRotation);if(__wrdData){{var idx=__wrdData.findIndex(function(it){{return it.clothing_id===__currentItemId}});if(idx>=0){{__wrdData[idx]=data;renderCatRows(__wrdData)}}else{{fetch('/api/wardrobe/items').then(function(r){{return r.json()}}).then(function(d2){{__wrdData=d2.items;renderCatRows(d2.items)}})}}}}setTimeout(function(){{var b=document.querySelector('.im-btn-save-tags');if(b)b.textContent='💾 保存修改'}},800)}}else{{showToast('❌ 保存失败','#c4523c');if(btn)btn.textContent='💾 保存修改'}}}}).catch(function(){{if(btn){{btn.disabled=false;btn.textContent='💾 保存修改'}}showToast('❌ 网络错误','#c4523c')}})}};if(hasRotation){{fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId)+'/transform',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{rotate:__imgRotation,scale:1.0,translate_x:0,translate_y:0}})}}).then(function(r){{return r.json()}}).then(function(){{doSave()}}).catch(function(){{doSave()}})}}else{{doSave()}}}}
function boostItem(){{if(!__currentItemId||!__currentItemData)return;var cur=(__currentItemData.meta&&__currentItemData.meta.boost_score)||0;var newBoost=cur+1;if(!__currentItemData.meta)__currentItemData.meta={{}};__currentItemData.meta.boost_score=newBoost;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{boost_score:newBoost}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok)renderItemCard(__currentItemData)}})}}
function archiveItem(){{if(!__currentItemId||!confirm('确定移入旧衣库吗？'))return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{archived:true}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{closeItemModal();__wrdData=null;loadWardrobe()}}}})}}
function restoreItem(){{if(!__currentItemId)return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{archived:false}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{closeItemModal();__wrdData=null;loadWardrobe()}}}})}}
function deleteItem(){{if(!__currentItemId||!confirm('确定彻底删除 '+__currentItemId+' 吗？\\n\\n将删除标签、图片等所有数据，不可恢复！'))return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId)+'/delete',{{method:'POST'}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{showToast('已删除 '+d.deleted+' 个文件','#c4523c');closeItemModal();__wrdData=null;loadWardrobe()}}else{{showToast('删除失败: '+(d.error||'未知'),'#c4523c')}}}}).catch(function(){{showToast('网络错误','#c4523c')}})}}
function loadReport(period){{period=period||'weekly';var el=document.getElementById('wrd-report-content');el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';fetch('/api/report?period='+period).then(function(r){{return r.json()}}).then(function(d){{if(d.empty){{el.innerHTML='<div class=\"report-empty\">📊 暂无评分数据<br><span style=\"font-size:12px;color:var(--muted)\">评分后会在这里生成报告</span></div>';return}}var html='<div class=\"wrd-monthly\">';var periodLabel=d.period==='weekly'?'📊 穿搭周报':'📊 穿搭月报';html+='<div class=\"wm-card\"><div class=\"wm-title\">'+periodLabel+'</div>';html+='<div style=\"font-size:11px;color:var(--muted);margin-bottom:8px\">📅 '+escHtml(d.date_range)+' | '+d.total_ratings+' 次评分</div>';html+='<div class=\"wm-stat-row\"><div class=\"wm-stat-item\"><div class=\"wm-stat-val\" style=\"color:#e74c3c\">'+d.satisfaction_rate+'%</div><div class=\"wm-stat-lbl\">❤️ 满意</div></div>';html+='<div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.neutral_rate+'%</div><div class=\"wm-stat-lbl\">🤔 一般</div></div>';html+='<div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.avg_rating+'</div><div class=\"wm-stat-lbl\">⭐ 均分</div></div></div>';if(d.trend_label)html+='<div style=\"font-size:11px;color:var(--muted);margin-top:4px\">'+escHtml(d.trend_label)+'</div>';html+='</div>';if(d.top_styles&&d.top_styles.length){{html+='<div class=\"report-section-title\">🎯 '+(d.period==='weekly'?'本周风格':'风格偏好')+'</div>';html+='<div class=\"report-style-grid\">';d.top_styles.forEach(function(s){{html+='<div class=\"report-style-card\">';if(s.image_url){{html+='<img class=\"report-style-img\" src=\"'+s.image_url+'\" alt=\"'+escHtml(s.name)+'\" loading=\"lazy\">'}}else{{html+='<div class=\"report-style-placeholder\">'+escHtml(s.name)+'</div>'}}html+='<div class=\"report-style-info\"><div class=\"report-style-name\">'+escHtml(s.name)+'</div>';html+='<div class=\"report-style-meta\">'+s.count+'次 · '+s.avg_rating+'分</div></div>';html+='</div>'}});html+='</div>'}}if(d.top_items&&d.top_items.length){{html+='<div class=\"report-section-title\">👔 '+(d.period==='weekly'?'本周最爱':'最爱单品')+'</div>';d.top_items.forEach(function(item){{html+='<div class=\"report-item-card\">';if(item.thumbnail_url){{html+='<img class=\"report-item-thumb\" src=\"'+item.thumbnail_url+'\" alt=\"'+escHtml(item.id)+'\" loading=\"lazy\">'}}else{{html+='<div class=\"report-item-thumb\" style=\"display:flex;align-items:center;justify-content:center;font-size:20px\">👔</div>'}}html+='<div class=\"report-item-info\">';html+='<div class=\"report-item-name\">'+escHtml(item.name||item.id)+'</div>';if(item.description)html+='<div class=\"report-item-desc\">'+escHtml(item.description)+'</div>';html+='<div class=\"report-item-count\">穿过 '+item.count+' 次</div>';html+='</div></div>'}});}}if(d.period==='monthly'){{if(d.neutral_analysis&&d.neutral_analysis.length){{html+='<div class=\"wm-card\"><div class=\"wm-title\">🔍 中立模式分析</div>';d.neutral_analysis.forEach(function(s){{html+='<div style=\"font-size:11px;color:var(--sub);margin-bottom:4px\">'+escHtml(s)+'</div>'}});html+='</div>'}}if(d.suggestions&&d.suggestions.length){{html+='<div class=\"wm-card\"><div class=\"wm-title\">💡 AI 建议</div>';d.suggestions.forEach(function(s){{html+='<div style=\"font-size:11px;color:var(--sub);margin-bottom:4px\">'+escHtml(s)+'</div>'}});html+='</div>'}}}}html+='</div>';if(d.period==='weekly'){{html+='<button class=\"report-toggle-btn\" onclick=\"loadReport(\\'monthly\\')\">📅 查看完整月度报告 →</button>'}}else{{html+='<button class=\"report-toggle-btn\" onclick=\"loadReport(\\'weekly\\')\">↩ 返回周报</button>'}}el.innerHTML=html}}).catch(function(e){{el.innerHTML='<div class=\"report-empty\">⚠️ 加载失败<br><span style=\"font-size:12px\">'+e.message+'</span></div>'}})}}function loadMonthlyReport(){{loadReport('weekly')}}
function loadColdItems(){{var el=document.getElementById('wrd-cold-list');if(!__apiCache['cold'])el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';cachedFetch('cold','/api/wardrobe/cold-items',function(d,fromCache){{if(!d.cold_items||!d.cold_items.length){{el.innerHTML='<div class=\"wrd-empty\">🎉 所有单品都有穿着记录！</div>';return}}var html='';d.cold_items.forEach(function(it){{var badge=it.is_key?'<span class=\"cold-badge key\">关键</span>':'<span class=\"cold-badge\">闲置</span>';var cutout=it.cutout?'/api/image?f='+encodeURIComponent(it.cutout.split('?')[0])+'&w=600':'';var thumb=it.thumb?'<img class=\"wrd-item-thumb\" src=\"../'+escHtml(it.thumb)+'\" loading=\"lazy\" onclick=\"event.stopPropagation();showImg(cutout||this.src)\">':'<div class=\"wrd-item-thumb\" style=\"background:'+colorHex(it.color)+';display:flex;align-items:center;justify-content:center;font-size:7px;color:#fff;text-shadow:0 1px 1px rgba(0,0,0,.3)\">'+escHtml(it.id)+'</div>';html+='<div class=\"wrd-cold-item\">'+thumb+'<div class=\"wrd-item-info\"><div class=\"wi-name\">'+escHtml(it.name)+'</div><div class=\"wi-meta\">'+escHtml(it.brand||'')+' · '+escHtml(it.id)+'</div><div class=\"wi-usage\">上次穿: '+escHtml(it.last_used||'从未')+'</div></div>'+badge+'</div>'}});el.innerHTML=html}},false)}}
function loadGaps(){{var el=document.getElementById('wrd-gaps-content');if(!__apiCache['gaps'])el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';cachedFetch('gaps','/api/wardrobe/gaps',function(d,fromCache){{var html='';if(d.suggestions&&d.suggestions.length){{d.suggestions.forEach(function(s){{html+='<div class=\"wrd-gap-card priority-'+s.priority+'\"><span class=\"gap-priority '+s.priority+'\">'+{{'high':'🔴 高优先','medium':'🟡 中优先','low':'🟢 低优先'}}[s.priority]+'</span><div class=\"gap-item\">'+escHtml(s.item)+'</div><div class=\"gap-reason\">💡 '+escHtml(s.reason)+'</div></div>'}})}}if(d.category_gaps){{var gapCats=Object.entries(d.category_gaps).filter(function(e){{return e[1].status!=='healthy'}});if(gapCats.length){{html+='<div class=\"wm-card\" style=\"margin-top:12px\"><div class=\"wm-title\">📊 品类状态</div>';gapCats.forEach(function(e){{var g=e[1];var icon=g.status==='overstock'?'⚠️':'❌';html+='<div class=\"wm-bar-row\"><span class=\"wm-bar-label\">'+icon+' '+escHtml(g.name)+'</span><span class=\"wm-bar-num\" style=\"width:auto\">'+g.actual+'件 (理想'+g.ideal_lo+'-'+g.ideal_hi+')</span></div>'}});html+='</div>'}}}}el.innerHTML=html||'<div class=\"wrd-empty\">衣橱品类分布良好 👍</div>'}},false)}}
/* 衣橱子页切换 */
(function(){{var wrdSeg=document.getElementById('wrd-seg');if(wrdSeg){{wrdSeg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;wrdSeg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;document.querySelectorAll('#page-wardrobe .wrd-sub').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='block';if(sub==='my'){{if(!__wrdData||__wardrobeNeedsReload){{__wardrobeNeedsReload=false;loadWardrobe()}}}}else if(sub==='monthly'){{loadMonthlyReport()}}else if(sub==='cold'){{loadColdItems()}}else if(sub==='gaps'){{loadGaps()}}}})}};/* Auto-load wardrobe on first visit to wardrobe tab */var __wrdLoaded=false;var origTabHandler=document.querySelector('#tab-bar').onclick;document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{if(this.dataset.page==='wardrobe'){{if(!__wrdLoaded||__wardrobeNeedsReload){{__wrdLoaded=true;__wardrobeNeedsReload=false;setTimeout(loadWardrobe,100)}}}}}})}})}})();
/* ═══ 探索页 ═══ */
function renderStyleCards(styles,showDesc){{if(!styles||!styles.length)return'<div class="wrd-empty">暂无风格数据</div>';return styles.map(function(s){{var desc=showDesc&&s.description?'<div class="es-desc">'+escHtml(s.description)+'</div>':'';var hasImg=!!s.image;var fullImg=s.image_full||s.image||'';var iconHtml=hasImg?'<img data-src="'+escHtml(s.image)+'" alt="'+escHtml(s.name_zh)+'" onclick="event.stopPropagation();showImg(\\''+escHtml(fullImg)+'\\')" style="cursor:pointer;background:#eef2f7;min-height:48px">':s.name_zh.charAt(0);var iconCls=hasImg?'es-icon has-img lazy-img':'es-icon';var bottomHtml='';var items=[];if(s.top_items)items=s.top_items;if(items.length>0){{var chips=items.map(function(it){{var cutout=it.cutout||it.thumb||'';var thumb=it.thumb||'';var thumbHtml=thumb?'<img data-src="'+escHtml(thumb)+'" onclick="event.stopPropagation();showImg(\\''+escHtml(cutout)+'\\')" style="background:#eef2f7">':'';return'<span class="es-item-chip lazy-img">'+thumbHtml+'</span>'}}).join('');bottomHtml='<div class="es-bottom"><div class="es-items">'+chips+'</div><button class="es-try-btn" onclick="event.stopPropagation();tryStyle(\\''+escHtml(s.id)+'\\',this)">🧪 试穿</button></div>'}}return'<div class="exp-style-card" onclick="window.location=\\'/style/'+escHtml(s.id)+'\\'"><div class="es-header"><div class="'+iconCls+'">'+iconHtml+'</div><div class="es-info"><div class="es-name">'+escHtml(s.name_zh)+'</div><div class="es-en">'+escHtml(s.name_en||s.id)+'</div></div></div>'+desc+bottomHtml+'</div>'}}).join('')}}
function loadExploreTweak(){{var el=document.getElementById('exp-tweak-content');var _loaded=__apiCache['exp-tweak']!==undefined;if(!_loaded)el.innerHTML='<div class="wrd-loading">加载中...</div>';cachedFetch('exp-tweak','/api/explore/tweak',function(d,fromCache){{el.innerHTML=d?renderStyleCards(d.styles,true)||'<div class="wrd-empty">先完成几套穿搭推荐吧</div>':'<div class="wrd-empty">加载失败</div>';observeLazyImages(el)}})}}
function loadExploreTransform(){{var el=document.getElementById('exp-transform-content');var _loaded=__apiCache['exp-transform']!==undefined;if(!_loaded)el.innerHTML='<div class="wrd-loading">加载中...</div>';cachedFetch('exp-transform','/api/explore/transform',function(d,fromCache){{el.innerHTML=d?renderStyleCards(d.styles,true)||'<div class="wrd-empty">已探索全部风格</div>':'<div class="wrd-empty">加载失败</div>';observeLazyImages(el)}})}}
function loadExploreCross(){{var el=document.getElementById('exp-cross-content');var _loaded=__apiCache['exp-cross']!==undefined;if(!_loaded)el.innerHTML='<div class="wrd-loading">加载中...</div>';cachedFetch('exp-cross','/api/explore/cross',function(d,fromCache){{if(!d){{el.innerHTML='<div class="wrd-empty">加载失败</div>';return}}var html='';if(d.fusion)html+='<div class="es-fusion">🎲 '+escHtml(d.fusion)+'</div>';html+=renderStyleCards(d.styles,true);el.innerHTML=html||'<div class="wrd-empty">暂无跨界建议</div>';observeLazyImages(el)}})}}
function toggleTcGroup(headerEl){{var body=headerEl.nextElementSibling;var arrow=headerEl.querySelector('.tc-arrow');var collapsed=body.classList.contains('collapsed');if(collapsed){{body.classList.remove('collapsed');body.style.display='';if(arrow)arrow.textContent='▼'}}else{{body.classList.add('collapsed');body.style.display='none';if(arrow)arrow.textContent='▶'}}}}
function loadExploreTrends(){{var el=document.getElementById('exp-trends-content');var _loaded=__apiCache['exp-trends']!==undefined;if(!_loaded)el.innerHTML='<div class="wrd-loading">加载中...</div>';cachedFetch('exp-trends','/api/explore/trends',function(d,fromCache){{if(!d){{el.innerHTML='<div class="wrd-empty">加载失败</div>';return}}var html='<div class="section-header">📚 全部风格 ('+d.total+')</div>';var order=['popular_trend','classic','niche','uncategorized'];var groups=d.groups||{{}};order.forEach(function(tc,idx){{var items=groups[tc];if(!items||!items.length)return;var labels=d.tc_labels||{{}};var info=labels[tc]||{{label:tc,color:'#888'}};html+='<div class="tc-group" style="margin-bottom:4px"><div class="tc-group-header" onclick="toggleTcGroup(this)" style="margin:16px 0 8px;padding:10px 12px;background:'+info.color+'10;border-left:3px solid '+info.color+';border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none"><div><span style="font-weight:700;font-size:14px;color:'+info.color+'">'+info.label+'</span><span style="font-size:11px;color:var(--sub);margin-left:8px">'+items.length+' 个</span></div><span class="tc-arrow" style="font-size:11px;color:'+info.color+'">▼</span></div><div class="tc-group-body" style="display:block">'+renderStyleCards(items,false)+'</div></div>'}});el.innerHTML=html;observeLazyImages(el)}})}}
function tryExplore(){{var inp=document.getElementById('exp-input');var msg=inp.value.trim();if(!msg)return;showProgress();fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg}})}}).then(r=>r.json()).then(d=>{{if(d.task_id){{__activePollId=d.task_id;pollTask(d.task_id)}}else{{document.getElementById('progress-title').textContent=d.result||'已发送';document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block'}}}})}}
function tryStyle(styleId,btn){{btn.classList.add('loading');btn.textContent='生成中...';fetch('/api/explore/try-on?style='+encodeURIComponent(styleId)).then(function(r){{return r.json()}}).then(function(d){{if(d.task_id){{showProgress();__activePollId=d.task_id;pollTask(d.task_id)}}else{{btn.classList.remove('loading');btn.textContent='🧪 试穿'}}}}).catch(function(e){{btn.classList.remove('loading');btn.textContent='🧪 试穿';alert('生成失败，请重试')}})}}
/* 探索页子页切换 */
(function(){{var expSeg=document.getElementById('exp-seg');if(expSeg){{expSeg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;expSeg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;document.querySelectorAll('#page-explore .exp-sub').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='block';if(sub==='tweak'){{loadExploreTweak()}}else if(sub==='transform'){{loadExploreTransform()}}else if(sub==='cross'){{loadExploreCross()}}else if(sub==='trends'){{loadExploreTrends()}}}})}};var __expLoaded=false;document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{if(this.dataset.page==='explore'&&!__expLoaded){{__expLoaded=true;setTimeout(loadExploreTweak,100)}}if(this.dataset.page==='profile'&&!__profileLoaded){{setTimeout(loadProfile,100)}}}})}})}})();
/* ═══ 我的形象页 ═══ */
var __profilePhotos={{}};/* {{slot:b64data}} compressed thumbnails */
var __profilePhotoSlot=null;/* current uploading slot */
var __genderVal='男',__bodyVal='',__skinVal='',__shoulderVal='',__faceVal='';
function selectSeg(el,groupId,varName){{el.parentElement.querySelectorAll('.seg-choice').forEach(function(c){{c.classList.remove('selected')}});el.classList.add('selected');window[varName]=el.dataset.val;if(groupId==='seg-gender'){{var g=el.dataset.val;var maleEl=document.getElementById('seg-body-male');var femaleEl=document.getElementById('seg-body-female');if(g==='女'){{if(maleEl)maleEl.style.display='none';if(femaleEl)femaleEl.style.display=''}}else{{if(maleEl)maleEl.style.display='';if(femaleEl)femaleEl.style.display='none'}}__bodyVal='';document.querySelectorAll('#seg-body-male .seg-choice, #seg-body-female .seg-choice').forEach(function(c){{c.classList.remove('selected')}})}}updateProfilePreview();updateProfileGuide()}}
function switchBodyShapes(){{var el=document.querySelector('#seg-gender .seg-choice.selected');if(!el)el=document.querySelector('#seg-gender .seg-choice');if(el)selectSeg(el,'seg-gender','__genderVal')}}
function capturePhoto(slot){{__profilePhotoSlot=slot;document.getElementById('profile-camera-input').click()}}
function pickPhoto(slot){{__profilePhotoSlot=slot;document.getElementById('profile-album-input').click()}}
/* 前端图片压缩 - 性能关键：将10MB+照片压缩到~100KB */
function compressImage(file, maxW, quality, callback){{var reader=new FileReader();reader.onload=function(e){{var img=new Image();img.onload=function(){{var c=document.createElement('canvas');var w=img.width,h=img.height;if(w>maxW){{h=Math.round(h*maxW/w);w=maxW}}c.width=w;c.height=h;var ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);callback(c.toDataURL('image/jpeg',quality||0.75))}};img.src=e.target.result}};reader.readAsDataURL(file)}}
function handleProfilePhoto(input,source){{var f=input.files[0];if(!f)return;var slot=__profilePhotoSlot;var slotId='slot-'+slot.replace(/_/g,'-').replace('full-body-front','full').replace('face-closeup','face').replace('full-body-side','side');var el=document.getElementById(slotId);if(el){{el.classList.add('has-photo');var previewImg=el.querySelector('.photo-slot-preview');if(previewImg){{previewImg.src='';previewImg.style.display='none'}}var emptyEl=el.querySelector('.photo-slot-empty');if(emptyEl)emptyEl.textContent='压缩中...'}}compressImage(f,1024,0.75,function(b64){{__profilePhotos[slot]=b64;if(el){{var pi=el.querySelector('.photo-slot-preview');if(pi){{pi.src=b64;pi.style.display='block'}}var ee=el.querySelector('.photo-slot-empty');if(ee)ee.textContent='📷'}};/* 自动上传到服务器 */fetch('/api/profile/photos/upload',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{slot:slot,image:b64}})}}).then(function(r){{return r.json()}}).then(function(d){{if(!d.ok)console.warn('Photo upload failed:',d.error)}}).catch(function(){{}});updateProfileGuide()}});input.value=''}}
function toggleUseImage(){{var t=document.getElementById('toggle-use-image');t.classList.toggle('on');var detail=document.getElementById('profile-detail');var isOn=t.classList.contains('on');detail.style.display=isOn?'block':'none'}}
function updateProfileGuide(){{var emptyFields=[];var occ=document.getElementById('pf-occupation').value.trim();var pref=document.getElementById('pf-style-pref').value.trim();var pain=document.getElementById('pf-pain-points').value.trim();if(!occ)emptyFields.push('职业');if(!pref)emptyFields.push('偏好');if(!pain)emptyFields.push('困扰');var guide=document.getElementById('profile-guide');if(emptyFields.length===3){{guide.style.display='block';guide.innerHTML='<span>✨ 职业、偏好、困扰均留空 — AI 将完全自由探索，可能发现你意想不到的风格</span>'}}else if(emptyFields.length===2){{guide.style.display='block';guide.innerHTML='<span>✨ '+emptyFields.join('、')+'留空 — AI 将在这两个方面自由探索</span>'}}else if(emptyFields.length===1){{guide.style.display='block';guide.innerHTML='<span>✨ '+emptyFields[0]+'留空 — AI 将不受限制自由发挥</span>'}}else{{guide.style.display='none'}};updateProfilePreview()}}
function updateProfilePreview(){{var p=document.getElementById('profile-preview');var t=document.getElementById('profile-preview-text');var gender=__genderVal||'男';var h=document.getElementById('pf-height').value.trim();var w=document.getElementById('pf-weight').value.trim();var age=document.getElementById('pf-age').value.trim();var bt=__bodyVal;var st=__skinVal;var should=__shoulderVal;var face=__faceVal;var occ=document.getElementById('pf-occupation').value.trim();var pref=document.getElementById('pf-style-pref').value.trim();var pain=document.getElementById('pf-pain-points').value.trim();var secrets=document.getElementById('pf-body-secrets').value.trim();var parts=[];if(age)parts.push(age+'岁');parts.push(gender==='女'?'女性':'男性');if(h)parts.push(h+'cm');if(w)parts.push(w+'kg');if(bt)parts.push(bt);if(st)parts.push(st+'肤色');if(should)parts.push(should);if(face)parts.push(face);var extra=[];if(occ)extra.push('职业: '+occ);if(pref)extra.push('偏好: '+pref);if(pain)extra.push('困扰: '+pain);if(parts.length>3||extra.length||secrets){{p.style.display='block';var previewText='\"'+parts.join('，')+'\"';if(extra.length)previewText+='\\n'+extra.join(' · ');if(secrets)previewText+='\\n🔒 身材秘密: '+secrets;t.textContent=previewText;t.style.whiteSpace='pre-line'}}else{{p.style.display='none'}}}}
function analyzeProfilePhotos(){{var b64s=[];Object.keys(__profilePhotos).forEach(function(s){{b64s.push({{slot:s,b64:__profilePhotos[s]}})}});if(!b64s.length){{alert('请先上传至少一张照片');return}}var btn=document.getElementById('analyze-btn');btn.disabled=true;btn.textContent='📤 上传照片...';fetch('/api/profile/analyze',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{images:b64s}})}}).then(r=>r.json()).then(function(d){{btn.disabled=false;btn.textContent='🔍 AI 分析照片中的身形';if(d.ok&&d.analysis){{var a=d.analysis;if(a.gender){{__genderVal=a.gender;setSegVal('seg-gender',a.gender);window.__genderVal=a.gender;switchBodyShapes()}}if(a.estimated_height_cm&&parseInt(a.estimated_height_cm)>0)document.getElementById('pf-height').value=a.estimated_height_cm;if(a.body_type){{__bodyVal=a.body_type;setSegVal('seg-body',a.body_type)}}if(a.skin_tone){{__skinVal=a.skin_tone;setSegVal('seg-skin',a.skin_tone)}}if(a.shoulder_type){{__shoulderVal=a.shoulder_type;setSegVal('seg-shoulder',a.shoulder_type)}}if(a.face_shape){{__faceVal=a.face_shape;setSegVal('seg-face',a.face_shape)}}updateProfilePreview();updateProfileGuide();alert('✅ AI 分析完成，请核对并修正')}}else{{alert('AI 分析失败，请手动填写')}}}}).catch(function(e){{btn.disabled=false;btn.textContent='🔍 AI 分析照片中的身形';alert('网络错误: '+e.message)}})}}
function setSegVal(groupId,val){{var grp=document.getElementById(groupId);if(!grp)return;var found=false;grp.querySelectorAll('.seg-choice').forEach(function(c){{c.classList.remove('selected');if(c.dataset.val===val){{c.classList.add('selected');found=true}}}});if(!found){{var first=grp.querySelector('.seg-choice');if(first)first.classList.add('selected')}}}}
function saveProfile(){{var btn=document.getElementById('profile-save-btn');btn.disabled=true;btn.textContent='保存中...';var h=document.getElementById('pf-height').value.trim();var w=document.getElementById('pf-weight').value.trim();var age=document.getElementById('pf-age').value.trim();var occ=document.getElementById('pf-occupation').value.trim();var pref=document.getElementById('pf-style-pref').value.trim();var pain=document.getElementById('pf-pain-points').value.trim();var bodySecrets=document.getElementById('pf-body-secrets').value.trim();var useImg=document.getElementById('toggle-use-image').classList.contains('on');var data={{use_my_image:useImg,gender:__genderVal,height_cm:h,weight_kg:w,age:age,body_type:__bodyVal,skin_tone:__skinVal,shoulder_type:__shoulderVal,face_shape:__faceVal,occupation:occ,style_preference:pref,pain_points:pain,body_secrets:bodySecrets}};fetch('/api/profile/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}).then(r=>r.json()).then(function(d){{if(d.ok){{btn.textContent='✅ 已保存';btn.classList.add('saved');setTimeout(function(){{btn.textContent='保存形象信息';btn.classList.remove('saved');btn.disabled=false}},2000)}}else{{btn.disabled=false;btn.textContent='保存失败，重试'}}}}).catch(function(e){{btn.disabled=false;btn.textContent='网络错误，重试'}})}}
function resetProfile(){{if(!confirm('确定恢复默认吗？所有形象数据将被清除。'))return;fetch('/api/profile/reset').then(function(){{location.reload()}}).catch(function(){{location.reload()}})}}
/* ═══ 加载我的形象 ═══ */
var __profileLoaded=false;
function loadProfile(){{if(__profileLoaded)return;__profileLoaded=true;fetch('/api/profile').then(r=>r.json()).then(function(d){{var p=d.profile;if(!p)return;if(p.gender){{__genderVal=p.gender;setSegVal('seg-gender',p.gender);switchBodyShapes()}}if(p.height)document.getElementById('pf-height').value=p.height;if(p.weight)document.getElementById('pf-weight').value=p.weight;if(p.age)document.getElementById('pf-age').value=p.age;if(p.body_type){{__bodyVal=p.body_type;setSegVal('seg-body',p.body_type)}}if(p.skin_tone){{__skinVal=p.skin_tone;setSegVal('seg-skin',p.skin_tone)}}if(p.shoulder_type){{__shoulderVal=p.shoulder_type;setSegVal('seg-shoulder',p.shoulder_type)}}if(p.face_shape){{__faceVal=p.face_shape;setSegVal('seg-face',p.face_shape)}}if(p.occupation)document.getElementById('pf-occupation').value=p.occupation;if(p.style_preference)document.getElementById('pf-style-pref').value=p.style_preference;if(p.pain_points)document.getElementById('pf-pain-points').value=p.pain_points;if(p.body_secrets)document.getElementById('pf-body-secrets').value=p.body_secrets;var toggle=document.getElementById('toggle-use-image');var detail=document.getElementById('profile-detail');if(p.use_my_image===false){{toggle.classList.remove('on');detail.style.display='none'}}else{{toggle.classList.add('on');detail.style.display='block'}}/* load photos */if(p.photos){{Object.keys(p.photos).forEach(function(slot){{var slotId='slot-'+slot.replace(/_/g,'-').replace('full-body-front','full').replace('face-closeup','face').replace('full-body-side','side');var el=document.getElementById(slotId);if(el&&p.photos[slot]){{el.classList.add('has-photo');var img=el.querySelector('.photo-slot-preview');if(img)img.src='../'+p.photos[slot]+'?t='+Date.now()}}}})}}updateProfilePreview();updateProfileGuide()}}).catch(function(){{}})}}
function setPreference(mode){{fetch('/setpref?mode='+mode).catch(function(){{}})}}
/* ═══ 添加页 ═══ */
var __addImages=[];
function triggerAddCamera(){{document.getElementById('add-camera-input').click()}}
function triggerAddAlbum(){{document.getElementById('add-album-input').click()}}
function handleAddImages(input){{var files=Array.from(input.files);if(!files.length)return;var total=files.length;var loaded=0;files.forEach(function(f){{var blobUrl=URL.createObjectURL(f);__addImages.push({{file:f,preview:blobUrl,compressed:null}});loaded++;if(loaded===total){{renderAddImageStrip()}}}});input.value=''}}
function renderAddImageStrip(){{var strip=document.getElementById('add-image-strip');var hasImgs=__addImages.length>0;strip.style.display=hasImgs?'flex':'none';var html='';__addImages.forEach(function(img,i){{html+='<div class="add-image-thumb"><img src="'+img.preview+'"><span class="thumb-remove" onclick="event.stopPropagation();removeAddImage('+i+')">&times;</span></div>'}});html+='<div class="add-image-thumb add-more-btn" onclick="triggerAddAlbum()"><span class="add-more-plus">+</span><span class="add-more-label">添加</span></div>';strip.innerHTML=html;document.getElementById('add-confirm-btn').disabled=!hasImgs;document.getElementById('add-action-cards').style.display=hasImgs?'none':'grid'}}
function removeAddImage(index){{URL.revokeObjectURL(__addImages[index].preview);__addImages.splice(index,1);renderAddImageStrip();if(!__addImages.length){{document.getElementById('add-action-cards').style.display='grid';document.getElementById('add-confirm-btn').disabled=true}}}}
var __addAnalysisData=null,__matchResults=null,__selectedMatchIds=[],__previewOutfitData=null;
function clearAddImages(){{__addImages.forEach(function(img){{URL.revokeObjectURL(img.preview)}});__addImages=[];__addAnalysisData=null;__matchResults=null;__selectedMatchIds=[];__previewOutfitData=null;__addPollStopped=false;document.getElementById('add-image-strip').style.display='none';document.getElementById('add-image-strip').innerHTML='';document.getElementById('add-result').style.display='none';document.getElementById('add-result').innerHTML='';document.getElementById('add-progress').style.display='none';document.getElementById('add-action-cards').style.display='grid';var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='确认分析';btn.onclick=function(){{submitAddImages()}};document.getElementById('add-camera-input').value='';document.getElementById('add-album-input').value=''}}
function compressImageV2(file,callback,errCallback){{try{{var blobUrl=URL.createObjectURL(file);var img=new Image();img.onload=function(){{URL.revokeObjectURL(blobUrl);var w=img.width,h=img.height;var maxW=1024;if(w>maxW){{h=Math.round(h*maxW/w);w=maxW}}var c=document.createElement('canvas');c.width=w;c.height=h;var ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);c.toBlob(function(blob){{callback(blob)}},'image/jpeg',0.65)}};img.onerror=function(){{URL.revokeObjectURL(blobUrl);if(errCallback)errCallback('图片加载失败');else callback(file)}};img.src=blobUrl}}catch(e){{if(errCallback)errCallback(e.message);else callback(file)}}}}
function submitAddImages(){{if(!__addImages.length)return;__addPollStopped=false;var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='压缩中...';document.getElementById('add-progress').style.display='block';document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-loading\">压缩图片中...</div>';var compressedCount=0;var total=__addImages.length;var formData=new FormData();function doUpload(){{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-loading\">上传中...</div>';fetch('/api/wardrobe/add',{{method:'POST',body:formData}}).then(r=>r.json()).then(function(d){{if(d.task_id){{pollAddTask(d.task_id)}}else{{showAddReview(d)}}}}).catch(function(e){{document.getElementById('add-progress-text').innerHTML='<div class=\\"wrd-empty\\" style=\\"color:#e74c3c\\">⚠️ 上传失败<br><span style=\\"font-size:11px;color:var(--muted)\\">可能是网络超时或图片过大，请重试</span><br><button onclick=\\"submitAddImages()\\" style=\\"margin-top:10px;padding:10px 24px;background:var(--navy);color:#fff;border:none;border-radius:20px;font-size:14px\\">🔄 重试上传</button></div>';btn.textContent='重试';btn.disabled=false}})}}__addImages.forEach(function(img,i){{if(img.compressed){{formData.append('images',img.compressed,img.file.name||'photo.jpg');compressedCount++;if(compressedCount===total)doUpload();return}}compressImageV2(img.file,function(blob){{img.compressed=blob;formData.append('images',blob,img.file.name||'photo.jpg');compressedCount++;document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-loading\">压缩中 ('+compressedCount+'/'+total+')...</div>';if(compressedCount===total)doUpload()}},function(err){{img.compressed=img.file;formData.append('images',img.file,img.file.name||'photo.jpg');compressedCount++;if(compressedCount===total)doUpload()}})}})}}
function pollAddTask(tid){{if(__addPollStopped)return;fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){{if(d.status==='done'){{__addPollStopped=true;document.getElementById('add-progress').style.display='none';var data=JSON.parse(d.result);showAddReview(data)}}else if(d.status==='error'){{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\" style=\"color:#e74c3c\">识别失败: '+escHtml(d.message)+'<br><button onclick=\"submitAddImages()\" style=\"margin-top:10px;padding:10px 24px;background:var(--navy);color:#fff;border:none;border-radius:20px;font-size:14px\">🔄 重试</button></div>';var btn=document.getElementById('add-confirm-btn');btn.textContent='重试';btn.disabled=false}}if(d.error){{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\" style=\"color:#e74c3c\">识别失败: '+escHtml(d.error)+'<br><button onclick=\"submitAddImages()\" style=\"margin-top:10px;padding:10px 24px;background:var(--navy);color:#fff;border:none;border-radius:20px;font-size:14px\">🔄 重试</button></div>';var btn=document.getElementById('add-confirm-btn');btn.textContent='重试';btn.disabled=false}}else{{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-loading\">'+escHtml(d.message||'识别中...')+'</div>';setTimeout(function(){{pollAddTask(tid)}},1500)}}}}).catch(function(){{setTimeout(function(){{pollAddTask(tid)}},2000)}})}}
function showAddReview(data){{var items=data.items||[];if(!items.length){{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\">未识别到服装单品</div>';var btn=document.getElementById('add-confirm-btn');btn.textContent='重试';btn.disabled=false;return}}__addAnalysisData=data;__matchResults=null;__selectedMatchIds=[];__previewOutfitData=null;var btn=document.getElementById('add-confirm-btn');btn.textContent='确认入库 ('+items.length+'件)';btn.disabled=false;btn.onclick=function(){{confirmAddItems(data)}};var html='<div class=\"section-header\">AI 识别结果 · 请核对后确认</div>';items.forEach(function(item,i){{var c=item.color||{{}};var b=item.brand||{{}};var f=item.fabric||{{}};var colorHex=colorNameToHex(c.hue_name||'');html+='<div class=\"add-review-card\"><div class=\"ar-header\"><span class=\"ar-id\">'+escHtml(item.suggested_id||'')+'</span><span class=\"ar-cat\">'+escHtml(item.category||'')+'</span></div><div class=\"ar-fields\"><div class=\"ar-field\"><span class=\"ar-label\">品牌</span><span class=\"ar-value\">'+escHtml(b.name||'未知')+(b.confidence&&b.confidence!=='确定'?' <em>('+escHtml(b.confidence)+')</em>':'')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">颜色</span><span class=\"ar-value\">'+escHtml(c.hue_name||'')+' '+escHtml(c.hue_family||'')+'</span><span class=\"pal-dot\" style=\"display:inline-block;margin-left:6px;background:'+colorHex+'\"></span></div><div class=\"ar-field\"><span class=\"ar-label\">面料</span><span class=\"ar-value\">'+escHtml(f.primary||'')+' · '+escHtml(f.texture||'')+' · '+escHtml(f.weight||'')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">风格</span><span class=\"ar-value\">'+escHtml((item.style_modifiers||[]).join(' · ')||'基础款')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">场景</span><span class=\"ar-value\">'+escHtml((item.occasions||[]).join(' · ')||'日常')+'</span></div></div></div>'}});/* 衣橱匹配按钮 */html+='<div class=\"match-section\" id=\"match-section\"><div class=\"preview-cta\"><button class=\"preview-cta-btn\" onclick=\"loadWardrobeMatches()\">🔗 查看衣橱可搭配单品</button><div class=\"preview-cta-hint\">看看新衣服能和哪些已有单品搭配</div></div></div>';document.getElementById('add-result').innerHTML=html;document.getElementById('add-result').style.display='block'}}
function confirmAddItems(data){{var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='入库中...';fetch('/api/wardrobe/add/confirm',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{task_id:data._task_id,items:data.items}})}}).then(r=>r.json()).then(function(d){{if(d.ok){{document.getElementById('add-result').innerHTML='<div class=\"wrd-loading\" style=\"color:#2e7d32\">✅ 已添加 '+d.added.length+' 件单品</div>';setTimeout(function(){{clearAddImages();__wardrobeNeedsReload=true}},1500)}}else{{btn.disabled=false;btn.textContent='重试入库';document.getElementById('add-result').innerHTML='<div class=\"wrd-empty\">入库失败: '+escHtml(d.message||'')+'</div>'}}}}).catch(function(e){{btn.disabled=false;btn.textContent='重试入库';document.getElementById('add-result').innerHTML='<div class=\"wrd-empty\">网络错误: '+escHtml(e.message)+'</div>'}})}}
function colorNameToHex(name){{var m={{'红':'#c0392b','橙':'#e67e22','黄':'#f1c40f','绿':'#27ae60','青':'#1abc9c','蓝':'#2980b9','紫':'#8e44ad','粉':'#e91e63','棕':'#795548','灰':'#95a5a6','白':'#ecf0f1','黑':'#2c3e50','米':'#f5deb3','卡其':'#c3b091','藏青':'#1a3a5c','酒红':'#722f37','墨绿':'#1a4028','驼':'#c19a6b','焦糖':'#af6b3d','浅灰':'#bdc3c7','深灰':'#636e72','银':'#bdc3c7','金':'#d4a574'}};if(!name)return'#ccc';for(var k in m){{if(name.indexOf(k)>=0)return m[k]}}return'#ccc'}}
/* ═══ 🆕 衣橱匹配 + AI 穿搭预览 ═══ */
var CAT_ICON_MAP={{'TS':'👕','LS':'👔','SHIRT':'👔','TANK':'🎽','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','BAG':'🎒','HAT':'🧢','SOCK':'🧦','SUN':'🕶️','ACC':'⌚'}};
function loadWardrobeMatches(){{if(!__addAnalysisData||!__addAnalysisData.items)return;var btn=document.querySelector('.preview-cta-btn');if(btn){{btn.disabled=true;btn.textContent='匹配中...'}}fetch('/api/wardrobe/add/match',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{items:__addAnalysisData.items,task_id:__addAnalysisData._task_id}})}}).then(r=>r.json()).then(function(d){{if(d.ok&&d.match_results){{__matchResults=d.match_results;__selectedMatchIds=[];renderMatchSection(d.match_results)}}else{{var sec=document.getElementById('match-section');if(sec)sec.innerHTML='<div style=\"text-align:center;padding:16px;color:var(--muted)\">匹配失败，请重试</div>'}}}}).catch(function(e){{var sec=document.getElementById('match-section');if(sec)sec.innerHTML='<div style=\"text-align:center;padding:16px;color:var(--muted)\">网络错误</div>'}})}}
function renderMatchSection(matchResults){{if(!matchResults||!matchResults.length){{return}}var html='';matchResults.forEach(function(mr){{var matches=mr.matches||{{}};var catKeys=Object.keys(matches);if(!catKeys.length)return;var newItemCat=mr.category||'';html+='<div class=\"match-section-title\"><span class=\"ms-icon\">🔗</span> 衣橱中可与 <em>'+escHtml(newItemCat)+'</em> 搭配的</div>';catKeys.forEach(function(ck){{var catData=matches[ck];var items=catData.items||[];if(!items.length)return;var catIcon=CAT_ICON_MAP[ck]||'📦';html+='<div class=\"match-cat-group\"><div class=\"match-cat-label\">'+catIcon+' '+escHtml(catData.category_name)+' <span class=\"mcl-count\">('+items.length+'件)</span></div><div class=\"match-scroll\">';items.forEach(function(it){{var reasonsHtml=(it.match_reasons||[]).map(function(r){{return'<span class=\"mc-reason\">'+escHtml(r)+'</span>'}}).join('');var thumbHtml=it.thumb?'<img class=\"mc-thumb\" src=\"../'+escHtml(it.thumb.split('?')[0])+'?'+Date.now()+'\" loading=\"lazy\" onerror=\"this.style.display=\\'none\\'\">':'<div class=\"mc-thumb\" style=\"background:'+escHtml(it.color_hex||'#ccc')+';display:flex;align-items:center;justify-content:center;font-size:10px;color:#fff\">'+escHtml(it.id)+'</div>';html+='<div class=\"match-card\" data-item-id=\"'+escHtml(it.id)+'\" onclick=\"toggleMatchSelect(this,\\''+escHtml(it.id)+'\\')\"><span class=\"mc-score\">'+it.score+'%</span>'+thumbHtml+'<span class=\"mc-id\">'+escHtml(it.id)+'</span><span class=\"mc-brand\" title=\"'+escHtml(it.brand||'' )+'\">'+escHtml((it.brand||'').slice(0,12))+'</span><span class=\"mc-color\">'+escHtml(it.color)+'</span>'+reasonsHtml+'</div>'}});html+='</div></div>'}});/* 生图 CTA */html+='<div class=\"preview-cta\" id=\"preview-cta\"><button class=\"preview-cta-btn\" onclick=\"generatePreviewOutfit()\" id=\"preview-gen-btn\">🪄 以新衣为核心，AI 生成穿搭效果图</button><div class=\"preview-cta-hint\">已选 <span id=\"selected-count\">0</span> 件衣橱单品（点击卡片选择，未选则AI自动搭配）</div></div>'}});var sec=document.getElementById('match-section');if(sec)sec.innerHTML=html}}
function toggleMatchSelect(el,itemId){{var idx=__selectedMatchIds.indexOf(itemId);if(idx>=0){{__selectedMatchIds.splice(idx,1);el.classList.remove('selected')}}else{{__selectedMatchIds.push(itemId);el.classList.add('selected')}}var cnt=document.getElementById('selected-count');if(cnt)cnt.textContent=__selectedMatchIds.length}}
function generatePreviewOutfit(){{if(!__addAnalysisData||!__addAnalysisData.items||!__addAnalysisData.items.length)return;var btn=document.getElementById('preview-gen-btn');if(btn){{btn.disabled=true;btn.textContent='生成中...'}}var sel=document.getElementById('selected-count');if(sel)sel.textContent=__selectedMatchIds.length;showProgress();document.getElementById('progress-title').textContent='正在AI生成穿搭预览...';document.getElementById('progress-steps').innerHTML='<div style=\"text-align:center;padding:20px;color:#fff\">AI 选品搭配 + 生图约需 30 秒...</div>';fetch('/api/wardrobe/add/generate-outfit',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{new_item:__addAnalysisData.items[0],selected_ids:__selectedMatchIds}})}}).then(r=>r.json()).then(function(d){{if(d.task_id){{__activePollId=d.task_id;pollPreviewTask(d.task_id)}}else{{var ptitle=document.getElementById('progress-title');ptitle.textContent='❌ 生成失败';document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block';if(btn){{btn.disabled=false;btn.textContent='🪄 重试生成'}}}}}}).catch(function(e){{document.getElementById('progress-title').textContent='网络错误';document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block';if(btn){{btn.disabled=false;btn.textContent='🪄 重试生成'}}}})}}
function pollPreviewTask(tid){{fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){{if(tid!==__activePollId)return;var title=document.getElementById('progress-title');var steps=document.getElementById('progress-steps');var spinner=document.getElementById('progress-spinner');var closeBtn=document.getElementById('progress-close');var btn=document.getElementById('preview-gen-btn');if(d.status==='done'){{spinner.style.display='none';closeBtn.style.display='inline-block';closeBtn.onclick=function(){{closeProgress()}};title.textContent='✅ 穿搭预览完成';steps.innerHTML='';try{{var result=JSON.parse(d.result);__previewOutfitData=result;if(result.image_urls&&result.image_urls.length){{steps.innerHTML='<img class=\"progress-result-img\" src=\"'+escHtml(result.image_urls[0])+'\" loading=\"lazy\" style=\"max-width:100%;border-radius:8px\">'}}if(result.outfit_items){{var itemsHtml=result.outfit_items.map(function(oi){{var badge=oi.is_new?'<span class=\"opi-badge new\">🆕 新衣</span>':'<span class=\"opi-badge existing\">衣橱</span>';return'<div class=\"op-item\">'+badge+'<span class=\"opi-name\">'+escHtml(oi.brand||'')+' '+escHtml(oi.color||'')+escHtml(oi.category||'')+'</span></div>'}}).join('');steps.innerHTML+='<div style=\"margin-top:12px;text-align:left;color:var(--text);font-size:12px\">'+itemsHtml+'</div>'}}}}catch(e){{steps.innerHTML='<div style=\"color:var(--text)\">预览完成，刷新页面查看</div>'}}if(btn){{btn.disabled=false;btn.textContent='🪄 换一种搭配'}}}}else if(d.status==='error'){{spinner.style.display='none';closeBtn.style.display='inline-block';title.textContent='❌ 生成失败';steps.innerHTML='<div style=\"color:#c4523c\">'+escHtml(d.message||'未知错误')+'</div>';if(btn){{btn.disabled=false;btn.textContent='🪄 重试生成'}}}}else{{title.textContent=d.message||'生成中...';setTimeout(function(){{pollPreviewTask(tid)}},2000)}}}}).catch(function(){{setTimeout(function(){{pollPreviewTask(tid)}},2000)}})}}
function pinToHome(outfitId){{var card=document.querySelector('.fav-card[data-oid="'+outfitId+'"]');if(!card)return;var imgEl=card.querySelector('.h-char-img-lg');var heroImg=document.querySelector('.hero-img img');if(imgEl&&heroImg)heroImg.src=imgEl.src;var styleEl=card.querySelector('.fav-style');var heroStyle=document.querySelector('.hero-style');if(styleEl&&heroStyle){{var tn=styleEl.childNodes[0];var styleName=(tn&&tn.nodeType===3)?tn.nodeValue.trim():'';var scene=outfitId.replace(/^\\d{{4}}-\\d{{2}}-\\d{{2}}_/,'');heroStyle.textContent=scene+' · '+styleName}}var tagsEl=card.querySelector('.h-tags');var heroTags=document.querySelector('.style-tags');if(tagsEl&&heroTags)heroTags.innerHTML=tagsEl.innerHTML;var itemRows=card.querySelectorAll('.h-square-grid .item-row');var heroItems=document.querySelector('.hero-card .item-list');if(itemRows.length&&heroItems){{var itemsHtml='';itemRows.forEach(function(row){{var emoji=row.querySelector('.item-emoji');var idEl=row.querySelector('.item-id');var brandEl=row.querySelector('.ir-brand');var descEl=row.querySelector('.ir-desc');var thumbEl=row.querySelector('.item-img');var emojiHtml=emoji?emoji.outerHTML:'';var idText=idEl?idEl.textContent:'';var brandText=brandEl?brandEl.textContent:'';var descText=descEl?descEl.textContent:'';var thumbHtml=thumbEl?'<img class="item-thumb" src="'+thumbEl.src+'" onclick="event.stopPropagation();showImg(this.src)" loading="lazy">':'';var catMap={{'TS':'上衣','LS':'上衣','SHIRT':'上衣','TANK':'上衣','JK':'上衣','PT':'下装','SH':'下装','SHOE':'鞋子','HAT':'帽子','BAG':'包','SOCK':'袜子','SUN':'墨镜','ACC':'配饰'}};var cat=catMap[idText.split('-')[0]]||'';var name=brandText+' '+descText;itemsHtml+='<div class="item-row"><span class="item-emoji">'+emojiHtml+'</span><span class="item-cat">'+cat+'</span><span class="item-id">'+idText+'</span><span class="item-name">'+name+'</span>'+thumbHtml+'</div>'}});heroItems.innerHTML=itemsHtml}}var paletteEl=card.querySelector('.h-exp-palette');var heroPalette=document.querySelector('.hero-card .palette-strip');if(paletteEl&&heroPalette)heroPalette.outerHTML=paletteEl.outerHTML.replace('h-exp-palette','palette-strip');var dateEl=card.getAttribute('data-date')||'';if(dateEl){{var heroMeta=document.querySelector('.hero-meta');if(heroMeta)heroMeta.textContent=dateEl}}var srcRationale=card.querySelector('.pin-rationale .rationale-box');var heroCard=document.querySelector('.hero-card');if(srcRationale&&heroCard){{var dstRationale=heroCard.querySelector('.rationale-box');if(dstRationale){{dstRationale.innerHTML=srcRationale.innerHTML}}else{{var heroRate=heroCard.querySelector('.hero-rate');var clone=srcRationale.cloneNode(true);if(heroRate){{heroRate.parentNode.insertBefore(clone,heroRate)}}else{{heroCard.querySelector('.hero-body').appendChild(clone)}}}}}}var heroRate=document.querySelector('.hero-rate');if(heroRate)heroRate.setAttribute('data-oid',outfitId);var heroCancel=document.getElementById('hero-cancel');if(heroCancel)heroCancel.setAttribute('onclick',"cancelRating('"+outfitId+"')");var histStars=card.querySelector('.hist-stars');var existingRating=histStars?histStars.querySelectorAll('.sr-btn.filled').length:0;var heroStarRow=document.getElementById('hero-star-row');if(heroStarRow){{var heroBtns=heroStarRow.querySelectorAll('.sr-btn');heroBtns.forEach(function(b,i){{b.classList.toggle('filled',i<existingRating)}});var hc=document.getElementById('hero-cancel');if(hc)hc.classList.toggle('visible',existingRating>0)}}showToast('📌 已放回主页','#1e3a5f')}}
	function syncRatingsFromServer(){{var oids=[];document.querySelectorAll('.hist-stars').forEach(function(hs){{var oid=hs.dataset.oid;if(oid&&oids.indexOf(oid)===-1)oids.push(oid)}});var hr=document.querySelector('.hero-rate');if(hr&&hr.dataset.oid&&oids.indexOf(hr.dataset.oid)===-1)oids.push(hr.dataset.oid);try{{var rc=JSON.parse(localStorage.getItem('rc')||'{{}}');Object.keys(rc).forEach(function(oid){{syncAllStars(oid,rc[oid])}})}}catch(e){{}}if(!oids.length)return;fetch('/api/ratings',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{ids:oids}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ratings){{Object.keys(d.ratings).forEach(function(oid){{syncAllStars(oid,d.ratings[oid])}})}}}}).catch(function(){{}})}};syncRatingsFromServer();
</script>
</script>
</body></html>'''

# Fill in variables
tabs_html = '\n'.join([
    tab_btn('recommend', '推荐', True),
    tab_btn('explore', '探索'),
    tab_btn('wardrobe', '衣橱'),
    tab_btn('add', '添加'),
    tab_btn('profile', '我的'),
])

# ── Build history cards ──
# Style keyword dictionary for fallback matching
STYLE_KW_DICT = [
    # Style families
    (['日系','City Boy','city boy','cityboy'], '日系CityBoy'),
    (['韩系','韩式','korean'], '韩系简约'),
    (['美式','复古','retro','vintage'], '美式复古'),
    (['Clean Fit','clean fit','cleanfit','简约干净'], 'Clean Fit'),
    (['轻熟','smart casual','通勤'], '轻熟休闲'),
    (['街头','street','潮流','hip-hop'], '街头潮流'),
    (['机能','techwear','tech wear','户外'], '机能户外'),
    (['运动','athleisure','sport','跑步','网球','健身'], '运动休闲'),
    (['度假','resort','vacation','热带'], '度假休闲'),
    (['军事','工装','military','cargo'], '军事工装'),
    (['暗黑','先锋','avant-garde'], '暗黑先锋'),
    (['国风','新中式','heritage','东方'], '国风质感'),
    # Color tones
    (['低饱和','莫兰迪','大地色','earth tone','浅色系'], '低饱和配色'),
    (['深色','暗色','dark','黑色系'], '深色系'),
    (['亮色','撞色','鲜艳','亮眼'], '亮色撞色'),
    (['黑白灰','单色','monochrome'], '黑白灰'),
    (['蓝色系','蓝色调'], '蓝色系'),
    (['暖色','暖调','温暖'], '暖色系'),
    (['清爽','清凉','冷调'], '清爽配色'),
    # Occasion / mood
    (['雨天','防雨','防水','小雨'], '防小雨'),
    (['约会','date'], '约会'),
    (['休闲','日常','casual'], '日常休闲'),
    (['正式','formal','商务'], '正式场合'),
    # Silhouette / fabric
    (['叠穿','层次','layer'], '叠穿层次'),
    (['宽松','oversize','廓形','loose'], '宽松廓形'),
    (['修身','slim','合身'], '修身剪裁'),
    (['速干','透气','dry','吸湿'], '速干透气'),
    (['亚麻','linen','棉麻'], '天然面料'),
    (['丹宁','牛仔','denim'], '丹宁材质'),
]

# ── Encyclopedia keyword cache ──
_STYLE_ENC_KW_CACHE = {}
def _build_enc_cache():
    enc_dir = os.path.join(PROJ, 'styles_universal')
    if not os.path.isdir(enc_dir): return
    for edir in sorted(os.listdir(enc_dir)):
        ep = os.path.join(enc_dir, edir, 'encyclopedia.md')
        if not os.path.exists(ep): continue
        try:
            with open(ep) as f:
                first_line = f.readline()
                title_m = re.search(r"#\s*(.+)", first_line)
                title_clean = title_m.group(1).lower().replace(' ','').replace('-','').replace('_','') if title_m else ''
                if not title_clean: continue
                for cline in f:
                    m = re.search(r"\*{0,2}风格关键词\*{0,2}[：:]\s*(.+)", cline)
                    if m:
                        kws = [kw.strip()[:8] for kw in re.split(r"[、,，\s]+", m.group(1)) if len(kw.strip())>=2]
                        _STYLE_ENC_KW_CACHE[title_clean] = kws
                        parts = title_clean.split('(')[0] if '(' in title_clean else title_clean
                        if parts and parts != title_clean:
                            _STYLE_ENC_KW_CACHE[parts] = kws
                        break
        except: pass
_build_enc_cache()


def extract_tags(outfit):
    """Extract style tags: outfit.md keywords → content matching → style name"""
    tags = []
    dp = os.path.join(OUTFITS_DIR, outfit['dir'], 'outfit.md')
    content = ''
    if os.path.exists(dp):
        with open(dp) as f: content = f.read()
        # Strategy 1: 风格关键词 section
        in_kw = False
        for line in content.split('\n'):
            s = line.strip()
            if '风格关键词' in s:
                in_kw = True
                m = re.search(r'[：:]\s*(.+)', s)
                if m:
                    text = m.group(1).replace('、',',').replace('，',',')
                    for kw in text.split(','):
                        kw = kw.strip()
                        if kw and len(kw)>=2: tags.append(kw[:8])
                continue
            if in_kw:
                if s.startswith('##') or s.startswith('---'): break
                if s.startswith('- '): s = s[2:]
                for kw in s.replace('、',',').replace('，',',').split(','):
                    kw = kw.strip()
                    if kw and len(kw)>=2 and kw not in tags:
                        tags.append(kw[:8])
        # Basic junk filter: clear obviously bad tags so next strategies can contribute
        tags = [t for t in tags if not any(re.search(pat, t) for pat in JUNK_PATTERNS)]
        # Strategy 2.5: 从风格百科缓存查关键词
        if not tags:
            style_name = outfit.get('style','')
            if style_name and _STYLE_ENC_KW_CACHE:
                sn = style_name.lower().replace(' ','').replace('-','').replace('_','')
                if sn in _STYLE_ENC_KW_CACHE:
                    tags = list(_STYLE_ENC_KW_CACHE[sn])
                else:
                    for k, v in _STYLE_ENC_KW_CACHE.items():
                        if sn in k or k in sn:
                            tags = list(v)
                            break
        # Strategy 3: Content keyword matching (renamed from Strategy 3)
        if not tags:
            # Search whole outfit.md content for known style keywords
            matched = set()
            for patterns, label in STYLE_KW_DICT:
                for p in patterns:
                    if p.lower() in content.lower():
                        matched.add(label)
                        break
            tags = list(matched)[:4]
        # Strategy 4: from style name + weather
        if not tags:
            style = outfit.get('style','')
            weather = outfit.get('weather','')
            combined = style + ' ' + weather
            for sep in ['丨','｜','/','·','-',' ']:
                combined = combined.replace(sep, ' ')
            tags = [w.strip()[:8] for w in combined.split() if len(w.strip())>=2][:4]
    # Quality filter: remove junk tags
    tags = [t for t in tags if not any(re.search(pat, t) for pat in JUNK_PATTERNS)]
    # Also remove style name clones
    style_clean = outfit.get('style','').lower().replace(' ','').replace('-','').replace('_','')
    tags = [t for t in tags if not (t.strip().lower().replace(" ","").replace("-","").replace("_","") in style_clean or style_clean in t.strip().lower().replace(" ","").replace("-","").replace("_","") or len(t.strip().lower().replace(" ","").replace("-","").replace("_","")) < 2)]
    return tags[:4]

def gen_history_card(outfit, idx):
    items_html = ''
    # All keys must map to valid item_icons entries (tshirt/pants/shoe/hat/bag/sock/sun/acc)
    cat_icons = {'TS':'tshirt','LS':'tshirt','SHIRT':'tshirt','TANK':'tshirt',
                 'JK':'tshirt','PT':'pants','SH':'pants','SHOE':'shoe',
                 'HAT':'hat','BAG':'bag','SOCK':'sock','SUN':'sun','ACC':'acc'}
    for it in outfit['items'][:8]:
        prefix = it['id'].split('-')[0]
        ico_key = cat_icons.get(prefix, 'tshirt')
        # Never empty icon — fallback to tshirt
        ico = item_icons.get(ico_key) or item_icons.get('tshirt', '')
        img_html = ''
        # 历史卡片优先用 CDN 缩略图（/api/image 走 Funnel 不可靠）
        if it.get('thumb'):
            img_html = '<img class="item-img" src="{}" loading="lazy">'.format(cdn_url(it['thumb']))
        # Split brand from description using original full name
        full_name = it.get('full_name', it['name'])
        brand, desc = split_brand_desc(full_name)
        # Apple Watch: ensure band info in description
        if it['id'] == 'ACC-003':
            if not desc or len(desc) < 3:
                for b in ['尼龙回环','回环尼龙','米兰尼斯','运动表带','黑色运动','回环']:
                    if b in full_name: desc = b + '表带'; break
                if not desc: desc = '表带套组'
        brand_html = '<span class="ir-brand">{}</span>'.format(brand) if brand else ''
        desc_html = '<span class="ir-desc">{}</span>'.format(desc if desc else full_name[:18])
        items_html += '<div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle(\'expanded\')"><div class="ir-top"><span class="item-emoji">{}</span><span class="item-id">{}</span></div>{}{}{}</div>'.format(ico, it['id'], brand_html, desc_html, img_html)
    # Style tags from real data
    tags = extract_tags(outfit)
    tags_html = '<div class="h-tags">' + ''.join(['<span>{}</span>'.format(t[:8]) for t in tags]) + '</div>'
    # Display-only SVG star rating for history cards (read-only)
    rating_val = outfit['rating'] or 0
    ods = outfit['dir'].replace("'", "\\'").replace('"', '&quot;')
    stars_html = '<span class="star-row">'
    for s in range(1, 4):
        filled = ' filled' if s <= rating_val else ''
        svg = star_filled_svg if s <= rating_val else star_outline_svg
        stars_html += '<span class="sr-btn{}">{}</span>'.format(filled, svg)
    stars_html += '</span>'
    rating_html = '<span class="hist-stars" data-oid="{}">{}</span>'.format(ods, stars_html)
    # Character image
    img_tag = ''
    if outfit.get('char_img'):
        img_tag = '<img class="h-char-img" src="{}" onclick="event.stopPropagation();showImg(this.src)" loading="lazy">'.format(outfit['char_img'])
    else:
        img_tag = '<div class="h-char-img" style="background:#eaf0f6;display:flex;align-items:center;justify-content:center;color:#c8d4e2;font-size:16px">暂无</div>'
    # Color palette — only shown in expanded view
    palette_html = build_palette_html(outfit).replace('palette-strip', 'h-exp-palette')
    odir = outfit['dir'].replace("'", "\\'")
    # Rationale
    rationale_html = build_rationale_html(outfit)
    # Expanded: image + items, hidden rationale (for pinToHome), bottom row
    rationale_hidden = '<div style="display:none" class="pin-rationale">{}</div>'.format(rationale_html) if rationale_html else ''
    expanded_html = '<div class="h-expand-row">{img}<div class="h-square-grid">{items}</div></div>{rationale_hidden}<div class="h-exp-bottom"><button class="pin-btn" onclick="event.stopPropagation();pinToHome(\'{oid}\')">📌 放回主页</button>{palette}</div>'.format(
        img=img_tag.replace('h-char-img','h-char-img-lg'), items=items_html, rationale_hidden=rationale_hidden, palette=palette_html, oid=odir)
    # Small thumbnail for collapsed state — 优先用 300px 缩略图（10-25KB），大幅减少移动端加载时间
    thumb_small = ''
    char_thumb = outfit.get('char_thumb') or outfit.get('char_img', '')
    if char_thumb:
        thumb_small = '<img class="h-thumb-sm" src="{}" loading="lazy">'.format(char_thumb)
    # Header: style + tags only (no palette when collapsed)
    tag_info_html = '<div class="fav-style">{style}{rating}</div>{tags}'.format(
        style=outfit['style'][:30], rating=rating_html, tags=tags_html)
    odate = outfit.get('date', '')
    return '<div class="fav-card" data-oid="{oid}" data-date="{odate}" onclick="this.classList.toggle(\'expanded\')"><div class="fav-num">{idx}</div><div class="fav-info">{tag_info}</div>{thumb}<div class="fav-arrow">▾</div><div class="fav-expand">{expanded}</div></div>'.format(oid=odir, odate=odate, idx=idx, tag_info=tag_info_html, thumb=thumb_small, expanded=expanded_html)

today_outfits = scan_outfits(date_filter=time.strftime('%Y-%m-%d'), limit=10)
fav_outfits = scan_outfits(rating_filter=3, limit=10)
today_cards = '\n'.join([gen_history_card(o, i+1) for i, o in enumerate(today_outfits)])
fav_cards = '\n'.join([gen_history_card(o, i+1) for i, o in enumerate(fav_outfits)])
if not today_cards: today_cards = '<div style="padding:16px;color:var(--muted);font-size:13px">今日暂无推荐</div>'
if not fav_cards: fav_cards = '<div style="padding:16px;color:var(--muted);font-size:13px">暂无三星好评 · 给穿搭点 ⭐⭐⭐ 后会出现在这里</div>'

# ── Hero: use today's latest outfit (fallback to most recent if none today) ──
today = scan_outfits(date_filter=time.strftime('%Y-%m-%d'), limit=1)
if not today:
    today = scan_outfits(limit=1)  # fallback: latest outfit from any date
if today:
    ho = today[0]
    hero_outfit_id = ho['dir']
    hero_img = ho['char_img']
    # 标题格式：用户指令 · 风格名
    scene_name = ho.get('dir', '').split('_',1)[-1] if '_' in ho.get('dir','') else ''
    style_name = ho['style'][:25] if ho.get('style') else ''
    hero_style = '{} · {}'.format(scene_name.rstrip('。,，. ')[:20], style_name) if scene_name and style_name else (style_name or scene_name or '今日穿搭')
    hero_meta = '{} · {}'.format(ho['date'], (ho.get('weather','') or '晴 22~34°C')[:30])
    tags = extract_tags(ho)
    hero_tags_html = ''.join('<span>{}</span>'.format(t) for t in tags)
    palette_html = build_palette_html(ho)
    rationale_html = build_rationale_html(ho)
    hero_items_html = ''.join(item_row(
        item_icons.get({'TS':'tshirt','LS':'tshirt','SHIRT':'tshirt','TANK':'tshirt','JK':'tshirt','PT':'pants','SH':'pants','SHOE':'shoe','HAT':'hat','BAG':'bag','SOCK':'sock','SUN':'sun','ACC':'acc'}.get(it['id'].split('-')[0],'tshirt'),''),
        it.get('cat',''), it['id'], it['name'], it.get('thumb',''), it.get('cutout','')
    ) for it in ho['items'][:8])
    # Star rating row
    hero_rating_val = ho.get('rating') or 0
    hero_star_html = ''
    for s in range(1, 4):
        filled = ' filled' if s <= hero_rating_val else ''
        hero_star_html += '<button class="sr-btn{}" data-r="{}" onclick="rateOutfit(this,{})">{}</button>'.format(filled, s, s, star_filled_svg if s <= hero_rating_val else star_outline_svg)
    cancel_visible = ' visible' if hero_rating_val > 0 else ''
else:
    # Absolute fallback: no outfits exist at all — show placeholder
    hero_img = ''
    hero_style = '暂无推荐'
    hero_meta = '今天还没有生成穿搭，请先点击下方按钮生成'
    hero_tags_html = '<span>等待首套穿搭</span>'
    palette_html = ''
    rationale_html = ''
    hero_items_html = ''
    hero_star_html = ''
    cancel_visible = ''
    hero_outfit_id = ''

if USER_ID:
    # ── 多用户：从用户自己的衣橱生成其他推荐 ──
    user_tags = os.path.join(WARDROBE_DIR, 'tags')
    user_items = []
    if os.path.isdir(user_tags):
        for fn in sorted(os.listdir(user_tags)):
            if not fn.endswith('.json') or fn.startswith('SCORE_CACHE'):
                continue
            try:
                with open(os.path.join(user_tags, fn)) as f:
                    tag = json.load(f)
                cid = tag.get('clothing_id', '')
                cat = tag.get('category', '')
                name = get_display_name(cid)
                user_items.append({'id': cid, 'name': name, 'cat': cat, 'code': tag.get('category_code', '')})
            except:
                pass
    # 按品类分组，构建推荐组合
    tops = [it for it in user_items if it['code'] in ('TS', 'SHIRT', 'LS', 'TANK', 'JK')]
    bots = [it for it in user_items if it['code'] in ('PT', 'SH')]
    shoes = [it for it in user_items if it['code'] == 'SHOE']
    hats = [it for it in user_items if it['code'] == 'HAT']
    all_items = user_items

    def _pick(items, n=2):
        return [it['name'] for it in items[:n]]

    # 构建3组推荐
    alt_groups = []
    if tops and bots:
        alt_groups.append(['基础搭配', _pick(tops, 1) + _pick(bots, 1) + _pick(shoes, 1)])
    if len(tops) >= 2:
        alt_groups.append(['上衣组合', _pick(tops, 3)])
    if bots and shoes:
        alt_groups.append(['下装鞋履', _pick(bots, 1) + _pick(shoes, 2)])
    if all_items:
        alt_groups.append(['全部单品', _pick(all_items, 4)])

    while len(alt_groups) < 3:
        alt_groups.append(['你的衣橱', _pick(all_items, 3)])

    card1 = mini_card(alt_groups[0][0], alt_groups[0][1])
    card2 = mini_card(alt_groups[1][0], alt_groups[1][1])
    card3 = mini_card(alt_groups[2][0], alt_groups[2][1])

    # 生成 JS refreshAlts 数据
    alts_js = json.dumps(alt_groups[:6], ensure_ascii=False)
else:
    card1 = mini_card('日系 City Boy', ['TS-011 落肩T恤', 'SHIRT-001 条纹衬衫', 'PT-001 宽松牛仔裤', 'SHOE-009 AF1'])
    card2 = mini_card('轻熟休闲', ['SHIRT-003 牛津衬衫', 'PT-005 休闲西裤', 'SHOE-009 皮质板鞋', 'ACC-001 手串'])
    card3 = mini_card('韩系简约', ['TS-010 条纹T恤', 'PT-006 直筒牛仔裤', 'SHOE-005 网球鞋', 'HAT-004 棒球帽'])
    alts_js = json.dumps([
        ['日系 City Boy', ['TS-011 落肩T恤', 'SHIRT-001 条纹衬衫', 'SHOE-009 AF1']],
        ['轻熟休闲', ['SHIRT-003 牛津衬衫', 'PT-005 西裤', 'SHOE-009 板鞋']],
        ['韩系简约', ['TS-010 条纹T恤', 'PT-006 直筒牛仔裤', 'SHOE-005']],
        ['Clean Fit', ['TS-009 短袖', 'PT-002 牛仔裤', 'SHOE-006']],
        ['街头潮流', ['TS-006 黑T', 'JK-003 棒球服', 'SHOE-008']],
        ['运动休闲', ['TANK-001 背心', 'SH-001 速干短裤', 'SHOE-003']]
    ], ensure_ascii=False)

# Post-process: inject evaluated SVG strings into JS
html = html.replace('__CHECK_SVG__', check_svg)
html = html.replace('__TSHIRT_SVG__', item_icons.get('tshirt', ''))
html = html.replace('__SF_T__', star_filled_svg)
html = html.replace('__SO_T__', star_outline_svg)
html = html.replace('__X_SVG__', x_svg)
html = html.replace('__ALT_DATA__', alts_js)
html = html.replace('__STYLE_ICON__', style_icon_svg)
html = html.replace('__SCENE_ICON__', scene_icon_svg)
html = html.replace('__COMBO_ICON__', combo_icon_svg)

html = html.format(
    tabs=tabs_html,
    hero_img=hero_img, hero_style=hero_style, hero_meta=hero_meta,
    hero_tags_html=hero_tags_html, palette_html=palette_html, rationale_html=rationale_html, hero_items_html=hero_items_html,
    hero_outfit_id=hero_outfit_id, hero_star_html=hero_star_html, cancel_visible=cancel_visible,
    today_cards=today_cards, fav_cards=fav_cards,
    card1=card1, card2=card2, card3=card3, alts_js=alts_js,
    camera_lg_icon=add_icons['camera_lg_icon'], image_icon=add_icons['image_icon'],
    lock_icon=add_icons['lock_icon'],
)

# Replace JS relative path prefix '../' with CDN variable
# Pattern: '.../...'+func() → __CDN__+func()
html = html.replace("'../'+", "__CDN__+")
# Set CDN value + 注入用户标识 + fetch 拦截器（告别 Cookie 依赖）
cdn_base = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{}/'.format(get_git_commit())
_user_js = "var __USER__='{}';".format(USER_ID or '')
_fetch_wrapper = """var _origFetch=window.fetch;window.fetch=function(u,o){if(__USER__&&u.startsWith('/api/')&&!u.includes('?user=')){u=u+(u.includes('?')?'&':'?')+'user='+__USER__};return _origFetch.call(window,u,o)};"""
html = html.replace("var __CDN__='';", "var __CDN__='{}';{}{}".format(cdn_base, _user_js, _fetch_wrapper))

# 确定输出路径
if USER_ID:
    user_dir = resolve_user_dir(USER_ID)
    output_path = os.path.join(user_dir, 'cache', 'prototype.html')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
else:
    output_path = os.path.join(PROJ, 'prototype', 'mobile-v2.html')

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Written {} bytes to {}'.format(len(html), output_path))
print('CI icons: tshirt={} pants={} hat={}'.format(
    'OK' if item_icons['tshirt'] else 'MISSING',
    'OK' if item_icons['pants'] else 'MISSING',
    'OK' if item_icons['hat'] else 'MISSING',
))
