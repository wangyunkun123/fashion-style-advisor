#!/usr/bin/env python3
"""穿搭排版 v2 方案1 — ACOC Lookbook 直角网格风"""
import os, sys, re, glob, math, json, base64, urllib.request, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTFIT_BASE = os.path.join(BASE_DIR, '..', 'outfits')
WARDROBE_ENHANCED = os.path.join(BASE_DIR, '..', 'wardrobe', 'enhanced')
CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.local.json')
def _get_ark_key():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f).get('api_key', '')
    return os.environ.get('ARK_API_KEY', '')

BASE_DIR_FONTS = os.path.dirname(os.path.abspath(__file__))
FONTS = {
    # 时尚杂志标题 — Didot (Vogue同款) + Cormorant Garamond
    'title_cn': '/System/Library/Fonts/Supplemental/Songti.ttc',
    'title_en': '/System/Library/Fonts/Supplemental/Didot.ttc',
    'luxury':   os.path.join(BASE_DIR_FONTS, '..', 'fonts', 'CormorantGaramond-Bold.ttf'),
    # 正文 — Georgia + 细黑
    'body_cn':  '/System/Library/Fonts/STHeiti Light.ttc',
    'body_en':  '/System/Library/Fonts/Supplemental/Georgia.ttf',
    # 标签/辅助 — 黑体
    'label':    '/System/Library/Fonts/STHeiti Medium.ttc',
}

def font(size, style='body_cn'):
    p = FONTS.get(style, FONTS['body_cn'])
    if os.path.exists(p): return ImageFont.truetype(p, size)
    # fallback
    for fp in FONTS.values():
        if os.path.exists(fp): return ImageFont.truetype(fp, size)
    return ImageFont.load_default()
CAT_ORDER = ["HAT-","SUN-","JK-","TS-","LS-","SHIRT-","TANK-","SH-","PT-","ACC-","BAG-","SHOE-","SOCK-"]

def prep(path, prefix, w, h):
    img=Image.open(path); img=ImageOps.exif_transpose(img)
    if img.mode=='RGBA':
        bb=img.getbbox()
        if bb:
            img=img.crop(bb)
            px=img.load(); l,t,r,b=0,0,img.width,img.height
            while l<r and max(px[l,y][3] for y in range(0,img.height,3))<200: l+=1
            while r>l and max(px[r-1,y][3] for y in range(0,img.height,3))<200: r-=1
            while t<b and max(px[x,t][3] for x in range(0,img.width,3))<200: t+=1
            while b>t and max(px[x,b-1][3] for x in range(0,img.width,3))<200: b-=1
            if l<r and t<b: img=img.crop((l,t,r,b))
    ow,oh=img.size; ir=oh/ow
    ratios={'1:1':1.0,'3:4':1.333,'4:3':0.75}
    best=min(ratios,key=lambda k:abs(ratios[k]-ir)); cr=ratios[best]
    pad=18; iw,ih=w-pad*2,h-pad*2
    scale=min(iw/ow,ih/oh)*0.82; nw,nh=int(ow*scale),int(oh*scale)
    if img.mode!='RGBA': img=img.convert('RGBA')
    img=img.resize((nw,nh),Image.LANCZOS)
    fixed={'HAT-':0,'JK-':0,'TS-':-10,'LS-':-8,'SHIRT-':-8,'TANK-':-8}.get(prefix)
    if fixed is not None and fixed!=0: img=img.rotate(fixed,expand=True,resample=Image.BICUBIC)
    elif fixed is None:
        xs,ys=[],[]
        for y in range(0,img.height,3):
            for x in range(0,img.width,3):
                if img.getpixel((x,y))[3]>200: xs.append(x);ys.append(y)
        if len(xs)>100:
            cx=sum(xs)/len(xs);cy=sum(ys)/len(ys)
            xx=sum((x-cx)**2 for x in xs);yy=sum((y-cy)**2 for y in ys)
            xy=sum((xs[i]-cx)*(ys[i]-cy) for i in range(len(xs)))
            if xx!=yy:
                a=math.degrees(0.5*math.atan2(2*xy,xx-yy))
                if abs(a)>1.0: img=img.rotate(-a*0.5,expand=True,resample=Image.BICUBIC)
    if img.mode=='RGBA':
        bb=img.getbbox()
        if bb: img=img.crop(bb)
    return img

