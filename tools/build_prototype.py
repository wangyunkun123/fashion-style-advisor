#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build mobile-v2.html prototype with proper icons from icon library"""
import re, os, json, time, random

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')
OUTFITS_DIR = os.path.join(PROJ, 'outfits')

def simplify_name(iid, name):
    """Simplify item name: brand + description, remove filler terms only"""
    brands = ['Lululemon','Nike','Adidas','Uniqlo','FUR SPEED','Champion','Decathlon',
              'Artengo','Decathlon Artengo','Decathlon Kiprun','Kiprun','Wilson','Converse',
              'Puma','FILA','HLA','COMME des GARCONS','COMME des GARÇONS PLAY','CDG',
              'Merrell','Timberland','Jordan','Cotton On','H FOREST','DAN JOHN',
              'LIBERTY SHINE','SHINO','YASCIQ','NBA','Apple']
    # Apple Watch: keep band info
    if iid == 'ACC-003' or 'Apple Watch' in name:
        band = ''
        for b in ['尼龙回环','回环尼龙','米兰尼斯','运动表带','黑色运动','回环']:
            if b in name: band = b; break
        if not band:
            # Try extracting from "表带套组（xxx）"
            m = re.search(r'表带套组[（(](.+?)[）)]', name)
            if m: band = m.group(1)
        if not band and '表带套组' in name:
            band = '表带套组'
        return 'Apple Watch {}'.format(band).strip() if band else 'Apple Watch'
    # Detect brand (longest match first)
    found_brand = ''
    for b in sorted(brands, key=len, reverse=True):
        if b.lower() in name.lower():
            found_brand = b
            break
    # Remove filler/tech terms only — keep the descriptive parts
    remove = ['Metal Vent Tech','Metal Vent','Court Lite','入门级','Artengo',
              'Leisure Club','敞穿或卷袖','敞穿','卷袖','叠穿','基本款','常规','标准']
    clean = name
    for r in remove:
        clean = clean.replace(r, '').replace('  ', ' ')
    if found_brand:
        desc = clean.replace(found_brand, '').strip()
        desc = desc.replace('  ', ' ').strip()
        if len(desc) <= 1:
            for cat in ['短袖','长袖','短裤','长裤','衬衫','外套','鞋子','帽子','袜子','墨镜','包']:
                if cat in clean: desc = cat; break
        return '{} {}'.format(found_brand, desc)[:30]
    clean = clean.strip()
    return clean[:24]

