#!/usr/bin/env python3
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
    'rec': lu('shirt'), 'exp': lu('crosshair'), 'wrd': lu('layout-grid'),
    'add': lu('camera'), 'me': lu('user'),
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
.page{{display:none;flex:1;flex-direction:column;overflow:hidden}}
.page.active{{display:flex}}
.scroll-area{{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 14px 16px}}
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
.rec-card{{display:flex;flex-direction:column}}
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
.placeholder{{text-align:center;padding:60px 20px}}
.placeholder .ph-icon{{font-size:40px;margin-bottom:12px;opacity:.2}}
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
<div class="segmented"><div class="seg-btn active">日常穿搭</div><div class="seg-btn">改变自己</div><div class="seg-btn">大胆跨界</div><div class="seg-btn">时尚圈子</div></div>
<div class="scroll-area"><div class="placeholder"><div class="ph-icon">&#x1f9ea;</div><div class="ph-text">日常微调探索<br>以你最近的风格为基点<br>小幅延伸出新搭配</div></div></div>
<div class="page-bottom"><input type="text" placeholder="描述你想尝试的风格..."></div>
</div>

<!-- ═══ 衣橱页 ═══ -->
<div class="page" id="page-wardrobe">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented"><div class="seg-btn active">我的衣橱</div><div class="seg-btn">月度报告</div><div class="seg-btn">冷门单品</div><div class="seg-btn">购买建议</div></div>
<div class="scroll-area">
<div style="display:flex;gap:10px;margin:16px 0 12px">
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:var(--navy)">76</div><div style="font-size:10px;color:var(--muted)">总件数</div></div>
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:#c4523c">26%</div><div style="font-size:10px;color:var(--muted)">利用率</div></div>
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:#c4523c">8</div><div style="font-size:10px;color:var(--muted)">超标</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" placeholder="搜索衣服..."></div>
</div>

<!-- ═══ 添加页 ═══ -->
<div class="page" id="page-add">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented"><div class="seg-btn active">拍照</div><div class="seg-btn">上传图片</div></div>
<div class="scroll-area"><div class="placeholder"><div class="ph-icon">&#x1f4f8;</div><div class="ph-text">拍照识别衣服<br>对准衣服拍照<br>AI 自动识别品牌品类颜色</div></div></div>
<div class="page-bottom" style="display:flex;gap:10px">
<button style="flex:1;padding:14px;background:var(--navy);color:#fff;border:none;border-radius:24px;font-size:15px;font-weight:600">确认分析</button>
<button style="flex:1;padding:14px;background:#eef2f7;color:var(--sub);border:none;border-radius:24px;font-size:15px">取消重选</button>
</div>
</div>

