#!/usr/bin/env python3
"""
风格研究代理 v2 — 加载共享知识，聚焦差异化研究。

与 style_research.py（旧）的区别：
  - 旧：生成通用 prompt → 人复制到 Claude → 全手动研究
  - 新：加载集群共享知识 → 智能 prompt（只搜差异化）→ 预填百科模板

用法:
  python3 tools/style_research_agent.py WF-01                    # 研究女性风格（自动检测集群）
  python3 tools/style_research_agent.py WF-01 --gender female    # 同上，显式指定
  python3 tools/style_research_agent.py japanese_amekaji --gender male  # 研究男性风格
  python3 tools/style_research_agent.py --list-clusters          # 列出所有集群
  python3 tools/style_research_agent.py --batch-female           # 批量生成 12 个女性风格提示词
"""

import os, sys, json, glob, time, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')

# ── 女性风格集群定义 ──
FEMALE_CLUSTERS = {
    'east_asian': {
        'name': '东亚',
        'shared': 'styles/female/_shared/east_asian.md',
        'styles': ['WF-02', 'WF-03', 'WF-04'],
        'style_names': {
            'WF-02': '韩系少女 Korean Girlie',
            'WF-03': '日系森系 Mori Kei',
            'WF-04': '新中式 New Chinese',
        },
    },
    'european_classic': {
        'name': '欧洲经典',
        'shared': 'styles/female/_shared/european_classic.md',
        'styles': ['WF-01', 'WF-06', 'WF-07', 'WF-09', 'WF-12'],
        'style_names': {
            'WF-01': '法式慵懒 French Effortless',
            'WF-06': '极简 Minimalist',
            'WF-07': '学院风 Preppy',
            'WF-09': '波西米亚 Boho',
            'WF-12': '暗黑学院 Dark Academia',
        },
    },
    'modern_urban': {
        'name': '现代都市',
        'shared': 'styles/female/_shared/modern_urban.md',
        'styles': ['WF-05', 'WF-08', 'WF-10', 'WF-11'],
        'style_names': {
            'WF-05': '美式休闲 American Casual',
            'WF-08': '运动休闲 Athleisure',
            'WF-10': 'Y2K 千禧复古',
            'WF-11': '都市通勤 City Girl',
        },
    },
}

# ── 女性风格完整信息（来自设计文档）──
FEMALE_STYLE_INFO = {
    'WF-01': {'name_zh': '法式慵懒', 'name_en': 'French Effortless', 'keywords': 'french effortless style women 2025', 'dir': 'WF-01_french_effortless'},
    'WF-02': {'name_zh': '韩系少女', 'name_en': 'Korean Girlie', 'keywords': 'korean girlie fashion 2025', 'dir': 'WF-02_korean_girlie'},
    'WF-03': {'name_zh': '日系森系', 'name_en': 'Mori Kei', 'keywords': 'mori kei japanese forest girl', 'dir': 'WF-03_mori_kei'},
    'WF-04': {'name_zh': '新中式', 'name_en': 'New Chinese', 'keywords': 'new chinese style women modern', 'dir': 'WF-04_new_chinese'},
    'WF-05': {'name_zh': '美式休闲', 'name_en': 'American Casual', 'keywords': 'american casual women street style', 'dir': 'WF-05_american_casual'},
    'WF-06': {'name_zh': '极简', 'name_en': 'Minimalist', 'keywords': 'minimalist women capsule wardrobe', 'dir': 'WF-06_minimalist'},
    'WF-07': {'name_zh': '学院风', 'name_en': 'Preppy', 'keywords': 'preppy women style academic', 'dir': 'WF-07_preppy'},
    'WF-08': {'name_zh': '运动休闲', 'name_en': 'Athleisure', 'keywords': 'athleisure women sporty chic', 'dir': 'WF-08_athleisure'},
    'WF-09': {'name_zh': '波西米亚', 'name_en': 'Boho', 'keywords': 'boho chic women bohemian', 'dir': 'WF-09_boho'},
    'WF-10': {'name_zh': 'Y2K 千禧复古', 'name_en': 'Y2K Revival', 'keywords': 'y2k fashion women 2025 revival', 'dir': 'WF-10_y2k'},
    'WF-11': {'name_zh': '都市通勤', 'name_en': 'City Girl', 'keywords': 'city commute workwear women', 'dir': 'WF-11_city_girl'},
    'WF-12': {'name_zh': '暗黑学院', 'name_en': 'Dark Academia', 'keywords': 'dark academia women aesthetic', 'dir': 'WF-12_dark_academia'},
}


