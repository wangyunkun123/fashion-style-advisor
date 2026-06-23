#!/usr/bin/env python3
"""
风格图片搜集代理
为每种风格搜集杂志/秀场/名人/街拍图片 URL，存入 references/images.json

用法:
  python3 tools/style_image_scout.py <style_id>        搜集单个风格图片
  python3 tools/style_image_scout.py --batch            批量处理所有风格
  python3 tools/style_image_scout.py --list             列出图片覆盖率
"""

import os, sys, json, glob, time, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles_universal')
CATEGORIES_FILE = os.path.join(STYLES_DIR, 'categories.json')

# 图片搜索提示词模板
SEARCH_TEMPLATES = {
    "editorial": '"{style_name_zh}" "{style_name_en}" magazine editorial photoshoot men fashion',
    "runway": '"{style_name_en}" runway show fashion week men look',
    "celebrity": '"{style_name_en}" style celebrity men outfit inspiration',
    "streetstyle": '"{style_name_zh}" 穿搭 街拍 男装 street style men',
    "social": '"{style_name_zh}" 穿搭 Instagram 小红书 men outfit',
}


def load_registry():
    with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f).get('style_registry', {})


def get_style_dir(style_id):
    d = os.path.join(STYLES_DIR, style_id)
    os.makedirs(os.path.join(d, 'references'), exist_ok=True)
    return d


def load_images_json(style_id):
    path = os.path.join(STYLES_DIR, style_id, 'references', 'images.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_images_json(style_id, data):
    path = os.path.join(STYLES_DIR, style_id, 'references', 'images.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_empty_catalog(style_id, info):
    return {
        "style_id": style_id,
        "name_zh": info.get('name_zh', style_id),
        "name_en": info.get('name_en', ''),
        "_last_updated": time.strftime('%Y-%m-%d'),
        "_status": "empty",
        "categories": {
            "editorial": {"label": "杂志大片", "images": []},
            "runway": {"label": "秀场T台", "images": []},
            "celebrity": {"label": "明星名人", "images": []},
            "streetstyle": {"label": "街拍造型", "images": []},
            "social": {"label": "社交平台", "images": []},
            "lookbook": {"label": "品牌画册", "images": []},
        }
    }


def generate_search_prompts(style_id, info):
    """生成图片搜索提示词"""
    name_zh = info.get('name_zh', style_id)
    name_en = info.get('name_en', '')
    prompts = {}
    for cat, template in SEARCH_TEMPLATES.items():
        prompts[cat] = template.format(style_name_zh=name_zh, style_name_en=name_en)
    return prompts


def cmd_scout(style_id):
    """为单个风格生成图片搜集提示词"""
    registry = load_registry()
    info = registry.get(style_id)
    if not info:
        print(f"❌ 未知风格: {style_id}")
        return

    name_zh = info['name_zh']
    name_en = info.get('name_en', '')
    prompts = generate_search_prompts(style_id, info)

    print(f"\n{'='*60}")
    print(f"🔍 图片搜集: {name_zh} ({name_en})")
    print(f"{'='*60}")

    for cat, prompt in prompts.items():
        cat_label = {"editorial": "杂志大片", "runway": "秀场T台", "celebrity": "明星名人", "streetstyle": "街拍", "social": "社交平台"}[cat]
        print(f"\n📸 {cat_label}:")
        print(f"   搜索关键词: {prompt}")

    # 生成 Claude 用的搜集任务
    task = f"""请为"{name_zh} ({name_en})"风格搜集参考图片URL。每个类别找3-5张。

搜索关键词:
- 杂志: {prompts['editorial']}
- 秀场: {prompts['runway']}
- 名人: {prompts['celebrity']}
- 街拍: {prompts['streetstyle']}
- 社交: {prompts['social']}

对每张图片，输出JSON格式:
{{"url": "图片URL", "caption": "简短描述(含人名/品牌/年份)", "source": "来源网站", "category": "editorial|runway|celebrity|streetstyle|social"}}

将结果保存到: styles_universal/{style_id}/references/images.json
"""

    task_path = os.path.join(get_style_dir(style_id), 'references', '_scout_task.txt')
    with open(task_path, 'w', encoding='utf-8') as f:
        f.write(task)
    print(f"\n📋 搜集任务已保存: references/_scout_task.txt")
    print(f"👉 将以上搜索关键词用于 WebSearch，结果存入 references/images.json")


def cmd_batch():
    """批量生成所有风格的图片搜集任务"""
    registry = load_registry()
    todo = []
    for sid, info in registry.items():
        img = load_images_json(sid)
        if not img or img.get('_status') == 'empty':
            todo.append((sid, info))

    print(f"📊 {len(todo)}/{len(registry)} 风格需要搜集图片")
    for sid, info in todo:
        prompts = generate_search_prompts(sid, info)
        task_path = os.path.join(get_style_dir(sid), 'references', '_scout_task.txt')
        with open(task_path, 'w', encoding='utf-8') as f:
            f.write(f"搜集任务: {info['name_zh']} ({info.get('name_en', '')})\n\n")
            for cat, prompt in prompts.items():
                f.write(f"[{cat}] {prompt}\n")
        print(f"  ✅ {sid}")


def cmd_list():
    """列出图片覆盖率"""
    registry = load_registry()
    total = 0
    has_images = 0
    total_images = 0

    print(f"\n{'='*60}")
    print(f"📸 图片参考覆盖率")
    print(f"{'='*60}")

    for sid, info in registry.items():
        img = load_images_json(sid)
        if img and img.get('_status') != 'empty':
            count = sum(len(v.get('images', [])) for v in img.get('categories', {}).values())
            if count > 0:
                has_images += 1
                total_images += count
                print(f"  ✅ {sid:30s} {count}张")
            else:
                print(f"  ⬜ {sid:30s} 0张")
        else:
            print(f"  ⬜ {sid:30s} 未搜集")
        total += 1

    print(f"\n📊 覆盖率: {has_images}/{total} ({has_images*100//total}%) | 总图片: {total_images}张")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h'):
        print("风格图片搜集代理")
        print("\n用法:")
        print("  python3 tools/style_image_scout.py <style_id>   搜集单个风格")
        print("  python3 tools/style_image_scout.py --batch       批量生成任务")
        print("  python3 tools/style_image_scout.py --list        列出覆盖率")
        return

    cmd = sys.argv[1]
    if cmd == '--batch':
        cmd_batch()
    elif cmd == '--list':
        cmd_list()
    else:
        cmd_scout(cmd)


if __name__ == '__main__':
    main()
