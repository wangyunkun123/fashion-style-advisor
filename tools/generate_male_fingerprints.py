#!/usr/bin/env python3
"""
批量生成男性风格指纹 — 从 styles_universal/<style>/encyclopedia.md 提取结构化数据
→ styles/male/<style>.json（扁平文件，语义名 ID）

复用 generate_female_fingerprints.py 的全部 extract/infer 解析函数，
仅适配男性的路径与命名约定：
  - 百科来源: styles_universal/<style_id>/encyclopedia.md
  - 指纹输出: styles/male/<style_id>.json （扁平单文件，非目录）
  - style_id = 语义名（如 italian_sprezzatura），非 WF 编号

用法:
  python3 tools/generate_male_fingerprints.py --dry-run          # 预览全部缺失
  python3 tools/generate_male_fingerprints.py                    # 生成全部缺失指纹
  python3 tools/generate_male_fingerprints.py italian_sprezzatura # 只生成一个
  python3 tools/generate_male_fingerprints.py --force <id>       # 覆盖已有指纹
"""

import os, sys, json, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

# 复用女性工具的解析/推断函数（纯函数，无性别耦合）
from generate_female_fingerprints import (
    parse_md_section, parse_subsection, extract_table_rows, extract_list_items,
    extract_silhouette, extract_colors, extract_pattern_rules,
    extract_fabric_prefs, extract_key_items,
    infer_hard_constraints, infer_soft_constraints, infer_body_bonus, infer_hue_family,
)

STYLES_UNIVERSAL = os.path.join(PROJ_DIR, 'styles_universal')
STYLES_MALE = os.path.join(PROJ_DIR, 'styles', 'male')

# 非风格目录（跳过）
SKIP_DIRS = {'references', 'templates'}

# formality → 中文分类（与现有男性指纹 category 命名对齐）
_FORMALITY_CAT = {
    'ultra_formal': '正式',
    'formal': '正式',
    'semi_formal': '半正式',
    'smart_casual': '轻正式',
    'business_casual': '商务休闲',
    'casual': '日常休闲',
    'ultra_casual': '休闲潮流',
    'sporty': '运动休闲',
    'street': '休闲潮流',
}

_CATEGORIES_REGISTRY = None


def _load_categories_registry():
    """加载 styles_universal/categories.json 的 style_registry（权威分类/formality）。"""
    global _CATEGORIES_REGISTRY
    if _CATEGORIES_REGISTRY is None:
        cp = os.path.join(STYLES_UNIVERSAL, 'categories.json')
        try:
            with open(cp, encoding='utf-8') as f:
                _CATEGORIES_REGISTRY = json.load(f).get('style_registry', {})
        except Exception:
            _CATEGORIES_REGISTRY = {}
    return _CATEGORIES_REGISTRY


def _category_from_registry(style_id):
    """从 categories.json 的 formality 推断中文 category。"""
    reg = _load_categories_registry().get(style_id, {})
    formality = reg.get('formality', '')
    return _FORMALITY_CAT.get(formality, '')


# ═══ 男性 md 格式专用增强提取（女性 parser 返回空时的 fallback）═══

# 标准色词库（用于从自由文本/代码块中识别颜色）
_COLOR_LEXICON = [
    '海军蓝', '藏青', '藏蓝', '天蓝', '湖蓝', '雾霾蓝', '靛蓝', '钴蓝', '浅蓝', '深蓝', '蓝',
    '橄榄绿', '森林绿', '猎人绿', '军绿', '墨绿', '深绿', '鼠尾草', '薄荷', '绿',
    '酒红', '勃艮第', '砖红', '正红', '暗红', '红',
    '芥末黄', '淡黄', '姜黄', '金', '黄',
    '焦糖', '驼', '卡其', '棕', '咖啡', '巧克力', '奶咖', '栗',
    '米白', '奶油', '象牙', '燕麦', '米', '裸',
    '炭灰', '深灰', '浅灰', '麻灰', '烟灰', '灰',
    '白', '黑',
    '紫', '薰衣草', '桃', '珊瑚', '粉',
]


def _dedup(seq):
    return list(dict.fromkeys([s for s in seq if s]))


