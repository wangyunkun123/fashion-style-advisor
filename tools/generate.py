#!/usr/bin/env python3
"""
Seedream API 自动生图
通过火山引擎 API 调用 Seedream 5.0 Lite 模型生成穿搭效果图
"""

import os, json, base64, urllib.request, time, io
from PIL import Image

# ===== 加载配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.json')
LOCAL_CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.local.json')

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 合并本地密钥（不提交Git）
if os.path.exists(LOCAL_CONFIG_FILE):
    with open(LOCAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
        local = json.load(f)
    config.update(local)

API_KEY = config['api_key']
API_URL = config['api_url']
MODEL = config['model']
SIZE = config['size']
MAX_IMAGES = config['max_images']

OUTFIT_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outfits')

def find_latest_outfit():
    dirs = sorted([d for d in os.listdir(OUTFIT_BASE)
                   if os.path.isdir(os.path.join(OUTFIT_BASE, d)) and not d.startswith('.')])
    return os.path.join(OUTFIT_BASE, dirs[-1]) if dirs else None

def compress_image(path, max_size=1024, quality=70):
    """压缩图片为 base64"""
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

def collect_key_images(doubao_dir):
    """收集核心参考图：人物+上衣+下装+鞋子"""
    images = []
    for f in sorted(os.listdir(doubao_dir)):
        if f.startswith("人物_") and f.lower().endswith(('.jpg','.jpeg','.png')):
            images.append(os.path.join(doubao_dir, f))
            break
    for prefix in ['上衣_', '外搭_', '下装_', '鞋子_']:
        for f in sorted(os.listdir(doubao_dir)):
            if f.startswith(prefix) and f.lower().endswith(('.jpg','.jpeg','.png')):
                images.append(os.path.join(doubao_dir, f))
                break
    return images

def load_prompt(doubao_dir):
    pf = os.path.join(doubao_dir, "豆包提示词.txt")
    if os.path.exists(pf):
        with open(pf, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

def call_seedream(prompt, image_paths):
    """调用 Seedream API"""
    print(f"📷 编码 {len(image_paths)} 张参考图...")
    refs = []
    for path in image_paths:
        b64 = compress_image(path)
        refs.append(b64)
        print(f"   ✅ {os.path.basename(path)[:50]} ({len(b64)//1024}KB)")

    print(f"\n🎨 调用 {MODEL}...")
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "reference_images": refs,
        "size": SIZE,
        "response_format": "url",
        "watermark": False,
        "max_images": MAX_IMAGES,
    }).encode('utf-8')

    req = urllib.request.Request(API_URL, data=payload, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    })

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.request.HTTPError as e:
        print(f"❌ API 错误 ({e.code}): {e.read().decode('utf-8')[:500]}")
        return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def download_results(result, output_dir):
    """下载生成结果"""
    os.makedirs(output_dir, exist_ok=True)
    downloaded = []

    if 'data' not in result:
        print(f"⚠️ 响应无图片: {json.dumps(result, ensure_ascii=False)[:300]}")
        return downloaded

    for i, item in enumerate(result['data']):
        url = item.get('url', '')
        if not url:
            continue
        try:
            fname = f"上身效果_{i+1}.png"
            spath = os.path.join(output_dir, fname)
            urllib.request.urlretrieve(url, spath)
            sz = os.path.getsize(spath) // 1024
            downloaded.append(spath)
            print(f"   ✅ {fname} ({sz}KB)")
        except Exception as e:
            print(f"   ❌ {fname}: {e}")
    return downloaded

def main():
    print("=" * 60)
    print("🎨 Seedream API 自动生图")
    print("=" * 60)

    outfit_dir = find_latest_outfit()
    if not outfit_dir:
        print("❌ 未找到穿搭文件夹")
        return

    doubao_dir = os.path.join(outfit_dir, "豆包生图")
    if not os.path.exists(doubao_dir):
        doubao_dir = outfit_dir

    print(f"\n📁 {os.path.basename(outfit_dir)}")

    images = collect_key_images(doubao_dir)
    prompt = load_prompt(doubao_dir)

    if not images:
        print("❌ 未找到参考图")
        return
    if not prompt:
        print("❌ 未找到提示词")
        return

    print(f"📷 {len(images)} 张参考图 | 📝 {len(prompt)}字符")

    start = time.time()
    result = call_seedream(prompt, images)

    if not result:
        return

    elapsed = int(time.time() - start)
    print(f"   ⏱ API 耗时: {elapsed}秒")

    output_dir = os.path.join(outfit_dir, "上身效果")
    print(f"\n📥 下载到: {output_dir}")
    downloaded = download_results(result, output_dir)

    print(f"\n{'=' * 60}")
    if downloaded:
        total_kb = sum(os.path.getsize(d)//1024 for d in downloaded)
        print(f"✅ 生图完成！{len(downloaded)} 张，{total_kb}KB，总耗时 {elapsed}秒")
        print(f"📁 {output_dir}")
        for d in downloaded:
            print(f"   ▸ {os.path.basename(d)}")
    else:
        print(f"⚠️ 未获取到图片")

if __name__ == '__main__':
    main()
