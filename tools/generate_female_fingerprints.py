#!/usr/bin/env python3
"""
批量生成女性风格指纹 — 从 encyclopedia.md 提取结构化数据 → fingerprint.json

用法:
  python3 tools/generate_female_fingerprints.py           # 生成所有缺失指纹
  python3 tools/generate_female_fingerprints.py --dry-run  # 预览不生写
  python3 tools/generate_female_fingerprints.py WF-13      # 只生成一个
"""

import os, sys, json, re, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

STYLES_FEMALE = os.path.join(PROJ_DIR, 'styles', 'female')

# ═══ 解析工具 ═══

def parse_md_section(md_text, heading):
    """提取 markdown 中某个 ## 标题下的内容"""
    pattern = rf'##\s+{re.escape(heading)}.*?\n(.*?)(?=\n##\s|\Z)'
    m = re.search(pattern, md_text, re.DOTALL)
    return m.group(1).strip() if m else ''

def parse_subsection(md_text, sub_heading):
    """提取 ### 子标题内容"""
    # 匹配到下一个 ### 或 ##
    pattern = rf'###\s+{re.escape(sub_heading)}.*?\n(.*?)(?=\n###\s|\n##\s|\Z)'
    m = re.search(pattern, md_text, re.DOTALL)
    if not m:
        # 尝试 **粗体标签**
        pattern = rf'\*\*{re.escape(sub_heading)}\*\*[：:]\s*(.*?)(?=\n\*\*|\n##|\Z)'
        m = re.search(pattern, md_text, re.DOTALL)
    return m.group(1).strip() if m else ''

def extract_table_rows(section_text):
    """从markdown表格提取行数据"""
    rows = []
    lines = section_text.strip().split('\n')
    header_found = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if '|---' in line or '| ---' in line:
            header_found = True
            continue
        if line.startswith('|') and header_found:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and cells[0]:
                rows.append(cells)
    return rows

def extract_list_items(section_text):
    """从列表提取条目"""
    items = []
    for line in section_text.split('\n'):
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            item = line[2:].strip()
            # 移除内联标记
            item = re.sub(r'\*\*', '', item)
            if item:
                items.append(item)
    return items

def extract_colors(color_text):
    """从色板文本提取颜色信息"""
    result = {
        'allowed_hues': [],
        'forbidden_hues': [],
        'max_saturation': '中饱和',
        'min_lightness': '低明度',
        'max_lightness': '高明度',
        'max_colors_per_outfit': 3,
        'color_logic': '',
    }

    # 主色调
    main_pat = r'主色调[：:]\s*(.*?)(?=\n|$)'
    m = re.search(main_pat, color_text)
    if m:
        colors = re.split(r'[、,，]', m.group(1))
        result['allowed_hues'].extend([c.strip() for c in colors if c.strip()])

    # 辅助色
    aux_pat = r'辅助色[：:]\s*(.*?)(?=\n|$)'
    m = re.search(aux_pat, color_text)
    if m:
        colors = re.split(r'[、,，]', m.group(1))
        result['allowed_hues'].extend([c.strip() for c in colors if c.strip()])

    # 禁忌色
    forbid_pat = r'禁忌色[：:]\s*(.*?)(?=\n|$)'
    m = re.search(forbid_pat, color_text)
    if m:
        colors = re.split(r'[、,，]', m.group(1))
        result['forbidden_hues'] = [c.strip() for c in colors if c.strip()]

    # 去重 + 清理 hex 码
    result['allowed_hues'] = list(dict.fromkeys([
        re.sub(r'\(#[0-9A-Fa-f]{6}\)', '', c).strip() for c in result['allowed_hues'] if c.strip()
    ]))
    result['forbidden_hues'] = list(dict.fromkeys([
        re.sub(r'\(#[0-9A-Fa-f]{6}\)', '', c).strip() for c in result['forbidden_hues'] if c.strip()
    ]))

    # 色板逻辑
    logic_pat = r'色板逻辑[：:]\s*(.*?)(?=\n|$)'
    m = re.search(logic_pat, color_text)
    if m:
        result['color_logic'] = m.group(1).strip()[:80]

    # 从 allowed_hues 推断色系家族
    families = set()
    warm = {'红', '橙', '黄', '金', '棕', '驼', '卡其', '焦糖', '杏', '奶油', '米', '裸', '粉', '桃', '珊瑚', '勃艮第', '酒红'}
    cool = {'蓝', '绿', '紫', '青', '藏青', '海军蓝', '天蓝', '鼠尾草', '薄荷', '薰衣草', '靛蓝', '湖蓝'}
    neutral = {'白', '黑', '灰', '米白', '象牙', '奶油白', '浅灰', '深灰', '炭灰', '燕麦'}

    for hue in result['allowed_hues']:
        for w in warm:
            if w in hue:
                families.add('暖色')
                break
        for c in cool:
            if c in hue:
                families.add('冷色')
                break
        for n in neutral:
            if n in hue:
                families.add('中性')
                break

    if not families:
        families.add('中性')

    result['allowed_hue_families'] = list(families)

    return result


