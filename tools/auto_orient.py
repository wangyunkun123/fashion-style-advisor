#!/usr/bin/env python3
"""
衣物方向自动检测与修正工具
使用豆包视觉模型判断衣服朝向（领口/上端方向），自动旋转到正向
"""
import os, sys, json, re, base64, time, urllib.request
from PIL import Image, ImageOps

# ===== 配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WARDROBE = os.path.join(BASE_DIR, '..', 'wardrobe')
LOCAL_CONFIG = os.path.join(BASE_DIR, '..', 'config', 'seedream.local.json')

API_KEY = None
API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
MODEL = "doubao-seed-2.0-code"

def _load_api_key():
    global API_KEY
    if API_KEY:
        return
    if os.path.exists(LOCAL_CONFIG):
        with open(LOCAL_CONFIG, 'r') as f:
            API_KEY = json.load(f).get('api_key', '')
    if not API_KEY:
        API_KEY = os.environ.get('ARK_API_KEY', '')

def encode_image(path, max_size=1024):
    """将图片编码为 base64，先缩放以节省 token"""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
    # 转为 RGB JPEG 编码
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    import io
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def ask_orientation(image_path):
    """
    调用豆包视觉模型判断衣服朝向
    返回: '上' | '下' | '左' | '右' | None(失败)
    """
    _load_api_key()
    b64 = encode_image(image_path)

    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "图片里是一件衣物/鞋子/配饰。请判断它的正常穿着方向上端"
                        "（衣领/裤腰/鞋口/帽顶/包口）在图片的哪个方向。"
                        "严格只回复一个字：上、下、左、右。不要解释。"
                    )
                }
            ]
        }],
        "max_tokens": 1000,
        "temperature": 0,
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            answer = result['choices'][0]['message']['content'].strip()
            # 从结论句中提取方向（避免"左右展开""上下颠倒"等描述干扰）
            # 模型通常会在最后给出明确结论
            import re
            # 优先级匹配：上端/朝向 + 在/朝 + 上/下/左/右
            m = re.search(r'(?:上端|朝向|顶端|方向).*?[在朝向是].*?([上下左右])', answer)
            if m:
                return m.group(1)
            # 回退：找 **上**方 / **下**方 等加粗标记
            m = re.search(r'\*\*([上下左右])\*\*', answer)
            if m:
                return m.group(1)
            # 最后回退：从末尾找第一个方向字（结论通常在末尾）
            for char in reversed(answer):
                if char in '上下左右':
                    return char
            print(f"     ⚠️ 模型返回无法解析: '{answer[:80]}'")
            return None
    except urllib.request.HTTPError as e:
        body = e.read().decode('utf-8')[:200]
        print(f"     ❌ API错误 {e.code}: {body}")
        return None
    except Exception as e:
        print(f"     ❌ 请求失败: {e}")
        return None

def fix_image(path, orientation):
    """
    根据朝向旋转图片到正向
    - 上: 方向正确，无需旋转
    - 下: 上下颠倒，旋转180°
    - 左: 上端在左侧，顺时针90°（PIL ROTATE_270）
    - 右: 上端在右侧，逆时针90°（PIL ROTATE_90）
    """
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)

    rotate_map = {
        '上': (0, None),
        '下': (180, Image.ROTATE_180),
        '左': (90, Image.ROTATE_270),   # 左→上需要顺时针90°=PIL ROTATE_270
        '右': (-90, Image.ROTATE_90),   # 右→上需要逆时针90°=PIL ROTATE_90
    }

    deg, transpose_op = rotate_map.get(orientation, (0, None))
    if transpose_op:
        img = img.transpose(transpose_op)
        img.save(path, quality=95)
    return deg

def main():
    print("=" * 60)
    print("👁️  衣物方向自动检测与修正")
    print(f"   模型: {MODEL}")
    print("=" * 60)

    # 收集所有图片
    images = []
    for root, dirs, files in os.walk(WARDROBE):
        for f in sorted(files):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')) and not f.startswith('.'):
                images.append(os.path.join(root, f))

    print(f"\n📦 共 {len(images)} 件衣物待检测\n")

    stats = {'上': 0, '下': 0, '左': 0, '右': 0, 'fail': 0}

    for i, path in enumerate(images, 1):
        rel = os.path.relpath(path, WARDROBE)
        print(f"[{i}/{len(images)}] {rel}")

        orientation = ask_orientation(path)

        if orientation is None:
            stats['fail'] += 1
            continue

        deg = fix_image(path, orientation)
        if deg == 0:
            print(f"     ✅ 朝向「{orientation}」无需旋转")
        else:
            print(f"     🔄 朝向「{orientation}」→ 旋转 {deg}°")
        stats[orientation] += 1

        # 限速：避免触发 API 频率限制
        time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"📊 检测结果:")
    print(f"   正向(上): {stats['上']} 件 — 无需处理")
    print(f"   颠倒(下): {stats['下']} 件 — 已旋转180°")
    print(f"   左偏(左): {stats['左']} 件 — 已旋转-90°")
    print(f"   右偏(右): {stats['右']} 件 — 已旋转+90°")
    if stats['fail']:
        print(f"   ❌ 失败:   {stats['fail']} 件")
    print(f"\n💡 以后添加新衣服后运行: python3 tools/auto_orient.py")

if __name__ == '__main__':
    main()
