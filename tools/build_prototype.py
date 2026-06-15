#!/usr/bin/env python3
"""Build mobile-v2.html prototype with proper icons from icon library"""
import re, os, json, time, random

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')
OUTFITS_DIR = os.path.join(PROJ, 'outfits')

def simplify_name(iid, name):
    """Simplify item name: brand + basic description, remove series/wearing style"""
    # Keep brand name if present
    brands = ['Lululemon','Nike','Adidas','Uniqlo','FUR SPEED','Champion','Decathlon',
              'Artengo','Wilson','Converse','Puma','FILA','HLA','COMME des GARCONS','CDG',
              'Merrell','Timberland','Jordan','Cotton On','Kiprun']
    found_brand = ''
    for b in brands:
        if b.lower() in name.lower():
            found_brand = b
            break
    # Apple Watch: keep band info
    if iid == 'ACC-003' or 'Apple Watch' in name:
        band = ''
        for b in ['回环尼龙','尼龙回环','米兰尼斯','运动表带','黑色运动','回环']:
            if b in name: band = b; break
        return 'Apple Watch {}'.format(band) if band else 'Apple Watch'
    # Remove series/tech terms
    remove = ['Metal Vent Tech','Metal Vent','Court Lite','入门级','Artengo',
              'Leisure Club','基础','简约实用','经典','复古','专业','入门',
              '敞穿或卷袖','敞穿','卷袖','叠穿','基本款','常规','标准']
    clean = name
    for r in remove:
        clean = clean.replace(r, '').replace('  ', ' ')
    # If brand found, use "Brand + short name"
    if found_brand:
        short = clean.replace(found_brand, '').strip()
        # Keep only first meaningful part
        parts = [p for p in short.split() if len(p)>=2 and p not in [' ','']]
        short = parts[0] if parts else short[:4]
        # Add category suffix if too short
        if len(short) <= 2:
            for cat in ['短袖','长袖','短裤','长裤','衬衫','外套','鞋子','帽子','袜子','墨镜','包']:
                if cat in clean: short = cat; break
        return '{} {}'.format(found_brand, short)[:16]
    # No brand: just first meaningful words
    clean = clean.strip()
    return clean[:14]

def scan_outfits(date_filter=None, rating_filter=None, limit=20):
    """Scan outfits directory, return list of outfit dicts"""
    results = []
    for d in sorted(os.listdir(OUTFITS_DIR), reverse=True):
        dp = os.path.join(OUTFITS_DIR, d)
        if not os.path.isdir(dp) or d.startswith('.') or d.startswith('_'):
            continue
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
                items.append({'id': cells[2], 'name': simplify_name(cells[2], cells[3]), 'cat': cells[1] if len(cells)>1 else ''})
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
.scroll-area{{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 20px 16px}}
.page-bottom{{flex-shrink:0;padding:10px 20px;background:var(--bg);border-top:1px solid var(--border);z-index:5}}
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