def extract_fabric_prefs(md_text):
    """提取面料偏好"""
    section = parse_subsection(md_text, '面料偏好')
    if not section:
        section = parse_subsection(md_text, '面料')

    items = extract_list_items(section) if section else []
    preferred = []
    acceptable = []

    # 简化的面料分类
    for item in items:
        item_clean = item.split('>')[0].split('：')[0].strip().rstrip(';；')
        # 去掉修饰词
        for prefix in ['优先', '推荐', '首选', '核心', '灵魂']:
            item_clean = item_clean.replace(prefix, '').strip()

        if not item_clean or len(item_clean) > 20:
            continue

        if '<' not in item_clean and '>' not in item_clean:
            preferred.append(item_clean)

    # 从文本直接提取面料关键词
    fabric_kw = ['棉', '麻', '亚麻', '真丝', '丝绸', '羊绒', '羊毛', '针织', '皮质', '皮革',
                 '蕾丝', '薄纱', '雪纺', '丹宁', '牛仔', '灯芯绒', '粗花呢', '钩针', '编织',
                 '缎面', '绸缎', '尼龙', '涤纶', '天鹅绒', '丝绒', '毛呢', '羊毛混纺']

    found = set()
    for kw in fabric_kw:
        if kw in section or kw in md_text[:3000]:
            found.add(kw)

    # 分类
    luxury = {'真丝', '丝绸', '羊绒', '缎面', '绸缎', '天鹅绒', '丝绒', '粗花呢', '毛呢'}
    natural = {'棉', '麻', '亚麻', '蕾丝', '薄纱', '钩针', '编织', '灯芯绒'}
    synthetic = {'尼龙', '涤纶', '雪纺'}

    preferred = list(found & (luxury | natural))
    acceptable = list(found - set(preferred))

    return {
        'preferred': preferred[:6] or ['棉', '真丝'],
        'acceptable': acceptable[:4] or ['针织', '羊毛混纺'],
        'rejected': [],
    }


def extract_silhouette(md_text):
    """从廓形描述提取偏好"""
    section = parse_subsection(md_text, '廓形特点')
    if not section:
        section = parse_subsection(md_text, '廓形')

    text = (section or '') + ' ' + (md_text[:2000] or '')

    result = {
        'preferred': [],
        'acceptable': [],
        'rejected': [],
    }

    # 关键词匹配
    pref_map = {
        '宽松': ['宽松', 'Oversize', 'oversize', '廓形宽松', '阔腿', '宽大'],
        '合身': ['合身', '修身', '收腰', '高腰', 'A字', 'A型', 'H型'],
        '紧身': ['紧身', '贴身', '包身', 'bodycon'],
        '略宽松': ['略宽松', '微宽松', '稍宽松', '直筒', '烟管'],
        '超宽松': ['超宽松', '极度宽松', '宽大廓形'],
        '层叠': ['层叠', '叠穿', '多层次', 'layer'],
    }

    avoided = set()

    # "绝不紧身" → rejected
    if '不紧身' in text or '拒绝紧身' in text or '避免紧身' in text:
        result['rejected'].append('紧身')
        avoided.add('紧身')
    if '不宽松' in text:
        result['rejected'].append('宽松')
        avoided.add('宽松')

    for pref, keywords in pref_map.items():
        if pref in avoided:
            continue
        for kw in keywords:
            if kw in text:
                if '避免' in text[max(0, text.find(kw)-10):text.find(kw)]:
                    continue
                if pref not in result['preferred'] and pref not in result['acceptable']:
                    result['preferred'].append(pref)
                break

    # 从 preferred/acceptable 中移除所有 rejected 项
    result['preferred'] = [p for p in result['preferred'] if p not in result['rejected']]
    result['acceptable'] = [a for a in result['acceptable'] if a not in result['rejected']]
    # 去重：acceptable 中移除已在 preferred 中的项
    result['acceptable'] = [a for a in result['acceptable'] if a not in result['preferred']]
    if not result['preferred']:
        result['preferred'] = ['合身', '略宽松']
    if not result['acceptable']:
        result['acceptable'] = ['宽松']
    # acceptable 再去重（相对于新的 preferred）
    result['acceptable'] = [a for a in result['acceptable'] if a not in result['preferred']]
    # 默认 rejected：仅当 preferred 中没有紧身/超宽松时才拒绝它们
    if not result['rejected']:
        default_reject = []
        if '紧身' not in result['preferred']:
            default_reject.append('紧身')
        if '超宽松' not in result['preferred']:
            default_reject.append('超宽松')
        result['rejected'] = default_reject

    return result


