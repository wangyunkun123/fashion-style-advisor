#!/usr/bin/env python3
"""Seedream 生图 — 2026-06-11 曼联运动风"""
import os, json, base64, urllib.request, time, io
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(BASE_DIR, '..')

with open(os.path.join(PROJECT, 'config', 'seedream.json'), 'r') as f:
    config = json.load(f)
with open(os.path.join(PROJECT, 'config', 'seedream.local.json'), 'r') as f:
    config.update(json.load(f))

API_KEY = config['api_key']
API_URL = config['api_url']
MODEL = config['model']
SIZE = config['size']
MAX_IMAGES = config['max_images']

OUTFIT_DIR = os.path.join(PROJECT, 'outfits', '2026-06-11_曼联运动风')
DOUBAO_DIR = os.path.join(OUTFIT_DIR, '豆包生图')
OUTPUT_DIR = os.path.join(OUTFIT_DIR, 'generated')

def compress_image(path, max_size=1024, quality=70):
    img = Image.open(path)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"

def main():
    print("=" * 60)
    print("🎨 Seedream API 生图 — 曼联运动风")
    print("=" * 60)

    # 收集参考图：人物、外套、上衣、下装、鞋子
    refs = []
    for prefix in ['人物_', '外套_', '上衣_', '下装_', '鞋子_']:
        for f in sorted(os.listdir(DOUBAO_DIR)):
            if f.startswith(prefix) and f.lower().endswith(('.jpg','.jpeg','.png')):
                refs.append(os.path.join(DOUBAO_DIR, f))
                break

    prompt_file = os.path.join(DOUBAO_DIR, '豆包提示词.txt')
    with open(prompt_file, 'r') as f:
        prompt = f.read().strip()

    print(f"\n📁 {os.path.basename(OUTFIT_DIR)}")
    print(f"📷 {len(refs)} 张参考图 | 📝 {len(prompt)}字符")
    for r in refs:
        print(f"   ▸ {os.path.basename(r)}")

    print(f"\n📷 编码参考图...")
    encoded = []
    for path in refs:
        b64 = compress_image(path)
        encoded.append(b64)
        print(f"   ✅ {os.path.basename(path)[:50]} ({len(b64)//1024}KB)")

    print(f"\n🎨 调用 {MODEL}...")
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "reference_images": encoded,
        "size": SIZE,
        "response_format": "url",
        "watermark": False,
        "max_images": MAX_IMAGES,
    }).encode('utf-8')

    req = urllib.request.Request(API_URL, data=payload, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    })

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.request.HTTPError as e:
        print(f"❌ API 错误 ({e.code}): {e.read().decode('utf-8')[:500]}")
        return
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return

    elapsed = int(time.time() - start)
    print(f"   ⏱ API 耗时: {elapsed}秒")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    downloaded = []

    if 'data' not in result:
        print(f"⚠️ 响应无图片: {json.dumps(result, ensure_ascii=False)[:500]}")
        return

    print(f"\n📥 下载到: {OUTPUT_DIR}")
    for i, item in enumerate(result['data']):
        url = item.get('url', '')
        if not url:
            continue
        try:
            fname = f"穿搭参考图_{i+1}.jpg"
            spath = os.path.join(OUTPUT_DIR, fname)
            urllib.request.urlretrieve(url, spath)
            sz = os.path.getsize(spath) // 1024
            downloaded.append(spath)
            print(f"   ✅ {fname} ({sz}KB)")
        except Exception as e:
            print(f"   ❌ {fname}: {e}")

    print(f"\n{'=' * 60}")
    if downloaded:
        total_kb = sum(os.path.getsize(d)//1024 for d in downloaded)
        print(f"✅ 生图完成！{len(downloaded)} 张，{total_kb}KB，总耗时 {elapsed}秒")
        for d in downloaded:
            print(f"   ▸ {os.path.basename(d)}")
    else:
        print(f"⚠️ 未获取到图片")

if __name__ == '__main__':
    main()