def extract_colors_male(md_text, aesthetics):
    """男性 md 配色提取：兼容 ```代码块 / 「核心色彩体系」加粗列表 / 主色调标签 / 表格「配色」行。"""
    base = extract_colors(aesthetics)
    if base.get('allowed_hues'):
        return base  # 女性 parser 已命中

    hues = []
    logic = base.get('color_logic', '')

    # 1) 代码块色板：```\n主调: ...\n点缀: ...\n逻辑: ...\n```
    for block in re.findall(r'```(.*?)```', aesthetics, re.DOTALL):
        for label in ['主调', '主色调', '基础色', '点缀', '辅助色', '辅色']:
            m = re.search(rf'{label}[：:]\s*(.*?)(?=\n|$)', block)
            if m:
                hues += re.split(r'[、,，/]', m.group(1))
        m = re.search(r'逻辑[：:]\s*(.*?)(?=\n|$)', block)
        if m and not logic:
            logic = m.group(1).strip()[:80]

    # 2) 「核心色彩体系」加粗标题 + 列表
    if not hues:
        m = re.search(r'\*\*核心色彩体系[：:]?\*\*\s*(.*?)(?=\n\*\*|\n##|\n###|\Z)', aesthetics, re.DOTALL)
        if m:
            for line in extract_list_items(m.group(1)):
                # 取破折号/括号前的中文颜色词
                seg = re.split(r'[—\-（(]', line)[0]
                hues.append(seg.strip())

    # 3) 「配色/色板」子章节列表（korean_clean_fit 式：主色调/配色法则）
    if not hues:
        sec = parse_subsection(aesthetics, '配色') or parse_subsection(aesthetics, '色板')
        if sec:
            for label in ['主色调', '主色', '基础色', '点缀色', '辅色']:
                m = re.search(rf'{label}[^：:]*[：:]\s*(.*?)(?=\n|$)', sec)
                if m:
                    hues += re.split(r'[、,，/]', m.group(1))

    # 4) 兜底：从美学章节全文按色词库扫描
    if not hues:
        for c in _COLOR_LEXICON:
            if c in aesthetics:
                hues.append(c)

    # 归一化：保留在色词库中的规范颜色（长词优先，避免「蓝」吞掉「海军蓝」）
    normed = []
    for raw in hues:
        raw = re.sub(r'\(#?[0-9A-Fa-f]{3,6}\)|（.*?）|\(.*?\)', '', raw).strip()
        raw = re.sub(r'\*\*|【|】', '', raw).strip()
        if not raw:
            continue
        matched = None
        for c in _COLOR_LEXICON:  # 已按长度大致降序
            if c in raw:
                matched = c
                break
        normed.append(matched or (raw if len(raw) <= 6 else None))
    normed = _dedup([n for n in normed if n])[:10]

    if normed:
        base['allowed_hues'] = normed
        base['allowed_hue_families'] = infer_hue_family(normed)
    if logic:
        base['color_logic'] = logic
    return base


# 男性单品品类映射（补充女性映射中缺的男装品类）
_CAT_MAP_MALE = {
    '西装外套': 'JK', '西装夹克': 'JK', '西装': 'JK', '夹克': 'JK', '外套': 'JK',
    '风衣': 'JK', '大衣': 'JK', '开衫': 'KNIT', '针织': 'KNIT', '毛衣': 'KNIT',
    '羊毛衫': 'KNIT', '卫衣': 'LS', '帽衫': 'LS',
    '衬衫': 'SHIRT', '衬衣': 'SHIRT', 'OCBD': 'SHIRT', '牛津布': 'SHIRT', 'Polo': 'TS',
    'T恤': 'TS', 'Tee': 'TS', '上衣': 'TS', '背心': 'TANK',
    '西裤': 'PT', '长裤': 'PT', '斜纹裤': 'PT', 'Chinos': 'PT', '牛仔裤': 'PT',
    '牛仔': 'PT', '工装裤': 'PT', '裤': 'PT', '短裤': 'SH',
    '乐福鞋': 'SHOE', '德比鞋': 'SHOE', '牛津鞋': 'SHOE', '皮鞋': 'SHOE',
    '船鞋': 'SHOE', '运动鞋': 'SHOE', '球鞋': 'SHOE', '靴': 'SHOE', '鞋': 'SHOE',
    '包': 'BAG', '邮差包': 'BAG', '托特': 'BAG', '背包': 'BAG',
    '帽': 'HAT', '领带': 'ACC', '方巾': 'ACC', '围巾': 'ACC', '腰带': 'ACC',
    '袖扣': 'ACC', '墨镜': 'SUN', '眼镜': 'SUN',
}