def get_style_dir(style_id, gender='female'):
    """根据 style_id 返回实际目录名。如 WF-01 → WF-01_french_effortless"""
    if gender == 'female':
        info = FEMALE_STYLE_INFO.get(style_id, {})
        return info.get('dir', style_id)
    return style_id


# ============================================================
# 1. 共享知识加载
# ============================================================

def find_cluster(style_id, gender='female'):
    """自动检测风格所属集群。返回 (cluster_key, cluster_info) 或 (None, None)"""
    if gender == 'female':
        for ck, ci in FEMALE_CLUSTERS.items():
            if style_id in ci['styles']:
                return ck, ci
    # 男性风格回退到旧的 style_research.py 逻辑
    return None, None


def load_shared_knowledge(style_id, gender='female'):
    """加载风格的共享知识文本。无共享知识时返回空字符串。"""
    ck, ci = find_cluster(style_id, gender)
    if not ci:
        return '', None

    shared_path = os.path.join(PROJ_DIR, ci['shared'])
    if os.path.exists(shared_path):
        with open(shared_path, 'r', encoding='utf-8') as f:
            return f.read(), ci
    return '', ci


def get_sister_styles(style_id, cluster_info):
    """获取同一集群内其他风格的名称列表"""
    if not cluster_info:
        return []
    sisters = []
    for sid in cluster_info['styles']:
        if sid != style_id:
            name = cluster_info['style_names'].get(sid) or FEMALE_STYLE_INFO.get(sid, {}).get('name_zh', sid)
            sisters.append(f"{sid} ({name})")
    return sisters


TREND_LABELS = {
    "popular_trend": "流行趋势",
    "classic": "经典风格",
    "niche": "小众领域"
}


