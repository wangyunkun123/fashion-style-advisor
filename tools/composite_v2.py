#!/usr/bin/env python3
"""穿搭排版 v2 方案1 — ACOC Lookbook 直角网格风"""
import os, sys, re, glob, math, json, base64, urllib.request, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTFIT_BASE = os.path.join(BASE_DIR, '..', 'outfits')
WARDROBE_ENHANCED = os.path.join(BASE_DIR, '..', 'wardrobe', 'enhanced')
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
LABELS = list('ABCDEFGH')

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
    fixed={'HAT-':0,'JK-':10,'TS-':-10,'LS-':-8,'SHIRT-':-8,'TANK-':-8}.get(prefix)
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
    with open(md,encoding='utf-8') as f: lines=f.readlines()
    in_sec,items=False,[]
    for line in lines:
        if '穿搭方案' in line: in_sec=True; continue
        if in_sec and line.strip().startswith('##') and '穿搭方案' not in line: break
        if not in_sec: continue
        s=line.strip()
        if not s.startswith('|') or '---' in s: continue
        cells=[c.strip() for c in s.split('|')]
        if len(cells)<4: continue
        iid=cells[2].replace('**','').strip(); iname=cells[3].strip()
        if iid in ('单品ID','ID','') or not re.match(r'^[A-Z]+-\d+',iid): continue
        items.append({'id':iid,'name':iname,'prefix':iid.split('-')[0]+'-'})
    return items

def find_ai(d):
    for sub in ['generated','上身效果']:
        sd=os.path.join(d,sub)
        if not os.path.exists(sd): continue
        for f in sorted(os.listdir(sd)):
            if f.lower().endswith(('.jpg','.jpeg','.png')) and not f.startswith('.'): return os.path.join(sd,f)

def find_img(dd,item):
    for f in sorted(os.listdir(dd)):
        if f.startswith(item['id']+'_') and f.lower().endswith(('.jpg','.jpeg','.png')): orig=f; break
    else: return None
    base=os.path.splitext(orig)[0]
    for p in [os.path.join(dd,base+'_cutout.png'),os.path.join(WARDROBE_ENHANCED,orig),os.path.join(dd,orig)]:
        if os.path.exists(p): return p

