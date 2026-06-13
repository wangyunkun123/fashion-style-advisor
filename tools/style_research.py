#!/usr/bin/env python3
"""
风格研究代理 — 自动搜集、分析、整理风格百科内容。

模式:
  python3 tools/style_research.py <style_id>              研究单个风格 → 生成 encyclopedia.md 草稿
  python3 tools/style_research.py --discover                发现新风格 → 搜索最新流行趋势
  python3 tools/style_research.py --enrich <style_id>       充实已有风格 → 补充品牌/名人/秀场
  python3 tools/style_research.py --batch                   批量处理所有待研究风格
  python3 tools/style_research.py --list                    列出所有风格及其状态

工作流程:
  WebSearch → WebFetch → Claude 结构化提取 → encyclopedia.md
"""

import os, sys, json, glob, time, re, subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles_universal')
CATEGORIES_FILE = os.path.join(STYLES_DIR, 'categories.json')
TEMPLATE_FILE = os.path.join(STYLES_DIR, 'templates', 'encyclopedia_template.md')

# ============================================================
# 1. 数据加载
# ============================================================

def load_categories():
    with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_template():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def get_style_registry():
    cats = load_categories()
    return cats.get('style_registry', {})

def get_style_status(style_id):
    """获取风格研究状态"""
    encyc_path = os.path.join(STYLES_DIR, style_id, 'encyclopedia.md')
    if not os.path.exists(encyc_path):
        return 'empty'
    with open(encyc_path, 'r', encoding='utf-8') as f:
        content = f.read(500)
    if 'draft' in content:
        return 'draft'
    if 'reviewed' in content:
        return 'reviewed'
    return 'draft'


# ============================================================
# 2. 研究提示词生成
# ============================================================

def build_research_prompt(style_id, style_info, mode='full'):
    """构建研究提示词"""
    name_zh = style_info.get('name_zh', style_id)
    name_en = style_info.get('name_en', '')

    prompts = {
        'full': f"""请研究"{name_zh} ({name_en})"男性穿搭风格，输出以下内容（中文）：

## 概述
- 发源年代、发源地
- 风格关键词（5-8个）
- 一句话定义（50字以内）

## 历史文化
- 起源：什么时候、什么背景下诞生？与哪些人物/品牌/事件有关？
- 发展脉络：从起源到现在的重要时间节点
- 文化意义：这个风格在时尚史上的位置

## 美学特征
- 廓形特点
- 色板（主色调/点缀色/禁忌色）
- 面料偏好
- 标志单品表（单品名 | 品牌示例 | 选择要点）

## 代表品牌
- 核心品牌（5-10个，含品牌简介）
- 平价替代（3-5个）
- 新兴品牌（如有）

## 风格偶像 & 名人
- 关键推动者（设计师/编辑/造型师）
- 穿着此风格的明星/博主（含人名+身份+贡献/特点）

## 秀场 & 时装周
- 哪些品牌在秀场上展示过此风格
- 代表性秀场/系列

## 关联风格
- 父风格、子风格、平行风格、对立风格

## 流行趋势
- 当前状态（上升/稳定/衰退）
- 流行区域
- 发展方向

## 穿搭建议
- 适合体型、肤色、场合
- 入门建议（3-5条实操建议）

请尽可能提供具体的人名、品牌名、年份、事件。使用 WebSearch 搜索最新信息。""",

        'enrich': f"""请为"{name_zh} ({name_en})"风格补充以下信息（中文）：

1. 代表品牌（品牌名+国家+简介+价位）
2. 风格偶像（人名+身份+为什么是 icon）
3. 秀场/时装周（品牌+季节+秀场亮点）
4. 最新趋势（2025-2026年的变化）

使用 WebSearch 搜索最新信息，提供具体人名/品牌名/年份。""",

        'discover': """请搜索2025-2026年男性时尚领域新出现的穿搭风格/亚文化趋势。

对每个新风格提供：
- 风格名称（中文+英文）
- 一句话描述
- 发源时间/地点
- 关键特征（3-5个关键词）
- 代表品牌/人物

重点关注：
- 社交媒体（小红书/Instagram/TikTok）上的新标签
- 时装周上出现的新趋势
- K-pop/明星带火的新风格
- 户外/运动/科技跨界产生的融合风格

使用 WebSearch 搜索最新信息。"""
    }

    return prompts.get(mode, prompts['full'])


# ============================================================
# 3. 内容写入
# ============================================================

