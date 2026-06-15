#!/usr/bin/env python3
"""Build mobile-v2.html prototype with proper icons from icon library"""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')

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

def item_row(icon_svg, cat, iid, name):
    return '<div class="item-row"><span class="item-emoji">{}</span><span class="item-cat">{}</span><span class="item-id">{}</span><span class="item-name">{}</span></div>'.format(icon_svg, cat, iid, name)

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
.hero-img{{width:100%;aspect-ratio:4/3;background:#eaf0f6;position:relative;overflow:hidden}}
.hero-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.hero-img::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:60px;background:linear-gradient(transparent,rgba(26,40,56,.4));pointer-events:none}}
.hero-body{{padding:18px}}
.hero-style{{font-size:22px;font-weight:800;color:var(--text);letter-spacing:-.5px;margin-bottom:6px}}
.hero-meta{{font-size:12px;color:var(--sub);margin-bottom:16px}}

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
.fav-card{{display:flex;align-items:center;gap:12px;background:var(--white);border-radius:var(--radius-sm);padding:14px 16px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04)}}
.fav-num{{width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.fav-info{{flex:1;min-width:0}}
.fav-style{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:3px}}
.fav-meta{{font-size:11px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
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
<div class="hero-img"><img src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/%E8%B1%86%E5%8C%85%E7%94%9F%E5%9B%BE/%E4%BA%BA%E7%89%A9_IMG_8493.jpg" alt="" style="width:100%;height:100%;object-fit:cover"></div>
<div class="hero-body">
<div class="hero-style">清爽专业网球运动风</div>
<div class="hero-meta">2026/06/14 · 晴 · 22~34&deg;C · 紫外线 强</div>
<div class="item-list">
{item_tshirt_tennis}
{item_pants_tennis}
{item_shoe_tennis}
{item_hat_tennis}
{item_bag_tennis}
</div></div></div>

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
<div class="scroll-area">
<div class="section-header" style="margin-top:4px">今日全部</div>
<div class="fav-list" style="margin-bottom:16px">
<div class="fav-card"><div class="fav-num">1</div><div class="fav-info"><div class="fav-style">清爽雾天城市休闲</div><div class="fav-meta">TS-011、SH-004、SHOE-005、HAT-004…</div></div></div>
<div class="fav-card"><div class="fav-num">2</div><div class="fav-info"><div class="fav-style">夏日度假休闲</div><div class="fav-meta">TS-008、SH-008、SHOE-002</div></div></div>
</div>
<div class="section-header">历史最爱</div>
<div class="fav-list" style="margin-bottom:16px">
<div class="fav-card"><div class="fav-num">1</div><div class="fav-info"><div class="fav-style">打网球穿搭</div><div class="fav-meta">2026-06-14 · TS-009、SH-005、SHOE-005</div></div></div>
</div>
</div>
<div class="page-bottom"><input type="text" placeholder="搜索历史推荐..."></div>
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
<div class="tab-bar" id="tab-bar">
{tabs}
</div>

<script>
var currentPage='recommend';
document.querySelectorAll('#tab-bar .tab').forEach(function(tab){{tab.addEventListener('click',function(){{var p=this.dataset.page;if(p===currentPage)return;currentPage=p;document.querySelectorAll('#tab-bar .tab').forEach(function(t){{t.classList.remove('active')}});this.classList.add('active');document.querySelectorAll('.page').forEach(function(pg){{pg.classList.remove('active')}});document.getElementById('page-'+p).classList.add('active')}})}});
document.querySelectorAll('.segmented').forEach(function(seg){{seg.addEventListener('click',function(e){{var b=e.target.closest('.seg-btn');if(!b)return;seg.querySelectorAll('.seg-btn').forEach(function(s){{s.classList.remove('active')}});b.classList.add('active');var sub=b.dataset.sub;if(!sub)return;var parent=seg.parentElement;parent.querySelectorAll('.subpage').forEach(function(sp){{sp.style.display='none'}});var t=document.getElementById('sub-'+sub);if(t)t.style.display='flex'}})}});
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

card1 = mini_card('夏日度假休闲', ['TS-008 椰树印花短袖', 'SH-008 亚麻短裤', 'SHOE-002 复古训练鞋', 'HAT-004 棒球帽', 'SOCK-005 船袜'])
card2 = mini_card('衬衫叠穿层次', ['SHIRT-002 基础衬衫', 'TS-011 落肩T恤', 'SHOE-005 网球鞋', 'SH-004 休闲短裤', 'SOCK-005 船袜'])

html = html.format(
    tabs=tabs_html,
    item_tshirt_tennis=item_row(item_icons['tshirt'], '上衣', 'TS-009', 'Lululemon Metal Vent Tech 运动短袖'),
    item_pants_tennis=item_row(item_icons['pants'], '下装', 'SH-005', 'Decathlon Artengo 网球运动短裤'),
    item_shoe_tennis=item_row(item_icons['shoe'], '鞋子', 'SHOE-005', 'Nike Court Lite 网球鞋'),
    item_hat_tennis=item_row(item_icons['hat'], '帽子', 'HAT-004', '基础棒球帽'),
    item_bag_tennis=item_row(item_icons['bag'], '包', 'BAG-007', 'Wilson 复古网球桶包'),
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