def extract_key_items(md_text):
    """从标志单品表提取关键单品及奖励分"""
    section = parse_subsection(md_text, '标志单品表')
    if not section:
        section = parse_subsection(md_text, '标志单品')

    rows = extract_table_rows(section) if section else []
    items = []
    bonus_scores = [20, 15, 15, 10, 10]  # 递减奖励分

    for i, row in enumerate(rows[:6]):
        name = row[0] if row else ''
        # 清理：去品牌、去英文
        name_clean = re.sub(r'\(.*?\)', '', name).strip()
        name_clean = re.sub(r'[（].*?[）]', '', name_clean).strip()

        if not name_clean or len(name_clean) < 2:
            continue

        # 映射到品类代码
        cat_map = {
            '连衣裙': 'DRESS', '裙': 'SKIRT', '衬衣': 'SHIRT', '衬衫': 'SHIRT',
            'blouse': 'BLOUSE', '上衣': 'TS', 'T恤': 'TS', '卫衣': 'LS',
            '外套': 'JK', '夹克': 'JK', '风衣': 'JK', '大衣': 'JK', '西装': 'JK',
            '裤': 'PT', '牛仔': 'PT', '短裤': 'SH',
            '鞋': 'SHOE', '靴': 'SHOE', '平底': 'SHOE', '高跟': 'SHOE', '运动鞋': 'SHOE',
            '包': 'BAG', '草编': 'BAG', '托特': 'BAG', '腋下': 'BAG',
            '帽': 'HAT', '丝巾': 'ACC', '围巾': 'ACC', '腰带': 'ACC', '墨镜': 'SUN',
            '开衫': 'KNIT', '针织': 'KNIT', '毛衣': 'KNIT', '马甲': 'KNIT',
            '吊带': 'TANK', '背心': 'TANK', '连体裤': 'JMP',
        }

        cat_code = 'TS'
        for kw, code in cat_map.items():
            if kw in name_clean:
                cat_code = code
                break

        bonus = bonus_scores[i] if i < len(bonus_scores) else 5
        items.append({
            'name': name_clean[:30],
            'category_code': cat_code,
            'bonus': bonus,
            'description': row[2][:60] if len(row) > 2 else '',
        })

    return items


def extract_pattern_rules(md_text):
    """从文本推断图案规则"""
    text = md_text[:3000]

    result = {
        'preferred': [],
        'acceptable': [],
        'rejected': [],
    }

    pattern_map = {
        '碎花': ['碎花', '花卉', '印花', '小碎花', '花朵'],
        '条纹': ['条纹', '横条', '竖条', '条纹衫'],
        '格纹': ['格纹', '格子', '方格', '棋盘格', '千鸟格'],
        '纯色': ['纯色', '单色', '素色', '净色', '无图案'],
        '波点': ['波点', '圆点', '波尔卡'],
        'Logo': ['Logo', 'logo', '大Logo', '品牌标识'],
        '动物纹': ['动物纹', '豹纹', '斑马纹', '蛇纹'],
        '拼接': ['拼接', '拼色', '拼布'],
        '扎染': ['扎染', '蜡染', 'tie-dye'],
        '蕾丝': ['蕾丝', '镂空'],
        '刺绣': ['刺绣', '绣花'],
        '渐变': ['渐变', '晕染', '扎染渐变'],
    }

    preferred_pats = set()
    rejected_pats = set()

    for pat, keywords in pattern_map.items():
        for kw in keywords:
            if kw in text:
                # 检查上下文是否有否定
                idx = text.find(kw)
                ctx = text[max(0, idx-30):idx+len(kw)+30]
                if any(neg in ctx for neg in ['避免', '禁忌', '不使用', '拒绝', '排斥', '不宜']):
                    rejected_pats.add(pat)
                elif any(pos in ctx for pos in ['优先', '推荐', '核心', '经典', '灵魂', '标志']):
                    preferred_pats.add(pat)
                else:
                    if pat not in rejected_pats:
                        preferred_pats.add(pat)

    result['preferred'] = list(preferred_pats)[:4] or ['纯色', '条纹']
    result['acceptable'] = ['格纹', '碎花']
    result['rejected'] = list(rejected_pats)[:3] or ['Logo', '动物纹']

    return result