def save_encyclopedia(style_id, content, status='draft'):
    """保存百科内容到文件"""
    style_dir = os.path.join(STYLES_DIR, style_id)
    os.makedirs(style_dir, exist_ok=True)
    os.makedirs(os.path.join(style_dir, 'references'), exist_ok=True)

    # 替换模板变量
    if status == 'draft':
        content = content.replace('{{STATUS}}', 'draft')
    content = content.replace('{{DATE}}', time.strftime('%Y-%m-%d'))

    encyc_path = os.path.join(style_dir, 'encyclopedia.md')
    with open(encyc_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 生成 brands.json 骨架
    brands_path = os.path.join(style_dir, 'brands.json')
    if not os.path.exists(brands_path):
        with open(brands_path, 'w', encoding='utf-8') as f:
            json.dump({
                'style_id': style_id,
                'core_brands': [],
                'affordable_alternatives': [],
                'emerging_brands': [],
                '_last_updated': time.strftime('%Y-%m-%d'),
            }, f, ensure_ascii=False, indent=2)

    # 生成 people.json 骨架
    people_path = os.path.join(style_dir, 'people.json')
    if not os.path.exists(people_path):
        with open(people_path, 'w', encoding='utf-8') as f:
            json.dump({
                'style_id': style_id,
                'key_figures': [],
                'celebrities': [],
                'influencers': [],
                '_last_updated': time.strftime('%Y-%m-%d'),
            }, f, ensure_ascii=False, indent=2)

    return encyc_path


# ============================================================
# 4. 命令行接口
# ============================================================

def cmd_research(style_id):
    """研究单个风格 — 输出提示词供 Claude 使用"""
    registry = get_style_registry()
    info = registry.get(style_id)
    if not info:
        print(f"❌ 未知风格: {style_id}")
        print(f"   可用: {', '.join(registry.keys())}")
        return

    prompt = build_research_prompt(style_id, info, 'full')
    out_path = os.path.join(STYLES_DIR, style_id, 'research_prompt.txt')
    os.makedirs(os.path.join(STYLES_DIR, style_id), exist_ok=True)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"📋 研究提示词已生成: {out_path}")
    print(f"\n{'='*60}")
    print(prompt)
    print(f"{'='*60}")
    print(f"\n👉 将此提示词复制到 Claude 对话中，配合 WebSearch 进行研究。")
    print(f"   研究结果保存为: styles_universal/{style_id}/encyclopedia.md")


def cmd_discover():
    """发现新风格"""
    prompt = build_research_prompt(None, {}, 'discover')

    out_path = os.path.join(STYLES_DIR, 'discover_prompt.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print("🔍 风格发现模式")
    print(f"📋 提示词已保存: {out_path}")
    print(f"\n{prompt[:500]}...")


def cmd_enrich(style_id):
    """充实已有风格"""
    registry = get_style_registry()
    info = registry.get(style_id)
    if not info:
        print(f"❌ 未知风格: {style_id}")
        return

    status = get_style_status(style_id)
    print(f"📝 {info['name_zh']} ({style_id}) — 状态: {status}")

    prompt = build_research_prompt(style_id, info, 'enrich')
    out_path = os.path.join(STYLES_DIR, style_id, 'enrich_prompt.txt')
    os.makedirs(os.path.join(STYLES_DIR, style_id), exist_ok=True)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"📋 充实提示词已生成: {out_path}")
    print(f"\n👉 将此提示词复制到 Claude 对话中进行研究。")


def cmd_list():
    """列出所有风格状态"""
    registry = get_style_registry()
    print(f"\n{'='*60}")
    print(f"📚 通用风格百科 — {len(registry)} 个风格")
    print(f"{'='*60}")

    by_status = {'reviewed': [], 'draft': [], 'empty': []}
    for sid, info in registry.items():
        status = get_style_status(sid)
        by_status.setdefault(status, []).append((sid, info))

    for status, label in [('reviewed', '✅ 已完成'), ('draft', '📝 草稿'), ('empty', '⬜ 待研究')]:
        items = by_status.get(status, [])
        if items:
            print(f"\n{label} ({len(items)}):")
            for sid, info in items:
                parent = info.get('parent', '?')
                print(f"  {sid:30s} | {info['name_zh']:12s} | {parent}")

    total_done = len(by_status.get('reviewed', [])) + len(by_status.get('draft', []))
    print(f"\n📊 覆盖率: {total_done}/{len(registry)} ({total_done*100//len(registry)}%)")


def cmd_batch():
    """批量处理：为所有待研究风格生成提示词"""
    registry = get_style_registry()
    pending = []

    for sid in registry:
        status = get_style_status(sid)
        if status == 'empty':
            pending.append(sid)

    if not pending:
        print("✅ 所有风格已覆盖！")
        return

    print(f"📋 生成 {len(pending)} 个待研究风格的提示词...")
    for sid in pending:
        info = registry[sid]
        prompt = build_research_prompt(sid, info, 'full')
        out_path = os.path.join(STYLES_DIR, sid, 'research_prompt.txt')
        os.makedirs(os.path.join(STYLES_DIR, sid), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"  ✅ {sid} ({info['name_zh']})")

    print(f"\n✅ 已完成。使用 --list 查看状态。")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h'):
        print("风格研究代理 — 自动搜集分析风格百科内容")
        print("\n用法:")
        print("  python3 tools/style_research.py <style_id>       研究单个风格")
        print("  python3 tools/style_research.py --discover         发现新风格趋势")
        print("  python3 tools/style_research.py --enrich <id>      充实已有风格")
        print("  python3 tools/style_research.py --batch            批量生成待研究提示词")
        print("  python3 tools/style_research.py --list             列出所有风格状态")
        print("\n示例:")
        print("  python3 tools/style_research.py american_ivy_league")
        print("  python3 tools/style_research.py --enrich japanese_city_boy")
        return

    cmd = sys.argv[1]

    if cmd == '--discover':
        cmd_discover()
    elif cmd == '--list':
        cmd_list()
    elif cmd == '--batch':
        cmd_batch()
    elif cmd == '--enrich':
        if len(sys.argv) < 3:
            print("❌ 请指定风格ID: --enrich <style_id>")
            return
        cmd_enrich(sys.argv[2])
    else:
        cmd_research(cmd)


if __name__ == '__main__':
    main()