def parse(d):
    md=os.path.join(d,'outfit.md')
    if not os.path.exists(md): return []
    # 读取 JSON 标签获取品牌（用于精简显示名）
    tags_dir=os.path.join(BASE_DIR,'..','wardrobe','tags')
    brand_map={}
    try:
        for fname in os.listdir(tags_dir):
            if not fname.endswith('.json') or fname=='SCORE_CACHE.json': continue
            with open(os.path.join(tags_dir,fname)) as f: td=json.load(f)
            cid=td.get('clothing_id','')
            if cid:
                b=td.get('brand',{}) or {}
                brand_map[cid]=(b.get('name','') or '').strip()
    except: pass

    def short_name(iid,iname):
        """构建精简显示名：品牌 + 品类，控在14字内"""
        brand=brand_map.get(iid,'')
        # 品类词提取 — 保留运动/场景关键词
        cat_word=''
        for full in ['网球鞋','跑步鞋','训练鞋','帆布鞋','篮球鞋','足球鞋','工装靴',
                     '运动短裤','跑步短裤','休闲短裤','速干短袖','运动短袖','运动背心',
                     'Polo衫','棒球帽','渔夫帽','托特包','桶包','运动背包','运动表带',
                     '拖鞋','短袜','墨镜','发带']:
            if full in iname:
                cat_word=full; break
        if not cat_word:
            for tail,short in [('短袖','短袖'),('长袖','长袖'),('短裤','短裤'),('长裤','长裤'),
                               ('衬衫','衬衫'),('卫衣','卫衣'),('外套','外套'),('背心','背心'),
                               ('帽','帽'),('包','包'),('袜','袜'),('鞋','鞋'),('镜','墨镜'),('表','表')]:
                if tail in iname[-4:]:
                    cat_word=short; break
        if not cat_word:
            cat_word=''

        if brand and brand!='未知':
            # Decathlon 子品牌用简称
            for parent,sub in [('Decathlon Artengo','Artengo'),('Decathlon Kiprun','Kiprun')]:
                if brand==parent: brand=sub
            # Apple Watch 显示表带类型
            if iid == 'ACC-003':
                band = ''
                for b in ['回环尼龙','米兰尼斯','运动表带','黑色运动']:
                    if b in iname:
                        band = b; break
                display = f'{brand} {band}' if band else f'{brand} {cat_word}'
            else:
                display = f'{brand} {cat_word}' if cat_word else brand
            if len(display) > 16:
                return brand[:16]
            return display
        # 无品牌
        if len(iname) <= 16: return iname
        return iname[:14] + '…'
    with open(md,encoding='utf-8') as f: lines=f.readlines()
    in_sec,items=False,[]
    for line in lines:
        if '穿搭方案' in line or '单品清单' in line: in_sec=True; continue
        if in_sec and line.strip().startswith('##') and '穿搭方案' not in line and '单品清单' not in line: break
        if not in_sec: continue
        s=line.strip()
        if not s.startswith('|') or '---' in s: continue
        cells=[c.strip() for c in s.split('|')]
        if len(cells)<4: continue
        iid=cells[2].replace('**','').strip(); iname=cells[3].strip()
        if iid in ('单品ID','ID','') or not re.match(r'^[A-Z]+-\d+',iid): continue
        dname=short_name(iid,iname)
        items.append({'id':iid,'name':iname,'display_name':dname,'prefix':iid.split('-')[0]+'-'})
    return items

def find_ai(d):
    # 参考图前缀（用户照片 + 服装抠图），这些不是 AI 生图结果
    REF_PREFIXES = ('人物_', '上衣_', '下装_', '鞋子_', '帽子_', '包_', '墨镜_', '袜子_', '配饰_')
    for sub in ['generated','上身效果']:
        sd=os.path.join(d,sub)
        if not os.path.exists(sd): continue
        files = sorted(os.listdir(sd))
        for f in files:
            if f.lower().endswith(('.jpg','.jpeg','.png')) and not f.startswith('.') and not f.startswith('_'): return os.path.join(sd,f)
    # 豆包生图目录：排除参考图，只取 AI 生图结果
    sd=os.path.join(d,'豆包生图')
    if os.path.exists(sd):
        files = sorted(os.listdir(sd))
        for f in files:
            if not f.lower().endswith(('.jpg','.jpeg','.png')): continue
            if f.startswith('.') or f.startswith('_'): continue
            if any(f.startswith(p) for p in REF_PREFIXES): continue
            return os.path.join(sd, f)

def find_img(dd,item):
    for f in sorted(os.listdir(dd)):
        if f.startswith(item['id']+'_') and f.lower().endswith(('.jpg','.jpeg','.png')): orig=f; break
    else: return None
    base=os.path.splitext(orig)[0]
    for p in [os.path.join(dd,base+'_cutout.png'),os.path.join(WARDROBE_ENHANCED,orig),os.path.join(dd,orig)]:
        if os.path.exists(p): return p

