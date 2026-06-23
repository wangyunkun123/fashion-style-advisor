#!/usr/bin/env python3
"""将 gallery/ 中的备选图片插入风格百科文章 encyclopedia.md。

为每个有图库的风格在文章末尾添加"📸 风格图库"章节。
如果文章已有图库章节则跳过。

用法:
  python3 tools/insert_gallery_to_encyclopedia.py          # 处理所有风格
  python3 tools/insert_gallery_to_encyclopedia.py --dry-run # 预览不写入
"""

import os
import json
import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
STYLES_UNIVERSAL = PROJECT_DIR / "styles_universal"


def get_gallery_images(style_dir):
    """获取 gallery 目录中的图片列表，按文件名排序"""
    gallery_dir = style_dir / "gallery"
    if not gallery_dir.is_dir():
        return []
    images = sorted(gallery_dir.glob("*.jpg"))
    return [img.name for img in images]


def get_image_titles(style_dir):
    """从 images_meta.json 获取图片标题"""
    meta_path = style_dir / "images_meta.json"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path) as f:
            data = json.load(f)
    except Exception:
        return {}
    titles = {}
    for img in data.get("images", []):
        fn = img.get("filename", "")
        title = img.get("title", "")
        # 截断长标题
        if len(title) > 80:
            title = title[:77] + "..."
        titles[fn] = title
    return titles


def build_gallery_section(images, titles):
    """构建图库 markdown 章节"""
    if not images:
        return ""

    lines = [
        "",
        "## 📸 风格图库",
        "",
        "> 以下为风格代表性穿搭参考图，搜集自公开时尚媒体。",
        "",
    ]

    # 每行最多 3 张图
    for i, img_name in enumerate(images):
        title = titles.get(img_name, "风格穿搭参考")
        # 由于 markdown 表格中图片不好渲染，使用简单的图片列表
        lines.append(f"![{title}](gallery/{img_name})")
        lines.append(f"*{title}*")
        lines.append("")

    return "\n".join(lines)


def find_insertion_point(lines):
    """找到图库章节的插入位置（在最后的版权声明之前）"""
    # 如果已有图库章节，跳过
    for i, line in enumerate(lines):
        if "📸 风格图库" in line or "风格图库" in line:
            return -1  # 已存在，跳过

    # 找到 "*本文基于多源研究整理" 所在行，在其前插入
    for i, line in enumerate(lines):
        if "本文基于多源研究整理" in line or "本文基于" in line:
            return i - 1  # 插入在版权声明前一行的空行处

    # 回退：插入在末尾
    return len(lines)


def process_style(style_id, dry_run=False):
    """处理一个风格的百科文章"""
    style_dir = STYLES_UNIVERSAL / style_id
    enc_path = style_dir / "encyclopedia.md"

    if not enc_path.exists():
        print(f"  ⏭ 无百科文章，跳过")
        return False

    images = get_gallery_images(style_dir)
    if not images:
        print(f"  ⏭ 无图库图片，跳过")
        return False

    with open(enc_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    insert_at = find_insertion_point(lines)

    if insert_at == -1:
        print(f"  ⏭ 已有图库章节，跳过")
        return False

    titles = get_image_titles(style_dir)
    gallery_section = build_gallery_section(images, titles)

    # 在插入点后添加图库章节
    new_lines = lines[:insert_at + 1] + gallery_section.split("\n") + lines[insert_at + 1:]
    new_content = "\n".join(new_lines)

    if dry_run:
        print(f"  📝 预览: 将在第 {insert_at} 行后插入 {len(images)} 张图")
        return True

    with open(enc_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  ✅ 已插入 {len(images)} 张图库图片")
    return True


def main():
    parser = argparse.ArgumentParser(description="将图库图片插入风格百科文章")
    parser.add_argument("--style", help="仅处理指定风格ID")
    parser.add_argument("--dry-run", action="store_true", help="预览不写入")
    args = parser.parse_args()

    if args.style:
        style_ids = [args.style]
    else:
        style_ids = sorted(
            d.name for d in STYLES_UNIVERSAL.iterdir()
            if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")
            and d.name not in ("references", "templates")
        )

    total = len(style_ids)
    updated = 0

    for idx, style_id in enumerate(style_ids, 1):
        print(f"[{idx}/{total}] {style_id}...", end=" ")
        try:
            if process_style(style_id, dry_run=args.dry_run):
                updated += 1
        except Exception as e:
            print(f"❌ 错误: {e}")

    print(f"\n✅ 完成！更新了 {updated}/{total} 篇百科文章")


if __name__ == "__main__":
    main()