def extract_style_relations(md_text, style_id, style_name):
    """推断相关/冲突风格"""
    # 从文本推断关系
    related = []
    conflicting = []

    # 常见风格关系映射（基于category）
    category = ''
    m = re.search(r'分类[：:]\s*(.*?)(?=\n|$)', md_text)
    if m:
        category = m.group(1).strip()

    # Related by category
    cat_relations = {
        '欧洲经典': ['WF-01', 'WF-06', 'WF-07'],
        '东亚': ['WF-02', 'WF-03'],
        '现代都市': ['WF-05', 'WF-08', 'WF-11'],
        '浪漫少女': ['WF-13', 'WF-14', 'WF-15', 'WF-16', 'WF-46'],
        '复古怀旧': ['WF-10', 'WF-29'],
        '暗黑前卫': ['WF-23', 'WF-24', 'WF-31'],
        '户外运动': ['WF-08', 'WF-33', 'WF-38'],
        '奢华精致': ['WF-17', 'WF-18', 'WF-34', 'WF-35'],
    }

    style_num = int(style_id.split('-')[1]) if '-' in style_id else 0

    for cat, ids in cat_relations.items():
        if category and cat in category:
            related = [s for s in ids if s != style_id][:3]
            break

    # Conflicting: vastly different styles
    if style_num <= 12:
        conflicting = ['WF-10', 'WF-23']  # 经典 vs 前卫
    elif 13 <= style_num <= 22:
        conflicting = ['WF-31', 'WF-24']  # 浪漫 vs 暗黑
    elif 23 <= style_num <= 32:
        conflicting = ['WF-13', 'WF-16']  # 前卫 vs 田园
    else:
        conflicting = ['WF-10', 'WF-23']

    return related, conflicting


def infer_hard_constraints(md_text, silhouette):
    """推断硬约束"""
    constraints = []

    # 廓形约束
    if '紧身' in silhouette.get('rejected', []):
        constraints.append({
            'field': 'silhouette.fit',
            'operator': 'not_in',
            'value': ['紧身'],
            'reason': f'风格排斥紧身廓形',
        })

    # 面料约束 - 从文本推断
    fabric_section = parse_subsection(md_text, '面料偏好') or ''
    if '绝不' in fabric_section or '禁止' in fabric_section:
        constraints.append({
            'field': 'fabric.primary',
            'operator': 'not_in',
            'value': ['化纤', '涤纶'],
            'reason': '天然面料优先',
        })

    # 颜色约束
    color_section = parse_subsection(md_text, '色板') or ''
    forbid = extract_colors(color_section).get('forbidden_hues', [])
    if forbid:
        constraints.append({
            'field': 'color.hue_name',
            'operator': 'not_in',
            'value': forbid[:3],
            'reason': f'风格禁忌色: {", ".join(forbid[:3])}',
        })

    if not constraints:
        constraints = [
            {'field': 'silhouette.fit', 'operator': 'not_in', 'value': ['紧身'], 'reason': '风格偏好宽松/合身'},
        ]

    return constraints


