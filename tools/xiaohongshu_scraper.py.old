#!/usr/bin/env python3
"""
小红书穿搭帖子采集工具
======================
使用 Playwright 浏览器自动化采集小红书穿搭帖子和图片。

首次使用需要扫码登录，之后 Cookie 会保存，无需重复登录。

用法:
    # 搜索穿搭帖子
    python3 tools/xiaohongshu_scraper.py --search "City Boy 穿搭"

    # 保存图片到指定目录
    python3 tools/xiaohongshu_scraper.py --search "日系 男装" --save ./outfits/xiaohongshu

    # 指定采集数量
    python3 tools/xiaohongshu_scraper.py --search "Clean Fit 男装" --count 30

    # 只保存图片（不保存文案）
    python3 tools/xiaohongshu_scraper.py --search "City Boy" --images-only

    # 打开浏览器（手动操作/登录）
    python3 tools/xiaohongshu_scraper.py --open

    # 查看已保存的帖子
    python3 tools/xiaohongshu_scraper.py --list-saved
"""

import argparse
import json
import os
import re
import sys
import time
import hashlib
import html as html_module
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse


def parse_js_json(js_text):
    """
    将 JavaScript 对象字面量转为有效 JSON。
    处理: true/false/null, undefined, 单引号, 尾逗号
    """
    # 替换 JS 布尔值和 null
    text = re.sub(r':\s*undefined', ':"undefined"', js_text)
    text = re.sub(r'(?<=[:,])\s*true\s*(?=[,}\]])', 'true', text)
    text = re.sub(r'(?<=[:,])\s*false\s*(?=[,}\]])', 'false', text)
    text = re.sub(r'(?<=[:,])\s*null\s*(?=[,}\]])', 'null', text)

    # 移除尾逗号
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # 尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 如果还是失败，尝试修复更多问题
        # 替换不在字符串中的单引号为双引号
        text = re.sub(r"(?<=[{,])\s*'([^']+)'\s*:", r'"\1":', text)
        text = re.sub(r':\s*\'([^\']+)\'', r':"\1"', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            return None

# ============================================================
# 配置
# ============================================================

BASE_DIR = Path(__file__).parent.parent
SAVE_DIR = BASE_DIR / "xiaohongshu_data"
COOKIE_FILE = BASE_DIR / "config" / ".xhs_cookies.json"
SCREENSHOT_DIR = BASE_DIR / "xiaohongshu_screenshots"

# 搜索 URL 模板
XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"

# 笔记详情 URL 模板
XHS_NOTE_URL = "https://www.xiaohongshu.com/explore/{note_id}"

HEADLESS = False  # 默认显示浏览器窗口（登录需要手动操作）


def ensure_dirs():
    """确保目录存在"""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_note_from_state(state):
    """从 __INITIAL_STATE__ 中递归提取笔记数据"""
    try:
        # 尝试直接路径
        note_detail_map = state.get("note", {}).get("noteDetailMap", {})
        if note_detail_map:
            for key, val in note_detail_map.items():
                note = val.get("note", {})
                result = {
                    "title": note.get("title", ""),
                    "desc": note.get("desc", ""),
                    "author": note.get("user", {}).get("nickname", ""),
                    "author_url": note.get("user", {}).get("url", ""),
                    "tags": [t.get("name", "") for t in note.get("tagList", []) if t.get("name")],
                    "images": [],
                }
                # 提取高清图片
                for img in note.get("imageList", []):
                    url_list = img.get("urlList", [])
                    if url_list:
                        result["images"].append(url_list[0])
                    elif img.get("urlDefault"):
                        result["images"].append(img["urlDefault"])
                return result

        # 备选路径: 直接搜整个 state
        result = {"images": []}
        def _walk(obj, depth=0):
            if depth > 5:
                return
            if isinstance(obj, dict):
                if "noteDetailMap" in obj:
                    for k, v in obj["noteDetailMap"].items():
                        n = v.get("note", {})
                        if n.get("title") and not result.get("title"):
                            result["title"] = n["title"]
                        if n.get("desc") and not result.get("desc"):
                            result["desc"] = n["desc"]
                        for img in n.get("imageList", []):
                            urls = img.get("urlList", [])
                            if urls:
                                result["images"].append(urls[0])
                for v in obj.values():
                    _walk(v, depth + 1)
            elif isinstance(obj, list):
                for v in obj:
                    _walk(v, depth + 1)
        _walk(state)
        return result if result.get("title") or result.get("images") else None
    except Exception:
        return None


def get_browser_context(playwright):
    """获取浏览器上下文，尝试恢复已保存的 Cookie"""
    from playwright.sync_api import sync_playwright

    browser = playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
    )

    # 尝试加载 Cookie
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE) as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print(f"📂 已加载登录状态 (Cookie 文件: {COOKIE_FILE.name})")
        except Exception as e:
            print(f"⚠️ Cookie 加载失败: {e}")

    return browser, context