def _map_cat_male(name):
    for kw, code in _CAT_MAP_MALE.items():
        if kw in name:
            return code
    return 'TS'


def extract_key_items_male(aesthetics):
    """男性单品提取：先试女性表格 parser，失败则从多种「单品」章节/表格/列表提取。"""
    items = extract_key_items(aesthetics)
    if items:
        for it in items:
            if it.get('category_code') in (None, 'TS'):
                it['category_code'] = _map_cat_male(it.get('name', ''))
        return items

    bonus_scores = [20, 15, 15, 10, 10, 5]

    # 1) 尝试多种单品子章节名（含"标志性单品"变体）
    lines = []
    for label in ['标志性单品', '核心廓形与单品', '标志单品', '核心单品', '关键单品', '经典单品']:
        sec = parse_subsection(aesthetics, label)
        if not sec:
            m = re.search(rf'\*\*[^*]*{label}[：:]?\*\*\s*(.*?)(?=\n\*\*|\n##|\n###|\Z)', aesthetics, re.DOTALL)
            sec = m.group(1) if m else ''
        if sec:
            # 优先表格，其次列表
            rows = extract_table_rows(sec)
            if rows:
                lines = [r[1] if len(r) > 1 and r[1] else r[0] for r in rows]
            else:
                lines = extract_list_items(sec)
            if lines:
                break

    # 2) 兜底：从美学章节任意含"单品/衬衫/西装/裤/鞋"的表格行提取
    if not lines:
        for line in aesthetics.split('\n'):
            if line.strip().startswith('|') and any(k in line for k in ['单品', '衬衫', '西装', '裤', '鞋', '外套', '夹克']):
                cells = [c.strip() for c in line.split('|')[1:-1]]
                cand = next((c for c in cells if any(kw in c for kw in _CAT_MAP_MALE)), '')
                if cand and '---' not in cand:
                    lines.append(cand)

    # 3) 兜底：美学章节顶层的加粗列表 / 编号列表 / 配件表格首列
    if not lines:
        head_text = re.split(r'\n###\s', aesthetics)[0]  # 首个 ### 之前
        # 加粗列表 - **领巾** / * **XX**
        for m in re.finditer(r'^[\-*]\s*\*\*(.+?)\*\*', head_text, re.M):
            lines.append(m.group(1).strip())
        # 编号列表 1. **双排扣西装** 或 1. 入门：...
        if not lines:
            for m in re.finditer(r'^\d+\.\s*\*\*(.+?)\*\*', aesthetics, re.M):
                lines.append(m.group(1).strip())
        # 配件/公式表格首列（whimsymaxxing 式）
        if not lines:
            for label in ['入门配件', '配件', '核心配件', 'Pitti 公式', '公式']:
                sec = parse_subsection(aesthetics, label)
                if sec:
                    rows = extract_table_rows(sec)
                    lines += [r[0] for r in rows if r and r[0]]
                    for m in re.finditer(r'^\d+\.\s*\*\*(.+?)\*\*', sec, re.M):
                        lines.append(m.group(1).strip())
                    if lines:
                        break

    result = []
    seen_cat = set()
    for i, line in enumerate(lines[:8]):
        name = re.split(r'[—（(:，,]', line)[0].strip()
        name = re.sub(r'\*\*|【|】', '', name).strip()
        if not name or len(name) < 2:
            continue
        cat = _map_cat_male(name)
        result.append({
            'name': name[:30],
            'category_code': cat,
            'bonus': bonus_scores[len(result)] if len(result) < len(bonus_scores) else 5,
            'description': line[:60],
        })
        if len(result) >= 6:
            break
    return result


