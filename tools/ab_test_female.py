#!/usr/bin/env python3
"""
女装还原度 A/B 实验：抠图补底 × 服装文字描述 的 4 组对照
只跑 Pass 1，每组生 1 张图，隔离单一变量。
"""
import os, sys, json, base64, io, urllib.request
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTFIT = os.path.join(BASE, "users/female/nan/outfits/2026-07-07_今日穿搭。")
DOUBAO = os.path.join(OUTFIT, "豆包生图")
OUT = os.path.join(OUTFIT, "AB实验")
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(BASE, "config/seedream.json")) as f:
    cfg = json.load(f)
lc = os.path.join(BASE, "config/seedream.local.json")
if os.path.exists(lc):
    with open(lc) as f:
        cfg.update(json.load(f))

API_KEY, API_URL, MODEL, SIZE = cfg["api_key"], cfg["api_url"], cfg["model"], cfg["size"]

# ── 参考图（全部单品，保证 4 组图片输入完全一致）──
REFS = ["人物_1.jpg", "连衣裙_DRESS-006.png", "鞋子_SHOE-003.png",
        "帽子_HAT-002.png", "包_BAG-013.png"]

# ── 身份保持前缀（与 generate.py 一致）──
IDENTITY = ("The person in the reference photo is the fixed model. Keep her face, "
            "facial features and identity exactly consistent; they are the model "
            "wearing this outfit. ")

# ── 三段式 prompt：前段（摄影+场景+人物+妆容）/ 服装段 / 尾段（景别）──
PREFIX = ("Editorial fashion photography shot with Fujifilm X-T5 35mm f/1.4 at low knee height, "
          "shallow depth of field, rule of thirds. Golden hour backlight casts soft warm rim light "
          "on a modern urban street with clean concrete walls and potted olive trees, candid "
          "effortlessly cool energy. Asian woman with long black straight hair styled into loose "
          "face-framing waves with side-parted fluffy roots, slight natural bedhead texture, walking "
          "mid-stride toward camera with one hand casually slipped into the dress pocket. She has dewy "
          "natural makeup with groomed natural brows, thin black winged liner, individual lashes, soft "
          "warm coral-red lips, and light sun-kissed bronze contour on high cheekbones, wearing a slight "
          "relaxed smile. ")
SUFFIX = " full body shot from head to toe."

GARMENT_FULL = ("She wears a light gray linen dress with V-neck, short cap sleeves, natural waistline "
                "with a subtle cinched fit, A-line midi-length skirt with visible natural slubs, soft "
                "wrinkles, and relaxed breathable drape. Paired with off-white smooth glossy leather Nike "
                "sneakers with round toes and flat soles, an oversized beige straw wide brim sun hat slightly "
                "angled right, and a dark gray minimalist Nike logo oversized large nylon tote bag carried "
                "over one shoulder with crisp swishy movement.")
GARMENT_ANCHOR = ("She wears exactly the dress, sneakers, straw sun hat and tote bag shown in the "
                  "reference images — match their color, shape, texture and details precisely.")
GARMENT_NONE = ""

LIGHT_BG, DARK_BG, THRESH = (217, 217, 217), (64, 64, 64), 130


def encode(path, adaptive):
    """adaptive=True 用自适应补底；False 用旧的固定浅灰(217)"""
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        if adaptive:
            px, (w, h) = img.load(), img.size
            step = max(1, min(w, h) // 100)
            tot = cnt = 0
            for y in range(0, h, step):
                for x in range(0, w, step):
                    r, g, b, a = px[x, y]
                    if a > 30:
                        tot += 0.299*r + 0.587*g + 0.114*b
                        cnt += 1
            avg = tot/cnt if cnt else 128
            bg_color = DARK_BG if avg > THRESH else LIGHT_BG
        else:
            bg_color = LIGHT_BG
        bg = Image.new("RGB", img.size, bg_color)
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > 1024:
        r = 1024/max(w, h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def call(prompt, refs):
    payload = json.dumps({
        "model": MODEL, "prompt": prompt, "image": refs, "size": SIZE,
        "response_format": "url", "watermark": False, "max_images": 1,
    }).encode()
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


GROUPS = [
    ("G1_旧图_详细文字", False, GARMENT_FULL),
    ("G2_新图_详细文字", True,  GARMENT_FULL),
    ("G3_新图_最小锚点", True,  GARMENT_ANCHOR),
    ("G4_新图_无服装描述", True, GARMENT_NONE),
]

for name, adaptive, garment in GROUPS:
    print(f"\n{'='*50}\n▶ {name}")
    refs = [encode(os.path.join(DOUBAO, f), adaptive) for f in REFS]
    prompt = IDENTITY + PREFIX + garment + SUFFIX
    print(f"  prompt尾段: ...{garment[:60]}..." if garment else "  (无服装描述)")
    try:
        res = call(prompt, refs)
        url = res["data"][0]["url"]
        out = os.path.join(OUT, f"{name}.png")
        urllib.request.urlretrieve(url, out)
        print(f"  ✅ 已存 {out} ({os.path.getsize(out)//1024}KB)")
    except Exception as e:
        print(f"  ❌ {e}")
        if hasattr(e, "read"):
            print(f"     {e.read().decode()[:300]}")

print(f"\n全部完成 → {OUT}")
