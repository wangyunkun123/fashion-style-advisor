#!/usr/bin/env python3
"""
穿搭排版合成 vFinal
- AI生图加白框放在纯色背景上
- 单品以配色卡片形式排列在四周
- 核心大件大卡片 / 配饰小贴纸
- 自动提取生图主色调作为点缀色
"""
import os, sys, re, glob, json, base64, urllib.request, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTFIT_BASE = os.path.join(BASE_DIR, '..', 'outfits')
WARDROBE_ENHANCED = os.path.join(BASE_DIR, '..', 'wardrobe', 'enhanced')

ARK_KEY = 'ark-73c10b0a-0549-47fa-9811-39d37b6e452f-a7ac6'
ARK_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions'
ARK_MODEL = 'doubao-seed-2.0-code'

FONT_PATHS = ['/System/Library/Fonts/STHeiti Medium.ttc','/System/Library/Fonts/STHeiti Light.ttc','/System/Library/Fonts/Hiragino Sans GB.ttc']
CATEGORY_ORDER = ["HAT-","SUN-","JK-","TS-","LS-","SHIRT-","TANK-","SH-","PT-","ACC-","BAG-","SHOE-","SOCK-"]
CORE_PREFIXES = {'JK-','TS-','LS-','SHIRT-','TANK-','SH-','PT-','SHOE-'}

def load_font(size):
    for p in FONT_PATHS:
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ====== 数据获取 ======
def find_latest_outfit():
    dirs = sorted([d for d in os.listdir(OUTFIT_BASE) if os.path.isdir(os.path.join(OUTFIT_BASE,d)) and not d.startswith('.')])
    return os.path.join(OUTFIT_BASE, dirs[-1]) if dirs else None

def parse_outfit_md(outfit_dir):
    md_path = os.path.join(outfit_dir, 'outfit.md')
    if not os.path.exists(md_path): return []
    with open(md_path, encoding='utf-8') as f: lines = f.readlines()
    in_sec, items = False, []
    for line in lines:
        if '穿搭方案' in line: in_sec = True; continue
        if in_sec and line.strip().startswith('##') and '穿搭方案' not in line: break
        if not in_sec: continue
        s = line.strip()
        if not s.startswith('|') or '---' in s: continue
        cells = [c.strip() for c in s.split('|')]
        if len(cells) < 4: continue
        iid = cells[2].replace('**','').strip()
        iname = cells[3].strip()
        if iid in ('单品ID','ID','') or not re.match(r'^[A-Z]+-\d+', iid): continue
        cat = re.sub(r'[^一-鿿\w]','', cells[1]).strip()
        items.append({'id':iid, 'name':iname, 'category':cat, 'prefix':iid.split('-')[0]+'-'})
    return items

def find_ai_image(outfit_dir):
    cand = []
    for sub in ['generated','上身效果']:
        sd = os.path.join(outfit_dir, sub)
        if not os.path.exists(sd): continue
        for f in sorted(os.listdir(sd)):
            if f.lower().endswith(('.jpg','.jpeg','.png')) and not f.startswith('.') and 'vA' not in f and 'vB' not in f and 'vC' not in f:
                cand.append(os.path.join(sd, f))
    return cand[0] if cand else None

def find_best_image(items_dir, item):
    """优先抠图PNG → 增强JPG → 原图"""
    # 1. 先在 items 目录找原文件
    orig = None
    for f in sorted(os.listdir(items_dir)):
        if f.startswith(item['id']+'_') and f.lower().endswith(('.jpg','.jpeg','.png')):
            orig = f; break
    if not orig: return None

    # 2. 查增强目录同名抠图
    base_name = os.path.splitext(orig)[0]
    cutout_path = os.path.join(WARDROBE_ENHANCED, base_name + '_cutout.png')
    if os.path.exists(cutout_path):
        return cutout_path

    # 3. 查 items 目录下的抠图副本
    local_cutout = os.path.join(items_dir, base_name + '_cutout.png')
    if os.path.exists(local_cutout):
        return local_cutout

    # 4. 查增强目录同名 JPG
    enhanced_jpg = os.path.join(WARDROBE_ENHANCED, orig)
    if os.path.exists(enhanced_jpg):
        return enhanced_jpg

    # 5. 原图
    return os.path.join(items_dir, orig)


