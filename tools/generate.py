#!/usr/bin/env python3
"""
Seedream API 自动生图（两轮接力版）
Pass 1: 人物 + 上衣 + 下装 + 鞋子 → 基础穿搭
Pass 2: Pass1最佳图 + 帽子 + 包 + 墨镜 + 袜子 + 配饰 → 精确配饰
通过火山引擎 API 调用 Seedream 5.0 Lite 模型
"""
import os, sys, json, base64, urllib.request, time, io
from PIL import Image

# ── 确保项目根目录在 sys.path（子进程需要）──
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# ── 多用户支持 ──
import sys as _sys
_USER_ID = None
for _i, _arg in enumerate(_sys.argv[1:]):
    if _arg == '--user' and _i + 1 < len(_sys.argv) - 1:
        _USER_ID = _sys.argv[_i + 2]
        break
    elif _arg.startswith('--user='):
        _USER_ID = _arg.split('=', 1)[1]
        break

if _USER_ID:
    from tools.common import resolve_user_dir, resolve_outfits_dir, resolve_wardrobe_dir
    _USER_DIR = resolve_user_dir(_USER_ID)
else:
    _USER_DIR = None

# ===== 加载配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.json')
LOCAL_CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config', 'seedream.local.json')

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

if os.path.exists(LOCAL_CONFIG_FILE):
    with open(LOCAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
        local = json.load(f)
    config.update(local)

API_KEY = config['api_key']
API_URL = config['api_url']
MODEL = config['model']
SIZE = config['size']
MAX_IMAGES = config['max_images']

if _USER_ID:
    OUTFIT_BASE = resolve_outfits_dir(_USER_ID)
else:
    OUTFIT_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outfits')

# 抠图补底色：浅色单品用深灰、深色单品用浅灰，保证参考图始终有足够对比度
# （浅色单品贴近白灰底会糊掉细节，导致 Seedream 看不清单品 → 还原度低）
LIGHT_BG = (217, 217, 217)   # 浅灰，衬深色单品
DARK_BG = (64, 64, 64)       # 深灰，衬浅色单品
BRIGHTNESS_THRESHOLD = 130   # 单品不透明区平均亮度高于此值 → 判为浅色 → 用深灰底


def find_latest_outfit():
    dirs = sorted([d for d in os.listdir(OUTFIT_BASE)
                   if os.path.isdir(os.path.join(OUTFIT_BASE, d)) and not d.startswith('.')])
    return os.path.join(OUTFIT_BASE, dirs[-1]) if dirs else None


def compress_image(path, max_size=1024, quality=70):
    """压缩图片为 base64。透明 PNG 自适应补底：浅色单品补深灰、深色单品补浅灰"""
    img = Image.open(path)
    # 处理透明通道：根据单品自身亮度选补底色，保证对比度
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        # 计算不透明区域（单品本体）的平均亮度
        px = img.load()
        w0, h0 = img.size
        step = max(1, min(w0, h0) // 100)  # 采样步长，避免大图逐像素太慢
        total, count = 0, 0
        for y in range(0, h0, step):
            for x in range(0, w0, step):
                r, g, b, a = px[x, y]
                if a > 30:  # 只统计不透明像素
                    total += 0.299 * r + 0.587 * g + 0.114 * b
                    count += 1
        avg_lum = total / count if count else 128
        bg_color = DARK_BG if avg_lum > BRIGHTNESS_THRESHOLD else LIGHT_BG
        bg = Image.new('RGB', img.size, bg_color)
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode not in ('RGB',):
        img = img.convert('RGB')
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


def collect_core_images(doubao_dir):
    """Pass 1 核心参考图：人物（所有）+ 上衣 + 下装 + 鞋子"""
    images = []
    # 收集所有人物参考照（全身正面 + 面部近照 + 侧面），最多3张
    person_count = 0
    for f in sorted(os.listdir(doubao_dir)):
        if f.startswith("人物_") and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            images.append(os.path.join(doubao_dir, f))
            person_count += 1
            if person_count >= 3:
                break
    for prefix in ['上衣_', '下装_', '鞋子_']:
        for f in sorted(os.listdir(doubao_dir)):
            if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
                images.append(os.path.join(doubao_dir, f))
                break
    return images


def collect_accessory_images(doubao_dir):
    """Pass 2 配饰参考图：帽子 + 包 + 墨镜 + 袜子 + 配饰"""
    images = []
    for prefix in ['帽子_', '包_', '墨镜_', '袜子_', '配饰_']:
        for f in sorted(os.listdir(doubao_dir)):
            if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
                images.append(os.path.join(doubao_dir, f))
                break
    return images


def get_item_descriptions(doubao_dir):
    """从参考图文件名提取配饰描述（用于 Pass 2 prompt）"""
    descs = {}
    for prefix, label in [('帽子_', 'hat'), ('包_', 'bag'), ('墨镜_', 'sunglasses'),
                           ('袜子_', 'socks'), ('配饰_', 'accessory')]:
        for f in sorted(os.listdir(doubao_dir)):
            if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
                # 提取文件名中描述部分
                name = f[len(prefix):]
                name = os.path.splitext(name)[0][:40]
                descs[label] = name
                break
    return descs


def load_prompt(doubao_dir):
    pf = os.path.join(doubao_dir, "豆包提示词.txt")
    if os.path.exists(pf):
        with open(pf, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""


def convert_to_anchor_prompt(prompt):
    """女装专用锚点模式：将服装详细描述替换为最小锚点，让参考图主导还原。
    解决问题：女装的剪裁/廓形/细节用文字描述不准确，反而导致"平均化坍缩"。
    策略：摄影/人物/场景 详细写 → 稳定锚；服装 → 交给参考图。"""
    import re
    ANCHOR = (
        "She wears exactly the dress, top, bottom, sneakers, hat and bag shown in the reference images. "
        "Match their color, shape, fabric texture, button details, cut lines, seams and brand logos precisely. "
    )
    # 识别服装段：从 (She|she) (wears|is wearing) 或 [Pp]aired with 开始，到句子末
    garment_pattern = re.compile(
        r'\b([Ss]he (wears|is wearing)|[Pp]aired with).*?\.\s*',
        re.DOTALL
    )
    prompt = garment_pattern.sub(ANCHOR, prompt, count=1)
    # 兜底：如果没匹配到，在 "full body shot" 前插入
    if ANCHOR[:40] not in prompt and "full body shot" in prompt:
        prompt = prompt.replace("full body shot", ANCHOR + "full body shot")
    return prompt


def call_seedream(prompt, image_paths, max_images=None):
    """调用 Seedream API"""
    if max_images is None:
        max_images = MAX_IMAGES

    print(f"📷 编码 {len(image_paths)} 张参考图...")
    refs = []
    for i, path in enumerate(image_paths):
        b64 = compress_image(path)
        refs.append(b64)
        print(f"   [{i+1}] ✅ {os.path.basename(path)[:50]} ({len(b64)//1024}KB)")

    print(f"\n🎨 调用 {MODEL}...")
    print(f"📝 Prompt ({len(prompt)}字符): {prompt[:150]}...")

    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "image": refs,               # 官方参数名: image（非 reference_images）
        "size": SIZE,
        "response_format": "url",
        "watermark": False,
        "max_images": max_images,
    }).encode('utf-8')

    req = urllib.request.Request(API_URL, data=payload, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    })

    # 网络抖动/超时/5xx 时重试（4xx 参数错误不重试）
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.request.HTTPError as e:
            body = e.read().decode('utf-8')[:500]
            print(f"❌ API 错误 ({e.code}): {body}")
            if e.code and 400 <= e.code < 500:
                return None  # 客户端错误重试无意义
            last_err = f"HTTP {e.code}"
        except Exception as e:
            print(f"❌ 请求失败 (尝试 {attempt+1}/3): {e}")
            last_err = str(e)
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    print(f"❌ Seedream 3 次尝试均失败: {last_err}")
    return None