def infer_soft_constraints(md_text):
    """推断软约束"""
    text = md_text[:3000]
    constraints = []

    # 面料加分
    if any(kw in text for kw in ['棉麻', '天然面料', '真丝', '羊绒']):
        constraints.append({
            'field': 'fabric.primary',
            'operator': 'in',
            'weight': 8,
            'value': ['棉', '麻', '亚麻', '真丝', '羊绒'],
            'reason': '天然面料加分',
        })

    # 颜色加分
    constraints.append({
        'field': 'color.saturation',
        'operator': 'in',
        'weight': 5,
        'value': ['低饱和', '无彩色'],
        'reason': '低饱和色系优先',
    })

    # 图案
    if any(kw in text for kw in ['碎花', '花卉']):
        constraints.append({
            'field': 'pattern.type',
            'operator': 'in',
            'weight': 5,
            'value': ['碎花', '花卉'],
            'reason': '碎花元素加分',
        })

    # 长度
    if any(kw in text for kw in ['及踝', '长裙', '长款', '过膝']):
        constraints.append({
            'field': 'silhouette.length_ratio',
            'operator': 'in',
            'weight': 3,
            'value': ['长款', '及踝'],
            'reason': '长款优先',
        })

    if not constraints:
        constraints = [
            {'field': 'color.saturation', 'operator': 'in', 'weight': 5, 'value': ['低饱和'], 'reason': '柔和色调优先'},
        ]

    return constraints[:5]


def infer_body_bonus(md_text, silhouette):
    """推断身形修饰加成"""
    text = md_text[:3000]
    bonus = {}

    body_map = {
        '显腰线': ['收腰', '高腰', '腰带', '腰线', 'A字', '帝国腰', '沙漏'],
        '拉长腿部': ['高腰', '长裤', '直筒', '拉长', '阔腿', '及踝', '九分'],
        '颜色显白': ['显白', '衬肤色', '提亮', '奶油', '暖调'],
        '遮盖臀胯': ['A字', '宽松', '阔腿', '遮盖', '修饰臀'],
        '修饰肩部': ['泡泡袖', '垫肩', 'V领', '方领', '一字领'],
    }

    for bonus_name, keywords in body_map.items():
        for kw in keywords:
            if kw in text:
                bonus[bonus_name] = min(13, bonus.get(bonus_name, 0) + 3)

    if not bonus:
        bonus = {'颜色显白': 3}

    return bonus


def infer_hue_family(allowed_hues):
    """从允许的颜色推断色系家族"""
    families = set()

    warm_colors = ['红', '橙', '黄', '金', '棕', '驼', '卡其', '焦糖', '杏', '奶油', '米', '裸', '粉', '桃', '珊瑚', '勃艮第', '酒红', '玫红', '干玫瑰', '铁锈红', '砖红']
    cool_colors = ['蓝', '绿', '紫', '青', '藏青', '海军蓝', '天蓝', '鼠尾草', '薄荷', '薰衣草', '靛蓝', '湖蓝', '灰蓝', '雾蓝']
    neutral_colors = ['白', '黑', '灰', '米白', '象牙', '奶油白', '浅灰', '深灰', '炭灰', '燕麦', '沙色', '拿铁']

    for hue in allowed_hues:
        for w in warm_colors:
            if w in hue:
                families.add('暖色')
                break
        for c in cool_colors:
            if c in hue:
                families.add('冷色')
                break
        for n in neutral_colors:
            if n in hue:
                families.add('中性')
                break

    if not families:
        families.add('中性')

    return list(families)


# ═══ 主生成逻辑 ═══