def parse_style_info(outfit_dir):
    """从outfit.md提取风格笔记（每行一条，用于 STYLE NOTES）"""
    md=os.path.join(outfit_dir,'outfit.md')
    if not os.path.exists(md): return []
    with open(md,encoding='utf-8') as f: text=f.read()
    lines=text.split('\n')
    notes=[]

    # 策略1：读取 "## 风格笔记" 或 "## 风格关键词" 小节（每行一条笔记）
    for section_tag in ['风格笔记', '风格关键词']:
        in_section = False
        for line in lines:
            if section_tag in line:
                in_section = True
                # 同行冒号后的内容作为第一条
                m = re.search(r'[：:]\s*(.+)', line)
                if m:
                    v = m.group(1).strip().replace('**', '')
                    if v:
                        notes.append(v)
                continue
            if in_section:
                if line.strip().startswith('##') or line.strip().startswith('---'):
                    break
                s = line.strip().lstrip('- ').strip()
                if s:
                    notes.append(s)
        if notes:
            return notes[:5]

    # 策略2：回退——从元数据组装
    # 提取风格名
    style_name = ''
    for line in lines:
        if '风格' in line and '关键词' not in line and '故事' not in line and '笔记' not in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m:
                style_name = re.sub(r'[（(][^）)]*[）)]', '', m.group(1)).strip()
                break

    # 提取天气/场景
    weather = ''
    occasion = ''
    for line in lines:
        if '天气' in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m: weather = m.group(1).strip()[:12]  # 截断以适配卡片
        if '场景' in line or '场合' in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m: occasion = m.group(1).strip()[:12]

    if style_name:
        notes.append(f'{style_name}风格')
    if weather:
        notes.append(f'适合{weather}')
    if occasion:
        notes.append(f'{occasion}穿搭')

    # 从单品表格提取风格提示（选品理由列）
    reasons = []
    in_table = False
    for line in lines:
        if '单品清单' in line:
            in_table = True; continue
        if in_table and (line.startswith('##') or line.startswith('---')):
            break
        if in_table and line.startswith('|') and '---' not in line:
            cells = [c.strip().replace('**', '') for c in line.split('|')]
            if len(cells) >= 6:
                reason = cells[5]  # A线表格第6列是选品理由
            elif len(cells) >= 5:
                reason = cells[4]  # B线表格第5列是选品理由
            else:
                continue
            if reason and reason not in ('选品理由', '') and True:  # no length limit (wrapping)
                reasons.append(reason)
    # 取前2条作为风格提示
    for r in reasons[:2]:
        if r not in notes:
            notes.append(r)

    return notes[:5]


def wrap_text(text, font, max_width):
    """中文换行：标点处优先断，行首不留标点"""
    PUNCT = '，,.。、：；！？'
    lines = []
    line = ''
    for ch in text:
        test = line + ch
        if font.getbbox(test)[2] <= max_width:
            line = test
        else:
            if line:
                cut = len(line)
                for p in PUNCT:
                    idx = line.rfind(p, max(0, len(line)-10))
                    if idx > 0 and font.getbbox(line[:idx+1])[2] <= max_width:
                        cut = min(cut, idx+1)
                lines.append(line[:cut])
                rest = line[cut:].lstrip(PUNCT)
                line = rest
            if ch not in PUNCT:
                line += ch
    if line.strip():
        lines.append(line)
    return lines
