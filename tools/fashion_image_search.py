"""
Fashion Image Search — 免费服装图片搜索工具
=============================================
整合三个免费源：Pexels API | Unsplash API | DuckDuckGo（免 API）

用法:
    # 搜索服装图片（默认 DuckDuckGo，无需 API Key）
    python3 tools/fashion_image_search.py --query "men linen shirt summer"

    # 搜索穿搭灵感
    python3 tools/fashion_image_search.py --query "smart casual outfit men" --source unsplash --count 20

    # 多源同时搜索
    python3 tools/fashion_image_search.py --query "men summer outfit" --all-sources --count 10

    # 保存到指定目录
    python3 tools/fashion_image_search.py --query "linen shirt" --save ./search_results

    # 列出可用源
    python3 tools/fashion_image_search.py --list-sources
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

# ============================================================
# 配置
# ============================================================

# API Key 配置路径
CONFIG_PATH = Path(__file__).parent.parent / "config" / "seedream.local.json"

# 默认图片保存目录
DEFAULT_SAVE_DIR = Path(__file__).parent.parent / "search_results"

def _load_api_keys():
    """从配置加载 API Key"""
    keys = {"pexels": None, "unsplash": None}
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            keys["pexels"] = data.get("pexels_api_key")
            keys["unsplash"] = data.get("unsplash_api_key")
    except Exception:
        pass
    return keys

# ============================================================
# Pexels API（完全免费，200次/小时）
# ============================================================

def search_pexels(query, count=10, api_key=None):
    """
    搜索 Pexels 服装图片
    免费层：200 请求/小时
    无需信用卡注册：https://www.pexels.com/api/
    """
    if not api_key:
        return {"error": "需要 Pexels API Key。免费注册: https://www.pexels.com/api/"}

    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": min(count, 80),
        "orientation": "portrait",  # 适合穿搭展示
    }

    try:
        import requests
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for photo in data.get("photos", []):
            results.append({
                "source": "pexels",
                "id": photo["id"],
                "title": query,
                "url": photo["url"],
                "image_url": photo["src"]["large"],  # 中等尺寸
                "original_url": photo["src"]["original"],  # 原图
                "thumbnail": photo["src"]["tiny"],
                "photographer": photo["photographer"],
                "photographer_url": photo["photographer_url"],
                "alt": photo.get("alt", query),
                "width": photo["width"],
                "height": photo["height"],
            })
        return {"results": results, "total": data.get("total_results", 0)}
    except Exception as e:
        return {"error": f"Pexels 搜索失败: {e}"}


# ============================================================
# Unsplash API（完全免费，50次/小时）
# ============================================================

def search_unsplash(query, count=10, api_key=None):
    """
    搜索 Unsplash 服装/时尚图片
    免费层：50 请求/小时
    注册：https://unsplash.com/developers
    """
    if not api_key:
        return {"error": "需要 Unsplash API Key。免费注册: https://unsplash.com/developers"}

    url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {api_key}"}
    params = {
        "query": query,
        "per_page": min(count, 30),
        "orientation": "portrait",
        "content_filter": "high",
    }

    try:
        import requests
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for photo in data.get("results", []):
            results.append({
                "source": "unsplash",
                "id": photo["id"],
                "title": photo.get("description") or photo.get("alt_description") or query,
                "url": photo["links"]["html"],
                "image_url": photo["urls"]["regular"],
                "original_url": photo["urls"]["raw"],
                "thumbnail": photo["urls"]["thumb"],
                "photographer": photo["user"]["name"],
                "photographer_url": photo["user"]["links"]["html"],
                "alt": photo.get("alt_description", query),
                "width": photo["width"],
                "height": photo["height"],
            })
        return {"results": results, "total": data.get("total", 0)}
    except Exception as e:
        return {"error": f"Unsplash 搜索失败: {e}"}


# ============================================================
# Pinterest 抓取（无需 API）
# ============================================================

def search_duckduckgo(query, count=10):
    """
    DuckDuckGo 图片搜索（完全免费，无需 API Key，无限次数）
    通过 DuckDuckGo 图片搜索 API 获取结果
    """
    encoded = urllib.parse.quote(query)
    url = f"https://duckduckgo.com/i.js?q={encoded}&o=json&p=1&vqd="

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://duckduckgo.com/",
    }

    try:
        import requests
        # 第一步：获取 vqd 参数（DuckDuckGo 的反爬 token）
        html_url = f"https://duckduckgo.com/?q={encoded}&t=h_&ia=images"
        sess = requests.Session()
        sess.headers.update(headers)
        html_resp = sess.get(html_url, timeout=15)

        import re
        vqd_match = re.search(r'vqd=([\d-]+)', html_resp.text)
        if not vqd_match:
            # 尝试从 script 标签提取
            vqd_match = re.search(r'"vqd":"([\d-]+)"', html_resp.text)

        vqd = vqd_match.group(1) if vqd_match else ""

        # 第二步：搜索图片
        search_url = f"https://duckduckgo.com/i.js"
        params = {
            "q": query,
            "o": "json",
            "p": "1",
            "vqd": vqd,
            "f": ",,,",
        }
        resp = sess.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for i, img in enumerate(data.get("results", [])[:count]):
            img_url = img.get("image") or img.get("thumbnail") or ""
            if img_url:
                results.append({
                    "source": "duckduckgo",
                    "id": img.get("id", f"ddg_{i}"),
                    "title": img.get("title", query),
                    "url": img.get("url", ""),
                    "image_url": img_url,
                    "thumbnail": img.get("thumbnail", img_url),
                    "photographer": img.get("source", "DuckDuckGo"),
                    "photographer_url": img.get("url", ""),
                    "alt": img.get("title", query),
                    "width": img.get("width", 0),
                    "height": img.get("height", 0),
                })

        return {"results": results, "total": data.get("total", len(results))}
    except Exception as e:
        return {"error": f"DuckDuckGo 搜索失败: {e}"}


# ============================================================
# 保存图片到本地
# ============================================================

def download_image(item, save_dir):
    """下载单张图片到本地目录"""
    import requests

    img_url = item["image_url"]
    if not img_url:
        return None

    try:
        resp = requests.get(img_url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        # 生成文件名
        ext = img_url.split(".")[-1].split("?")[0]
        if ext.lower() not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        safe_query = item.get("title", "fashion")[:30]
        filename = f"{item['source']}_{item['id']}_{safe_query}.{ext}"
        # 清理非法字符
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        filepath = save_dir / filename

        with open(filepath, "wb") as f:
            f.write(resp.content)

        return str(filepath)
    except Exception as e:
        return None


# ============================================================
# CLI 入口
# ============================================================

SOURCES_INFO = {
    "pexels": {
        "name": "Pexels",
        "free_tier": "200 次/小时，无需信用卡",
        "api_key_required": True,
        "register_url": "https://www.pexels.com/api/",
        "description": "高质量免费图库，时尚/穿搭图片丰富",
    },
    "unsplash": {
        "name": "Unsplash",
        "free_tier": "50 次/小时，无需信用卡",
        "api_key_required": True,
        "register_url": "https://unsplash.com/developers",
        "description": "高质街拍/时尚摄影，适合穿搭灵感",
    },
    "duckduckgo": {
        "name": "DuckDuckGo",
        "free_tier": "无限次，无需 API Key",
        "api_key_required": False,
        "register_url": None,
        "description": "免费无限制图片搜索，覆盖全网服装图片（替代 Pinterest）",
    },
}

SEARCH_FUNCTIONS = {
    "pexels": lambda q, c, k: search_pexels(q, c, api_key=k),
    "unsplash": lambda q, c, k: search_unsplash(q, c, api_key=k),
    "duckduckgo": lambda q, c, k: search_duckduckgo(q, c),
}


def main():
    parser = argparse.ArgumentParser(
        description="👕 免费服装图片搜索工具（Pexels / Unsplash / Pinterest）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 tools/fashion_image_search.py --query "men linen shirt" --source pexels
  python3 tools/fashion_image_search.py --query "summer outfit" --all-sources --count 5
  python3 tools/fashion_image_search.py --query "city boy style" --source pinterest --save ./灵感图
  python3 tools/fashion_image_search.py --list-sources
        """,
    )
    parser.add_argument("--query", "-q", type=str, help="搜索关键词（支持中英文）")
    parser.add_argument("--source", "-s", type=str, choices=["pexels", "unsplash", "duckduckgo"],
                        default="duckduckgo", help="图片来源（默认 duckduckgo，无需 API Key）")
    parser.add_argument("--all-sources", "-a", action="store_true", help="所有源同时搜索")
    parser.add_argument("--count", "-n", type=int, default=10, help="每源返回数量")
    parser.add_argument("--save", type=str, help="下载图片到本地目录")
    parser.add_argument("--list-sources", "-l", action="store_true", help="列出可用图片来源")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    # 列出源信息
    if args.list_sources:
        print("\n📸 可用的免费服装图片来源：\n")
        for key, info in SOURCES_INFO.items():
            print(f"  {key:12s} — {info['name']}")
            print(f"             {info['description']}")
            print(f"             免费: {info['free_tier']}")
            if info["api_key_required"]:
                print(f"             注册: {info['register_url']}")
            else:
                print(f"             无需注册，直接可用")
            print()
        return

    if not args.query:
        parser.print_help()
        print("\n❌ 请提供 --query 搜索关键词")
        sys.exit(1)

    # 加载 API Keys
    keys = _load_api_keys()

    # 确定要搜索的源
    if args.all_sources:
        sources = ["pexels", "unsplash", "duckduckgo"]
    else:
        sources = [args.source]

    all_results = []
    for src in sources:
        info = SOURCES_INFO[src]
        if info["api_key_required"] and not keys.get(src):
            msg = f"⚠️  {src}: 跳过（需要 API Key，免费注册: {info['register_url']}）"
            print(msg, file=sys.stderr)
            continue

        print(f"🔍 正在搜索 [{src}]: {args.query} ...", file=sys.stderr)
        result = SEARCH_FUNCTIONS[src](args.query, args.count, keys.get(src))

        if "error" in result:
            print(f"❌ {src}: {result['error']}", file=sys.stderr)
            continue

        items = result["results"]
        print(f"✅ {src}: 找到 {len(items)} 张图片\n", file=sys.stderr)
        all_results.extend(items)

    if not all_results:
        print("❌ 没有找到任何图片", file=sys.stderr)
        sys.exit(1)

    # 下载图片
    save_dir = None
    if args.save:
        save_dir = Path(args.save)
        save_dir.mkdir(parents=True, exist_ok=True)
        print(f"💾 正在下载到 {save_dir} ...", file=sys.stderr)
        downloaded = 0
        for item in all_results:
            path = download_image(item, save_dir)
            if path:
                downloaded += 1
        print(f"✅ 已下载 {downloaded}/{len(all_results)} 张图片", file=sys.stderr)

    # 输出结果
    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
    else:
        for i, item in enumerate(all_results, 1):
            print(f"\n{'='*60}")
            print(f"  #{i} [{item['source']}] {item['title']}")
            print(f"  📷 {item['image_url']}")
            print(f"  🔗 {item['url']}")
            print(f"  👤 {item['photographer']}")
            if save_dir and item.get("image_url"):
                local = download_image(item, save_dir)
                if local:
                    print(f"  💾 {local}")
            print(f"{'='*60}")

    # 汇总统计
    from collections import Counter
    counts = Counter(item["source"] for item in all_results)
    print(f"\n📊 总计: {len(all_results)} 张图片", file=sys.stderr)
    for src, cnt in counts.most_common():
        print(f"   {src}: {cnt} 张", file=sys.stderr)

    return all_results


if __name__ == "__main__":
    main()