/* Item rows */
.item-list{{display:flex;flex-direction:column}}
.item-row{{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f2f5f9}}
.item-row:last-child{{border-bottom:none}}
.item-emoji{{width:20px;height:20px;flex-shrink:0;color:var(--navy)}}
.item-emoji svg{{width:100%;height:100%;display:block}}
.item-cat{{font-size:11px;color:var(--muted);width:36px;flex-shrink:0;font-weight:500}}
.item-id{{font-size:10px;color:var(--sub);font-family:monospace;background:#f0f4f8;padding:3px 8px;border-radius:5px;flex-shrink:0}}
.item-name{{font-size:14px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}}

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
.h-char-img-lg{{width:170px;height:226px;border-radius:10px;object-fit:cover;flex-shrink:0;cursor:pointer}}
/* 2x4 square grid */
.h-square-grid{{flex:1;display:grid;grid-template-columns:repeat(2,1fr);gap:5px;align-content:start;grid-auto-rows:52px}}
.h-square-grid .item-row{{display:flex;flex-direction:column;gap:2px;padding:6px 5px;background:#f8fafc;border-radius:6px;cursor:pointer;position:relative;overflow:hidden;min-height:52px}}
.h-square-grid .item-row .ir-top{{display:flex;align-items:center;gap:3px}}
.h-square-grid .item-row.clickable:active{{background:#eef2f7}}
.h-square-grid .item-emoji{{width:16px;height:16px;flex-shrink:0}}
.h-square-grid .item-id{{font-size:7px;flex-shrink:0}}
.h-square-grid .item-name{{font-size:8px;line-height:1.3;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
.h-square-grid .item-row.expanded{{grid-row:span 2;padding:3px;z-index:2}}
.h-square-grid .item-row.expanded .ir-top,.h-square-grid .item-row.expanded .item-name{{display:none}}
.h-square-grid .item-row.expanded .item-img{{display:block}}
.h-square-grid .item-img{{display:none;width:100%;height:100%;object-fit:contain;position:absolute;top:0;left:0;padding:4px}}
.h-square-grid .item-row.showing-img .item-img{{display:block}}
.placeholder{{text-align:center;padding:60px 20px}}
.placeholder .ph-icon{{font-size:40px;margin-bottom:12px;opacity:.2}}
.placeholder .ph-text{{font-size:14px;line-height:1.7;color:var(--sub)}}
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
<div class="hero-img"><img src="outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/%E4%B8%8A%E8%BA%AB%E6%95%88%E6%9E%9C/%E4%B8%8A%E8%BA%AB%E6%95%88%E6%9E%9C_1.png" alt=""></div>
<div class="hero-body">
<div class="style-tags"><span>网球运动</span><span>清爽低饱和</span><span>专业功能</span><span>City Boy</span></div>
<div class="hero-style">清爽专业网球运动风</div>
<div class="hero-meta">2026/06/14 · 晴 · 22~34&deg;C · 紫外线 强</div>
<div class="item-list">
{item_tshirt_tennis}
{item_pants_tennis}
{item_shoe_tennis}
{item_hat_tennis}
{item_bag_tennis}
{item_sock_tennis}
{item_acc_tennis}
</div>
<div class="palette-strip"><span class="pal-label">COLOR PALETTE</span><span class="pal-dot" style="background:#dcd7cd"></span><span class="pal-dot" style="background:#b4b4a0"></span><span class="pal-dot" style="background:#fff"></span><span class="pal-dot" style="background:#3c5032"></span><span class="pal-dot" style="background:#282826"></span></div>
</div></div>

<div class="section-header">其他推荐</div>
<div class="rec-cards">
{card1}
{card2}
<div class="rec-card dashed"><div class="dash-text">+ 换一批</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" placeholder="描述穿搭需求，如「今天要去约会」..."></div>
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
(function refreshHero(){{fetch('/api/today').then(function(r){{return r.json()}}).then(function(d){{if(!d||d.empty)return;var hi=document.querySelector('.hero-img img');if(!hi||hi.getAttribute('data-loaded')===d.dir)return;hi.src=d.img||'';hi.setAttribute('data-loaded',d.dir);var el=document.querySelector('.hero-style');if(el&&d.style)el.textContent=d.style;el=document.querySelector('.hero-meta');if(el)el.textContent=(d.date||'')+(d.weather?' · '+d.weather:'');el=document.querySelector('.style-tags');if(el&&d.tags)el.innerHTML=d.tags.map(function(t){{return'<span>'+t+'</span>'}}).join('');el=document.querySelector('.item-grid');if(el&&d.items){{var ic={{TS:'👕',LS:'👔',SHIRT:'👔',TANK:'🎽',JK:'🧥',PT:'👖',SH:'🩳',SHOE:'👟',HAT:'🧢',BAG:'🎒',SOCK:'🧦',SUN:'🕶',ACC:'⌚'}};var cm={{TS:'上衣',LS:'长袖',SHIRT:'衬衫',TANK:'背心',JK:'外套',PT:'长裤',SH:'短裤',SHOE:'鞋子',HAT:'帽子',BAG:'包',SOCK:'袜子',SUN:'墨镜',ACC:'配饰'}};var h='';d.items.forEach(function(it){{var p=it.id.split('-')[0];h+='<div class=\"item-row\"><span class=\"item-emoji\">'+(ic[p]||'👔')+'</span><span class=\"item-cat\">'+(cm[p]||'')+'</span><span class=\"item-id\">'+it.id+'</span><span class=\"item-name\">'+(it.name||'').substring(0,14)+'</span></div>'}});el.innerHTML=h}}}})}})();
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
def extract_tags(outfit):
    """Extract style tags: same smart-matching as API"""
    tags = []
    known = ['日系','韩系','欧美','街头','复古','机能','简约','轻熟','运动','度假',
        'City Boy','Clean Fit','美式','户外','军事','工装','网球','跑步','健身',
        '宽松','低饱和','高对比','叠穿','单色','撞色','印花','条纹','纯色',
        '通勤','约会','商务','休闲','正式','清爽','优雅','硬朗','柔和',
        '机能休闲','美式复古','日常休闲','城市休闲','度假休闲']
    style = outfit.get('style','')
    st = style
    for sep in ['丨','｜','/','·','-']: st = st.replace(sep, ' ')
    for kw in known:
        if kw in st and kw not in tags: tags.append(kw)
    if len(tags) < 2:
        words = [w.strip() for w in st.split() if len(w.strip())>=2]
        for w in words:
            if w[:8] not in tags: tags.append(w[:8])
    return tags[:4]

def gen_history_card(outfit, idx):
    items_html = ''
    cat_icons = {'TS':'tshirt','LS':'tshirt','SHIRT':'shirt','TANK':'tank','JK':'jacket',
                 'PT':'pants','SH':'shorts','SHOE':'shoe','HAT':'hat','BAG':'bag',
                 'SOCK':'sock','SUN':'sun','ACC':'acc'}
    for it in outfit['items'][:8]:
        prefix = it['id'].split('-')[0]
        ico_key = cat_icons.get(prefix, 'tshirt')
        ico = item_icons.get(ico_key, '')
        thumb_attr = ''
        if it.get('thumb'):
            thumb_attr = ' data-thumb="{}"'.format(it['thumb'])
        img_html = ''
        if it.get('thumb'):
            img_html = '<img class="item-img" src="{}" loading="lazy">'.format(it['thumb'])
        clean_name = it['name'].replace('·','').replace('，',' ').replace('、',' ').replace('  ',' ').strip()[:20]
        items_html += '<div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle(\'expanded\')"><div class="ir-top"><span class="item-emoji">{}</span><span class="item-id">{}</span></div><span class="item-name">{}</span>{}</div>'.format(ico, it['id'], clean_name, img_html)
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
    # Expanded: left image, right 2x4 square grid
    expanded_html = '<div class="h-expand-row">{img}<div class="h-square-grid">{items}</div></div>'.format(img=img_tag.replace('h-char-img','h-char-img-lg'), items=items_html)
    # Small thumbnail for collapsed state
    thumb_small = ''
    if outfit.get('char_img'):
        thumb_small = '<img class="h-thumb-sm" src="{}" loading="lazy">'.format(outfit['char_img'])
    # Collapsed: number + style + tags + small thumbnail
    return '<div class="fav-card" onclick="this.classList.toggle(\'expanded\')"><div class="fav-num">{idx}</div><div class="fav-info"><div class="fav-style">{style}{rating}</div>{tags}</div>{thumb}<div class="fav-arrow">▾</div><div class="fav-expand">{expanded}</div></div>'.format(idx=idx, style=outfit['style'][:30], rating=rating_str, tags=tags_html, thumb=thumb_small, expanded=expanded_html)

today_outfits = scan_outfits(date_filter=time.strftime('%Y-%m-%d'), limit=10)
fav_outfits = scan_outfits(rating_filter=3, limit=10)
today_cards = '\n'.join([gen_history_card(o, i+1) for i, o in enumerate(today_outfits)])
fav_cards = '\n'.join([gen_history_card(o, i+1) for i, o in enumerate(fav_outfits)])
if not today_cards: today_cards = '<div style="padding:16px;color:var(--muted);font-size:13px">今日暂无推荐</div>'
if not fav_cards: fav_cards = '<div style="padding:16px;color:var(--muted);font-size:13px">暂无三星好评 · 给穿搭点 ⭐⭐⭐ 后会出现在这里</div>'

card1 = mini_card('夏日度假休闲', ['TS-008 椰树印花短袖', 'SH-008 亚麻短裤', 'SHOE-002 复古训练鞋', 'HAT-004 棒球帽', 'SOCK-005 船袜'])
card2 = mini_card('衬衫叠穿层次', ['SHIRT-002 基础衬衫', 'TS-011 落肩T恤', 'SHOE-005 网球鞋', 'SH-004 休闲短裤', 'SOCK-005 船袜'])

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
    today_cards=today_cards,
    fav_cards=fav_cards,
    card1=card1,
    card2=card2,
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