def composite(ai_path,items,output_path):
    ai_img=Image.open(ai_path).convert('RGB'); ai_w,ai_h=ai_img.size
    dd=os.path.join(os.path.dirname(ai_path),'..','items')
    if not os.path.exists(dd): dd=os.path.join(os.path.dirname(os.path.dirname(ai_path)),'items')
    si=sorted(items,key=lambda x:CAT_ORDER.index(x['prefix']) if x['prefix'] in CAT_ORDER else 99)
    # 左右均衡分列
    total=len(si); left_n=(total+1)//2; right_n=total-left_n
    left_items=si[:left_n]; right_items=si[left_n:]

    GAP=8; BORDER=1; MARGIN=48
    ai_display_w=ai_w; ai_display_h=ai_h
    cell_w=520; n=max(left_n,right_n,3)
    cell_h=(ai_display_h-GAP*(n-1))//n

    TITLE_H=20; NOTE_H=72; NOTE_GAP=8
    cw=margin_x=MARGIN
    canvas_w=cw+cell_w+GAP+ai_display_w+GAP+cell_w+cw

    # 顶部 STYLE NOTES 横条
    outfit_dir=os.path.dirname(ai_path)
    if 'generated' in outfit_dir or '上身效果' in outfit_dir:
        outfit_dir=os.path.dirname(outfit_dir)
    style_kw=parse_style_info(outfit_dir)
    f_item=font(24,'body_cn'); f_item_sm=font(20,'body_cn'); f_mini=font(22,'body_en')
    has_notes=bool(style_kw)

    top_offset=TITLE_H
    if has_notes:
        top_offset+=NOTE_H+NOTE_GAP
    top_y=MARGIN+top_offset

    canvas_h=top_y+ai_display_h+MARGIN+60
    canvas=Image.new('RGB',(canvas_w,canvas_h),(252,252,250))
    draw=ImageDraw.Draw(canvas)

    # 渲染顶部 STYLE NOTES
    if has_notes:
        note_y=MARGIN; note_h=NOTE_H; note_w=canvas_w-MARGIN*2
        note_x=MARGIN
        # 卡片背景
        canvas.paste((252,250,247),(note_x,note_y,note_x+note_w,note_y+note_h))
        # 左侧深色装饰条
        draw.rectangle([(note_x,note_y),(note_x+3,note_y+note_h-1)],fill=(58,48,40))
        # 底边细线
        draw.line([(note_x,note_y+note_h-1),(note_x+note_w,note_y+note_h-1)],fill=(200,198,193),width=1)
        # 标题
        title_font=font(14,'body_en')
        draw.text((note_x+18,note_y+12),'STYLE NOTES',font=title_font,fill=(140,138,135))
        # 内容——每行一个关键词，用稍大字号
        kw_font=font(22,'body_cn')
        tx=note_x+18; ty=note_y+36
        line_h=28
        for kw in style_kw:
            kw_text=f'· {kw}'
            kw_w=kw_font.getbbox(kw_text)[2]
            if tx+kw_w>note_x+note_w-24:
                tx=note_x+18; ty+=line_h
            # 仅两行，超出省略
            if ty>note_y+note_h-8: break
            draw.text((tx,ty),kw_text,font=kw_font,fill=(80,78,75))
            tx+=kw_w+20

    # 底部信息
    footer_text='FASHION STYLE ADVISOR'
    date_str=os.path.basename(outfit_dir)[:10] if outfit_dir else ''
    if date_str: footer_text+=f' / {date_str}'

    # 左列
    lx=cw; ly=top_y
    for it in left_items:
        box_w=cell_w; box_h=cell_h
        canvas.paste((255,255,255),(lx,ly,lx+box_w,ly+box_h))
        ip=find_img(dd,it)
        if ip:
            cloth=prep(ip,it['prefix'],box_w,box_h)
            ox=lx+(box_w-cloth.width)//2; oy=ly+(box_h-cloth.height)//2
            canvas.paste(cloth,(ox,oy),cloth)
        draw.rectangle([(lx,ly),(lx+box_w-1,ly+box_h-1)],outline=(189,189,184),width=BORDER)
        dname=it.get('display_name',it['name'][:16])
        fn=f_item_sm if len(dname)>12 else f_item
        draw.text((lx+14,ly+box_h-42),dname,font=fn,fill=(80,80,78))
        ly+=box_h+GAP

    # 中：AI人物大图
    ai_x=cw+cell_w+GAP; ai_y=top_y
    canvas.paste((255,255,255),(ai_x,ai_y,ai_x+ai_display_w,ai_y+ai_display_h))
    canvas.paste(ai_img,(ai_x,ai_y))
    draw.rectangle([(ai_x,ai_y),(ai_x+ai_display_w-1,ai_y+ai_display_h-1)],outline=(189,189,184),width=BORDER)

    # 右列
    rx=ai_x+ai_display_w+GAP; ry=top_y
    for it in right_items:
        box_w=cell_w; box_h=cell_h
        canvas.paste((255,255,255),(rx,ry,rx+box_w,ry+box_h))
        ip=find_img(dd,it)
        if ip:
            cloth=prep(ip,it['prefix'],box_w,box_h)
            ox=rx+(box_w-cloth.width)//2; oy=ry+(box_h-cloth.height)//2
            canvas.paste(cloth,(ox,oy),cloth)
        draw.rectangle([(rx,ry),(rx+box_w-1,ry+box_h-1)],outline=(189,189,184),width=BORDER)
        dname=it.get('display_name',it['name'][:16])
        fn=f_item_sm if len(dname)>12 else f_item
        draw.text((rx+14,ry+box_h-42),dname,font=fn,fill=(80,80,78))
        ry+=box_h+GAP

    # 底部配色色块 — 从单品抠图取主色（主服饰优先，显著差异配饰也纳入）
    cache_file=os.path.join(os.path.dirname(output_path),'.color_cache.json')
    top_colors=[]
    if os.path.exists(cache_file):
        try:
            cached=json.loads(open(cache_file).read())
            top_colors=[tuple(c) for c in cached]
        except: pass
    if not top_colors:
        try:
            # 主服饰优先，然后按品类遍历
            priority=['TS-','TANK-','LS-','SHIRT-','SH-','PT-','SHOE-','HAT-','BAG-','SOCK-','ACC-','SUN-']
            main_cats={'TS-','TANK-','LS-','SHIRT-','SH-','PT-','SHOE-'}
            item_colors=[]  # (r,g,b, is_main)
            for prefix in priority:
                for it in items:
                    if not it['id'].startswith(prefix): continue
                    ip=find_img(dd,it)
                    if not ip: continue
                    try:
                        cloth=Image.open(ip).convert('RGBA')
                        cloth=cloth.resize((80,80),Image.LANCZOS)
                        px=cloth.load()
                        r_vals,g_vals,b_vals=[],[],[]
                        for y in range(cloth.height):
                            for x in range(cloth.width):
                                r,g,b,a=px[x,y]
                                if a>100 and max(r,g,b)>20 and max(r,g,b)<245:
                                    r_vals.append(r); g_vals.append(g); b_vals.append(b)
                        if len(r_vals)>20:
                            r_vals.sort(); g_vals.sort(); b_vals.sort()
                            mr=r_vals[len(r_vals)//2]; mg=g_vals[len(g_vals)//2]; mb=b_vals[len(b_vals)//2]
                            item_colors.append((mr,mg,mb,prefix in main_cats))
                    except: pass

            def color_dist(a,b):
                return abs(a[0]-b[0])+abs(a[1]-b[1])+abs(a[2]-b[2])

            # 第一轮：取主服饰（去重）
            merged=[]
            for c in item_colors:
                if not c[3]: continue  # 跳过配饰
                if any(color_dist(c,mc)<50 for mc in merged): continue
                merged.append(c[:3])
            # 第二轮：取与已有色差异>80的配饰色（显著跳色）
            for c in item_colors:
                if c[3]: continue  # 主服饰已取完
                if len(merged)>=5: break
                if all(color_dist(c,mc)>=80 for mc in merged):
                    merged.append(c[:3])
            top_colors=merged[:5]
            if top_colors:
                open(cache_file,'w').write(json.dumps(top_colors))
        except Exception:
            pass
    if not top_colors:
        top_colors=[(40,40,38),(180,180,178),(120,120,118),(220,220,218),(80,80,78)]
    swatch_y=canvas_h-60; swatch_x=cw
    swatch_sz=24; swatch_gap=6
    draw.text((swatch_x,swatch_y-24),'COLOR PALETTE',font=f_mini,fill=(150,150,148))
    for i,(r,g,b) in enumerate(top_colors):
        sx=swatch_x+i*(swatch_sz+swatch_gap)
        draw.rectangle([(sx,swatch_y),(sx+swatch_sz-1,swatch_y+swatch_sz-1)],fill=(r,g,b),outline=(200,200,198),width=1)
    draw.text((swatch_x+len(top_colors)*(swatch_sz+swatch_gap)+12,swatch_y-2),footer_text,font=f_mini,fill=(170,170,168))

    canvas.save(output_path,'JPEG',quality=90)
    return (canvas_w,canvas_h)

def main():
    print("="*50); print("👔 方案1 ACOC网格风")
    if len(sys.argv)>1:
        d=sys.argv[1]
        if not os.path.isabs(d): d=os.path.join(BASE_DIR,'..',d)
        d=os.path.abspath(d)
    else:
        dirs=sorted([x for x in os.listdir(OUTFIT_BASE) if os.path.isdir(os.path.join(OUTFIT_BASE,x)) and not x.startswith('.')],
                   key=lambda x: os.path.getctime(os.path.join(OUTFIT_BASE, x)))
        d=os.path.join(OUTFIT_BASE,dirs[-1]) if dirs else None
    if not d or not os.path.exists(d): print("❌"); sys.exit(1)
    items=parse(d); ai=find_ai(d)
    if not ai or not items: print("❌"); sys.exit(1)
    ad=os.path.dirname(ai); base=os.path.splitext(os.path.basename(ai))[0]
    out=os.path.join(ad,f"{base}_方案1.jpg")
    sz=composite(ai,items,out)
    if sz: print(f"💾 {os.path.basename(out)} ({sz[0]}x{sz[1]}) ✅")

if __name__=='__main__': main()