def draw_label(draw,x,y,letter,sz=34):
    draw.rectangle([(x,y),(x+sz-1,y+sz-1)],fill=(60,60,58))
    f=font(22,'title_en'); tw=draw.textbbox((0,0),letter,f)[2]
    draw.text((x+(sz-tw)//2,y+3),letter,font=f,fill=(255,255,255))

def parse_style_info(outfit_dir):
    """从outfit.md提取风格关键词"""
    md=os.path.join(outfit_dir,'outfit.md')
    if not os.path.exists(md): return []
    with open(md,encoding='utf-8') as f: text=f.read()
    keywords=[]
    for line in text.split('\n'):
        if '风格关键词' in line or '风格' in line:
            # 提取冒号后的内容
            m=re.search(r'[：:]\s*(.+)',line)
            if m:
                for kw in re.split(r'[、,，/]',m.group(1)):
                    kw=kw.strip().replace('**','')
                    if kw and len(kw)<15: keywords.append(kw)
    return keywords[:5]

def composite(ai_path,items,output_path):
    ai_img=Image.open(ai_path).convert('RGB'); ai_w,ai_h=ai_img.size
    dd=os.path.join(os.path.dirname(ai_path),'..','items')
    if not os.path.exists(dd): dd=os.path.join(os.path.dirname(os.path.dirname(ai_path)),'items')
    si=sorted(items,key=lambda x:CAT_ORDER.index(x['prefix']) if x['prefix'] in CAT_ORDER else 99)
    main=[it for it in si if it['prefix'] in {'JK-','TS-','LS-','SHIRT-','TANK-','SH-','PT-','SHOE-'}]
    acc =[it for it in si if it['prefix'] in {'HAT-','SUN-','SOCK-','BAG-','ACC-'}]

    GAP=8; BORDER=1; MARGIN=48
    ai_display_w=ai_w; ai_display_h=ai_h
    cell_w=520; n=max(len(main),len(acc),1)
    cell_h=(ai_display_h-GAP*(n-1))//n

    # 标题栏高度
    TITLE_H=20  # A方案：极简留白，几乎无标题区

    cw=margin_x=MARGIN
    canvas_w=cw+cell_w+GAP+ai_display_w+GAP+cell_w+cw
    canvas_h=MARGIN+TITLE_H+ai_display_h+MARGIN+60
    canvas=Image.new('RGB',(canvas_w,canvas_h),(252,252,250))
    draw=ImageDraw.Draw(canvas)

    # 标题
    outfit_dir=os.path.dirname(ai_path)
    if 'generated' in outfit_dir or '上身效果' in outfit_dir:
        outfit_dir=os.path.dirname(outfit_dir)
    outfit=os.path.basename(outfit_dir).split('_',1)[-1] if '_' in os.path.basename(outfit_dir) else ''
    style_kw=parse_style_info(outfit_dir)
    f_item=font(28,'body_cn'); f_mini=font(22,'body_en')
    # C方案：底部小字标注
    footer_text='FASHION STYLE ADVISOR'
    date_str=os.path.basename(outfit_dir)[:10] if outfit_dir else ''
    if date_str: footer_text+=f' / {date_str}'

    top_y=MARGIN+TITLE_H

    # 左列：主衣服
    lx=cw; ly=top_y
    for it in main:
        box_w=cell_w; box_h=cell_h
        canvas.paste((255,255,255),(lx,ly,lx+box_w,ly+box_h))
        ip=find_img(dd,it)
        if ip:
            cloth=prep(ip,it['prefix'],box_w,box_h)
            ox=lx+(box_w-cloth.width)//2; oy=ly+(box_h-cloth.height)//2
            canvas.paste(cloth,(ox,oy),cloth)
        draw.rectangle([(lx,ly),(lx+box_w-1,ly+box_h-1)],outline=(189,189,184),width=BORDER)
        # 名称在卡片内底部
        draw.text((lx+14,ly+box_h-42),it['name'][:16],font=f_item,fill=(80,80,78))
        ly+=box_h+GAP

    # 中：AI人物大图
    ai_x=cw+cell_w+GAP; ai_y=top_y
    canvas.paste((255,255,255),(ai_x,ai_y,ai_x+ai_display_w,ai_y+ai_display_h))
    canvas.paste(ai_img,(ai_x,ai_y))
    draw.rectangle([(ai_x,ai_y),(ai_x+ai_display_w-1,ai_y+ai_display_h-1)],outline=(189,189,184),width=BORDER)

    # 右列：配饰
    rx=ai_x+ai_display_w+GAP; ry=top_y
    for it in acc:
        box_w=cell_w; box_h=cell_h
        canvas.paste((255,255,255),(rx,ry,rx+box_w,ry+box_h))
        ip=find_img(dd,it)
        if ip:
            cloth=prep(ip,it['prefix'],box_w,box_h)
            ox=rx+(box_w-cloth.width)//2; oy=ry+(box_h-cloth.height)//2
            canvas.paste(cloth,(ox,oy),cloth)
        draw.rectangle([(rx,ry),(rx+box_w-1,ry+box_h-1)],outline=(189,189,184),width=BORDER)
        draw.text((rx+14,ry+box_h-42),it['name'][:16],font=f_item,fill=(80,80,78))
        ry+=box_h+GAP

    # 右下文字卡片（填充空白）
    if ry < top_y+ai_display_h-20:
        info_h=top_y+ai_display_h-ry
        canvas.paste((255,255,255),(rx,ry,rx+cell_w,ry+info_h))
        draw.rectangle([(rx,ry),(rx+cell_w-1,ry+info_h-1)],outline=(189,189,184),width=BORDER)
        ty=ry+20
        if style_kw:
            draw.text((rx+16,ty),'STYLE NOTES',font=f_mini,fill=(140,140,138))
            ty+=36
            for kw in style_kw:
                draw.text((rx+16,ty),f'· {kw}',font=f_item,fill=(110,110,108))
                ty+=36
    # 底部：配色色块 — 从抠图衣服提取颜色（省token）
    # 底部：配色色块 — 豆包视觉识别
    top_colors=[]
    try:
        ai_tiny=ai_img.resize((int(ai_w*0.3),int(ai_h*0.3)),Image.LANCZOS).convert('RGB')
        buf=io.BytesIO(); ai_tiny.save(buf,format='JPEG',quality=70)
        b64=base64.b64encode(buf.getvalue()).decode('utf-8')
        payload={'model':'doubao-seed-2.0-code','messages':[{'role':'user','content':[
            {'type':'image_url','image_url':{'url':f'data:image/jpeg;base64,{b64}'}},
            {'type':'text','text':'列出这套穿搭的主要5个颜色，用Hex格式每行一个'}
        ]}],'max_tokens':2000,'temperature':0}
        data=json.dumps(payload).encode('utf-8')
        req=urllib.request.Request('https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions',
            data=data,headers={'Content-Type':'application/json',
            'Authorization':'Bearer ark-73c10b0a-0549-47fa-9811-39d37b6e452f-a7ac6'})
        with urllib.request.urlopen(req,timeout=60) as resp:
            result=json.loads(resp.read().decode('utf-8'))
            import re as re2
            hexes=re2.findall(r'#[0-9A-Fa-f]{6}',result['choices'][0]['message']['content'])
            for h in hexes[:5]:
                h=h.lstrip('#')
                top_colors.append((int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)))
    except: pass
    if not top_colors:
        top_colors=[(40,40,38),(180,180,178),(120,120,118),(220,220,218),(80,80,78)]
    swatch_y=canvas_h-60; swatch_x=cw
    swatch_sz=24; swatch_gap=6
    draw.text((swatch_x,swatch_y-24),'COLOR PALETTE',font=f_mini,fill=(150,150,148))
    for i,(r,g,b) in enumerate(top_colors):
        sx=swatch_x+i*(swatch_sz+swatch_gap)
        draw.rectangle([(sx,swatch_y),(sx+swatch_sz-1,swatch_y+swatch_sz-1)],fill=(r,g,b),outline=(200,200,198),width=1)
    draw.text((swatch_x+len(top_colors)*(swatch_sz+swatch_gap)+12,swatch_y-2),footer_text,font=f_mini,fill=(170,170,168))

    os.makedirs(os.path.dirname(output_path),exist_ok=True)
    canvas.save(output_path,'JPEG',quality=95)
    return canvas.size

def main():
    print("="*50); print("👔 方案1 ACOC网格风")
    if len(sys.argv)>1:
        d=sys.argv[1]
        if not os.path.isabs(d): d=os.path.join(BASE_DIR,'..',d)
        d=os.path.abspath(d)
    else:
        dirs=sorted([x for x in os.listdir(OUTFIT_BASE) if os.path.isdir(os.path.join(OUTFIT_BASE,x)) and not x.startswith('.')])
        d=os.path.join(OUTFIT_BASE,dirs[-1]) if dirs else None
    if not d or not os.path.exists(d): print("❌"); sys.exit(1)
    items=parse(d); ai=find_ai(d)
    if not ai or not items: print("❌"); sys.exit(1)
    ad=os.path.dirname(ai); base=os.path.splitext(os.path.basename(ai))[0]
    out=os.path.join(ad,f"{base}_方案1.jpg")
    sz=composite(ai,items,out)
    if sz: print(f"💾 {os.path.basename(out)} ({sz[0]}x{sz[1]}) ✅")

if __name__=='__main__': main()