# ====== 色彩提取 ======
def extract_colors(ai_path):
    """从生图提取背景色和点缀色"""
    img = Image.open(ai_path).convert('RGB').resize((80, 80), Image.LANCZOS)
    px = list(img.getdata())

    # 背景色：边缘像素平均
    edge = [px[y*80+x] for y in range(80) for x in range(80) if x<12 or x>67 or y<12 or y>67]
    if edge:
        r = int(sum(p[0] for p in edge)/len(edge))
        g = int(sum(p[1] for p in edge)/len(edge))
        b = int(sum(p[2] for p in edge)/len(edge))
        bg = (min(255, r+25), min(255, g+22), min(255, b+28))
    else:
        bg = (248, 246, 242)

    # 点缀色：最饱和
    best, accent = 0, (160, 130, 120)
    for r,g,b in px:
        mx, mn = max(r,g,b), min(r,g,b)
        sat = (mx - mn) / max(mx, 1) if mx > 0 else 0
        if sat > best and mx > 70:
            best = sat; accent = (r, g, b)

    return bg, accent


# ====== 单品卡片渲染 ======
def render_card(img_path, base_size, accent_color, prefix=''):
    """
    纯白卡片：仅用 1:1 / 3:4 / 4:3 三种比例
    选择最匹配衣服原始比例的卡片，图片居中撑满
    base_size = 卡片基准尺寸（较短的边）
    """
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img)

    # 裁剪透明边（严格模式：alpha≥200才算有效像素）+ 自动摆正
    if img.mode == 'RGBA':
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
            pixels = img.load()
            l, t, r, b = 0, 0, img.width, img.height
            while l < r and max(pixels[l, y][3] for y in range(0, img.height, 3)) < 200: l += 1
            while r > l and max(pixels[r-1, y][3] for y in range(0, img.height, 3)) < 200: r -= 1
            while t < b and max(pixels[x, t][3] for x in range(0, img.width, 3)) < 200: t += 1
            while b > t and max(pixels[x, b-1][3] for x in range(0, img.width, 3)) < 200: b -= 1
            if l < r and t < b:
                img = img.crop((l, t, r, b))

            # 倾斜修正：固定角度 + PCA 混合
            # 固定旋转角度（正值=顺时针）
            fixed_angle = {
                'HAT-': 0,      # 帽子不旋转
                'JK-': 10,      # 外套右倾10度灵动
                'TS-': -10,     # 短袖左倾10度
                'LS-': -8,      # 长袖略左倾
                'SHIRT-': -8,
                'TANK-': -8,
            }.get(prefix, None)

            if fixed_angle is not None:
                if fixed_angle != 0:
                    img = img.rotate(fixed_angle, expand=True, resample=Image.BICUBIC)
                    bbox2 = img.getbbox()
                    if bbox2: img = img.crop(bbox2)
                # 0度：不旋转，也不走PCA
                img = img.rotate(fixed_angle, expand=True, resample=Image.BICUBIC)
                bbox2 = img.getbbox()
                if bbox2: img = img.crop(bbox2)
            else:
                # 其他品类：PCA 50%保留自然感
                xs, ys = [], []
                for y in range(0, img.height, 3):
                    for x in range(0, img.width, 3):
                        if img.getpixel((x, y))[3] > 200:
                            xs.append(x); ys.append(y)
                if len(xs) > 100:
                    cx = sum(xs)/len(xs); cy = sum(ys)/len(ys)
                    xx = sum((x-cx)**2 for x in xs)
                    yy = sum((y-cy)**2 for y in ys)
                    xy = sum((xs[i]-cx)*(ys[i]-cy) for i in range(len(xs)))
                    if xx != yy:
                        import math
                        angle = math.degrees(0.5 * math.atan2(2*xy, xx-yy))
                        if abs(angle) > 1.0:
                            img = img.rotate(-angle * 0.5, expand=True, resample=Image.BICUBIC)
                            bbox2 = img.getbbox()
                            if bbox2: img = img.crop(bbox2)

    ow, oh = img.size
    img_ratio = oh / ow

    # 选最接近的标准比例
    ratios = {'1:1': 1.0, '3:4': 1.333, '4:3': 0.75}
    best = min(ratios, key=lambda k: abs(ratios[k] - img_ratio))
    card_ratio = ratios[best]

    # 卡片尺寸：长边 = base_size，短边按标准比例
    if card_ratio >= 1.0:  # 1:1 或 3:4，高≥宽
        card_h = base_size
        card_w = int(base_size / card_ratio)
    else:  # 4:3，宽>高
        card_w = base_size
        card_h = int(base_size * card_ratio)

    pad = 12
    inner_w = card_w - pad * 2
    inner_h = card_h - pad * 2

    # 图片缩放：适配 inner 内，留 10% 呼吸空间
    scale = min(inner_w / ow, inner_h / oh) * 0.9
    img_w = int(ow * scale)
    img_h = int(oh * scale)

    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img = img.resize((img_w, img_h), Image.LANCZOS)

    # 画布
    card = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))

    # 阴影
    sh = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [(4, 6), (card_w-5, card_h-5)], radius=14, fill=(0, 0, 0, 18)
    )
    card.paste(sh.filter(ImageFilter.GaussianBlur(radius=8)), (0, 0), sh)

    # 纯白底
    ww, wh = card_w - 6, card_h - 6
    white = Image.new('RGBA', (ww, wh), (255, 255, 255, 255))
    wm = Image.new('L', (ww, wh), 0)
    ImageDraw.Draw(wm).rounded_rectangle(
        [(2, 2), (ww-3, wh-3)], radius=12, fill=255
    )
    white.putalpha(wm)
    card.paste(white, (3, 3), white)

    # 居中贴入
    ox = (card_w - img_w) // 2
    oy = (card_h - img_h) // 2
    card.paste(img, (ox, oy), img)

    # 边框
    bd = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle(
        [(4, 4), (card_w-5, card_h-5)], radius=11,
        outline=accent_color + (140,), width=2
    )
    card.paste(bd, (0, 0), bd)

    return card

    card = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))

    # 阴影
    sh = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [(4, 6), (card_w-5, card_h-5)], radius=14, fill=(0, 0, 0, 18)
    )
    card.paste(sh.filter(ImageFilter.GaussianBlur(radius=8)), (0, 0), sh)

    # 纯白底
    white_w, white_h = card_w - 6, card_h - 6
    white = Image.new('RGBA', (white_w, white_h), (255, 255, 255, 255))
    wm = Image.new('L', (white_w, white_h), 0)
    ImageDraw.Draw(wm).rounded_rectangle(
        [(2, 2), (white_w-3, white_h-3)], radius=12, fill=255
    )
    white.putalpha(wm)
    card.paste(white, (3, 3), white)

    # 贴衣服
    card.paste(img, (pad, pad), img)

    # 边框
    bd = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle(
        [(4, 4), (card_w-5, card_h-5)], radius=11,
        outline=accent_color + (140,), width=2
    )
    card.paste(bd, (0, 0), bd)

    return card


