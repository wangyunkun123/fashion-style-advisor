#!/usr/bin/env python3
"""为 styles_universal 中的每个风格搜索代表性穿搭图片。

用法:
  python3 tools/fetch_style_images.py              # 搜索所有风格
  python3 tools/fetch_style_images.py --style ID   # 仅搜索指定风格
  python3 tools/fetch_style_images.py --dry-run    # 仅搜索不下载
  python3 tools/fetch_style_images.py --max 5      # 每个风格最多下载5张
"""

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image
from ddgs import DDGS

PROJECT_DIR = Path(__file__).resolve().parent.parent
STYLES_UNIVERSAL = PROJECT_DIR / "styles_universal"
CATEGORIES_PATH = STYLES_UNIVERSAL / "categories.json"

# 风格 → 搜索关键词映射
# 优先使用专业术语 + men fashion outfit 组合
STYLE_SEARCH_QUERIES = {
    # 日系
    "japanese_city_boy": "Japanese City Boy Popeye magazine men fashion outfit street style",
    "japanese_yama": "Japanese Yama style outdoor men fashion mountain camping lookbook",
    "japanese_amekaji": "Japanese Amekaji americana vintage men fashion workwear outfit",
    "japanese_urahara": "Japanese Urahara Harajuku streetwear men fashion A Bathing Ape",
    "japanese_wabi_sabi": "Japanese wabi sabi minimal men fashion linen natural fabric outfit",
    "japanese_techwear": "Japanese techwear men fashion Acronym Nike ACG functional outfit",

    # 韩系
    "korean_clean_fit": "Korean clean fit men fashion minimal outfit neutral palette street style",
    "korean_light_mature": "Korean light mature men fashion business casual outfit office look",
    "korean_kpop_street": "Korean K-pop street style men fashion idol outfit oversize",
    "korean_minimal": "Korean minimal men fashion beige neutral outfit clean lines Seoul",

    # 美式
    "american_ivy_league": "American Ivy League prep style men fashion blazer chinos oxford shirt campus",
    "american_preppy": "American preppy men fashion Ralph Lauren polo chinos boat shoes outfit",
    "american_workwear": "American workwear men fashion Carhartt chore coat denim boots heritage outfit",
    "american_western": "American western cowboy style men fashion denim boots hat rugged outfit",
    "american_streetwear": "American streetwear men fashion Supreme Stussy hip hop urban outfit",

    # 英式
    "british_mod": "British Mod style men fashion 1960s slim suit parka Vespa scooter outfit",
    "british_punk": "British punk style men fashion leather jacket ripped jeans band tee outfit",
    "british_savile_row": "British Savile Row bespoke tailoring men fashion suit classic elegance",
    "british_heritage": "British heritage country style men fashion tweed Barbour waxed jacket outdoor",

    # 意式
    "italian_sprezzatura": "Italian Sprezzatura men fashion Pitti Uomo relaxed elegance tailored outfit",
    "italian_pitti_uomo": "Pitti Uomo men street style fashion Florence tailored suit double breasted",

    # 法式
    "french_parisian_chic": "French Parisian chic men fashion simple elegant Breton stripe tailored casual",

    # 中式
    "chinese_heritage_luxe": "Chinese heritage luxury men fashion silk traditional modern fusion outfit",
    "chinese_new_traditional": "New Chinese traditional men fashion modern qipao inspired contemporary outfit",

    # 北欧
    "scandi_minimalism": "Scandinavian minimal men fashion COS Acne Studios clean lines neutral outfit",

    # 澳洲
    "australian_surf_casual": "Australian surf casual men fashion beach relaxed linen shorts summer outfit",

    # 复古系
    "retro_rockabilly": "Rockabilly men fashion 1950s greaser denim leather jacket retro outfit",
    "retro_grunge": "Grunge men fashion 1990s Nirvana flannel ripped jeans band tee Kurt Cobain style",
    "retro_90s_hiphop": "90s hip hop men fashion baggy jeans oversized jersey Timberland boots street style",

    # 当代趋势
    "contemporary_gorpcore": "Gorpcore men fashion outdoor technical Arc'teryx Salomon hiking urban outfit",
    "contemporary_genderless": "Genderless fashion men fluid silhouette neutral androgynous contemporary outfit",

    # 场景风格
    "scene_tenniscore": "Tenniscore men fashion tennis sport style polo pleated shorts preppy athletic outfit",
    "scene_blokecore": "Blokecore men fashion football soccer jersey vintage sport casual terrace style",
    "scene_cocktail": "Cocktail attire men fashion evening semi formal blazer dress shirt event outfit",

    # 美学调性
    "aesthetic_avant_garde": "Avant garde men fashion runway Rick Owens Yohji Yamamoto experimental silhouette",
    "aesthetic_deconstructed": "Deconstructed men fashion Maison Margiela Rei Kawakubo avant garde experimental outfit",

    # 通用风格
    "clean_fit": "Clean fit men fashion minimal simple essential neutral outfit everyday style",
    "smart_casual": "Smart casual men fashion blazer chinos outfit business casual modern office",
    "athleisure_sport": "Athleisure sport men fashion Nike tech fleece joggers sneakers gym casual outfit",
    "streetwear": "Streetwear men fashion Supreme Off-White sneakerhead urban hype outfit 2024",
    "resort_vacation": "Resort vacation men fashion linen shirt shorts sandals tropical beach summer outfit",

    # 新兴风格 (2025-2026)
    "poetcore": "Poetcore men fashion romantic literary aesthetic soft flowing fabric vintage bohemian",
    "whimsymaxxing": "Whimsymaxxing men fashion maximalist playful colorful eclectic joyful outfit",
    "rugged_comfort": "Rugged comfort men fashion cozy practical outdoor flannel knit durable relaxed",
    "detention_core": "Detention core men fashion dark academia preppy rebellious uniform blazer tie school",
    "quarter_zip_revival": "Quarter zip revival men fashion retro 90s pullover knit smart casual preppy",
    "torpedo_sneakers": "Torpedo sneakers men fashion slim low profile retro running shoe Adidas Samba outfit",
    "regency_romantic": "Regency romantic men fashion Bridgerton inspired ruffled shirt waistcoat historical modern",
    "rugged_luxury": "Rugged luxury men fashion Loro Piana Brunello Cucinelli quiet luxury outdoor refined",
    "scene_gorpcore": "Gorpcore outdoor hiking tech wear men fashion functional Arc'teryx Patagonia urban nature",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


def load_style_names():
    """从 categories.json 加载风格名称映射"""
    names = {}
    if CATEGORIES_PATH.exists():
        with open(CATEGORIES_PATH) as f:
            data = json.load(f)
        registry = data.get("style_registry", {})
        for sid, info in registry.items():
            names[sid] = {
                "name_zh": info.get("name_zh", sid),
                "name_en": info.get("name_en", sid.replace("_", " ").title()),
            }
    # 补充未在 categories.json 中的风格
    for dirname in os.listdir(STYLES_UNIVERSAL):
        if dirname.startswith(".") or dirname.startswith("_"):
            continue
        if dirname not in names and os.path.isdir(STYLES_UNIVERSAL / dirname):
            names[dirname] = {
                "name_zh": dirname.replace("_", " ").title(),
                "name_en": dirname.replace("_", " ").title(),
            }
    return names


def search_images(query, max_results=10):
    """使用 DDGS 搜索图片，返回 [{title, image_url, thumbnail, source, width, height}]"""
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=max_results, license="any"):
                results.append({
                    "title": r.get("title", ""),
                    "image_url": r.get("image", ""),
                    "thumbnail": r.get("thumbnail", ""),
                    "source": r.get("source", ""),
                    "width": r.get("width", 0),
                    "height": r.get("height", 0),
                })
        time.sleep(1.5)  # rate limit
    except Exception as e:
        print(f"  ⚠ 搜索失败: {e}")
    return results


