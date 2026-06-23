#!/usr/bin/env python3
"""Build icons-set.html from Clothing-Icons + Lucide"""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(BASE, '..')

with open(os.path.join(PROJ, 'node_modules/clothing-icons/dist/index.js')) as f:
    js = f.read()

def ci(name):
    i = js.find('Svg'+name)
    if i == -1: return None
    ps = re.findall(r'd:\s*"([^"]+)"', js[i:i+4000])[:10]
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

I = {}
# Tab Bar
for k, v in {'rec': 'shirt', 'exp': 'radar', 'wrd': 'layout-grid', 'add': 'camera', 'me': 'user'}.items():
    I[k] = lu(v)

# Men
men = [
    ('TS', '短袖', 'TShirt'), ('LS', '长袖', 'LongSleevedShirt'), ('SHIRT', '衬衫', 'Shirt'),
    ('TANK', '背心', 'Vest'), ('JK', '外套', 'Jacket'), ('PT', '长裤', 'PantsMans'),
    ('SH', '短裤', 'Shorts'), ('HAT', '帽子', 'BaseballCap'), ('SOCK', '袜子', 'Socks'),
    ('SCARF', '围巾', 'Scarf'), ('COAT', '大衣', 'Coat'), ('HOODIE', '卫衣', 'Hoodie'),
    ('SWEATER', '毛衣', 'Sweater'), ('TIE', '领结', 'ABowTie'),
    ('GLOVES', '手套', 'Gloves'), ('BLAZER', '西装', 'Blazer'),
    ('WAISTCOAT', '马甲', 'Waistcoat'), ('TUXEDO', '燕尾服', 'Tuxedo'),
    ('PARKA', '派克大衣', 'Parka'), ('WINDBREAKER', '风衣', 'Windbreaker'),
    ('DENIM', '牛仔外套', 'Denim'), ('CHINOS', '卡其裤', 'Chinos'),
    ('JOGGERS', '慢跑裤', 'Joggers'), ('BRIEFS', '内裤', 'Briefs'),
]
for code, name, src in men:
    I['c_' + code] = ci(src) or lu('shirt')

# Women
women = [
    ('DRESS', '连衣裙', 'Dress'), ('SUNDRESS', '吊带裙', 'Sundress'),
    ('COCKTAIL', '礼服裙', 'CocktailDress'), ('EVENING', '晚礼裙', 'EveningDress'),
    ('WRAP', '裹身裙', 'WrapDress'), ('BABYDOLL', '娃娃裙', 'BabydollDress'),
    ('FANCY', '华丽裙', 'FancyDress'), ('SKIRT', '半身裙', 'Skirt'),
    ('BLOUSE', '女衬衫', 'Blouse'), ('LOOSEBLOUSE', '宽松衫', 'LooseFittingBlouse'),
    ('CAMISOLE', '吊带衫', 'Camisole'), ('CARDIGAN', '开衫', 'Cardigan'),
    ('LEGGINGS', '打底裤', 'Leggings'), ('KIMONO', '和服外套', 'Kimono'),
    ('BRA', '内衣', 'Bra'),
]
for code, name, src in women:
    I['w_' + code] = ci(src) or lu('shirt')

# Accessories
acc = [
    ('a_shoe1', 'SHOE 运动鞋', 'sport-shoe'), ('a_shoe2', 'SHOE 靴子', 'footprints'),
    ('a_bag1', 'BAG 托特包', 'shopping-bag'), ('a_bag2', 'BAG 双肩包', 'backpack'),
    ('a_bag3', 'BAG 手拿包', 'handbag'), ('a_bag4', 'BAG 公文包', 'briefcase'),
    ('a_glass', 'SUN 眼镜', 'glasses'), ('a_watch', 'ACC 手表', 'watch'),
    ('a_gem', 'ACC 首饰', 'gem'),
]
for key, name, src in acc:
    I[key] = lu(src)

# Weather / Actions / Style / Nav
maps = {
    'we_sun': 'sun', 'we_cloud': 'cloud', 'we_cs': 'cloud-sun', 'we_rain': 'cloud-rain',
    'we_snow': 'cloud-snow', 'we_wind': 'wind', 'we_moon': 'moon', 'we_thermo': 'thermometer',
    'ac_s': 'search', 'ac_add': 'plus', 'ac_ok': 'check', 'ac_ref': 'refresh-ccw',
    'ac_more': 'more-horizontal', 'ac_share': 'share-2', 'ac_bell': 'bell', 'ac_gear': 'settings',
    'st_pal': 'palette', 'st_star': 'star', 'st_heart': 'heart', 'st_cal': 'calendar',
    'st_tag': 'tag', 'st_trend': 'trending-up', 'st_sp': 'sparkles', 'st_crown': 'crown',
    'nv_l': 'chevron-left', 'nv_r': 'chevron-right', 'nv_d': 'chevron-down',
    'nv_u': 'chevron-up', 'nv_x': 'x',
}
for k, v in maps.items():
    I[k] = lu(v)