# ====== 主排版 ======
def composite(outfit_dir, output_path):
    ai_path = find_ai_image(outfit_dir)
    if not ai_path: return None
    items = parse_outfit_md(outfit_dir)
    if not items: return None
    items.sort(key=lambda x: CATEGORY_ORDER.index(x['prefix']) if x['prefix'] in CATEGORY_ORDER else 99)

    ai_img = Image.open(ai_path).convert('RGB')
    ai_w, ai_h = ai_img.size
    bg_color, accent = extract_colors(ai_path)

    items_dir = os.path.join(os.path.dirname(ai_path), '..', 'items')
    if not os.path.exists(items_dir):
        items_dir = os.path.join(os.path.dirname(os.path.dirname(ai_path)), 'items')

    # 画布
    frame = 12  # AI 图白框
    margin = int(ai_w * 0.24)
    canvas_w = ai_w + 2*frame + margin*2
    canvas_h = ai_h + 2*frame + 80
    canvas = Image.new('RGB', (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    # AI 图白框
    ai_x, ai_y = margin + frame, 60 + frame
    border_box = [(ai_x-frame, ai_y-frame), (ai_x+ai_w+frame-1, ai_y+ai_h+frame-1)]
    draw.rectangle(border_box, fill=(255,255,255), outline=accent+(60,), width=1)
    canvas.paste(ai_img, (ai_x, ai_y))

    # 标题
    font_title = load_font(22)
    outfit_name = os.path.basename(outfit_dir).split('_',1)[-1] if '_' in os.path.basename(outfit_dir) else ''
    title = outfit_name or '穿搭单品'
    tw = draw.textbbox((0,0), title, font_title)[2]
    draw.text(((canvas_w-tw)//2, 20), title, font=font_title, fill=(55,55,52))

    # 字体
    font_id = load_font(14)
    font_name = load_font(11)

    # 左右分配
    mid = (len(items)+1)//2
    left_items = items[:mid]
    right_items = items[mid:]

    core_sz = int(margin * 0.85)
    acc_sz = int(core_sz * 0.6)
    label_h = 42  # 标签区高度

    def col(col_items, side_x, side):
        n = len(col_items)
        if n == 0: return
        base_sizes = [core_sz if it['prefix'] in CORE_PREFIXES else acc_sz for it in col_items]
        # 预估卡片高度（3:4最多，按1.25估算）
        est_heights = [int(s * 1.25) for s in base_sizes]
        total = sum(h + label_h for h in est_heights) + (n-1)*14
        avail = ai_h - 20
        if total > avail:
            scale = avail / total
            base_sizes = [max(100, int(s*scale)) for s in base_sizes]
            est_heights = [int(s * 1.25) for s in base_sizes]
            total = sum(h + label_h for h in est_heights) + (n-1)*14
        gap = max(8, (avail - total)//(n+1))
        cy = ai_y + gap
        max_w = max(base_sizes) if base_sizes else margin

        for item, base_sz in zip(col_items, base_sizes):
            ip = find_best_image(items_dir, item)
            if not ip:
                cy += base_sz + label_h + gap; continue
            obj = render_card(ip, base_sz, accent, item['prefix'])
            cw, ch = obj.width, obj.height

            # 列内右对齐（左侧列贴AI框） / 左对齐（右侧列贴AI框）
            if side == 'left':
                sx = ai_x - frame - 8 - cw  # 卡片右边贴AI框
            else:
                sx = ai_x + ai_w + frame + 8  # 卡片左边贴AI框
            sx = max(4, min(canvas_w - cw - 4, sx))
            canvas.paste(obj, (sx, cy), obj)

            draw.text((sx+8, cy+ch+4), item['id'], font=font_id, fill=(55,55,52))
            draw.text((sx+8, cy+ch+24), item['name'][:10], font=font_name, fill=(150,150,145))
            cy += ch + label_h + gap

    col(left_items, 0, 'left')
    col(right_items, canvas_w, 'right')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path, 'JPEG', quality=92)
    return canvas.size


# ====== 贴纸模式：衣服直接放在 AI 图上 ======
def sticker_mode(outfit_dir, output_path):
    """抠图衣服 + 白描边 + 投影，直接贴到 AI 图的非人物区域"""
    ai_path = find_ai_image(outfit_dir)
    if not ai_path: return None
    items = parse_outfit_md(outfit_dir)
    if not items: return None

    ai_img = Image.open(ai_path).convert('RGBA')
    ai_w, ai_h = ai_img.size
    items_dir = os.path.join(os.path.dirname(ai_path), '..', 'items')
    if not os.path.exists(items_dir):
        items_dir = os.path.join(os.path.dirname(os.path.dirname(ai_path)), 'items')

    # 按身体部位分散放置，同侧自动偏移
    base_positions = {
        'HAT-': (0.50, 0.03, 'top'),
        'SUN-': (0.85, 0.06, 'right'),
        'JK-': (0.04, 0.20, 'left'),
        'TS-': (0.04, 0.35, 'left'),
        'LS-': (0.04, 0.35, 'left'),
        'SHIRT-': (0.04, 0.35, 'left'),
        'TANK-': (0.04, 0.35, 'left'),
        'SH-': (0.04, 0.58, 'left'),
        'PT-': (0.04, 0.58, 'left'),
        'SHOE-': (0.35, 0.94, 'bottom'),
        'SOCK-': (0.62, 0.90, 'bottom'),
        'BAG-': (0.90, 0.48, 'right'),
        'ACC-': (0.90, 0.32, 'right'),
    }
    placements = {}
    for item in items:
        pos = base_positions.get(item['prefix'], (0.5, 0.5, 'left'))
        placements[item['id']] = pos

    # 渲染贴纸
    canvas = ai_img.copy()
    font_label = load_font(12)
    sticker_sz = int(ai_w * 0.13)  # 约 266px

    for item in items:
        ip = find_best_image(items_dir, item)
        if not ip: continue

        img = Image.open(ip); img = ImageOps.exif_transpose(img)
        if img.mode == 'RGBA':
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
                # 严格收紧
                pxls = img.load()
                l,t,r,b=0,0,img.width,img.height
                while l<r and max(pxls[l,y][3] for y in range(0,img.height,3))<200: l+=1
                while r>l and max(pxls[r-1,y][3] for y in range(0,img.height,3))<200: r-=1
                while t<b and max(pxls[x,t][3] for x in range(0,img.width,3))<200: t+=1
                while b>t and max(pxls[x,b-1][3] for x in range(0,img.width,3))<200: b-=1
                if l<r and t<b: img = img.crop((l,t,r,b))

        # 缩放
        ow, oh = img.size
        ratio = (sticker_sz - 16) / max(ow, oh)
        nw, nh = int(ow*ratio), int(oh*ratio)
        img = img.resize((nw, nh), Image.LANCZOS)
        if img.mode != 'RGBA': img = img.convert('RGBA')

        # 白描边：alpha膨胀
        from PIL import ImageChops
        stroke = 4
        alpha = img.split()[-1]
        dilated = Image.new('L', alpha.size, 0)
        for dx in range(-stroke, stroke+1):
            for dy in range(-stroke, stroke+1):
                if dx*dx + dy*dy <= stroke*stroke:
                    shifted = Image.new('L', alpha.size, 0)
                    shifted.paste(alpha, (dx, dy))
                    dilated = ImageChops.lighter(dilated, shifted)

        white_stroke = Image.new('RGBA', (nw, nh), (255,255,255,0))
        white_stroke.putalpha(dilated)
        white_stroke.paste(img, (0,0), img)

        # 投影 + 组装
        pad_s=8
        sticker = Image.new('RGBA', (nw+pad_s*2, nh+pad_s*2), (0,0,0,0))
        sh = Image.new('RGBA', sticker.size, (0,0,0,0))
        ImageDraw.Draw(sh).rectangle([(pad_s+2,pad_s+4),(pad_s+nw-1,pad_s+nh-1)], fill=(0,0,0,40))
        sticker.paste(sh.filter(ImageFilter.GaussianBlur(5)), (0,0), sh)
        sticker.paste(white_stroke, (pad_s, pad_s), white_stroke)

        # 位置：按身体部位，同侧自动偏移避免重叠
        pos = placements.get(item['id'])
        if pos:
            px, py, side = pos
            # 根据边决定锚点对齐方式
            if side == 'left':
                cx = int(px * ai_w) + 4
                cy = int(py * ai_h) - sticker.height//2
            elif side == 'right':
                cx = int(px * ai_w) - sticker.width - 4
                cy = int(py * ai_h) - sticker.height//2
            elif side == 'top':
                cx = int(px * ai_w) - sticker.width//2
                cy = int(py * ai_h) + 4
            else:  # bottom
                cx = int(px * ai_w) - sticker.width//2
                cy = int(py * ai_h) - sticker.height - 4
        else:
            cx = (ai_w - sticker.width)//2
            cy = ai_h - sticker.height - 20
        cx = max(4, min(ai_w-sticker.width-4, cx))
        cy = max(4, min(ai_h-sticker.height-4, cy))

        canvas.paste(sticker, (cx, cy), sticker)
        ImageDraw.Draw(canvas).text((cx+4, cy+sticker.height-16), item['id'], font=font_label, fill=(255,255,255))

    result = canvas.convert('RGB')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result.save(output_path, 'JPEG', quality=92)
    return result.size


def main():
    print("=" * 50)
    print("👔 穿搭排版合成")

    if len(sys.argv) > 1:
        outfit_dir = sys.argv[1]
        if not os.path.isabs(outfit_dir): outfit_dir = os.path.join(BASE_DIR,'..',outfit_dir)
        outfit_dir = os.path.abspath(outfit_dir)
    else:
        outfit_dir = find_latest_outfit()

    if not outfit_dir or not os.path.exists(outfit_dir):
        print("❌ 未找到"); sys.exit(1)

    print(f"📁 {os.path.basename(outfit_dir)}")
    items = parse_outfit_md(outfit_dir)
    print(f"📋 {len(items)} 件")

    ai_path = find_ai_image(outfit_dir)
    if not ai_path: print("❌ 无效果图"); sys.exit(1)

    ai_dir = os.path.dirname(ai_path)
    base = os.path.splitext(os.path.basename(ai_path))[0]

    # 卡片排版
    out_card = os.path.join(ai_dir, f"{base}_排版.jpg")
    sz = composite(outfit_dir, out_card)
    if sz: print(f"💾 卡片版 {os.path.basename(out_card)} ({sz[0]}x{sz[1]})")

    # 贴纸版
    out_sticker = os.path.join(ai_dir, f"{base}_贴纸版.jpg")
    sz2 = sticker_mode(outfit_dir, out_sticker)
    if sz2: print(f"💾 贴纸版 {os.path.basename(out_sticker)} ({sz2[0]}x{sz2[1]})")

    print("✅ 完成")

if __name__ == '__main__':
    main()