def save_cookies(context):
    """保存 Cookie 到文件"""
    cookies = context.cookies()
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"✅ Cookie 已保存 ({len(cookies)} 条)")


def cmd_login():
    """打开小红书网页供用户登录"""
    from playwright.sync_api import sync_playwright

    ensure_dirs()

    with sync_playwright() as p:
        browser, context = get_browser_context(p)
        page = context.new_page()

        print("\n🔑 正在打开小红书...")
        print("   👉 请用小红书App扫二维码登录")
        print("   👉 登录成功后页面会自动跳转首页")
        print("   👉 等待最长3分钟，检测到 Cookie 即保存")
        print("   👉 按 Ctrl+C 可随时退出\n")

        page.goto("https://www.xiaohongshu.com", timeout=60000)
        page.wait_for_timeout(3000)

        # 等待登录成功：持续检测 Cookie 变化
        initial_cookie_count = len(context.cookies())
        logged_in = False

        for i in range(90):  # 最长等 3 分钟（2秒一检测）
            page.wait_for_timeout(2000)

            current_cookies = context.cookies()
            # 检测是否有 session cookie
            has_session = any("session" in c["name"].lower() for c in current_cookies)
            cookie_count_increased = len(current_cookies) > initial_cookie_count + 3

            if has_session and cookie_count_increased:
                logged_in = True
                break

            if i % 10 == 0:  # 每20秒提示一次
                print(f"   ⏳ 等待登录中... ({i*2+2}秒)")

        if logged_in:
            print("✅ 登录成功！")
            page.wait_for_timeout(2000)
            save_cookies(context)
        else:
            print("\n⚠️  未检测到登录状态")

        print(f"\n📸 保存目录: {SAVE_DIR}")
        browser.close()