I['st_starf'] = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'

for k in list(I):
    if I[k] is None: del I[k]

print('{} icons'.format(len(I)))

# Build HTML
def cell(key, name, note=''):
    svg = I.get(key, '')
    n = '<div class="name">{}</div>'.format(name)
    k = '<div class="key">{}</div>'.format(note) if note else ''
    return '<div class="cell"><div style="color:var(--navy)">{}</div>{}{}</div>'.format(svg, n, k)

html = r'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=440"><title>Style Advisor Icons</title>
<style>
:root{--navy:#1e3a5f;--muted:#94a3b5;--bg:#f8fafc;--card:#fff;--text:#1a2838}
body{font-family:-apple-system,sans-serif;background:#e2e6ec;display:flex;justify-content:center;padding:20px}
.container{width:420px}
h2{font-size:14px;color:var(--text);margin:24px 0 10px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.cell{background:var(--card);border-radius:10px;padding:14px 6px;text-align:center;box-shadow:0 1px 3px rgba(30,58,95,.04)}
.cell svg{width:26px;height:26px;display:block;margin:0 auto 6px}
.cell .name{font-size:9px;color:var(--text);font-weight:500}
.cell .key{font-size:7px;color:var(--muted);margin-top:1px}
.tab-bar{display:flex;justify-content:space-around;background:rgba(30,58,95,.92);backdrop-filter:blur(20px);border-radius:18px;padding:6px 8px;margin-top:16px;box-shadow:0 8px 32px rgba(30,58,95,.25)}
.tb-tab{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;padding:8px 0;border-radius:14px;min-width:52px}
.tb-tab svg{width:20px;height:20px}
.tb-tab .label{font-size:10px;font-weight:500}
.tb-tab.off svg{color:rgba(255,255,255,.5)}
.tb-tab.off .label{color:rgba(255,255,255,.5)}
.tb-tab.on{background:rgba(255,255,255,.15)}
.tb-tab.on svg{color:#fff}
.tb-tab.on .label{color:#fff;font-weight:600}
</style></head><body><div class="container">
<h1 style="font-size:18px;font-weight:800;color:var(--text);margin-bottom:2px">Style Advisor Icons</h1>
<p style="font-size:11px;color:var(--muted);margin-bottom:4px">男装16 + 女装15 | CI服装 + LU其他</p>
'''

html += '<h2>Tab Bar</h2><div class="grid">'
for k, n, s in [('rec', '推荐', 'shirt'), ('exp', '探索', 'radar'), ('wrd', '衣橱', 'layout-grid'), ('add', '添加', 'camera'), ('me', '我的', 'user')]:
    html += cell(k, n, s)
html += '</div>'

html += '<h2>Clothing Men (16)</h2><div class="grid">'
for code, name, src in men:
    html += cell('c_' + code, name, src)
html += '</div>'

html += '<h2>Clothing Women (15)</h2><div class="grid">'
for code, name, src in women:
    html += cell('w_' + code, name, src)
html += '</div>'

html += '<h2>Accessories</h2><div class="grid">'
for key, name, src in acc:
    html += cell(key, name, src)
html += '</div>'

for title, items in [
    ('Weather', [('we_sun', '晴天'), ('we_cloud', '多云'), ('we_cs', '晴转云'), ('we_rain', '雨天'), ('we_snow', '雪天'), ('we_wind', '风'), ('we_moon', '夜晚'), ('we_thermo', '温度')]),
    ('Actions', [('ac_s', '搜索'), ('ac_add', '添加'), ('ac_ok', '确认'), ('ac_ref', '刷新'), ('ac_more', '更多'), ('ac_share', '分享'), ('ac_bell', '通知'), ('ac_gear', '设置')]),
    ('Style', [('st_pal', '配色'), ('st_starf', '星实心'), ('st_star', '星空心'), ('st_heart', '喜欢'), ('st_cal', '日历'), ('st_tag', '标签'), ('st_trend', '趋势'), ('st_sp', '闪耀'), ('st_crown', '精品')]),
]:
    html += '<h2>{}</h2><div class="grid">'.format(title)
    for k, n in items:
        html += cell(k, n)
    html += '</div>'

html += '<h2>Tab Bar Preview</h2><div class="tab-bar">'
for i, (k, label) in enumerate(zip(['rec', 'exp', 'wrd', 'add', 'me'], ['推荐', '探索', '衣橱', '添加', '我的'])):
    st = 'on' if i == 0 else 'off'
    html += '<div class="tb-tab {}">{}{}</div>'.format(st, I[k], '<span class="label">' + label + '</span>')
html += '</div></div></body></html>'

out = os.path.join(PROJ, 'prototype/icons-set.html')
with open(out, 'w') as f:
    f.write(html)
print('Written to', out)