def auto_classify_trend_category(style_info):
    """
    自动判定女性风格的趋势分类（流行趋势/经典风格/小众领域）。
    基于 era + parent + scene 的决策树。
    返回 (category_key, confidence, reason)
    """
    parent = style_info.get('parent', '')
    era = style_info.get('era', '')
    scene = style_info.get('scene', '')
    status = style_info.get('status', '')

    # 规则 1: era == classic → 经典
    if era == 'classic':
        return 'classic', 'high', '时代标注为 classic，深厚的文化根基'

    # 规则 2: 复古时代 (1950s-1990s)
    retro_eras = {'1950s', '1960s', '1970s', '1980s', '1990s'}
    if era in retro_eras:
        # 欧洲经典 parent → 经典
        if parent in {'european_classic'}:
            return 'classic', 'high', f'{era} 欧洲经典风格，已被时尚史收录'
        # 现代都市的复古 → 经典（如美式休闲 1950s）
        if parent in {'modern_urban'}:
            return 'classic', 'high', f'{era} 都市风格，已稳定数十年'
        # 另类酷感的复古 → 小众（如 Soft Grunge 1990s）
        if parent in {'edgy_alternative'}:
            return 'niche', 'high', f'{era} 亚文化风格，保留小众身份'
        # 都市街头的复古 → 经典（如 Vintage 90s 是设计经典）
        if parent in {'urban_street'} and era == '1990s':
            return 'classic', 'medium', f'{era} 极简设计经典，超越复兴周期'
        return 'classic', 'medium', f'{era} 复古风格，大概率经典'

    # 规则 3: 当代 2010s
    if era == '2010s':
        # 现代都市/东亚的 2010s
        if parent == 'east_asian':
            return 'classic', 'medium', '韩流已有15+年成熟品牌生态（如 Stylenanda 2004）'
        if parent == 'modern_urban':
            return 'popular_trend', 'medium', '运动休闲是 2010s 社交媒体产物'
        if parent in {'romantic_feminine', 'luxe_minimalist'}:
            return 'popular_trend', 'medium', '社交媒体原生趋势'
        if parent in {'edgy_alternative', 'urban_street'}:
            return 'niche', 'high', '2010s 另类/街头亚文化'
        return 'popular_trend', 'medium', '2010s 时代，社交媒体兴起期'

    # 规则 4: 当代 2020s
    if era == '2020s':
        # 明确的趋势集群（TikTok 原生）
        if parent in {'dramatic_statement', 'nature_escape', 'romantic_feminine'}:
            return 'popular_trend', 'high', f'{parent} 集群是 TikTok 原生趋势'
        if parent == 'luxe_minimalist':
            # 静奢风=趋势, 老钱风=经典(era会被单独标注classic), 干净女孩=趋势
            return 'popular_trend', 'medium', f'{parent} 2020s 社交媒体标签'
        # 另类酷感 → 小众
        if parent == 'edgy_alternative':
            return 'niche', 'high', '另类酷感集群，亚文化驱动'
        # 都市街头 2020s → 趋势
        if parent == 'urban_street':
            return 'popular_trend', 'medium', 'TikTok 驱动的街头风格'
        # 东亚 2020s → 趋势（新中式是国潮）
        if parent == 'east_asian':
            return 'popular_trend', 'medium', '国潮/社交媒体驱动的新中式'
        # 欧洲经典 2020s → 检查是否 Dark Academia 这种过渡案例
        if parent == 'european_classic':
            return 'niche', 'medium', '欧洲经典集群中 2020s 风格（如暗黑学院）已转入小众稳定态'

    # 规则 5: 当代 2000s
    if era == '2000s':
        if parent == 'east_asian':
            return 'niche', 'medium', '日系森系，日本亚文化'
        if parent == 'modern_urban':
            return 'popular_trend', 'medium', 'Y2K 复兴由社交媒体驱动'

    return 'uncertain', 'low', '无法自动判定，需人工审核'