def generate_fingerprint(style_dir, dry_run=False):
    """从 encyclopedia.md 生成 fingerprint.json"""
    md_path = os.path.join(style_dir, 'encyclopedia.md')
    fp_path = os.path.join(style_dir, 'fingerprint.json')

    if not os.path.exists(md_path):
        print(f"  ⏭️  无 encyclopedia.md，跳过")
        return False

    # 读取现有 fingerprint（保留已有人工编辑内容）
    existing = {}
    if os.path.exists(fp_path):
        with open(fp_path) as f:
            existing = json.load(f)
        # 如果已有 fingerprint 键，跳过
        if 'fingerprint' in existing and existing['fingerprint']:
            print(f"  ⏭️  已有完整指纹，跳过")
            return False

    with open(md_path, encoding='utf-8') as f:
        md_text = f.read()

    # 从现有 JSON 获取基本信息
    style_id = existing.get('style_id', os.path.basename(style_dir).split('_')[0])
    name_zh = existing.get('name_zh', '')
    name_en = existing.get('name_en', '')
    description = existing.get('description', '')
    category = existing.get('category', '')
    tier = existing.get('tier', 'core')
    trend_category = existing.get('trend_category', 'classic')

    # 如果没有基本信息，从 md 提取
    if not name_zh:
        m = re.search(r'#\s+(.*?)(?:（|\(|$)', md_text)
        if m:
            name_zh = m.group(1).strip()

    if not description:
        m = re.search(r'一句话定义[：:]\s*(.*?)(?=\n|$)', md_text)
        if m:
            description = m.group(1).strip()[:120]

    if not category:
        m = re.search(r'分类[：:]\s*(.*?)(?=\n|$)', md_text)
        if m:
            category = m.group(1).strip()

    # ── 提取各维度 ──
    aesthetics = parse_md_section(md_text, '美学特征') or md_text

    silhouette = extract_silhouette(aesthetics)
    color_rules = extract_colors(aesthetics)
    pattern = extract_pattern_rules(aesthetics)
    fabric = extract_fabric_prefs(aesthetics)
    key_items = extract_key_items(aesthetics)

    # 补全 color_rules
    if not color_rules.get('allowed_hue_families'):
        color_rules['allowed_hue_families'] = infer_hue_family(color_rules.get('allowed_hues', []))
    if not color_rules.get('color_logic'):
        color_rules['color_logic'] = '自然柔和色调为主'

    # 推断关系和约束
    related, conflicting = extract_style_relations(md_text, style_id, name_zh)
    hard_constraints = infer_hard_constraints(md_text, silhouette)
    soft_constraints = infer_soft_constraints(md_text)
    body_bonus = infer_body_bonus(md_text, silhouette)

    # 判断 intensity (1=日常 2=中等 3=大胆)
    if any(kw in md_text[:500] for kw in ['日常', '通勤', '极简', '基础', '休闲']):
        intensity = 1
    elif any(kw in md_text[:500] for kw in ['华丽', '大胆', '前卫', '戏剧', '派对', '暗黑', '摇滚']):
        intensity = 3
    else:
        intensity = 2

    # 构建完整指纹
    fingerprint = {
        'silhouette': silhouette,
        'color_rules': color_rules,
        'pattern': pattern,
        'fabric': fabric,
        'layering': {
            'preferred': ['基础叠穿'],
            'acceptable': ['多层次叠穿'],
            'rejected': [],
        },
        'formality_range': [1, 4],
    }

    # 合并到现有数据
    existing.update({
        'style_id': style_id,
        'name_zh': name_zh or existing.get('name_zh', style_id),
        'name_en': name_en or existing.get('name_en', ''),
        'description': description or existing.get('description', ''),
        'category': category or existing.get('category', ''),
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
        print(f"  📝 {style_id} {name_zh}: {len(key_items)} key_items, {len(hard_constraints)} hard, {len(soft_constraints)} soft")
        return True

    # 写入
    with open(fp_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {style_id} {name_zh}: {len(key_items)} 关键单品, {len(hard_constraints)} 硬约束, {len(soft_constraints)} 软约束")
    return True


def main():
    dry_run = '--dry-run' in sys.argv
    single = None
    for a in sys.argv[1:]:
        if a.startswith('WF-'):
            single = a
            break

    if single:
        # 找到对应目录
        for d in os.listdir(STYLES_FEMALE):
            if d.startswith(single) and os.path.isdir(os.path.join(STYLES_FEMALE, d)):
                style_dir = os.path.join(STYLES_FEMALE, d)
                print(f"🎯 {single}")
                generate_fingerprint(style_dir, dry_run)
                return

    # 批量模式
    all_dirs = sorted([d for d in os.listdir(STYLES_FEMALE)
                       if os.path.isdir(os.path.join(STYLES_FEMALE, d))
                       and not d.startswith('.') and not d.startswith('_')])

    generated = 0
    skipped = 0

    print(f"{'🔍 预览' if dry_run else '🔨 生成'} 女性风格指纹...")
    print(f"   候选: {len(all_dirs)} 个风格目录\n")

    for d in all_dirs:
        style_dir = os.path.join(STYLES_FEMALE, d)
        fp_path = os.path.join(style_dir, 'fingerprint.json')

        # 检查是否已有完整指纹
        has_full = False
        if os.path.exists(fp_path):
            with open(fp_path) as f:
                existing = json.load(f)
            if 'fingerprint' in existing and existing['fingerprint']:
                has_full = True

        style_id = d.split('_')[0] if '_' in d else d

        if has_full:
            skipped += 1
            continue

        result = generate_fingerprint(style_dir, dry_run)
        if result:
            generated += 1

    print(f"\n{'='*50}")
    print(f"{'📝 预览' if dry_run else '✅ 生成'}: {generated} 个")
    print(f"⏭️  跳过(已有): {skipped} 个")


if __name__ == '__main__':
    main()