<!-- ═══ 我的页 ═══ -->
<div class="page" id="page-profile">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="scroll-area"><div class="placeholder" style="padding:80px 20px"><div class="ph-icon">&#x1f464;</div><div class="ph-text">个人中心<br>即将上线<br>推送偏好 · 穿搭统计 · 身形档案</div></div></div>
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
</script>
</body></html>'''

# Fill in variables
tabs_html = '\n'.join([
    tab_btn('rec', '推荐', True),
    tab_btn('exp', '探索'),
    tab_btn('wrd', '衣橱'),
    tab_btn('add', '添加'),
    tab_btn('me', '我的'),
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

# ── Hero: use today's latest outfit ──
today = scan_outfits(date_filter=time.strftime('%Y-%m-%d'), limit=1)
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
    hero_img = 'outfits/2026-06-14_打网球穿搭/上身效果/上身效果_1.png'
    hero_style = '清爽专业网球运动风'
    hero_meta = '2026/06/14 · 晴 · 22~34°C · 紫外线 强'
    hero_tags_html = '<span>网球运动</span><span>清爽低饱和</span><span>专业功能</span><span>City Boy</span>'
    palette_html = '<div class="palette-strip"><span class="pal-label">COLOR PALETTE</span><span class="pal-dot" style="background:#f5f3ef"></span><span class="pal-dot" style="background:#5c6e4a"></span><span class="pal-dot" style="background:#2a2a2a"></span><span class="pal-dot" style="background:#bdbdbd"></span><span class="pal-dot" style="background:#f0983c"></span></div>'
    hero_items_html = '{}{}{}{}{}{}{}'.format(item_tshirt_tennis, item_pants_tennis, item_shoe_tennis, item_hat_tennis, item_bag_tennis, item_sock_tennis, item_acc_tennis)

card1 = mini_card('日系 City Boy', ['TS-011 落肩T恤', 'SHIRT-001 条纹衬衫', 'PT-001 宽松牛仔裤', 'SHOE-009 AF1'])
card2 = mini_card('轻熟休闲', ['SHIRT-003 牛津衬衫', 'PT-005 休闲西裤', 'SHOE-009 皮质板鞋', 'ACC-001 手串'])
card3 = mini_card('韩系简约', ['TS-010 条纹T恤', 'PT-006 直筒牛仔裤', 'SHOE-005 网球鞋', 'HAT-004 棒球帽'])

html = html.format(
    tabs=tabs_html,
    # Tennis outfit items (for homepage)
    item_tshirt_tennis=item_row(item_icons['tshirt'], '上衣', 'TS-009', 'Lululemon 运动短袖', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/TS-009_Image_20260610_0821_27_191_cutout.png'),
    item_pants_tennis=item_row(item_icons['pants'], '下装', 'SH-005', 'Artengo 网球短裤', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SH-005_Image_20260610_0838_22_364_cutout.png'),
    item_shoe_tennis=item_row(item_icons['shoe'], '鞋子', 'SHOE-005', 'Nike 网球鞋', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SHOE-005_Image_20260610_0848_30_512_cutout.png'),
    item_hat_tennis=item_row(item_icons['hat'], '帽子', 'HAT-004', '基础棒球帽', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/HAT-004_Image_20260610_0810_53_039_cutout.png'),
    item_bag_tennis=item_row(item_icons['bag'], '包', 'BAG-007', 'Wilson 网球桶包', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/BAG-007_Image_20260610_1043_55_563%20%E6%8B%B7%E8%B4%9D_cutout.png'),
    item_sock_tennis=item_row(item_icons['sock'], '袜子', 'SOCK-006', '防滑底短袜', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SOCK-006_Image_20260610_0807_48_614_cutout.png'),
    item_acc_tennis=item_row(item_icons['acc'], '配饰', 'ACC-003', 'Apple Watch 黑色运动', 'outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/ACC-003_Image_20260610_0840_55_238_cutout.png'),
    # Summer outfit items
    item_tshirt_summer=item_row(item_icons['tshirt'], '上衣', 'TS-008', 'FUR SPEED 椰树印花短袖', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/TS-008_Image_20260610_0820_55_793_cutout.png'),
    item_pants_summer=item_row(item_icons['pants'], '下装', 'SH-008', '亚麻西装短裤', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/SH-008_Image_20260610_0839_33_059_cutout.png'),
    item_shoe_summer=item_row(item_icons['shoe'], '鞋子', 'SHOE-002', 'Adidas 复古训练鞋', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/SHOE-002_Image_20260610_0847_33_357_cutout.png'),
    item_hat_summer=item_row(item_icons['hat'], '帽子', 'HAT-004', '基础棒球帽', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/HAT-004_Image_20260610_0810_53_039_cutout.png'),
    item_bag_summer=item_row(item_icons['bag'], '包', 'BAG-004', 'Champion 米白托特包', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/BAG-004_Image_20260610_0812_10_563_cutout.png'),
    item_sun_summer=item_row(item_icons['sun'], '墨镜', 'SUN-002', '经典方形墨镜', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/SUN-002_Image_20260610_0845_19_011_cutout.png'),
    item_sock_summer=item_row(item_icons['sock'], '袜子', 'SOCK-005', '基础船袜', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/SOCK-005_Image_20260610_0807_09_360_cutout.png'),
    item_acc_summer=item_row(item_icons['acc'], '配饰', 'ACC-003', 'Apple Watch 回环尼龙表带', 'outfits/2026-06-15_%E4%BB%8A%E6%97%A5%E7%A9%BF%E6%90%AD%20%E7%AC%AC2%E7%89%88%20%E8%AF%B7%E4%B8%8E%E4%B9%8B%E5%89%8D%E4%B8%8D%E5%90%8C/items/ACC-003_Image_20260610_0840_55_238_cutout.png'),
    hero_img=hero_img, hero_style=hero_style, hero_meta=hero_meta,
    hero_tags_html=hero_tags_html, palette_html=palette_html, hero_items_html=hero_items_html,
    today_cards=today_cards, fav_cards=fav_cards,
    card1=card1, card2=card2, card3=card3,
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