def load_trend_from_categories(style_id, gender='female'):
    """从 categories.json 读取已存储的趋势分类"""
    if gender == 'female':
        cat_path = os.path.join(PROJ_DIR, 'styles/female', 'categories.json')
    else:
        cat_path = os.path.join(PROJ_DIR, 'styles_universal', 'categories.json')
    if os.path.exists(cat_path):
        with open(cat_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        registry = data.get('style_registry', {})
        info = registry.get(style_id, {})
        return info.get('trend_category', None)
    return None


# ============================================================
# 2. 智能 Prompt 生成
# ============================================================

ENCYCLOPEDIA_TEMPLATE = '''# {name_zh}（{name_en}）
> **状态**: draft | 最后更新: {date} | 分类: {cluster_name} | **趋势**: {trend_label}

![封面](representative.jpg)

## 📖 概述
- 发源年代:
- 发源地:
- 风格关键词（5-8个）:
- 一句话定义（50字以内）:

## 📜 历史文化
- 起源：什么时候、什么背景下诞生？
- 发展脉络：从起源到现在的重要时间节点
- 文化意义：这个风格在时尚史上的位置

## 🎨 美学特征
- 廓形特点:
- 色板（主色调/点缀色/禁忌色）:
- 面料偏好:
- 标志单品表（单品名 | 品牌示例 | 选择要点）:

## 🏷️ 代表品牌
- 核心品牌（5-10个，含品牌简介+国家+价位）:
- 平价替代（3-5个）:
- 新兴品牌（如有）:

## 👤 风格偶像 & 名人
- 关键推动者（设计师/编辑/造型师）:
- 穿着此风格的明星/博主（含人名+身份+贡献/特点）:

## 👗 秀场 & 时装周
- 哪些品牌在秀场上展示过此风格:
- 代表性秀场/系列:

## 🔗 关联风格
- 父风格 / 子风格 / 平行风格 / 对立风格

## 📈 流行趋势
- 当前状态（上升/稳定/衰退）:
- 流行区域:
- 发展方向:

## 💡 穿搭建议
- 适合体型:
- 适合肤色:
- 适合场合:
- 入门建议（3-5条实操建议）:

---
*本文基于多源研究整理，AI 辅助生成。*
'''


def build_smart_prompt(style_id, style_info, shared_knowledge, cluster_info, mode='full', gender='female'):
    """构建智能研究提示词 — 加载共享知识，聚焦差异化"""
    name_zh = style_info.get('name_zh', style_id)
    name_en = style_info.get('name_en', '')
    keywords = style_info.get('keywords', f'{name_en} women fashion 2025')
    cluster_name = cluster_info.get('name', '通用') if cluster_info else '通用'
    style_dir_name = get_style_dir(style_id, gender)

    sisters = get_sister_styles(style_id, cluster_info)
    sisters_text = '\n'.join([f'  - {s}' for s in sisters]) if sisters else '  无（独立风格）'

    # 是否已有共享知识
    has_shared = len(shared_knowledge) > 100 if shared_knowledge else False

    if has_shared:
        shared_context = f"""
## ⚠️ 已知共享知识（无需重新搜索）
以下信息已在集群研究中完成，请直接引用其中的品牌/人物/历史，**不要重复搜索**：

{shared_knowledge[:3000]}

---
## 🔍 本次研究焦点：{name_zh} 的差异化特征

**同集群姐妹风格**:
{sisters_text}

**研究指令**:
1. 基于共享知识中的品牌/历史/色板，**重点研究 {name_zh} 独有的特征**
2. 不要重复共享知识已有的品牌列表，而是标注"哪些品牌对本风格最重要，为什么"
3. 如果共享知识中某品牌与本风格高度关联，直接引用并展开
4. 搜索关键词优先使用: "{keywords}"
5. 与姐妹风格的差异至少用 3-5 个具体点说明
"""
    else:
        shared_context = f"""
## 🔍 研究任务：{name_zh} ({name_en})

**搜索关键词**: "{keywords}"

请从头研究这个风格的全部维度：
"""

    prompt = f"""{shared_context}
请输出以下内容（中文），保存为百科草稿：

## 📖 概述
- 发源年代、发源地（具体到城市/区域）
- 风格关键词（5-8个，中文+英文）
- 一句话定义（50字以内）

## 📜 历史文化
- 起源：诞生的具体背景、关键人物、标志事件
- 发展脉络：从起源到现在的重要时间节点（列出年份+事件）
- 文化意义：这个风格在女性时尚史上的位置

## 🎨 美学特征
- 廓形特点（具体剪裁/比例，如 A字/收腰/Oversize）
- 色板（主色调/点缀色/禁忌色，附色值）
- 面料偏好（具体面料名，非笼统描述）
- 标志单品表（表格：单品 | 品牌示例 | 选择要点）

## 🏷️ 代表品牌
- 核心品牌（5-10个，每个含：品牌名+国家+一句话定位+价位）
- 平价替代（3-5个）
- 新兴品牌（如有，2024-2026 年值得关注的）

## 👤 风格偶像 & 名人
- 关键推动者（设计师/编辑/造型师，含具体成就）
- 穿着此风格的明星/博主（含人名+身份+为什么是 icon）

## 👗 秀场 & 时装周
- 展示过此风格的品牌和系列（含具体季节/年份）
- 代表性秀场造型描述

## 🔗 关联风格
- 父风格 / 子风格 / 平行风格 / 对立风格（至少各列 1 个）

## 📈 流行趋势
- 当前状态（上升/稳定/衰退，附证据）
- 流行区域（具体国家/城市）
- 2025-2026 年发展方向

## 💡 穿搭建议
- 适合体型（苹果/梨型/沙漏/直筒/倒三角 — 选最合适的）
- 适合肤色（冷白/暖白/自然/小麦）
- 适合场合（具体场景）
- 入门建议（3-5条可操作的搭配公式）

{f'### ⚠️ 与姐妹风格的区分（关键）' if sisters else ''}
{f'请用 3-5 个具体点说明 {name_zh} 与以下风格的明确区别，避免内容雷同：' if sisters else ''}
{f'{sisters_text}' if sisters else ''}

---
格式要求：使用 WebSearch 搜索最新信息。提供具体的人名、品牌名、年份、事件。
保存到: styles/female/{style_dir_name}/encyclopedia.md
"""
    return prompt.strip()


# ============================================================
# 3. 百科模板预填
# ============================================================

def write_template(style_id, style_info, cluster_info, gender='female'):
    """预填百科模板（含共享知识引用 + 趋势分类自动建议），方便直接编辑"""
    name_zh = style_info.get('name_zh', style_id)
    name_en = style_info.get('name_en', '')
    cluster_name = cluster_info.get('name', '通用') if cluster_info else '通用'

    # 自动归类趋势分类
    trend_cat, confidence, reason = auto_classify_trend_category(style_info)
    trend_label = TREND_LABELS.get(trend_cat, '待分类')

    # 确定输出路径
    base_dir = 'styles/female' if gender == 'female' else 'styles_universal'
    style_dir_name = get_style_dir(style_id, gender)
    out_dir = os.path.join(PROJ_DIR, base_dir, style_dir_name)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, 'references'), exist_ok=True)

    encyc_path = os.path.join(out_dir, 'encyclopedia.md')
    if os.path.exists(encyc_path):
        print(f"   ⚠️ 百科已存在，跳过模板生成: {encyc_path}")
        return encyc_path

    template = ENCYCLOPEDIA_TEMPLATE.format(
        name_zh=name_zh,
        name_en=name_en,
        date=time.strftime('%Y-%m-%d'),
        cluster_name=cluster_name,
        trend_label=trend_label,
    )
    with open(encyc_path, 'w', encoding='utf-8') as f:
        f.write(template)
    return encyc_path