def extract_note_info(page):
    """从笔记详情页提取信息"""
    info = {
        "note_id": "",
        "title": "",
        "desc": "",
        "tags": [],
        "images": [],
        "author": "",
        "author_url": "",
        "likes": "",
        "collections": "",
        "comments": "",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 从 URL 提取 note_id
    url = page.url
    note_match = re.search(r"/explore/([a-f0-9]+)", url)
    if note_match:
        info["note_id"] = note_match.group(1)

    try:
        # 等待内容加载
        page.wait_for_timeout(3000)

        # 获取页面完整 HTML
        html = page.content()

        # === 提取标题 ===
        # 从 page title 提取
        title = page.title()
        if title and "小红书" not in title:
            info["title"] = title.strip()

        # === 提取文案描述 ===
        # 方法1: 从 meta description 提取
        desc_meta = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"',
            html
        )
        if desc_meta:
            desc_text = desc_meta.group(1)
            # 去掉标题重复部分
            if info["title"] and info["title"] in desc_text:
                desc_text = desc_text.replace(info["title"], "", 1).strip(" -")
            if desc_text:
                info["desc"] = desc_text[:500]

        # 方法2: 从 JSON-LD 提取
        if not info["desc"]:
            jsonld = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if jsonld:
                try:
                    ld = json.loads(jsonld.group(1))
                    desc = ld.get("description", "")
                    if desc:
                        info["desc"] = desc[:500]
                except json.JSONDecodeError:
                    pass

        # 方法3: 从 window.__INITIAL_STATE__ 提取（JS 对象格式，需特殊解析）
        init_state = re.search(
            r'<script>window\.__INITIAL_STATE__\s*=\s*({.*?});</script>',
            html, re.DOTALL
        )
        if init_state:
            state = parse_js_json(init_state.group(1))
            if state:
                # 探索 state 结构提取笔记数据
                note_data = _extract_note_from_state(state)
                if note_data:
                    if note_data.get("title"):
                        info["title"] = note_data["title"]
                    if note_data.get("desc"):
                        info["desc"] = note_data["desc"][:500]
                    if note_data.get("author"):
                        info["author"] = note_data["author"]
                    if note_data.get("author_url"):
                        info["author_url"] = note_data["author_url"]
                    if note_data.get("tags"):
                        info["tags"] = note_data["tags"]
                    if note_data.get("images"):
                        info["images"] = note_data["images"]

        # === 提取标签（从文案中的 # 标签） ===
        if not info["tags"]:
            hashtags = re.findall(r'#([一-鿿\w]+)', info["desc"])
            if hashtags:
                info["tags"] = [f"#{t}" for t in hashtags]

        # === 提取图片 URL ===
        # 从 __INITIAL_STATE__ 提取高清图
        if init_state:
            state = parse_js_json(init_state.group(1))
            if state:
                note_data = _extract_note_from_state(state)
                if note_data and note_data.get("images"):
                    info["images"] = note_data["images"]

        # 方法2: 从页面 img 标签提取（兜底）
        if not info["images"]:
            img_pattern = re.compile(
                r'https?://[^"\']*?xhscdn\.com/[^"\']*?\.(?:jpg|jpeg|png|webp)(?:[^"\'\\s]*)',
            )
            imgs = list(dict.fromkeys(img_pattern.findall(html)))
            for img_url in imgs:
                if "avatar" not in img_url and "logo" not in img_url and "sns" not in img_url:
                    # 转高清（去掉缩略图参数）
                    img_url = re.sub(r'![\w]+', '', img_url)
                    info["images"].append(img_url)

        # 去重
        info["images"] = list(dict.fromkeys(info["images"]))

        # === 提取作者 ===
        if not info["author"]:
            author_match = re.search(r'"nickname"\s*:\s*"([^"]+)"', html)
            if author_match:
                info["author"] = author_match.group(1)

        # === 提取互动数据 ===
        interact_match = re.search(
            r'"interactInfo"\s*:\s*\{[^}]*"likedCount"\s*:\s*"([^"]*)"[^}]*"collectedCount"\s*:\s*"([^"]*)"[^}]*"commentCount"\s*:\s*"([^"]*)"',
            html
        )
        if interact_match:
            info["likes"] = interact_match.group(1)
            info["collections"] = interact_match.group(2)
            info["comments"] = interact_match.group(3)

    except Exception as e:
        print(f"  ⚠️ 提取详情时出错: {e}")

    return info