def extract_silhouette_male(aesthetics, md_text):
    """男性廓形提取：女性 parser + 「### 廓形」章节 + 表格「廓形」行文本补充。"""
    # 汇总更多廓形语料：美学章节 + 廓形子章节 + 表格中含"廓形"的行
    extra = parse_subsection(aesthetics, '廓形') or ''
    for line in md_text.split('\n'):
        if '廓形' in line and '|' in line:
            extra += ' ' + line
    combined = aesthetics + '\n' + extra
    return extract_silhouette(combined)


def _basic_info_from_md(md_text, style_id):
    """从 md 头部提取 name_zh / name_en / description / category。"""
    name_zh, name_en, description, category = '', '', '', ''

    # 标题行：# 意式松弛感（Italian Sprezzatura）
    m = re.search(r'#\s+(.*?)(?:（|\(|\n|$)', md_text)
    if m:
        name_zh = m.group(1).strip()
    m = re.search(r'[（(]([A-Za-z][A-Za-z0-9 \'&/-]+)[)）]', md_text[:200])
    if m:
        name_en = m.group(1).strip()

    m = re.search(r'一句话定义[^：:]*[：:]\s*(.*?)(?=\n|$)', md_text)
    if m:
        description = m.group(1).strip()[:120]

    # 分类：男性百科格式 `> **分类**: 意式 > 当代2000s > 半正式 > 社交场景 > 浪漫调性`
    m = re.search(r'\*\*分类\*\*[：:]\s*(.*?)(?=\n|$)', md_text)
    if not m:
        m = re.search(r'分类[：:]\s*(.*?)(?=\n|$)', md_text)
    if m:
        raw_cat = m.group(1).strip()
        segs = [s.strip() for s in re.split(r'[>》]', raw_cat) if s.strip()]
        # 优先取含正式度/场景语义的段，否则取首段
        formality_kw = ['正式', '休闲', '半正式', '街头', '运动', '社交', '通勤', '度假', '商务']
        chosen = next((s for s in segs if any(k in s for k in formality_kw)), segs[0] if segs else raw_cat)
        category = re.sub(r'场景|调性', '', chosen).strip() or chosen

    return name_zh, name_en, description, category