# ============================================================
# 4. 命令行接口
# ============================================================

def cmd_research(style_id, gender='female'):
    """研究单个风格"""
    info = FEMALE_STYLE_INFO.get(style_id) if gender == 'female' else None
    if not info:
        print(f"❌ 未知风格: {style_id}")
        if gender == 'female':
            print(f"   可用: {', '.join(FEMALE_STYLE_INFO.keys())}")
        return

    shared, cluster_info = load_shared_knowledge(style_id, gender)
    has_shared = bool(shared and len(shared) > 100)

    print(f"\n{'='*60}")
    print(f"🔬 风格研究代理 v2: {info['name_zh']} ({info['name_en']})")
    print(f"{'='*60}")

    if has_shared:
        cluster_name = cluster_info.get('name', '?') if cluster_info else '?'
        print(f"📚 已加载共享知识: {cluster_name} 集群")
        sisters = get_sister_styles(style_id, cluster_info)
        if sisters:
            print(f"👯 姐妹风格: {', '.join(sisters)}")
    else:
        print(f"📝 无共享知识（独立研究模式）")

    # 自动归类建议
    trend_cat, confidence, reason = auto_classify_trend_category(info)
    trend_label = TREND_LABELS.get(trend_cat, trend_cat)
    confidence_icon = {'high': '🟢', 'medium': '🟡', 'low': '🔴'}.get(confidence, '⚪')
    print(f"🏷️  自动归类: {trend_label} {confidence_icon}（{reason}）")
    if confidence == 'low':
        print(f"   ⚠️ 置信度低，请人工审核后写入 categories.json")

    # 1. 生成智能 prompt
    prompt = build_smart_prompt(style_id, info, shared, cluster_info, 'full')
    style_dir_name = get_style_dir(style_id, gender)
    prompt_path = os.path.join(PROJ_DIR, 'styles/female', style_dir_name, '_research_prompt.txt')
    os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(prompt)

    # 2. 预填百科模板
    template_path = write_template(style_id, info, cluster_info)

    print(f"\n📋 智能研究提示词: {prompt_path}")
    print(f"📝 百科模板: {template_path}")
    print(f"\n⏱️ 预估 token: {'~10K（共享知识+' if has_shared else '~40K（无共享知识）'}差异化搜索)")
    print(f"👉 将研究提示词提供给 Claude，配合 WebSearch 进行研究。")
    print(f"   研究结果直接写入百科模板。")
    print(f"\n💡 提示: 研究时只需关注「与姐妹风格的差异」，共享知识中的品牌/历史已覆盖。")