def search_notes(page, keyword, max_count=20):
    """搜索关键词，返回笔记列表"""
    encoded = keyword.replace(" ", "%20")
    search_url = XHS_SEARCH_URL.format(keyword=encoded)

    print(f"\n🔍 搜索: {keyword}")
    page.goto(search_url, timeout=30000)
    page.wait_for_timeout(3000)

    notes = []
    scroll_attempts = 0
    max_scrolls = max_count // 4 + 5  # 估算需要的滚动次数

    while len(notes) < max_count and scroll_attempts < max_scrolls:
        # 获取当前页面的笔记卡片
        # 小红书搜索结果卡片有多种结构
        cards = page.query_selector_all(
            'a[href*="/explore/"], '
            'section[class*="note-item"], '
            'div[class*="note-item"], '
            'li[class*="note-item"]'
        )

        for card in cards:
            href = card.get_attribute("href") or ""
            # 如果 card 本身是 a 标签，href 就在它上面
            note_id_match = re.search(r"/explore/([a-f0-9]+)", href)
            if not note_id_match:
                # 尝试找子元素中的链接
                link = card.query_selector('a[href*="/explore/"]')
                if link:
                    href = link.get_attribute("href") or ""
                    note_id_match = re.search(r"/explore/([a-f0-9]+)", href)

            if note_id_match:
                note_id = note_id_match.group(1)
                # 去重
                if note_id in [n["note_id"] for n in notes]:
                    continue

                # 提取标题 - 从 card 的文本
                title = card.inner_text().strip() or ""
                # 如果标题太长，截取第一个换行前的内容
                if "\n" in title:
                    title = title.split("\n")[0]

                # 提取封面图
                img = card.query_selector("img")
                cover = img.get_attribute("src") or img.get_attribute("data-src") or "" if img else ""

                note_info = {
                    "note_id": note_id,
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                    "title": title[:100] if title else "",
                    "cover": cover,
                }
                notes.append(note_info)

                if len(notes) >= max_count:
                    break

        if len(notes) < max_count:
            # 滚动加载更多
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            scroll_attempts += 1

    print(f"  📊 找到 {len(notes)} 篇帖子")
    return notes[:max_count]


def download_images(note_info, save_dir):
    """下载笔记中的图片到本地"""
    import requests

    note_dir = save_dir / f"{note_info['note_id']}_{note_info['title'][:20] if note_info['title'] else 'untitled'}"
    # 清理目录名
    note_dir_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in note_dir.name)[:60]
    note_dir = save_dir / note_dir_name
    note_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for i, img_url in enumerate(note_info["images"]):
        try:
            resp = requests.get(img_url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

            ext = ".jpg"
            if ".png" in img_url:
                ext = ".png"
            elif ".webp" in img_url:
                ext = ".webp"

            filename = f"{note_info['note_id']}_{i+1:02d}{ext}"
            filepath = note_dir / filename

            with open(filepath, "wb") as f:
                f.write(resp.content)

            downloaded.append(str(filepath))
        except Exception as e:
            print(f"  ⚠️ 下载图片 {i+1} 失败: {e}")

    # 保存文案为 JSON
    meta_file = note_dir / "_meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        save_info = {k: v for k, v in note_info.items() if k != "images"}
        save_info["downloaded_images"] = downloaded
        json.dump(save_info, f, ensure_ascii=False, indent=2)

    # 保存文案为 TXT（方便阅读）
    txt_file = note_dir / "_笔记内容.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(f"标题: {note_info['title']}\n")
        f.write(f"链接: {note_info['url']}\n")
        f.write(f"作者: {note_info['author']}\n\n")
        f.write(f"文案:\n{note_info['desc']}\n\n")
        if note_info["tags"]:
            f.write(f"标签: {' '.join(note_info['tags'])}\n")
        f.write(f"\n图片: {len(downloaded)} 张\n")
        f.write(f"采集时间: {note_info['collected_at']}\n")

    return note_dir, downloaded


def cmd_search(keyword, max_count=20, save_dir=None, images_only=False):
    """搜索并采集穿搭帖子"""
    from playwright.sync_api import sync_playwright

    ensure_dirs()
    output_dir = Path(save_dir) if save_dir else SAVE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser, context = get_browser_context(p)
        page = context.new_page()

        # 先访问首页确保 Cookie 生效
        print("🌐 正在打开小红书...")
        page.goto("https://www.xiaohongshu.com", timeout=30000)
        page.wait_for_timeout(2000)

        # 检查是否登录
        is_logged_in = len(context.cookies()) > 5
        if not is_logged_in:
            print("⚠️  未检测到登录状态，搜索结果可能受限")
            print("   👉 请先运行: python3 tools/xiaohongshu_scraper.py --login\n")

        # 搜索
        notes = search_notes(page, keyword, max_count)
        print(f"\n📊 找到 {len(notes)} 篇帖子")

        if not notes:
            browser.close()
            return

        # 逐个打开笔记详情
        all_results = []
        for i, note in enumerate(notes, 1):
            print(f"\n[{i}/{len(notes)}] 正在采集: {note['title'][:30] or note['note_id']}")

            try:
                page.goto(note["url"], timeout=30000)
                page.wait_for_timeout(2000)

                note_info = extract_note_info(page)

                # 补充基本信息
                note_info["note_id"] = note["note_id"]
                if not note_info["title"]:
                    note_info["title"] = note["title"]
                if not note_info["images"] and note["cover"]:
                    note_info["images"] = [note["cover"]]
                note_info["url"] = note["url"]

                # 保存
                if not images_only and note_info["images"]:
                    note_dir, downloaded = download_images(note_info, output_dir)
                    print(f"  ✅ {len(downloaded)} 张图片 → {note_dir.name}")
                elif note_info["images"]:
                    note_dir, downloaded = download_images(note_info, output_dir)
                    print(f"  ✅ {len(downloaded)} 张图片（仅图片）")
                else:
                    print(f"  ⚠️ 无图片")

                all_results.append(note_info)

            except Exception as e:
                print(f"  ❌ 采集失败: {e}")
                continue

        # 保存汇总 JSON
        summary_file = output_dir / f"_search_{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n📄 汇总已保存: {summary_file}")

        browser.close()


