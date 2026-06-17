"""
Instagram Fashion Search — 无需登录的 Instagram 穿搭搜索工具
============================================================
通过 DuckDuckGo 限定 Instagram 域名搜索，Jina Reader 读帖子详情。

用法:
    # 搜索 Instagram 穿搭内容
    python3 tools/instagram_search.py --query "city boy style men"

    # 搜索并下载图片
    python3 tools/instagram_search.py --query "asian men streetwear" --save ./ig_results

    # 读取单个帖子详情
    python3 tools/instagram_search.py --post "https://www.instagram.com/p/XXXXX/"

    # JSON 输出
    python3 tools/instagram_search.py --query "menswear" --json

    # 多源搜索（DuckDuckGo + Bing 备用）
    python3 tools/instagram_search.py --query "summer outfit men" --all-sources
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

# ============================================================
# 配置
# ============================================================

DEFAULT_SAVE_DIR = Path(__file__).parent.parent / "ig_results"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# ============================================================
# DuckDuckGo 搜索 Instagram
# ============================================================

def search_duckduckgo(query, count=20):
    """
    DuckDuckGo 图片搜索，限定 Instagram 域名。
    完全免费，无需 API Key。
    """
    import requests

    # 拼接 Instagram 限定搜索词
    full_query = f"{query} site:instagram.com"
    encoded = urllib.parse.quote(full_query)

    headers = dict(HEADERS)
    headers["Referer"] = "https://duckduckgo.com/"

    try:
        sess = requests.Session()
        sess.headers.update(headers)

        # 第一步：获取 vqd token
        html_url = f"https://duckduckgo.com/?q={encoded}&t=h_&ia=images"
        html_resp = sess.get(html_url, timeout=15)

        vqd_match = re.search(r'vqd=([\d-]+)', html_resp.text)
        if not vqd_match:
            vqd_match = re.search(r'"vqd":"([\d-]+)"', html_resp.text)

        if not vqd_match:
            return {"error": "无法获取 DuckDuckGo vqd token", "results": []}

        vqd = vqd_match.group(1)

        # 第二步：搜索图片
        search_url = "https://duckduckgo.com/i.js"
        params = {
            "q": full_query,
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
            source_url = img.get("url", "")

            # 只保留 Instagram 的结果
            if "instagram.com" not in source_url:
                continue

            # 提取 Instagram 信息
            username = extract_username(source_url)
            shortcode = extract_shortcode(source_url)

            results.append({
                "source": "instagram",
                "search_method": "duckduckgo",
                "id": shortcode or f"ig_ddg_{i}",
                "title": img.get("title", query),
                "post_url": source_url,
                "username": username,
                "image_url": img_url,
                "thumbnail": img.get("thumbnail", img_url),
                "alt": img.get("title", query),
                "width": img.get("width", 0),
                "height": img.get("height", 0),
            })

        return {"results": results, "total": len(results)}

    except Exception as e:
        return {"error": f"DuckDuckGo 搜索失败: {e}", "results": []}


# ============================================================
# Bing 图片搜索兜底
# ============================================================

def search_bing(query, count=20):
    """
    Bing 图片搜索，用 site:instagram.com 限定。
    免费，无需 API Key。
    """
    import requests

    full_query = f"{query} site:instagram.com"
    encoded = urllib.parse.quote(full_query)

    headers = dict(HEADERS)

    try:
        sess = requests.Session()
        sess.headers.update(headers)

        # Bing 图片搜索
        url = f"https://www.bing.com/images/search?q={encoded}&first=1&count={count}"

        resp = sess.get(url, timeout=15)
        resp.raise_for_status()

        # 从 HTML 中提取图片 URL（Bing 把数据嵌在 JS 中）
        results = []

        # 匹配 murl（原图）和 purl（页面 URL）
        pattern = r'"murl"\s*:\s*"([^"]+)".*?"purl"\s*:\s*"([^"]+)".*?"turl"\s*:\s*"([^"]+)"'
        matches = re.findall(pattern, resp.text, re.DOTALL)

        for i, (murl, purl, turl) in enumerate(matches[:count]):
            if "instagram.com" not in purl:
                continue

            username = extract_username(purl)
            shortcode = extract_shortcode(purl)

            results.append({
                "source": "instagram",
                "search_method": "bing",
                "id": shortcode or f"ig_bing_{i}",
                "title": query,
                "post_url": purl,
                "username": username,
                "image_url": murl,
                "thumbnail": turl,
                "alt": query,
                "width": 0,
                "height": 0,
            })

        return {"results": results, "total": len(results)}

    except Exception as e:
        return {"error": f"Bing 搜索失败: {e}", "results": []}


# ============================================================
# 辅助函数
# ============================================================

def extract_username(url):
    """从 Instagram URL 提取用户名"""
    if not url:
        return None
    # 匹配 instagram.com/username/ 或 instagram.com/username
    match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)/?', url)
    if match and match.group(1) not in ("p", "reel", "stories", "reels"):
        return f"@{match.group(1)}"
    return None


def extract_shortcode(url):
    """从 Instagram URL 提取帖子短码"""
    if not url:
        return None
    # 匹配 instagram.com/p/SHORTCODE/ 或 instagram.com/reel/SHORTCODE/
    match = re.search(r'instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)/?', url)
    return match.group(1) if match else None


# ============================================================
# Jina Reader — 读取帖子详情
# ============================================================

def fetch_post_detail(post_url):
    """
    用 Jina Reader 读取 Instagram 帖子详情。
    返回 Markdown 格式内容（文案、标签等）。
    """
    import subprocess

    jina_url = f"https://r.jina.ai/{post_url}"
    headers = {
        "Accept": "text/markdown",
        "User-Agent": "Mozilla/5.0",
    }

    try:
        import requests
        resp = requests.get(jina_url, headers=headers, timeout=20)
        resp.raise_for_status()
        content = resp.text

        # 提取图片 URL
        image_urls = re.findall(r'!\[.*?\]\((https://[^)]+)\)', content)

        # 提取文本内容（去掉图片 markdown）
        text = re.sub(r'!\[.*?\]\(https://[^)]+\)', '', content).strip()

        return {
            "url": post_url,
            "content": text,
            "image_urls": image_urls,
            "raw_markdown": content,
        }
    except Exception as e:
        return {"error": f"Jina Reader 读取失败: {e}", "url": post_url}


# ============================================================
# 主搜索函数
# ============================================================

def search_instagram(query, count=20, sources=None, fetch_details=False):
    """
    搜索 Instagram 穿搭内容。

    Args:
        query: 搜索关键词（英文效果更好）
        count: 返回数量上限
        sources: 搜索源列表，默认 ['duckduckgo', 'bing']
        fetch_details: 是否用 Jina Reader 读每个帖子的详情

    Returns:
        {"results": [...], "total": N}
    """
    if sources is None:
        sources = ["duckduckgo", "bing"]

    SEARCH_FUNCTIONS = {
        "duckduckgo": search_duckduckgo,
        "bing": search_bing,
    }

    all_results = []
    seen_urls = set()

    for src in sources:
        func = SEARCH_FUNCTIONS.get(src)
        if not func:
            continue

        print(f"🔍 正在通过 [{src}] 搜索 Instagram: {query} ...", file=sys.stderr)
        result = func(query, count=count)

        if "error" in result and not result.get("results"):
            print(f"⚠️  {src}: {result['error']}", file=sys.stderr)
            continue

        items = result.get("results", [])
        new_items = []
        for item in items:
            url = item.get("post_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                new_items.append(item)

        print(f"✅ {src}: 找到 {len(new_items)} 条新结果（去重后）", file=sys.stderr)
        all_results.extend(new_items)

    # 可选：读取帖子详情
    if fetch_details and all_results:
        print(f"\n📖 正在读取 {len(all_results)} 个帖子详情 ...", file=sys.stderr)
        for i, item in enumerate(all_results):
            post_url = item.get("post_url")
            if not post_url:
                continue
            print(f"  [{i+1}/{len(all_results)}] {post_url}", file=sys.stderr)
            detail = fetch_post_detail(post_url)
            if "error" not in detail:
                item["caption"] = detail.get("content", "")[:500]
                item["detail_images"] = detail.get("image_urls", [])
                item["tags"] = re.findall(r'#(\w+)', detail.get("content", ""))
            time.sleep(1)  # 避免请求过快

    return {"results": all_results, "total": len(all_results)}


# ============================================================
# 下载图片
# ============================================================

def download_image(item, save_dir):
    """下载单张图片到本地目录"""
    import requests

    img_url = item.get("image_url") or ""
    if not img_url:
        # 尝试用 thumbnail
        img_url = item.get("thumbnail") or ""
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

        username = item.get("username", "unknown").lstrip("@")
        shortcode = item.get("id", "post")
        filename = f"ig_{username}_{shortcode}.{ext}"
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

def main():
    parser = argparse.ArgumentParser(
        description="📸 Instagram 穿搭搜索工具（无需登录）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 tools/instagram_search.py --query "city boy style men"
  python3 tools/instagram_search.py --query "asian men streetwear" --save ./ig_results
  python3 tools/instagram_search.py --query "menswear" --json
  python3 tools/instagram_search.py --post "https://www.instagram.com/p/XXXXX/"
  python3 tools/instagram_search.py --query "summer outfit men" --all-sources --details
        """,
    )
    parser.add_argument("--query", "-q", type=str, help="搜索关键词（建议英文）")
    parser.add_argument("--post", "-p", type=str, help="读取单个 Instagram 帖子详情（提供完整 URL）")
    parser.add_argument("--count", "-n", type=int, default=20, help="返回数量（默认 20）")
    parser.add_argument("--all-sources", "-a", action="store_true",
                        help="同时使用 DuckDuckGo + Bing 搜索")
    parser.add_argument("--details", "-d", action="store_true",
                        help="用 Jina Reader 读取每个帖子的详情（慢但详细）")
    parser.add_argument("--save", "-s", type=str, help="下载图片到本地目录")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 格式输出")
    parser.add_argument("--source", choices=["duckduckgo", "bing"],
                        default="duckduckgo", help="搜索源（默认 duckduckgo）")

    args = parser.parse_args()

    # 读取单个帖子
    if args.post:
        print(f"📖 正在读取帖子: {args.post}", file=sys.stderr)
        detail = fetch_post_detail(args.post)
        if "error" in detail:
            print(f"❌ {detail['error']}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"🔗 {args.post}")
            print(f"\n📝 内容:\n{detail.get('content', '无')}")
            print(f"\n🖼️  图片 ({len(detail.get('image_urls', []))} 张):")
            for img in detail.get("image_urls", []):
                print(f"   {img}")
            print(f"{'='*60}")
        return

    if not args.query:
        parser.print_help()
        print("\n❌ 请提供 --query 搜索关键词 或 --post 帖子 URL")
        sys.exit(1)

    # 搜索
    sources = ["duckduckgo", "bing"] if args.all_sources else [args.source]
    result = search_instagram(
        query=args.query,
        count=args.count,
        sources=sources,
        fetch_details=args.details,
    )

    items = result.get("results", [])

    if not items:
        print("❌ 没有找到任何 Instagram 帖子", file=sys.stderr)
        # 提示：试试别的关键词
        print("💡 建议: 试试英文关键词，比如 'men fashion', 'streetwear outfit'", file=sys.stderr)
        sys.exit(1)

    # 下载图片
    save_dir = None
    if args.save:
        save_dir = Path(args.save)
        save_dir.mkdir(parents=True, exist_ok=True)
        print(f"💾 正在下载到 {save_dir} ...", file=sys.stderr)
        downloaded = 0
        for item in items:
            path = download_image(item, save_dir)
            if path:
                downloaded += 1
        print(f"✅ 已下载 {downloaded}/{len(items)} 张图片", file=sys.stderr)

    # 输出结果
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for i, item in enumerate(items, 1):
            print(f"\n{'='*60}")
            print(f"  #{i} {item.get('username', '@unknown')}")
            print(f"  🔗 {item.get('post_url', 'N/A')}")
            if item.get("caption"):
                caption = item["caption"][:200]
                print(f"  📝 {caption}")
            print(f"  🖼️  {item.get('image_url', 'N/A')}")
            if item.get("tags"):
                print(f"  🏷️  {' '.join('#' + t for t in item['tags'][:10])}")
            print(f"  🔍 搜索方式: {item.get('search_method', 'unknown')}")
            print(f"{'='*60}")

    # 汇总
    usernames = set(item.get("username") for item in items if item.get("username"))
    print(f"\n📊 总计: {len(items)} 条 Instagram 帖子", file=sys.stderr)
    if usernames:
        print(f"👤 涉及 {len(usernames)} 个账号: {', '.join(sorted(usernames)[:10])}", file=sys.stderr)

    return items


if __name__ == "__main__":
    main()