def cmd_list_clusters():
    """列出所有女性风格集群"""
    print(f"\n{'='*60}")
    print(f"👗 女性风格集群 — 12 个风格")
    print(f"{'='*60}")
    for ck, ci in FEMALE_CLUSTERS.items():
        print(f"\n📚 {ci['name']} 集群:")
        print(f"   共享知识: {ci['shared']}")
        for sid in ci['styles']:
            name = ci['style_names'].get(sid) or FEMALE_STYLE_INFO.get(sid, {}).get('name_zh', sid)
            style_dir_name = get_style_dir(sid, 'female')
            encyc_exists = os.path.exists(os.path.join(PROJ_DIR, 'styles/female', style_dir_name, 'encyclopedia.md'))
            status = '📝' if encyc_exists else '⬜'
            print(f"   {status} {sid} — {name}")


def cmd_batch_female():
    """批量生成所有 12 个女性风格的智能提示词+模板"""
    print(f"\n{'='*60}")
    print(f"🔬 批量生成 12 个女性风格研究提示词")
    print(f"{'='*60}")

    for ck, ci in FEMALE_CLUSTERS.items():
        shared_path = os.path.join(PROJ_DIR, ci['shared'])
        shared = ''
        if os.path.exists(shared_path):
            with open(shared_path, 'r', encoding='utf-8') as f:
                shared = f.read()
            print(f"\n📚 {ci['name']} 集群 ({len(ci['styles'])} 风格) — 共享知识已加载")

        for sid in ci['styles']:
            info = FEMALE_STYLE_INFO.get(sid)
            if not info:
                continue
            prompt = build_smart_prompt(sid, info, shared, ci, 'full')
            style_dir_name = get_style_dir(sid, 'female')
            prompt_path = os.path.join(PROJ_DIR, 'styles/female', style_dir_name, '_research_prompt.txt')
            os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            template_path = write_template(sid, info, ci)
            print(f"   ✅ {sid} — {info['name_zh']} (prompt + template)")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h'):
        print("风格研究代理 v2 — 加载共享知识，聚焦差异化研究")
        print("\n用法:")
        print("  python3 tools/style_research_agent.py <style_id>          研究单个风格")
        print("  python3 tools/style_research_agent.py WF-01 --gender female  女性风格")
        print("  python3 tools/style_research_agent.py --list-clusters        列出集群")
        print("  python3 tools/style_research_agent.py --batch-female         批量生成")
        print("\n示例:")
        print("  python3 tools/style_research_agent.py WF-02                  # 韩系少女（含东亚共享知识）")
        print("  python3 tools/style_research_agent.py WF-01                  # 法式慵懒（含欧洲共享知识）")
        print("  python3 tools/style_research_agent.py --batch-female         # 批量生成 12 个")
        print("\n与旧工具对比:")
        print("  旧: style_research.py WF-01 → 通用 prompt → 人复制 → 全手动")
        print("  新: style_research_agent.py WF-01 → 智能 prompt（含共享知识+差异化焦点）")
        return

    cmd = sys.argv[1]

    # 解析 --gender
    gender = 'female'
    for i, a in enumerate(sys.argv):
        if a == '--gender' and i + 1 < len(sys.argv):
            gender = sys.argv[i + 1]

    if cmd == '--list-clusters':
        cmd_list_clusters()
    elif cmd == '--batch-female':
        cmd_batch_female()
    elif cmd.startswith('WF-'):
        cmd_research(cmd, gender=gender)
    else:
        # 尝试作为男性风格，回退到旧工具
        print(f"ℹ️ 非女性风格 ID，请使用 style_research.py:")
        print(f"   python3 tools/style_research.py {cmd}")


if __name__ == '__main__':
    main()