def cmd_list_saved():
    """列出已保存的帖子"""
    if not SAVE_DIR.exists():
        print("❌ 暂无已保存的数据")
        return

    dirs = sorted([d for d in SAVE_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")])
    if not dirs:
        print("📭 暂无已保存的帖子")
        return

    print(f"\n📂 已保存的帖子 ({len(dirs)} 篇):\n")
    for d in dirs:
        meta_file = d / "_meta.json"
        txt_file = d / "_笔记内容.txt"
        images = list(d.glob("*.[jJ][pP][gG]")) + list(d.glob("*.[pP][nN][gG]"))
        title = "未知"
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
                title = meta.get("title", "未知")[:40]
        elif txt_file.exists():
            with open(txt_file) as f:
                first_line = f.readline().strip()
                title = first_line.replace("标题: ", "")[:40]

        print(f"  📁 {d.name}")
        print(f"     📝 {title}")
        print(f"     🖼️  {len(images)} 张图片")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="📕 小红书穿搭帖子采集工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 首次使用，先登录
  python3 tools/xiaohongshu_scraper.py --login

  # 搜索穿搭帖子
  python3 tools/xiaohongshu_scraper.py --search "City Boy 穿搭"

  # 指定数量
  python3 tools/xiaohongshu_scraper.py --search "Clean Fit 男装" --count 30

  # 保存到指定目录
  python3 tools/xiaohongshu_scraper.py --search "日系 男装" --save ./搜索图片

  # 查看已保存
  python3 tools/xiaohongshu_scraper.py --list-saved

  # 直接打开浏览器操作
  python3 tools/xiaohongshu_scraper.py --open
        """,
    )
    parser.add_argument("--login", action="store_true", help="登录小红书（首次使用）")
    parser.add_argument("--open", action="store_true", help="打开浏览器手动操作")
    parser.add_argument("--search", "-s", type=str, help="搜索关键词")
    parser.add_argument("--count", "-n", type=int, default=20, help="采集数量（默认20）")
    parser.add_argument("--save", type=str, help="保存目录（默认 xiaohongshu_data/）")
    parser.add_argument("--images-only", action="store_true", help="仅保存图片，不保存文案")
    parser.add_argument("--list-saved", "-l", action="store_true", help="查看已保存的帖子")

    args = parser.parse_args()

    if args.login:
        cmd_login()
    elif args.open:
        cmd_login()  # 打开浏览器但不等待登录
    elif args.list_saved:
        cmd_list_saved()
    elif args.search:
        cmd_search(args.search, args.count, args.save, args.images_only)
    else:
        parser.print_help()
        print("\n❌ 请指定操作: --search / --login / --list-saved")


if __name__ == "__main__":
    main()