def download_results(result, output_dir, prefix="上身效果"):
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
            fname = f"{prefix}_{i+1}.png"
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
    print("🎨 Seedream API 两轮接力生图")
    print("=" * 60)

    # ── 参数解析 ──
    anchor_mode = False
    keyword = None
    _skip_next = False
    for _idx, arg in enumerate(sys.argv[1:]):
        if _skip_next:
            _skip_next = False
            continue
        if arg == '--anchor':
            anchor_mode = True
        elif arg == '--user':
            _skip_next = True  # 跳过 --user 后面的值，避免被当成 keyword
        elif arg.startswith('--'):
            continue
        elif keyword is None:
            keyword = arg

    outfit_dir = None
    if keyword:
        dirs = sorted([d for d in os.listdir(OUTFIT_BASE)
                       if os.path.isdir(os.path.join(OUTFIT_BASE, d)) and keyword in d],
                      key=lambda d: os.path.getctime(os.path.join(OUTFIT_BASE, d)))
        if dirs:
            outfit_dir = os.path.join(OUTFIT_BASE, dirs[-1])
            print(f"🔍 关键词匹配: {dirs[-1]}")

    if not outfit_dir:
        outfit_dir = find_latest_outfit()
    if not outfit_dir:
        print("❌ 未找到穿搭文件夹")
        return

    doubao_dir = os.path.join(outfit_dir, "豆包生图")
    if not os.path.exists(doubao_dir):
        doubao_dir = outfit_dir

    print(f"\n📁 {os.path.basename(outfit_dir)}")

    core_images = collect_core_images(doubao_dir)
    accessory_images = collect_accessory_images(doubao_dir)
    prompt = load_prompt(doubao_dir)

    if not core_images:
        print("❌ 未找到核心参考图（人物/上衣/下装/鞋子）")
        return
    if not prompt:
        print("❌ 未找到提示词")
        return

    # ── 锚点模式（女装专用）：替换服装详细描述为最小锚点 ──
    if anchor_mode:
        prompt = convert_to_anchor_prompt(prompt)
        print(f"\n🔧 锚点模式已激活：服装描述 → 最小锚点")
        print(f"   prompt 服装段已替换为: \"Match their color, shape, fabric texture...\"")

    print(f"\n🧥 核心参考图: {len(core_images)} 张")
    for img in core_images:
        print(f"   ▸ {os.path.basename(img)}")
    if accessory_images:
        print(f"🎒 配饰参考图: {len(accessory_images)} 张")
        for img in accessory_images:
            print(f"   ▸ {os.path.basename(img)}")
    else:
        print(f"🎒 配饰参考图: 无（仅核心4件）")

    # ═══════════════════════════════════════════
    # Pass 1: 基础穿搭（人物 + 上衣 + 下装 + 鞋子）
    # ═══════════════════════════════════════════
    print(f"\n{'─' * 60}")
    print(f"🔄 Pass 1/2: 基础穿搭（{len(core_images)} 张参考图）")
    print(f"{'─' * 60}")

    # ── 人物身份保持：如果参考图包含人物照，在 prompt 前注入身份保持指令 ──
    has_person_ref = any('人物_' in os.path.basename(img) for img in core_images)
    if has_person_ref:
        identity_clause = (
            f"Image 1 is a reference photo of the person to portray. "
            f"Preserve their facial identity, skin tone, and body shape — "
            f"they are the model wearing this outfit. "
        )
        prompt = identity_clause + prompt

    start = time.time()
    result1 = call_seedream(prompt, core_images)

    if not result1:
        print("❌ Pass 1 失败，终止")
        return

    elapsed1 = int(time.time() - start)
    print(f"   ⏱ Pass 1 耗时: {elapsed1}秒")

    output_dir = os.path.join(outfit_dir, "上身效果")
    # 清空旧的上身效果图
    if os.path.exists(output_dir):
        import shutil
        shutil.rmtree(output_dir)

    downloaded1 = download_results(result1, output_dir, prefix="上身效果")

    if not downloaded1:
        print("❌ Pass 1 未下载到图片")
        return

    # 取第一张（通常最好）作为 Pass 2 的底图
    pass1_best = downloaded1[0]
    print(f"\n   🏆 Pass 1 最佳: {os.path.basename(pass1_best)}")

    # ═══════════════════════════════════════════
    # Pass 2: 配饰精确化（Pass1最佳 + 配饰图）
    # ═══════════════════════════════════════════
    result2 = None
    elapsed2 = 0
    if len(accessory_images) < 2:
        if len(accessory_images) == 1:
            print(f"\n{'─' * 60}")
            print(f"⏭️  仅1件配饰（{os.path.basename(accessory_images[0])}），合并到 Pass 1，跳过 Pass 2")
            print(f"{'─' * 60}")
            core_images.append(accessory_images[0])
        else:
            print(f"\n{'─' * 60}")
            print(f"⏭️  无配饰参考图，跳过 Pass 2")
            print(f"{'─' * 60}")
    else:
        print(f"\n{'─' * 60}")
        print(f"🔄 Pass 2/2: 配饰精确化（1张底图 + {len(accessory_images)} 张配饰）")
        print(f"{'─' * 60}")

        # 构建 Pass 2 的参考图列表：底图 + 配饰
        pass2_images = [pass1_best] + accessory_images
        print(f"   参考图: 1张底图 + {len(accessory_images)}张配饰 = {len(pass2_images)}张")

        # 构建 Pass 2 prompt：保持基础，精确配饰
        item_descs = get_item_descriptions(doubao_dir)
        accessory_hints = []
        for i, img in enumerate(accessory_images):
            basename = os.path.splitext(os.path.basename(img))[0]
            # 去掉前缀（帽子_/包_/墨镜_/袜子_/配饰_）
            for prefix in ['帽子_', '包_', '墨镜_', '袜子_', '配饰_']:
                if basename.startswith(prefix):
                    basename = basename[len(prefix):]
                    break
            accessory_hints.append(f"image {i+2} = {basename}")

        pass2_prompt = (
            f"Image 1 is a base outfit photo serving as the identity and style anchor. "
            f"Preserve the person's facial identity, skin tone, and the overall outfit "
            f"(top, dress, pants, shoes) shown in image 1 — these are the core to keep. "
            f"Match their exact cut, texture, and color. "
            f"However, you may subtly improve the pose, expression, camera angle, or "
            f"background to make the image more dynamic and editorial — avoid stiff "
            f"standing posture. A slight change in stance, hand position, or head tilt "
            f"is welcome if it adds natural energy. "
            f"Images 2-{len(pass2_images)} are reference cutouts of accessories to ADD or REFINE: "
            f"{'; '.join(accessory_hints)}. "
            f"Accurately render these specific accessories onto the person, matching "
            f"their exact shape, brand logo, color, material and size. Preserve all details. "
            f"The output should feel like a natural, more polished evolution of image 1 "
            f"— same person, same outfit, but more alive and editorial. "
            f"Fashion editorial photography, high quality, photorealistic."
        )

        start2 = time.time()
        result2 = call_seedream(pass2_prompt, pass2_images, max_images=2)

        if not result2:
            print("⚠️ Pass 2 失败，保留 Pass 1 结果")
        else:
            elapsed2 = int(time.time() - start2)
            print(f"   ⏱ Pass 2 耗时: {elapsed2}秒")

            # Pass 2 结果保存为 上身效果_1p2.png, _2p2.png
            downloaded2 = download_results(result2, output_dir, prefix="上身效果_p2")

            if downloaded2:
                # 把 Pass 2 最佳图也存为 上身效果_1.png（覆盖，作为最终效果图）
                final_best = downloaded2[0]
                final_name = os.path.join(output_dir, "上身效果_1.png")
                # 先备份 Pass1 的图
                pass1_backup = os.path.join(output_dir, "上身效果_p1_backup.png")
                os.rename(pass1_best, pass1_backup)
                # 复制 Pass2 最佳为最终图
                import shutil
                shutil.copy2(final_best, final_name)
                print(f"\n   🏆 最终效果图: 上身效果_1.png (来自 Pass 2)")
                print(f"   💾 Pass 1 备份: 上身效果_p1_backup.png")
                total_elapsed = elapsed1 + elapsed2
            else:
                total_elapsed = elapsed1
        total_elapsed = elapsed1 + elapsed2

    total_elapsed = elapsed1
    if accessory_images and result2:
        total_elapsed = elapsed1 + elapsed2

    # ── 汇总 ──
    print(f"\n{'=' * 60}")
    final_files = sorted([f for f in os.listdir(output_dir) if f.endswith('.png')])
    total_kb = sum(os.path.getsize(os.path.join(output_dir, f)) // 1024 for f in final_files)
    print(f"✅ 两轮生图完成！{len(final_files)} 张，{total_kb}KB，总耗时 {total_elapsed}秒")
    print(f"📁 {output_dir}")
    for f in final_files:
        print(f"   ▸ {f}")


if __name__ == '__main__':
    main()