def download_image(url, timeout=15):
    """下载图片，返回 (PIL.Image, format) 或 (None, None)"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        fmt = img.format or "JPEG"
        # 转为 RGB（处理 RGBA/P 模式）
        if img.mode in ("RGBA", "P", "LA"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")
        return img, fmt
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        return None, None


def is_good_image(img, min_width=400, min_height=300):
    """检查图片质量"""
    if img is None:
        return False
    w, h = img.size
    if w < min_width or h < min_height:
        return False
    # 排除极端宽高比（如横幅广告、超长图）
    ratio = max(w, h) / min(w, h)
    if ratio > 4:
        return False
    return True


def fetch_style_images(style_id, max_images=5, dry_run=False):
    """为一个风格搜索并下载代表性图片"""
    style_dir = STYLES_UNIVERSAL / style_id
    if not style_dir.exists():
        print(f"  ⚠ 目录不存在: {style_dir}")
        return []

    query = STYLE_SEARCH_QUERIES.get(style_id, f"{style_id.replace('_', ' ')} men fashion outfit")
    print(f"  🔍 搜索: {query[:80]}...")

    results = search_images(query, max_results=max_images * 3)  # 多搜一些用于筛选
    print(f"  📸 找到 {len(results)} 张候选图片")

    if dry_run:
        for i, r in enumerate(results[:max_images]):
            print(f"    [{i+1}] {r['title'][:60]} | {r['source']} | {r['width']}×{r['height']}")
        return results

    downloaded = []
    for i, r in enumerate(results):
        if len(downloaded) >= max_images:
            break

        img_url = r.get("image_url", "")
        if not img_url or not img_url.startswith("http"):
            continue

        # 跳过明显是图标的
        if any(x in img_url.lower() for x in ["favicon", "icon-", "logo-", "avatar"]):
            continue

        print(f"    ⬇ [{len(downloaded)+1}/{max_images}] {r['title'][:50]}...")
        img, fmt = download_image(img_url)

        if img and is_good_image(img):
            # 保存为主图
            if len(downloaded) == 0:
                main_path = style_dir / "representative.jpg"
                img.save(main_path, "JPEG", quality=92)
                print(f"      ✅ 主图: {main_path.name} ({img.size[0]}×{img.size[1]})")

            # 所有图片存入 gallery/
            gallery_dir = style_dir / "gallery"
            gallery_dir.mkdir(exist_ok=True)
            img_path = gallery_dir / f"{style_id}_{len(downloaded)+1:02d}.jpg"
            img.save(img_path, "JPEG", quality=92)
            print(f"      ✅ 图库: {img_path.name} ({img.size[0]}×{img.size[1]})")

            downloaded.append({
                "filename": img_path.name if len(downloaded) > 0 else main_path.name,
                "source_url": img_url,
                "source": r.get("source", ""),
                "title": r.get("title", ""),
                "width": img.size[0],
                "height": img.size[1],
            })
        else:
            print(f"      ⏭ 跳过（质量不符合要求）")

        time.sleep(0.5)  # 下载间隔

    # 保存元数据
    if downloaded:
        meta_path = style_dir / "images_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"images": downloaded, "search_query": query}, f, ensure_ascii=False, indent=2)

    return downloaded


def main():
    parser = argparse.ArgumentParser(description="为风格百科搜集代表性穿搭图片")
    parser.add_argument("--style", help="仅处理指定风格ID")
    parser.add_argument("--max", type=int, default=5, help="每个风格最多下载图片数")
    parser.add_argument("--dry-run", action="store_true", help="仅搜索不下载")
    parser.add_argument("--delay", type=float, default=3.0, help="风格间延迟秒数")
    args = parser.parse_args()

    names = load_style_names()
    print(f"📚 风格总数: {len(names)}")

    if args.style:
        style_ids = [args.style]
    else:
        style_ids = sorted(names.keys())

    total = len(style_ids)
    success = 0
    total_images = 0

    for idx, style_id in enumerate(style_ids, 1):
        info = names.get(style_id, {})
        name_zh = info.get("name_zh", style_id)
        print(f"\n{'='*60}")
        print(f"[{idx}/{total}] {name_zh} ({style_id})")
        print(f"{'='*60}")

        try:
            downloaded = fetch_style_images(style_id, max_images=args.max, dry_run=args.dry_run)
            if downloaded:
                success += 1
                total_images += len(downloaded)
        except Exception as e:
            print(f"  ❌ 处理失败: {e}")

        if idx < total:
            print(f"  ⏳ 等待 {args.delay}s...")
            time.sleep(args.delay)

    print(f"\n{'='*60}")
    print(f"✅ 完成！成功: {success}/{total} 个风格，共 {total_images} 张图片")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