def generate_fingerprint(style_id, dry_run=False, force=False):
    """从 styles_universal/<style_id>/encyclopedia.md 生成 styles/male/<style_id>.json"""
    md_path = os.path.join(STYLES_UNIVERSAL, style_id, 'encyclopedia.md')
    fp_path = os.path.join(STYLES_MALE, f'{style_id}.json')

    if not os.path.exists(md_path):
        print(f"  ⏭️  {style_id}: 无 encyclopedia.md，跳过")
        return False

    existing = {}
    if os.path.exists(fp_path):
        with open(fp_path) as f:
            existing = json.load(f)
        if not force and existing.get('fingerprint'):
            print(f"  ⏭️  {style_id}: 已有完整指纹，跳过（--force 覆盖）")
            return False

    with open(md_path, encoding='utf-8') as f:
        md_text = f.read()

    # 基本信息：现有 JSON 优先，其次从 md 提取，再次从 categories.json 兜底
    name_zh, name_en, description, category = _basic_info_from_md(md_text, style_id)
    _reg = _load_categories_registry().get(style_id, {})
    name_zh = existing.get('name_zh') or name_zh or _reg.get('name_zh') or style_id
    name_en = existing.get('name_en') or name_en or _reg.get('name_en') or ''
    description = existing.get('description') or description or ''
    category = existing.get('category') or category or _category_from_registry(style_id) or ''
    tier = existing.get('tier', 'explore')
    trend_category = existing.get('trend_category') or _reg.get('trend_category') or 'classic'

    # 以「美学特征」章节为主提取源
    aesthetics = parse_md_section(md_text, '美学特征') or md_text

    silhouette = extract_silhouette_male(aesthetics, md_text)
    color_rules = extract_colors_male(md_text, aesthetics)
    pattern = extract_pattern_rules(aesthetics)
    fabric = extract_fabric_prefs(aesthetics if len(aesthetics) > 200 else md_text)
    key_items = extract_key_items_male(aesthetics)

    if not color_rules.get('allowed_hue_families'):
        color_rules['allowed_hue_families'] = infer_hue_family(color_rules.get('allowed_hues', []))
    if not color_rules.get('color_logic'):
        color_rules['color_logic'] = '自然协调色调为主'

    # 清理颜色脏数据（残留括号/标点/非颜色词）
    clean_hues = []
    for h in color_rules.get('allowed_hues', []):
        h = re.sub(r'[（）()：:、，,]', '', h).strip()
        # 必须命中色词库，否则丢弃
        if h and any(c in h for c in _COLOR_LEXICON):
            clean_hues.append(h)
    if clean_hues:
        color_rules['allowed_hues'] = _dedup(clean_hues)[:10]
        color_rules['allowed_hue_families'] = infer_hue_family(color_rules['allowed_hues'])

    # 相关/冲突风格：不复用女性 WF 映射，留空由后续人工/工具补充（不影响匹配打分）
    related = existing.get('related_styles', []) if isinstance(existing.get('related_styles'), list) else []
    related = [r for r in related if not str(r).startswith('WF-')]
    conflicting = existing.get('conflicting_styles', []) if isinstance(existing.get('conflicting_styles'), list) else []
    conflicting = [c for c in conflicting if not str(c).startswith('WF-')]
    hard_constraints = infer_hard_constraints(md_text, silhouette)
    soft_constraints = infer_soft_constraints(md_text)
    body_bonus = infer_body_bonus(md_text, silhouette)

    head = md_text[:500]
    if any(kw in head for kw in ['日常', '通勤', '极简', '基础', '休闲']):
        intensity = 1
    elif any(kw in head for kw in ['华丽', '大胆', '前卫', '戏剧', '派对', '暗黑', '摇滚', '解构']):
        intensity = 3
    else:
        intensity = 2

    fingerprint = {
        'silhouette': silhouette,
        'color_rules': color_rules,
        'pattern': pattern,
        'fabric': fabric,
        'layering': {
            'level': '中',
            'min_layers': 1,
            'max_layers': 2,
        },
        'formality_range': {'min': 1, 'max': 4},
    }

    result = dict(existing)
    result.update({
        'style_id': style_id,
        'name_zh': name_zh,
        'name_en': name_en,
        'description': description,
        'category': category,
        'intensity': intensity,
        'fingerprint': fingerprint,
        'key_items': key_items,
        'hard_constraints': hard_constraints,
        'soft_constraints': soft_constraints,
        'body_modifier_bonus': body_bonus,
        'related_styles': related,
        'conflicting_styles': conflicting,
        'tier': tier,
        'trend_category': trend_category,
    })

    if dry_run:
        print(f"  📝 {style_id} ({name_zh}): {len(key_items)} 单品 | "
              f"{len(color_rules.get('allowed_hues', []))} 色 | "
              f"{len(hard_constraints)} 硬 | {len(soft_constraints)} 软 | "
              f"廓形{silhouette.get('preferred', [])}")
        return True

    os.makedirs(STYLES_MALE, exist_ok=True)
    with open(fp_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {style_id} ({name_zh}): {len(key_items)} 单品, "
          f"{len(hard_constraints)} 硬约束, {len(soft_constraints)} 软约束")
    return True


def _all_style_ids():
    return sorted([d for d in os.listdir(STYLES_UNIVERSAL)
                   if os.path.isdir(os.path.join(STYLES_UNIVERSAL, d))
                   and d not in SKIP_DIRS and not d.startswith('.') and not d.startswith('_')])


def _missing_style_ids():
    existing = {f[:-5] for f in os.listdir(STYLES_MALE) if f.endswith('.json')}
    return [s for s in _all_style_ids() if s not in existing]


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    force = '--force' in args
    positional = [a for a in args if not a.startswith('--')]

    if positional:
        for sid in positional:
            print(f"🎯 {sid}")
            generate_fingerprint(sid, dry_run, force)
        return

    targets = _all_style_ids() if force else _missing_style_ids()
    print(f"{'🔍 预览' if dry_run else '🔨 生成'} 男性风格指纹 — {len(targets)} 个{'（含已有，--force）' if force else '缺失'}\n")

    generated = 0
    for sid in targets:
        if generate_fingerprint(sid, dry_run, force):
            generated += 1

    print(f"\n{'📝 预览' if dry_run else '✅ 完成'}: {generated}/{len(targets)}")


if __name__ == '__main__':
    main()