def scan_outfits(date_filter=None, rating_filter=None, limit=20):
    """Scan outfits directory, return list of outfit dicts"""
    results = []
    # Sort by modification time (newest first) not name, so newly generated
    # outfits always appear first in Hero and history lists.
    dirs = [d for d in os.listdir(OUTFITS_DIR)
            if os.path.isdir(os.path.join(OUTFITS_DIR, d))
            and not d.startswith('.') and not d.startswith('_')]
    dirs.sort(key=lambda d: os.path.getmtime(os.path.join(OUTFITS_DIR, d)), reverse=True)
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
                items.append({'id': cells[2], 'name': simplify_name(cells[2], full_name),
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
        # Find character image: 上身效果_1.png (AI原图) > 人物*.jpg > 排版图 > any
        char_img = ''
        for sub in ['上身效果','豆包生图']:
            sd = os.path.join(dp, sub)
            if not os.path.exists(sd): continue
            # First: 上身效果_1.png (raw AI gen, first stored)
            for f in sorted(os.listdir(sd)):
                if f == '上身效果_1.png':
                    char_img = os.path.join('..', 'outfits', d, sub, f)
                    break
            if char_img: break
            # Second: 人物_*.jpg
            for f in sorted(os.listdir(sd)):
                if '人物' in f and f.endswith(('.jpg','.png')) and not f.startswith('.'):
                    char_img = os.path.join('..', 'outfits', d, sub, f)
                    break
            if char_img: break
            # Third: *_方案*.jpg (composite)
            for f in sorted(os.listdir(sd)):
                if '方案' in f and f.endswith('.jpg') and not f.startswith('.'):
                    char_img = os.path.join('..', 'outfits', d, sub, f)
                    break
            if char_img: break
            # Last: any image
            for f in sorted(os.listdir(sd)):
                if f.endswith(('.jpg','.png')) and not f.startswith('.') and not f.startswith('_') and not f.startswith('.'):
                    char_img = os.path.join('..', 'outfits', d, sub, f)
                    break
            if char_img: break
        # Build item thumbnails
        items_dir = os.path.join(dp, 'items')
        for it in items:
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
        results.append({'dir': d, 'date': date_str, 'style': style or scene[:30], 'items': items, 'rating': rating, 'char_img': char_img, 'weather': weather, 'temp': temp_str, 'uv': uv_str})
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
    'camera_icon': lu('camera'),        # segmented tab icon
    'upload_icon': lu('upload'),        # segmented tab icon
    'camera_lg_icon': lu('camera'),     # large camera icon
    'image_icon': lu('image'),          # album/image icon
    'file_icon': lu('folder-open'),     # file picker icon
    'construction_icon': lu('construction'),  # under construction
}

# ── Build HTML ──
def tab_btn(key, label, active=False):
    cls = 'tab active' if active else 'tab'
    svg = tab.get(key, '')
    return '<div class="{}" data-page="{}"><div class="t-icon">{}</div><span class="t-label">{}</span></div>'.format(cls, key, svg, label)

def item_row(icon_svg, cat, iid, name, thumb=''):
    thumb_html = ''
    if thumb:
        thumb_html = '<img class="item-thumb" src="{}" onclick="event.stopPropagation();showImg(this.src)" loading="lazy">'.format(thumb)
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

def build_hero_item_card(icon_svg, iid, name, cat='', thumb=''):
    """Build a compact hero item card (brand + desc on two lines)"""
    brand, desc = split_brand_desc(name)
    thumb_html = ''
    if thumb:
        thumb_html = '<img class="item-thumb" src="{}" onclick="event.stopPropagation();showImg(this.src)" loading="lazy">'.format(thumb)
    ico = '<span class="item-emoji">{}</span>'.format(icon_svg) if icon_svg else ''
    bid = '<span class="ir-id">{}</span>'.format(iid)
    brand_html = '<span class="ir-brand">{}</span>'.format(brand) if brand else ''
    desc_html = '<span class="ir-desc">{}</span>'.format(desc if desc else name[:18])
    return '<div class="hero-item">{}{}{}{}{}</div>'.format(ico, bid, brand_html, desc_html, thumb_html)

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
.palette-strip{{display:flex;align-items:center;gap:4px;padding-top:10px;border-top:1px solid var(--border)}}
.pal-label{{font-size:9px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-right:6px}}
.pal-dot{{width:16px;height:16px;border-radius:4px;border:1px solid var(--border);display:inline-block}}

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
.tab-bar{{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(30,58,95,.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:18px;padding:6px 8px;display:flex;gap:2px;z-index:100;box-shadow:0 8px 32px rgba(30,58,95,.25);max-width:440px;width:calc(100% - 32px)}}
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
.h-exp-palette{{display:flex;align-items:center;gap:4px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}}
.h-exp-palette .pal-dot{{width:16px;height:16px;border-radius:3px;border:1px solid var(--border)}}
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
.wrd-cat-scroll{{display:flex;gap:10px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-bottom:8px;scrollbar-width:none}}
.wrd-cat-scroll::-webkit-scrollbar{{display:none}}
/* Horizontal item card */
.wrd-item-card-h{{flex:0 0 auto;width:100px;scroll-snap-align:start;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:transform .15s}}
.wrd-item-card-h:active{{transform:scale(.96)}}
.wrd-item-card-img-wrap{{position:relative;width:100px;height:120px;background:#f0f4f8;border-radius:var(--radius-sm);overflow:hidden}}
.wrd-item-card-img{{width:100%;height:100%;object-fit:cover;display:block}}
.wrd-item-card-id{{position:absolute;bottom:4px;left:4px;font-size:8px;font-family:monospace;color:#fff;background:rgba(0,0,0,.55);padding:2px 5px;border-radius:4px;letter-spacing:.3px;line-height:1}}
/* Item detail modal — bottom sheet */
.item-modal-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(26,40,56,.6);z-index:180;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);justify-content:center;align-items:flex-end}}
.item-modal-overlay.show{{display:flex}}
.item-modal{{background:var(--white);border-radius:var(--radius) var(--radius) 0 0;width:100%;max-width:500px;max-height:92vh;display:flex;flex-direction:column;animation:slideUp .3s ease}}
@keyframes slideUp{{from{{transform:translateY(100%)}}to{{transform:translateY(0)}}}}
.item-modal-close{{position:absolute;top:12px;right:16px;font-size:26px;color:var(--muted);cursor:pointer;z-index:5;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:rgba(255,255,255,.85)}}
.item-modal-scroll{{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 0 20px}}
/* Hero image + rotate */
.im-hero{{position:relative;width:100%;background:#f0f4f8;min-height:200px;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.im-hero-img{{width:100%;display:block;max-height:50vh;object-fit:contain;transition:transform .3s ease}}
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
.es-cat{{font-size:10px;color:var(--navy);background:#f0f4ff;padding:3px 8px;border-radius:6px;font-weight:500}}
.es-arrow{{font-size:14px;color:var(--muted)}}
.es-fusion{{text-align:center;font-size:16px;font-weight:700;color:var(--navy);padding:14px;background:linear-gradient(135deg,#f0f4ff,#faf5ff);border-radius:var(--radius-sm);margin-bottom:14px;border:1px solid #e0e4f8}}
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
<div class="hero-card">
<div class="hero-img"><img src="{hero_img}" alt=""></div>
<div class="hero-body">
<div class="style-tags">{hero_tags_html}</div>
<div class="hero-style">{hero_style}</div>
<div class="hero-meta">{hero_meta}</div>
<div class="item-list">{hero_items_html}</div>
{palette_html}
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
<div class="segmented" id="wrd-seg"><div class="seg-btn active" data-sub="my">我的衣橱</div><div class="seg-btn" data-sub="monthly">月度报告</div><div class="seg-btn" data-sub="cold">冷门单品</div><div class="seg-btn" data-sub="gaps">购买建议</div></div>
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
<div id="wrd-monthly-content"><div class="wrd-loading">加载中...</div></div>
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
<div class="placeholder" style="padding:100px 20px">
<div class="ph-icon">{construction_icon}</div>
<div class="ph-text">施工中<br>敬请期待</div>
</div>
</div>
</div>

</div>

<!-- Tab Bar -->
<div class="lightbox" id="lightbox" onclick="this.classList.remove('show')"><span class="close">&times;</span><img id="lightbox-img" src=""></div>

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
function showImg(src){{document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').classList.add('show')}}
function showItemImg(el){{var t=el.dataset.thumb;if(t)showImg(t)}}
var currentPage='recommend';
document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{var p=this.dataset.page;if(p===currentPage)return;currentPage=p;document.querySelectorAll('#tab-bar .tab').forEach(function(t){{t.classList.remove('active')}});this.classList.add('active');document.querySelectorAll('.page').forEach(function(pg){{pg.classList.remove('active')}});document.getElementById('page-'+p).classList.add('active')}})}});
document.querySelectorAll('.segmented').forEach(function(seg){{seg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;seg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;if(!sub)return;var parent=seg.parentElement;parent.querySelectorAll('.subpage').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='flex'}})}});
function filterHistory(){{var q=document.getElementById('history-search').value.toLowerCase();document.querySelectorAll('#today-list .fav-card, #fav-list .fav-card').forEach(function(c){{var t=c.textContent.toLowerCase();c.classList.toggle('filtered',q&&!t.includes(q))}})}}
var __activePollId=null;
function escHtml(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}}
function showProgress(){{var o=document.getElementById('progress-overlay');o.classList.add('show');document.getElementById('progress-title').textContent='正在分析...';document.getElementById('progress-steps').innerHTML='';document.getElementById('progress-spinner').style.display='block';document.getElementById('progress-close').style.display='none'}}
function dismissProgress(){{location.href=location.href.split('#')[0]+'?t='+Date.now()}}
function sendOutfit(){{var inp=document.getElementById('today-input');var msg=inp.value.trim()||'推荐穿搭';inp.value='';inp.placeholder='描述穿搭需求...';showProgress();fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg}})}}).then(r=>r.json()).then(d=>{{if(d.result){{document.getElementById('progress-title').textContent=d.result;document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block';if(d.image_url){{document.getElementById('progress-steps').innerHTML='<img class=\"progress-result-img\" src=\"'+d.image_url+'\" loading=\"lazy\">'}}}}else if(d.task_id){{__activePollId=d.task_id;pollTask(d.task_id)}}else{{document.getElementById('progress-title').textContent='已发送';setTimeout(dismissProgress,2000)}}}}).catch(function(e){{document.getElementById('progress-title').textContent='网络错误: '+e.message;document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block'}})}}
function pollTask(tid){{fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){{if(tid!==__activePollId)return;var title=document.getElementById('progress-title');var steps=document.getElementById('progress-steps');var spinner=document.getElementById('progress-spinner');var closeBtn=document.getElementById('progress-close');if(d.status==='done'){{spinner.style.display='none';closeBtn.style.display='inline-block';title.textContent='✅ 穿搭完成';var log=d.log||'';var lines=log.split('\\n').filter(function(l){{return l.trim()}});steps.innerHTML=lines.map(function(l,i){{var cls=i<lines.length-1?'step-done':'step-done';return'<div class=\"'+cls+'\"><span class=\"progress-dot done\"></span>'+escHtml(l)+'</div>'}}).join('');if(d.image_url){{steps.innerHTML+='<img class=\"progress-result-img\" src=\"'+d.image_url+'\" onerror=\"this.style.display=\\'none\\'\" loading=\"lazy\">'}}if(d.result){{steps.innerHTML+='<div style=\"margin-top:10px;font-size:13px;color:var(--text);white-space:pre-wrap\">'+escHtml(d.result)+'</div>'}}}}else if(d.status==='error'){{spinner.style.display='none';closeBtn.style.display='inline-block';title.textContent='❌ 生成失败';steps.innerHTML='<div style=\"color:#c4523c\">'+escHtml(d.message||'未知错误')+'</div>'}}else{{title.textContent=d.message||'生成中...';var log=d.log||'';if(log){{var lines=log.split('\\n').filter(function(l){{return l.trim()}});steps.innerHTML=lines.map(function(l,i){{var isLast=i===lines.length-1;var cls=isLast?'step-active':'step-done';var dot=isLast?'active':'done';return'<div class=\"'+cls+'\"><span class=\"progress-dot '+dot+'\"></span>'+escHtml(l)+'</div>'}}).join('')}}setTimeout(function(){{pollTask(tid)}},2000)}}}}).catch(function(){{setTimeout(function(){{pollTask(tid)}},2000)}})}}
function refreshAlts(){{var alts=[['日系 City Boy',['TS-011 落肩T恤','SHIRT-001 条纹衬衫','SHOE-009 AF1']],['轻熟休闲',['SHIRT-003 牛津衬衫','PT-005 西裤','SHOE-009 板鞋']],['韩系简约',['TS-010 条纹T恤','PT-006 直筒牛仔裤','SHOE-005']],['Clean Fit',['TS-009 短袖','PT-002 牛仔裤','SHOE-006']],['街头潮流',['TS-006 黑T','JK-003 棒球服','SHOE-008']],['运动休闲',['TANK-001 背心','SH-001 速干短裤','SHOE-003']]];var pool=alts.sort(function(){{return Math.random()-0.5}}).slice(0,3);var h='';pool.forEach(function(a){{var items=a[1].map(function(i){{return'<div>'+i+'</div>'}}).join('');h+='<div class=\"rec-card\" onclick=\"this.classList.toggle(\\'open\\')\"><div class=\"rc-style-name\">'+a[0]+'</div><div class=\"rc-items\">'+items+'</div><div class=\"rc-arrow\">▾</div></div>'}});var el=document.getElementById('alt-cards');if(el)el.innerHTML=h}}
/* ═══ 衣橱页 ═══ */
var __wrdData=null,__wrdStats=null,__newItemIds=[],__wardrobeNeedsReload=false;
function loadWardrobe(){{fetch('/api/wardrobe').then(r=>r.json()).then(d=>{{__wrdStats=d;var elTotal=document.getElementById('wrd-total'),elUtil=document.getElementById('wrd-util'),elOver=document.getElementById('wrd-over');if(elTotal){{elTotal.textContent=d.metadata.total_items;elTotal.classList.remove('skeleton-text')}}if(elUtil){{var pct=Math.round((d.utilization||{{}}).utilization_rate*100)||0;elUtil.textContent=pct+'%';elUtil.classList.remove('skeleton-text');if(pct<30)elUtil.parentElement.classList.add('warn')}}if(elOver){{var over=Object.values(d.category_gaps||{{}}).filter(function(g){{return g.status==='overstock'}}).length;elOver.textContent=over;elOver.classList.remove('skeleton-text');if(over>2)elOver.parentElement.classList.add('warn')}}}}).catch(function(e){{console.error('Wardrobe stats error:',e)}});fetch('/api/wardrobe/items').then(r=>r.json()).then(d=>{{__wrdData=d.items;renderCatRows(d.items)}}).catch(function(e){{console.error('Wardrobe items error:',e)}});fetch('/api/wardrobe/new-items').then(r=>r.json()).then(function(d){{__newItemIds=(d.new_items||[]).map(function(it){{return it.id}});if(__wrdData)renderCatRows(__wrdData)}}).catch(function(){{}})}}
var COLOR_MAP={{'黑色':'#2a2a2a','白色':'#f5f3ef','米白':'#f5f0e8','乳白':'#faf8f5','深灰':'#4a4a4a','灰色':'#9e9e9e','浅灰':'#d0d0d0','银灰':'#bdbdbd','灰绿':'#8a9a82','卡其':'#c4b5a0','卡其色':'#c4b5a0','驼色':'#b8976e','深棕':'#5c3d2e','棕色':'#7a5230','浅棕':'#b8956a','深蓝':'#1e3a5f','藏蓝':'#1e3a6f','藏青':'#1e3a5f','海军蓝':'#1e3a5f','蓝色':'#4a7eb5','浅蓝':'#7ea3c8','天蓝':'#8bb8d6','军绿':'#5c6e4a','军绿色':'#5c6e4a','墨绿':'#3c5032','绿色':'#6b8c5c','浅绿':'#9cba8c','正红色':'#c4523c','红色':'#c4523c','暗红':'#8b2e3e','酒红':'#8b2e3e','橙色':'#e88a3c','亮橙':'#f0983c','橘色':'#e88030','黄色':'#d4a84b','姜黄':'#c49a3c','米黄':'#e8d8b0','紫色':'#8b6b9e','浅紫':'#b89ac8','粉色':'#e8b4b8','浅粉':'#f0c8cc','米色':'#e8dcc8','沙色':'#d8ccb0','深牛仔蓝':'#2a4a6c','牛仔蓝':'#4a6a8c','浅牛仔蓝':'#7a9ab8','牛油果绿':'#7a9a5c','条纹':'#c0c0c0','印花':'#c0c0c0'}};function colorHex(name){{var c=COLOR_MAP[name];if(c)return c;for(var k in COLOR_MAP){{if(k.indexOf(name)!=-1||name.indexOf(k)!=-1)return COLOR_MAP[k]}}return'#bdbdbd'}}
	var CAT_ORDER=['TS','LS','SHIRT','TANK','JK','PT','SH','SHOE','BAG','HAT','SOCK','SUN','ACC'];
var CAT_ICONS={{'TS':'👕','LS':'👔','SHIRT':'👔','TANK':'🎽','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','BAG':'🎒','HAT':'🧢','SOCK':'🧦','SUN':'🕶️','ACC':'⌚'}};
function renderCatRows(items){{var cats={{}};var archived=[];items.forEach(function(it){{if(it._archived){{archived.push(it);return}}var c=it.category_code;if(!cats[c])cats[c]=[];cats[c].push(it)}});var html='';CAT_ORDER.forEach(function(code){{var list=cats[code]||[];if(!list.length)return;var icon=CAT_ICONS[code]||'📦';var name=list[0].category;html+='<div class=\"wrd-cat-row\"><div class=\"wrd-cat-header\"><span class=\"wrd-cat-header-icon\">'+icon+'</span><span class=\"wrd-cat-header-name\">'+escHtml(name)+'</span><span class=\"wrd-cat-header-count\">'+list.length+'件</span></div><div class=\"wrd-cat-scroll\">'+list.map(function(it){{return renderItemCardH(it)}}).join('')+'</div></div>'}});if(archived.length){{html+='<div class=\"wrd-cat-row\" style=\"opacity:.7\"><div class=\"wrd-cat-header\"><span class=\"wrd-cat-header-icon\">🗄️</span><span class=\"wrd-cat-header-name\">旧衣库</span><span class=\"wrd-cat-header-count\">'+archived.length+'件</span></div><div class=\"wrd-cat-scroll\">'+archived.map(function(it){{return renderItemCardH(it)}}).join('')+'</div></div>'}}document.getElementById('wrd-rows').innerHTML=html||'<div class=\"wrd-empty\">暂无数据</div>'}}
function renderItemCardH(it){{var inner='';if(it.thumb){{inner='<img class=\"wrd-item-card-img\" src=\"../'+escHtml(it.thumb)+'\" loading=\"lazy\" onerror=\"this.style.display=\\'none\\';this.parentElement.innerHTML=\\'<span style=font-size:11px;color:var(--muted)>'+escHtml(it.id)+'</span>\\'\">'}}else{{inner='<span style=\"font-size:11px;color:var(--muted)\">'+escHtml(it.id)+'</span>'}}var badgeHtml='';if(__newItemIds&&__newItemIds.indexOf(it.id)!==-1){{badgeHtml='<span class=\"new-badge\">NEW</span>'}}return'<div class=\"wrd-item-card-h\" onclick=\"openItemModal(\\''+escHtml(it.id)+'\\')\" style=\"position:relative\"><div class=\"wrd-item-card-img-wrap\">'+inner+'<span class=\"wrd-item-card-id\">'+escHtml(it.id)+'</span></div>'+badgeHtml+'</div>'}}
function filterWardrobe(){{var q=document.getElementById('wrd-search').value.toLowerCase();document.querySelectorAll('.wrd-cat-row').forEach(function(row){{var cards=row.querySelectorAll('.wrd-item-card-h');var anyVisible=false;cards.forEach(function(c){{var t=(c.querySelector('.wrd-item-card-id')||{{}}).textContent||'';var visible=!q||t.toLowerCase().includes(q);c.style.display=visible?'':'none';if(visible)anyVisible=true}});row.style.display=anyVisible?'':'none'}})}}
var __currentItemId=null,__currentItemData=null,__imgRotation=0,__editingTagIdx=-1,__editingTagGroup='';
function openItemModal(itemId){{__currentItemId=itemId;__imgRotation=0;__editingTagIdx=-1;var overlay=document.getElementById('item-modal');var scroll=document.getElementById('item-modal-scroll');overlay.classList.add('show');scroll.innerHTML='<div class=\"wrd-loading\">加载中...</div>';if(__newItemIds&&__newItemIds.indexOf(itemId)!==-1){{fetch('/api/wardrobe/new-items/dismiss',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{clothing_id:itemId}})}}).then(function(){{__newItemIds=__newItemIds.filter(function(id){{return id!==itemId}});if(__wrdData)renderCatRows(__wrdData)}})}}fetch('/api/wardrobe/item/'+encodeURIComponent(itemId)).then(function(r){{return r.json()}}).then(function(data){{if(data.error){{scroll.innerHTML='<div class=\"wrd-empty\">加载失败</div>';return}}__currentItemData=data;if(!data.recommended_styles||!data.recommended_styles.length){{data.recommended_styles=matchStyles(data)}}renderItemCard(data)}}).catch(function(){{scroll.innerHTML='<div class=\"wrd-empty\">网络错误</div>'}})}}
function closeItemModal(){{document.getElementById('item-modal').classList.remove('show');__currentItemId=null;__currentItemData=null}}
function rotateImg(dir){{__imgRotation+=dir*90;var img=document.getElementById('im-hero-img');if(img)img.style.transform='rotate('+__imgRotation+'deg)'}}
function matchStyles(data){{var styles=[];var allTags=[];if(data.brand&&data.brand.name)allTags.push(data.brand.name);var c=data.color||{{}};if(c.hue_family)allTags.push(c.hue_family);if(c.hue_name)allTags.push(c.hue_name);var f=data.fabric||{{}};if(f.primary)allTags.push(f.primary);if(f.texture)allTags.push(f.texture);var s=data.silhouette||{{}};if(s.fit)allTags.push(s.fit);var p=data.pattern||{{}};if(p.type)allTags.push(p.type);var sm=data.style_modifiers||[];allTags=allTags.concat(sm);var occ=data.occasions||[];allTags=allTags.concat(occ);var str=allTags.join(' ').toLowerCase();var rules=[{{k:'日系简约',m:['uniqlo','日系','简约','基本','基础百搭']}},{{k:'韩系潮流',m:['韩','韩流','街头','潮流','oversize']}},{{k:'City Boy',m:['宽松','落肩','city','boy','日系']}},{{k:'Clean Fit',m:['合身','clean','简约','基本','纯色']}},{{k:'街头潮流',m:['街头','潮流','logo','印花','oversize','棒球']}},{{k:'轻熟商务',m:['商务','通勤','正式','衬衫','西裤','牛津','polo']}},{{k:'运动休闲',m:['运动','速干','nike','adidas','跑步','健身','网球']}},{{k:'复古工装',m:['工装','复古','军绿','卡其','帆布','牛仔']}},{{k:'意式运动',m:['意式','fila','italia','运动','复古']}},{{k:'高街暗黑',m:['黑色','暗黑','高街','cdg','comme']}},{{k:'户外机能',m:['户外','机能','冲锋','防风','防水','登山','徒步']}},{{k:'夏日度假',m:['度假','海滩','亚麻','短裤','凉鞋','夏日']}},{{k:'极简主义',m:['极简','纯色','基本','无logo','单色']}}];rules.forEach(function(r){{var hit=r.m.some(function(kw){{return str.indexOf(kw)!=-1}});if(hit&&styles.indexOf(r.k)==-1)styles.push(r.k)}});if(!styles.length)styles.push('基础百搭');return styles.slice(0,5)}}
function getTagGroups(data){{var g=[];var rs=data.recommended_styles||matchStyles(data);g.push({{id:'recommended_styles',title:'🤖 AI 适合风格',tags:rs.slice(),readonly:true,highlight:true}});var b=data.brand||{{}};if(b.name)g.push({{id:'brand',title:'品牌',tags:b.name?[b.name+(b.collection?' · '+b.collection:'')]:[]}});var c=data.color||{{}};var colorTags=[];if(c.hue_family)colorTags.push(c.hue_family);if(c.hue_name)colorTags.push(c.hue_name);if(c.saturation)colorTags.push(c.saturation);if(c.lightness)colorTags.push(c.lightness);if(c.is_neutral)colorTags.push('中性色');if(c.friendly_for_pale_skin)colorTags.push('显白');if(colorTags.length)g.push({{id:'color',title:'色彩',tags:colorTags}});var f=data.fabric||{{}};var fabTags=[];if(f.primary)fabTags.push(f.primary);if(f.texture)fabTags.push(f.texture);if(f.weight)fabTags.push(f.weight);if(fabTags.length)g.push({{id:'fabric',title:'面料',tags:fabTags}});var s=data.silhouette||{{}};var silTags=[];if(s.fit)silTags.push(s.fit);if(s.shoulder_effect&&s.shoulder_effect!='无特殊效果')silTags.push(s.shoulder_effect);if(s.torso_effect&&s.torso_effect!='无特殊效果')silTags.push(s.torso_effect);if(silTags.length)g.push({{id:'silhouette',title:'版型',tags:silTags}});var p=data.pattern||{{}};var patTags=[];if(p.type&&p.type!='纯色')patTags.push(p.type);if(p.density&&p.density!='无')patTags.push(p.density);if(p.logo_visible)patTags.push('Logo');if(patTags.length)g.push({{id:'pattern',title:'图案',tags:patTags}});var season=(f.seasonality||[]).slice();if(season.length)g.push({{id:'season',title:'季节',tags:season}});var occ=data.occasions||[];g.push({{id:'occasions',title:'场景',tags:occ.slice()}});var sm=(data.style_modifiers||[]).slice();g.push({{id:'style_modifiers',title:'风格修饰',tags:sm}});return g}}
function renderItemCard(data,forceRefresh){{var isArchived=data.meta&&data.meta.archived;var boost=(data.meta&&data.meta.boost_score)||0;var thumbPath=data._thumb?data._thumb.split('?')[0]:'';var imgSrc=thumbPath?'../'+escHtml(thumbPath)+(forceRefresh?'?v='+Date.now():''):'';var groups=getTagGroups(data);var groupsHtml=groups.map(function(grp){{var wrapCls=grp.highlight?'im-tag-group im-tag-group-hl':'im-tag-group';var chips=grp.tags.map(function(t,i){{var cls=grp.readonly?'im-tag im-tag-ro':'im-tag';var del=grp.readonly?'':'<span class=\"im-tag-del\" onclick=\"event.stopPropagation();removeChip(\\''+grp.id+'\\','+i+')\">×</span>';return'<span class=\"'+cls+'\" onclick=\"'+(grp.readonly?'':'editChip(\\''+grp.id+'\\','+i+')')+'\">'+escHtml(t)+del+'</span>'}}).join('');if(!grp.readonly)chips+='<span class=\"im-tag im-tag-add\" onclick=\"addChip(\\''+grp.id+'\\')\">+</span>';return'<div class=\"'+wrapCls+'\"><div class=\"im-tag-group-title\">'+escHtml(grp.title)+'</div><div class=\"im-tags\">'+chips+'</div></div>'}}).join('');var archiveLabel=isArchived?'↩️ 移回衣橱':'🗑️ 移入旧衣库';var archiveBtnClass=isArchived?'im-btn-restore':'im-btn-archive';var archiveFn=isArchived?'restoreItem()':'archiveItem()';var deleteBtn=isArchived?'<button class=\"im-btn-archive\" onclick=\"deleteItem()\" style=\"color:#c62828;border-color:#fce4ec!important\">🗑️ 彻底扔掉</button>':'';var boostLabel=boost>0?'⭐ 已推荐('+boost+')':'⭐ 多推荐';var actionsHtml=isArchived?'<div class=\"im-actions\"><button class=\"'+archiveBtnClass+'\" onclick=\"'+archiveFn+'\">'+archiveLabel+'</button>'+deleteBtn+'</div>':'<div class=\"im-actions\"><button class=\"im-btn-save-tags\" onclick=\"saveAllChanges()\">💾 保存修改</button><button class=\"im-btn-boost\" onclick=\"boostItem()\">'+boostLabel+'</button><button class=\"'+archiveBtnClass+'\" onclick=\"'+archiveFn+'\">'+archiveLabel+'</button></div>';var scroll=document.getElementById('item-modal-scroll');scroll.innerHTML='<div class=\"im-hero\"><img class=\"im-hero-img\" id=\"im-hero-img\" src=\"'+imgSrc+'\" onerror=\"this.style.display=\\'none\\'\" style=\"transform:rotate('+__imgRotation+'deg)\"><span class=\"im-hero-id\">'+escHtml(data.clothing_id)+'</span><button class=\"im-rotate-btn im-rotate-left\" onclick=\"rotateImg(-1)\">↺</button><button class=\"im-rotate-btn im-rotate-right\" onclick=\"rotateImg(1)\">↻</button></div><div class=\"im-info\"><div class=\"im-info-name\">'+escHtml(data.meta&&data.meta.claude_fit_comment||data.category)+'</div><div class=\"im-info-brand\">'+escHtml(data.clothing_id)+' · '+escHtml(data.category)+' · 穿着'+escHtml(String(data.meta&&data.meta.wear_count||0))+'次</div></div>'+groupsHtml+'<div id=\"im-chip-editor\" style=\"display:none\"></div><div class=\"im-actions\">'+actionsHtml+'</div>'}}
function editChip(groupId,idx){{var data=__currentItemData;if(!data)return;var grp=getTagGroups(data).find(function(g){{return g.id===groupId}});if(!grp||idx<0||idx>=grp.tags.length)return;__editingTagGroup=groupId;__editingTagIdx=idx;var el=document.getElementById('im-chip-editor');el.style.display='block';el.innerHTML='<div class=\"im-tag-detail\"><input id=\"im-chip-input\" value=\"'+escHtml(grp.tags[idx])+'\"><div class=\"im-tag-detail-btns\"><button class=\"im-btn-save\" onclick=\"saveChipEdit()\">确认</button><button class=\"im-btn-cancel\" onclick=\"cancelChipEdit()\">取消</button></div></div>';var inp=document.getElementById('im-chip-input');inp.focus();inp.select()}}
function saveChipEdit(){{var val=document.getElementById('im-chip-input').value.trim();if(!val||__editingTagIdx<0||!__editingTagGroup)return cancelChipEdit();var data=__currentItemData;var gid=__editingTagGroup;if(gid==='brand'){{if(!data.brand)data.brand={{}};data.brand.name=val}}else if(gid==='color'){{var colorTags=getTagGroups(data).find(function(g){{return g.id==='color'}});if(colorTags&&__editingTagIdx<colorTags.tags.length){{var oldVal=colorTags.tags[__editingTagIdx];var c=data.color||{{}};if(oldVal===c.hue_family)c.hue_family=val;else if(oldVal===c.hue_name)c.hue_name=val;else if(oldVal===c.saturation)c.saturation=val;else if(oldVal===c.lightness)c.lightness=val}}}}else if(gid==='fabric'){{var fabTags=getTagGroups(data).find(function(g){{return g.id==='fabric'}});if(fabTags&&__editingTagIdx<fabTags.tags.length){{var oldVal=fabTags.tags[__editingTagIdx];var f=data.fabric||{{}};if(oldVal===f.primary)f.primary=val;else if(oldVal===f.texture)f.texture=val;else if(oldVal===f.weight)f.weight=val}}}}else if(gid==='silhouette'){{var silTags=getTagGroups(data).find(function(g){{return g.id==='silhouette'}});if(silTags&&__editingTagIdx<silTags.tags.length){{var oldVal=silTags.tags[__editingTagIdx];var s=data.silhouette||{{}};if(oldVal===s.fit)s.fit=val;else if(oldVal===s.shoulder_effect)s.shoulder_effect=val;else if(oldVal===s.torso_effect)s.torso_effect=val}}}}else if(gid==='pattern'){{var patTags=getTagGroups(data).find(function(g){{return g.id==='pattern'}});if(patTags&&__editingTagIdx<patTags.tags.length){{var oldVal=patTags.tags[__editingTagIdx];var p=data.pattern||{{}};if(oldVal===p.type)p.type=val;else if(oldVal===p.density)p.density=val}}}}else if(gid==='season'){{if(!data.fabric)data.fabric={{}};if(!data.fabric.seasonality)data.fabric.seasonality=[];data.fabric.seasonality[__editingTagIdx]=val}}else if(gid==='occasions'){{if(!data.occasions)data.occasions=[];data.occasions[__editingTagIdx]=val}}else if(gid==='style_modifiers'){{if(!data.style_modifiers)data.style_modifiers=[];data.style_modifiers[__editingTagIdx]=val}}cancelChipEdit();renderItemCard(data)}}
function cancelChipEdit(){{__editingTagIdx=-1;__editingTagGroup='';document.getElementById('im-chip-editor').style.display='none'}}
function addChip(groupId){{var data=__currentItemData;if(!data)return;var grp=getTagGroups(data).find(function(g){{return g.id===groupId}});if(!grp||grp.readonly)return;var newVal='新标签';if(groupId==='brand'){{if(!data.brand)data.brand={{}};data.brand.name=data.brand.name||newVal}}else if(groupId==='color'){{if(!data.color)data.color={{}};data.color.hue_name=data.color.hue_name||newVal}}else if(groupId==='fabric'){{if(!data.fabric)data.fabric={{}};data.fabric.primary=data.fabric.primary||newVal}}else if(groupId==='silhouette'){{if(!data.silhouette)data.silhouette={{}};data.silhouette.fit=data.silhouette.fit||newVal}}else if(groupId==='pattern'){{if(!data.pattern)data.pattern={{}};data.pattern.type=data.pattern.type||newVal}}else if(groupId==='season'){{if(!data.fabric)data.fabric={{}};if(!data.fabric.seasonality)data.fabric.seasonality=[];data.fabric.seasonality.push(newVal)}}else if(groupId==='occasions'){{if(!data.occasions)data.occasions=[];data.occasions.push(newVal)}}else if(groupId==='style_modifiers'){{if(!data.style_modifiers)data.style_modifiers=[];data.style_modifiers.push(newVal)}}renderItemCard(data);__editingTagGroup=groupId;__editingTagIdx=grp.tags.length;var el=document.getElementById('im-chip-editor');el.style.display='block';el.innerHTML='<div class=\"im-tag-detail\"><input id=\"im-chip-input\" value=\"'+escHtml(newVal)+'\"><div class=\"im-tag-detail-btns\"><button class=\"im-btn-save\" onclick=\"saveChipEdit()\">确认</button><button class=\"im-btn-cancel\" onclick=\"cancelChipEdit()\">取消</button></div></div>';var inp=document.getElementById('im-chip-input');inp.focus();inp.select()}}
function removeChip(groupId,idx){{var data=__currentItemData;if(!data)return;if(groupId==='brand'){{if(data.brand)data.brand.name=''}}else if(groupId==='season'){{if(data.fabric&&data.fabric.seasonality)data.fabric.seasonality.splice(idx,1)}}else if(groupId==='occasions'){{if(data.occasions)data.occasions.splice(idx,1)}}else if(groupId==='style_modifiers'){{if(data.style_modifiers)data.style_modifiers.splice(idx,1)}}renderItemCard(data)}}
function showToast(msg,color){{var t=document.createElement('div');t.textContent=msg;t.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:'+(color||'#1e3a5f')+';color:#fff;padding:14px 28px;border-radius:12px;font-size:15px;font-weight:600;z-index:300;box-shadow:0 8px 32px rgba(0,0,0,.25);animation:fadeInUp .3s ease';document.body.appendChild(t);setTimeout(function(){{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(function(){{t.remove()}},300)}},1800)}}
function saveAllChanges(){{if(!__currentItemId||!__currentItemData)return;var data=__currentItemData;var btn=document.querySelector('.im-btn-save-tags');if(btn){{btn.textContent='保存中...';btn.disabled=true}}var hasRotation=__imgRotation%360!==0;var doSave=function(){{var newStyles=matchStyles(data);data.recommended_styles=newStyles;var updates={{}};if(data.brand)updates.brand=data.brand;if(data.color)updates.color=data.color;if(data.fabric)updates.fabric=data.fabric;if(data.silhouette)updates.silhouette=data.silhouette;if(data.pattern)updates.pattern=data.pattern;if(data.occasions!==undefined)updates.occasions=data.occasions;if(data.style_modifiers!==undefined)updates.style_modifiers=data.style_modifiers;updates.recommended_styles=newStyles;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(updates)}}).then(function(r){{return r.json()}}).then(function(d){{if(btn)btn.disabled=false;if(d.ok){{showToast('✅ 保存成功','#2e7d32');var hadRotation=hasRotation;__imgRotation=0;renderItemCard(data,!!hadRotation);if(hadRotation){{fetch('/api/wardrobe/items').then(function(r){{return r.json()}}).then(function(d2){{__wrdData=d2.items;renderCatRows(d2.items)}})}}setTimeout(function(){{var b=document.querySelector('.im-btn-save-tags');if(b)b.textContent='💾 保存修改'}},800)}}else{{showToast('❌ 保存失败','#c4523c');if(btn)btn.textContent='💾 保存修改'}}}}).catch(function(){{if(btn){{btn.disabled=false;btn.textContent='💾 保存修改'}}showToast('❌ 网络错误','#c4523c')}})}};if(hasRotation){{fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId)+'/transform',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{rotate:__imgRotation,scale:1.0,translate_x:0,translate_y:0}})}}).then(function(r){{return r.json()}}).then(function(){{doSave()}}).catch(function(){{doSave()}})}}else{{doSave()}}}}
function boostItem(){{if(!__currentItemId||!__currentItemData)return;var cur=(__currentItemData.meta&&__currentItemData.meta.boost_score)||0;var newBoost=cur+1;if(!__currentItemData.meta)__currentItemData.meta={{}};__currentItemData.meta.boost_score=newBoost;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{boost_score:newBoost}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok)renderItemCard(__currentItemData)}})}}
function archiveItem(){{if(!__currentItemId||!confirm('确定移入旧衣库吗？'))return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{archived:true}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{closeItemModal();loadWardrobe()}}}})}}
function restoreItem(){{if(!__currentItemId)return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{meta:{{archived:false}}}})}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{closeItemModal();loadWardrobe()}}}})}}
function deleteItem(){{if(!__currentItemId||!confirm('确定彻底删除 '+__currentItemId+' 吗？\\n\\n将删除标签、图片等所有数据，不可恢复！'))return;fetch('/api/wardrobe/item/'+encodeURIComponent(__currentItemId)+'/delete',{{method:'POST'}}).then(function(r){{return r.json()}}).then(function(d){{if(d.ok){{showToast('已删除 '+d.deleted+' 个文件','#c4523c');closeItemModal();loadWardrobe()}}else{{showToast('删除失败: '+(d.error||'未知'),'#c4523c')}}}}).catch(function(){{showToast('网络错误','#c4523c')}})}}
function loadMonthlyReport(){{var el=document.getElementById('wrd-monthly-content');el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';fetch('/api/wardrobe/stats').then(r=>r.json()).then(d=>{{var html='<div class=\"wrd-monthly\"><div class=\"wm-card\"><div class=\"wm-title\">📈 核心数据</div><div class=\"wm-stat-row\"><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.total_outfits+'</div><div class=\"wm-stat-lbl\">累计穿搭</div></div><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.active_days+'</div><div class=\"wm-stat-lbl\">活跃天数</div></div><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.avg_rating+'</div><div class=\"wm-stat-lbl\">平均评分</div></div></div><div class=\"wm-stat-row\"><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+Math.round(d.utilization_rate*100)+'%</div><div class=\"wm-stat-lbl\">利用率</div></div><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.items_worn+'/'+d.items_total+'</div><div class=\"wm-stat-lbl\">已穿/总数</div></div><div class=\"wm-stat-item\"><div class=\"wm-stat-val\">'+d.rated_count+'</div><div class=\"wm-stat-lbl\">有评分</div></div></div></div>';if(d.top_styles&&d.top_styles.length){{html+='<div class=\"wm-card\"><div class=\"wm-title\">🎯 最爱风格</div>';var maxS=d.top_styles[0].count;d.top_styles.forEach(function(s){{var pct=Math.round(s.count/maxS*100);html+='<div class=\"wm-bar-row\"><span class=\"wm-bar-label\">'+escHtml(s.name)+'</span><div class=\"wm-bar-track\"><div class=\"wm-bar-fill\" style=\"width:'+pct+'%\"></div></div><span class=\"wm-bar-num\">'+s.count+'</span></div>'}});html+='</div>'}}if(d.top_items&&d.top_items.length){{html+='<div class=\"wm-card\"><div class=\"wm-title\">👟 最爱单品</div>';var maxI=d.top_items[0].count;d.top_items.forEach(function(s){{var pct=Math.round(s.count/maxI*100);html+='<div class=\"wm-bar-row\"><span class=\"wm-bar-label\">'+escHtml(s.id)+'</span><div class=\"wm-bar-track\"><div class=\"wm-bar-fill\" style=\"width:'+pct+'%\"></div></div><span class=\"wm-bar-num\">'+s.count+'</span></div>'}});html+='</div>'}}html+='</div>';el.innerHTML=html}}).catch(function(e){{el.innerHTML='<div class=\"wrd-empty\">加载失败: '+escHtml(e.message)+'</div>'}})}}
function loadColdItems(){{var el=document.getElementById('wrd-cold-list');el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';fetch('/api/wardrobe/cold-items').then(r=>r.json()).then(d=>{{if(!d.cold_items||!d.cold_items.length){{el.innerHTML='<div class=\"wrd-empty\">🎉 所有单品都有穿着记录！</div>';return}}var html='';d.cold_items.forEach(function(it){{var badge=it.is_key?'<span class=\"cold-badge key\">关键</span>':'<span class=\"cold-badge\">闲置</span>';var thumb=it.thumb?'<img class=\"wrd-item-thumb\" src=\"../'+escHtml(it.thumb)+'\" loading=\"lazy\" onclick=\"event.stopPropagation();showImg(this.src)\">':'<div class=\"wrd-item-thumb\" style=\"background:'+colorHex(it.color)+';display:flex;align-items:center;justify-content:center;font-size:7px;color:#fff;text-shadow:0 1px 1px rgba(0,0,0,.3)\">'+escHtml(it.id)+'</div>';html+='<div class=\"wrd-cold-item\">'+thumb+'<div class=\"wrd-item-info\"><div class=\"wi-name\">'+escHtml(it.name)+'</div><div class=\"wi-meta\">'+escHtml(it.brand||'')+' · '+escHtml(it.id)+'</div><div class=\"wi-usage\">上次穿: '+escHtml(it.last_used||'从未')+'</div></div>'+badge+'</div>'}});el.innerHTML=html}}).catch(function(e){{el.innerHTML='<div class=\"wrd-empty\">加载失败: '+escHtml(e.message)+'</div>'}})}}
function loadGaps(){{var el=document.getElementById('wrd-gaps-content');el.innerHTML='<div class=\"wrd-loading\">加载中...</div>';fetch('/api/wardrobe/gaps').then(r=>r.json()).then(d=>{{var html='';if(d.suggestions&&d.suggestions.length){{d.suggestions.forEach(function(s){{html+='<div class=\"wrd-gap-card priority-'+s.priority+'\"><span class=\"gap-priority '+s.priority+'\">'+{{'high':'🔴 高优先','medium':'🟡 中优先','low':'🟢 低优先'}}[s.priority]+'</span><div class=\"gap-item\">'+escHtml(s.item)+'</div><div class=\"gap-reason\">💡 '+escHtml(s.reason)+'</div></div>'}})}}if(d.category_gaps){{var gapCats=Object.entries(d.category_gaps).filter(function(e){{return e[1].status!=='healthy'}});if(gapCats.length){{html+='<div class=\"wm-card\" style=\"margin-top:12px\"><div class=\"wm-title\">📊 品类状态</div>';gapCats.forEach(function(e){{var g=e[1];var icon=g.status==='overstock'?'⚠️':'❌';html+='<div class=\"wm-bar-row\"><span class=\"wm-bar-label\">'+icon+' '+escHtml(g.name)+'</span><span class=\"wm-bar-num\" style=\"width:auto\">'+g.actual+'件 (理想'+g.ideal_lo+'-'+g.ideal_hi+')</span></div>'}});html+='</div>'}}}}el.innerHTML=html||'<div class=\"wrd-empty\">衣橱品类分布良好 👍</div>'}}).catch(function(e){{el.innerHTML='<div class=\"wrd-empty\">加载失败: '+escHtml(e.message)+'</div>'}})}}
/* 衣橱子页切换 */
(function(){{var wrdSeg=document.getElementById('wrd-seg');if(wrdSeg){{wrdSeg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;wrdSeg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;document.querySelectorAll('#page-wardrobe .wrd-sub').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='block';if(sub==='my'){{if(!__wrdData)loadWardrobe()}}else if(sub==='monthly'){{loadMonthlyReport()}}else if(sub==='cold'){{loadColdItems()}}else if(sub==='gaps'){{loadGaps()}}}})}};/* Auto-load wardrobe on first visit to wardrobe tab */var __wrdLoaded=false;var origTabHandler=document.querySelector('#tab-bar').onclick;document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{if(this.dataset.page==='wardrobe'&&!__wrdLoaded){{__wrdLoaded=true;setTimeout(loadWardrobe,100)}}}})}})}})();
/* ═══ 探索页 ═══ */
function renderStyleCards(styles,showDesc){{if(!styles||!styles.length)return'<div class="wrd-empty">暂无风格数据</div>';return styles.map(function(s){{var desc=showDesc&&s.description?'<div class="es-desc">'+escHtml(s.description)+'</div>':'';var cat=s.category?'<span class="es-cat">'+escHtml(s.category)+'</span>':'';var hasImg=!!s.image;var iconHtml=hasImg?'<img src="'+escHtml(s.image)+'" alt="'+escHtml(s.name_zh)+'" loading="lazy" onclick="event.stopPropagation();showImg(\\''+escHtml(s.image)+'\\')" style="cursor:pointer">':s.name_zh.charAt(0);var iconCls=hasImg?'es-icon has-img':'es-icon';return'<div class="exp-style-card" onclick="window.location=\\'/style/'+escHtml(s.id)+'\\'"><div class="es-header"><div class="'+iconCls+'">'+iconHtml+'</div><div class="es-info"><div class="es-name">'+escHtml(s.name_zh)+'</div><div class="es-en">'+escHtml(s.name_en||s.id)+'</div></div></div>'+desc+'<div class="es-footer">'+cat+'<span class="es-arrow">›</span></div></div>'}}).join('')}}
function loadExploreTweak(){{var el=document.getElementById('exp-tweak-content');el.innerHTML='<div class="wrd-loading">加载中...</div>';fetch('/api/explore/tweak').then(r=>r.json()).then(d=>{{el.innerHTML=renderStyleCards(d.styles,true)||'<div class="wrd-empty">先完成几套穿搭推荐吧</div>'}}).catch(function(e){{el.innerHTML='<div class="wrd-empty">加载失败</div>'}})}}
function loadExploreTransform(){{var el=document.getElementById('exp-transform-content');el.innerHTML='<div class="wrd-loading">加载中...</div>';fetch('/api/explore/transform').then(r=>r.json()).then(d=>{{el.innerHTML=renderStyleCards(d.styles,true)||'<div class="wrd-empty">已探索全部风格</div>'}}).catch(function(e){{el.innerHTML='<div class="wrd-empty">加载失败</div>'}})}}
function loadExploreCross(){{var el=document.getElementById('exp-cross-content');el.innerHTML='<div class="wrd-loading">加载中...</div>';fetch('/api/explore/cross').then(r=>r.json()).then(d=>{{var html='';if(d.fusion)html+='<div class="es-fusion">🎲 '+escHtml(d.fusion)+'</div>';html+=renderStyleCards(d.styles,true);el.innerHTML=html||'<div class="wrd-empty">暂无跨界建议</div>'}}).catch(function(e){{el.innerHTML='<div class="wrd-empty">加载失败</div>'}})}}
function loadExploreTrends(){{var el=document.getElementById('exp-trends-content');el.innerHTML='<div class="wrd-loading">加载中...</div>';fetch('/api/explore/trends').then(r=>r.json()).then(d=>{{el.innerHTML='<div class="section-header">📚 全部风格 ('+d.total+')</div>'+renderStyleCards(d.styles,false)}}).catch(function(e){{el.innerHTML='<div class="wrd-empty">加载失败</div>'}})}}
function tryExplore(){{var inp=document.getElementById('exp-input');var msg=inp.value.trim();if(!msg)return;showProgress();fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg}})}}).then(r=>r.json()).then(d=>{{if(d.task_id){{__activePollId=d.task_id;pollTask(d.task_id)}}else{{document.getElementById('progress-title').textContent=d.result||'已发送';document.getElementById('progress-spinner').style.display='none';document.getElementById('progress-close').style.display='inline-block'}}}})}}
/* 探索页子页切换 */
(function(){{var expSeg=document.getElementById('exp-seg');if(expSeg){{expSeg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;expSeg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;document.querySelectorAll('#page-explore .exp-sub').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='block';if(sub==='tweak'){{loadExploreTweak()}}else if(sub==='transform'){{loadExploreTransform()}}else if(sub==='cross'){{loadExploreCross()}}else if(sub==='trends'){{loadExploreTrends()}}}})}};var __expLoaded=false;document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{if(this.dataset.page==='explore'&&!__expLoaded){{__expLoaded=true;setTimeout(loadExploreTweak,100)}}}})}})}})();
/* ═══ 我的页 ═══ */
function loadProfile(){{/* 施工中 */}}
function setPreference(mode){{fetch('/setpref?mode='+mode).catch(function(){{}})}}
/* ═══ 添加页 ═══ */
var __addImages=[];
function triggerAddCamera(){{document.getElementById('add-camera-input').click()}}
function triggerAddAlbum(){{document.getElementById('add-album-input').click()}}
function handleAddImages(input){{var files=Array.from(input.files);if(!files.length)return;files.forEach(function(f){{var reader=new FileReader();reader.onload=function(e){{__addImages.push({{file:f,preview:e.target.result}});renderAddImageStrip()}};reader.readAsDataURL(f)}});input.value=''}}
function renderAddImageStrip(){{var strip=document.getElementById('add-image-strip');var hasImgs=__addImages.length>0;strip.style.display=hasImgs?'flex':'none';var html='';__addImages.forEach(function(img,i){{html+='<div class="add-image-thumb"><img src="'+img.preview+'"><span class="thumb-remove" onclick="event.stopPropagation();removeAddImage('+i+')">&times;</span></div>'}});html+='<div class="add-image-thumb add-more-btn" onclick="triggerAddAlbum()"><span class="add-more-plus">+</span><span class="add-more-label">添加</span></div>';strip.innerHTML=html;document.getElementById('add-confirm-btn').disabled=!hasImgs;document.getElementById('add-action-cards').style.display=hasImgs?'none':'grid'}}
function removeAddImage(index){{__addImages.splice(index,1);renderAddImageStrip();if(!__addImages.length){{document.getElementById('add-action-cards').style.display='grid';document.getElementById('add-confirm-btn').disabled=true}}}}
function clearAddImages(){{__addImages=[];document.getElementById('add-image-strip').style.display='none';document.getElementById('add-image-strip').innerHTML='';document.getElementById('add-result').style.display='none';document.getElementById('add-result').innerHTML='';document.getElementById('add-progress').style.display='none';document.getElementById('add-action-cards').style.display='grid';var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='确认分析';btn.onclick=function(){{submitAddImages()}};document.getElementById('add-camera-input').value='';document.getElementById('add-album-input').value=''}}
function submitAddImages(){{if(!__addImages.length)return;var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='识别中...';document.getElementById('add-progress').style.display='block';document.getElementById('add-progress-text').innerHTML='<div class="wrd-loading">AI识别中...</div>';var b64s=__addImages.map(function(img){{return img.preview.split(',')[1]}});fetch('/api/wardrobe/add',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{images:b64s}})}}).then(r=>r.json()).then(function(d){{if(d.task_id){{pollAddTask(d.task_id)}}else{{showAddReview(d)}}}}).catch(function(e){{document.getElementById('add-progress').style.display='none';btn.textContent='重试';btn.disabled=false;document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\">上传失败: '+escHtml(e.message)+'</div>'}})}}
function pollAddTask(tid){{fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){{if(d.status==='done'){{document.getElementById('add-progress').style.display='none';var data=JSON.parse(d.result);showAddReview(data)}}else if(d.status==='error'){{document.getElementById('add-progress').style.display='none';document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\">识别失败: '+escHtml(d.message)+'</div>';var btn=document.getElementById('add-confirm-btn');btn.textContent='重试';btn.disabled=false}}else{{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-loading\">'+escHtml(d.message||'识别中...')+'</div>';setTimeout(function(){{pollAddTask(tid)}},1500)}}}}).catch(function(){{setTimeout(function(){{pollAddTask(tid)}},2000)}})}}
function showAddReview(data){{var items=data.items||[];if(!items.length){{document.getElementById('add-progress-text').innerHTML='<div class=\"wrd-empty\">未识别到服装单品</div>';var btn=document.getElementById('add-confirm-btn');btn.textContent='重试';btn.disabled=false;return}}var btn=document.getElementById('add-confirm-btn');btn.textContent='确认入库 ('+items.length+'件)';btn.disabled=false;btn.onclick=function(){{confirmAddItems(data)}};var html='<div class=\"section-header\">AI 识别结果 · 请核对后确认</div>';items.forEach(function(item,i){{var c=item.color||{{}};var b=item.brand||{{}};var f=item.fabric||{{}};var colorHex=colorNameToHex(c.hue_name||'');html+='<div class=\"add-review-card\"><div class=\"ar-header\"><span class=\"ar-id\">'+escHtml(item.suggested_id||'')+'</span><span class=\"ar-cat\">'+escHtml(item.category||'')+'</span></div><div class=\"ar-fields\"><div class=\"ar-field\"><span class=\"ar-label\">品牌</span><span class=\"ar-value\">'+escHtml(b.name||'未知')+(b.confidence&&b.confidence!=='确定'?' <em>('+escHtml(b.confidence)+')</em>':'')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">颜色</span><span class=\"ar-value\">'+escHtml(c.hue_name||'')+' '+escHtml(c.hue_family||'')+'</span><span class=\"pal-dot\" style=\"display:inline-block;margin-left:6px;background:'+colorHex+'\"></span></div><div class=\"ar-field\"><span class=\"ar-label\">面料</span><span class=\"ar-value\">'+escHtml(f.primary||'')+' · '+escHtml(f.texture||'')+' · '+escHtml(f.weight||'')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">风格</span><span class=\"ar-value\">'+escHtml((item.style_modifiers||[]).join(' · ')||'基础款')+'</span></div><div class=\"ar-field\"><span class=\"ar-label\">场景</span><span class=\"ar-value\">'+escHtml((item.occasions||[]).join(' · ')||'日常')+'</span></div></div></div>'}});document.getElementById('add-result').innerHTML=html;document.getElementById('add-result').style.display='block'}}
function confirmAddItems(data){{var btn=document.getElementById('add-confirm-btn');btn.disabled=true;btn.textContent='入库中...';fetch('/api/wardrobe/add/confirm',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{task_id:data._task_id,items:data.items}})}}).then(r=>r.json()).then(function(d){{if(d.ok){{document.getElementById('add-result').innerHTML='<div class=\"wrd-loading\" style=\"color:#2e7d32\">✅ 已添加 '+d.added.length+' 件单品</div>';setTimeout(function(){{clearAddImages();__wardrobeNeedsReload=true}},1500)}}else{{btn.disabled=false;btn.textContent='重试入库';document.getElementById('add-result').innerHTML='<div class=\"wrd-empty\">入库失败: '+escHtml(d.message||'')+'</div>'}}}}).catch(function(e){{btn.disabled=false;btn.textContent='重试入库';document.getElementById('add-result').innerHTML='<div class=\"wrd-empty\">网络错误: '+escHtml(e.message)+'</div>'}})}}
function colorNameToHex(name){{var m={{'红':'#c0392b','橙':'#e67e22','黄':'#f1c40f','绿':'#27ae60','青':'#1abc9c','蓝':'#2980b9','紫':'#8e44ad','粉':'#e91e63','棕':'#795548','灰':'#95a5a6','白':'#ecf0f1','黑':'#2c3e50','米':'#f5deb3','卡其':'#c3b091','藏青':'#1a3a5c','酒红':'#722f37','墨绿':'#1a4028','驼':'#c19a6b','焦糖':'#af6b3d','浅灰':'#bdc3c7','深灰':'#636e72','银':'#bdc3c7','金':'#d4a574'}};if(!name)return'#ccc';for(var k in m){{if(name.indexOf(k)>=0)return m[k]}}return'#ccc'}}
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
        # Strategy 2: 风格笔记 section (bullet points)
        if not tags:
            in_notes = False
            for line in content.split('\n'):
                if '风格笔记' in line: in_notes = True; continue
                if in_notes and line.strip().startswith('##'): break
                if in_notes and line.strip().startswith('- '):
                    kw = line.strip()[2:].split('：')[0].split('—')[0].strip()[:8]
                    if kw and len(kw)>=2: tags.append(kw)
        # Strategy 3: Content keyword matching
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
        if it.get('thumb'):
            img_html = '<img class="item-img" src="{}" loading="lazy">'.format(it['thumb'])
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
    rating_str = ' ⭐'*outfit['rating'] if outfit['rating'] else ''
    # Character image
    img_tag = ''
    if outfit.get('char_img'):
        img_tag = '<img class="h-char-img" src="{}" onclick="event.stopPropagation();showImg(this.src)" loading="lazy">'.format(outfit['char_img'])
    else:
        img_tag = '<div class="h-char-img" style="background:#eaf0f6;display:flex;align-items:center;justify-content:center;color:#c8d4e2;font-size:16px">暂无</div>'
    # Color palette — only shown in expanded view
    palette_html = build_palette_html(outfit).replace('palette-strip', 'h-exp-palette')
    # Expanded: left image, right 2x4 grid, palette below grid
    expanded_html = '<div class="h-expand-row">{img}<div class="h-square-grid">{items}</div></div>{palette}'.format(
        img=img_tag.replace('h-char-img','h-char-img-lg'), items=items_html, palette=palette_html)
    # Small thumbnail for collapsed state
    thumb_small = ''
    if outfit.get('char_img'):
        thumb_small = '<img class="h-thumb-sm" src="{}" loading="lazy">'.format(outfit['char_img'])
    # Header: style + tags only (no palette when collapsed)
    tag_info_html = '<div class="fav-style">{style}{rating}</div>{tags}'.format(
        style=outfit['style'][:30], rating=rating_str, tags=tags_html)
    return '<div class="fav-card" onclick="this.classList.toggle(\'expanded\')"><div class="fav-num">{idx}</div><div class="fav-info">{tag_info}</div>{thumb}<div class="fav-arrow">▾</div><div class="fav-expand">{expanded}</div></div>'.format(idx=idx, tag_info=tag_info_html, thumb=thumb_small, expanded=expanded_html)

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
    hero_img = ho['char_img']
    hero_style = ho['style'][:30]
    hero_meta = '{} · {}'.format(ho['date'], (ho.get('weather','') or '晴 22~34°C')[:30])
    tags = extract_tags(ho)
    hero_tags_html = ''.join('<span>{}</span>'.format(t) for t in tags)
    palette_html = build_palette_html(ho)
    hero_items_html = ''.join(item_row(
        item_icons.get({'TS':'tshirt','LS':'tshirt','SHIRT':'tshirt','TANK':'tshirt','JK':'tshirt','PT':'pants','SH':'pants','SHOE':'shoe','HAT':'hat','BAG':'bag','SOCK':'sock','SUN':'sun','ACC':'acc'}.get(it['id'].split('-')[0],'tshirt'),''),
        it.get('cat',''), it['id'], it['name'], it.get('thumb','')
    ) for it in ho['items'][:8])
else:
    # Absolute fallback: no outfits exist at all — show placeholder
    hero_img = ''
    hero_style = '暂无推荐'
    hero_meta = '今天还没有生成穿搭，请先点击下方按钮生成'
    hero_tags_html = '<span>等待首套穿搭</span>'
    palette_html = ''
    hero_items_html = ''

card1 = mini_card('日系 City Boy', ['TS-011 落肩T恤', 'SHIRT-001 条纹衬衫', 'PT-001 宽松牛仔裤', 'SHOE-009 AF1'])
card2 = mini_card('轻熟休闲', ['SHIRT-003 牛津衬衫', 'PT-005 休闲西裤', 'SHOE-009 皮质板鞋', 'ACC-001 手串'])
card3 = mini_card('韩系简约', ['TS-010 条纹T恤', 'PT-006 直筒牛仔裤', 'SHOE-005 网球鞋', 'HAT-004 棒球帽'])

html = html.format(
    tabs=tabs_html,
    hero_img=hero_img, hero_style=hero_style, hero_meta=hero_meta,
    hero_tags_html=hero_tags_html, palette_html=palette_html, hero_items_html=hero_items_html,
    today_cards=today_cards, fav_cards=fav_cards,
    card1=card1, card2=card2, card3=card3,
    camera_icon=add_icons['camera_icon'], upload_icon=add_icons['upload_icon'],
    camera_lg_icon=add_icons['camera_lg_icon'], image_icon=add_icons['image_icon'],
    file_icon=add_icons['file_icon'], construction_icon=add_icons['construction_icon'],
)

out = os.path.join(PROJ, 'prototype', 'mobile-v2.html')
with open(out, 'w') as f:
    f.write(html)
print('Written {} bytes to {}'.format(len(html), out))
print('CI icons: tshirt={} pants={} hat={}'.format(
    'OK' if item_icons['tshirt'] else 'MISSING',
    'OK' if item_icons['pants'] else 'MISSING',
    'OK' if item_icons['hat'] else 'MISSING',
))
