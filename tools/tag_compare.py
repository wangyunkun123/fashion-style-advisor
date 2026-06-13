#!/usr/bin/env python3
"""
服装标签对比工具
对比 Claude 识别结果与现有服装档案.md，输出差异报告，合并生成最终标签 JSON。

用法:
  python3 tools/tag_compare.py              # 对比 + 生成差异报告
  python3 tools/tag_compare.py --merge      # 对比 + 自动合并 + 写入 tags/*.json
  python3 tools/tag_compare.py --report     # 仅输出差异报告
"""

import os, sys, json, re, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
WARDROBE_MD = os.path.join(PROJ_DIR, 'wardrobe', '服装档案.md')
CLAUDE_RAW_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags_claude_raw')
TAGS_OUT_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')

CATEGORY_MAP = {
    '短袖上衣': 'TS', '长袖上衣': 'LS', '外套': 'JK', '长裤': 'PT',
    '短裤': 'SH', '衬衣': 'SHIRT', '背心': 'TANK', '鞋子': 'SHOE',
    '帽子': 'HAT', '包': 'BAG', '墨镜': 'SUN', '手部配饰': 'ACC', '袜子': 'SOCK'
}

# ============================================================
# 1. 解析现有服装档案.md
# ============================================================

def parse_wardrobe_md():
    """解析服装档案.md 表格，返回 {clothing_id: dict}"""
    with open(WARDROBE_MD, 'r', encoding='utf-8') as f:
        content = f.read()

    items = {}
    current_cat = None
    lines = content.split('\n')

    for line in lines:
        # 检测品类标题
        for cat_name in CATEGORY_MAP:
            if f'## {cat_name}' in line:
                current_cat = cat_name
                break

        # 解析表格行
        m = re.match(r'^\|\s*(\w+-\d+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\s*\|', line)
        if m and current_cat:
            cid = m.group(1)
            items[cid] = {
                'clothing_id': cid,
                'image_file': m.group(2).strip(),
                'color_text': m.group(3).strip(),
                'style_text': m.group(4).strip(),
                'features': m.group(5).strip(),
                'suitability': m.group(6).strip(),
                'notes': m.group(7).strip(),
                'category': current_cat,
                'category_code': CATEGORY_MAP[current_cat],
            }
    return items


# ============================================================
# 2. 加载 Claude 识别结果
# ============================================================

def load_claude_results():
    """加载 tags_claude_raw/ 下所有 JSON 文件，合并为一个 {clothing_id: dict}"""
    results = {}
    json_files = sorted(glob.glob(os.path.join(CLAUDE_RAW_DIR, '*.json')))

    if not json_files:
        print("⚠️ 未找到 Claude 识别结果文件。")
        print(f"   请将结果 JSON 放入: {CLAUDE_RAW_DIR}")
        return results

    for fpath in json_files:
        fname = os.path.basename(fpath)
        with open(fpath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"⚠️ {fname} JSON 解析失败: {e}")
                continue

        # 支持两种格式: 数组 [{...}] 或对象 {id: {...}}
        if isinstance(data, list):
            for item in data:
                cid = item.get('clothing_id', '')
                if cid:
                    results[cid] = item
        elif isinstance(data, dict):
            # 可能是 {clothing_id: {...}} 或单个对象
            if 'clothing_id' in data:
                results[data['clothing_id']] = data
            else:
                for cid, item in data.items():
                    if isinstance(item, dict):
                        results[cid] = item

    print(f"✅ 加载 Claude 识别结果: {len(results)} 件")
    return results


# ============================================================
# 3. 对比逻辑
# ============================================================

def classify_color(hue_name):
    """粗略颜色分类，用于对比"""
    warm = ['红', '橙', '黄', '焦糖', '棕', '咖啡', '米', '杏', '小麦', '姜黄', '粉']
    cool = ['蓝', '绿', '青', '藏青', '墨绿', '橄榄', '薄荷', '紫', '靛', '鸦青']
    neutral = ['黑', '白', '灰', '麻灰', '米白', '卡其', '银']

    for w in warm:
        if w in hue_name:
            return '暖色'
    for c in cool:
        if c in hue_name:
            return '冷色'
    for n in neutral:
        if n in hue_name:
            return '中性'
    return '未知'


def compare_colors(old_text, claude_color):
    """对比颜色: 返回 (level, detail)"""
    old_hue = old_text
    new_hue = claude_color.get('hue_name', '')
    new_family = claude_color.get('hue_family', '')

    if not new_hue:
        return ('🟡', 'Claude 未提供颜色信息')

    # 检查是否大致一致
    old_class = classify_color(old_hue)
    new_class = classify_color(new_hue)

    # 完全相同
    if old_hue == new_hue:
        return ('🟢', f'颜色一致: {old_hue}')

    # 同色系
    if old_class == new_class and old_class != '未知':
        return ('🟢', f'颜色接近: Markdown={old_hue}, Claude={new_hue} (同属{old_class})')

    # 严重冲突：色系不同
    if old_class != new_class and old_class != '未知' and new_class != '未知':
        return ('🔴', f'颜色冲突: Markdown={old_hue}({old_class}), Claude={new_hue}({new_class})')

    # 轻度差异
    return ('🟡', f'颜色有差异: Markdown={old_hue}, Claude={new_hue}')


def compare_pattern(old_style, old_features, claude_pattern):
    """对比图案/款式: 返回 (level, detail)"""
    new_type = claude_pattern.get('type', '')
    old_text = old_style + ' ' + old_features

    # 图案关键词映射
    pattern_keywords = {
        '纯色': ['纯色', '简约', '基础款', '干净', '纯色T恤', '纯色短袖'],
        '条纹': ['条纹'],
        '格纹': ['格纹', '千鸟格', '暗格纹'],
        '印花': ['印花', '热带', '植物', '夏威夷', '小熊'],
        'Logo': ['刺绣', '品牌', 'FILA', 'Nike', '阿迪达斯', 'Champion', '曼联', '球队'],
        '拼接': ['拼接', '拼色', '假两件'],
    }

    inferred_old = '纯色'  # 默认
    for ptype, keywords in pattern_keywords.items():
        for kw in keywords:
            if kw in old_text:
                inferred_old = ptype
                break

    if inferred_old == new_type:
        return ('🟢', f'图案一致: {new_type}')
    elif not new_type:
        return ('🟡', 'Claude 未提供图案信息')
    else:
        return ('🔴', f'图案冲突: Markdown推断={inferred_old}, Claude={new_type}')


def compare_fabric(old_features, claude_fabric):
    """对比面料: 返回 (level, detail)"""
    new_fabric = claude_fabric.get('primary', '')
    old_text = old_features

    fabric_keywords = {
        '棉': ['棉', '纯棉'],
        '麻': ['麻', '亚麻', '棉麻'],
        '牛仔': ['牛仔'],
        '合成': ['速干', '尼龙', '涤纶', '合成'],
        '皮质': ['皮质', '仿皮', '皮'],
        '针织': ['针织', '螺纹', '罗纹', '毛衣'],
        '灯芯绒': ['灯芯绒'],
        '帆布': ['帆布'],
        '牛津纺': ['牛津纺', '牛津'],
    }

    inferred_old = '棉'  # 默认
    for ftype, keywords in fabric_keywords.items():
        for kw in keywords:
            if kw in old_text:
                inferred_old = ftype
                break

    if inferred_old == new_fabric:
        return ('🟢', f'面料一致: {new_fabric}')
    elif not new_fabric:
        return ('🟡', 'Claude 未提供面料信息')
    elif inferred_old == '棉' and new_fabric in ['针织', '牛津纺']:
        return ('🟡', f'面料细分差异: Markdown推断={inferred_old}, Claude={new_fabric} (可能Claude更准确)')
    else:
        return ('🔴', f'面料冲突: Markdown推断={inferred_old}, Claude={new_fabric}')


def compare_formality(old_style, old_features, claude_formality):
    """对比正式度: 返回 (level, detail)"""
    new_f = claude_formality
    old_text = old_style + ' ' + old_features

    # 推断旧的正式度
    if any(kw in old_text for kw in ['西装', '正式', '商务', '暗格纹西裤']):
        inferred_old = 4
    elif any(kw in old_text for kw in ['衬衫', '衬衣', '轻商务', '轻熟', '质感']):
        inferred_old = 3
    elif any(kw in old_text for kw in ['运动', '球衣', '健身', '居家', '拖鞋']):
        inferred_old = 1
    else:
        inferred_old = 2  # 日常休闲

    if not new_f or not isinstance(new_f, (int, float)):
        return ('🟡', 'Claude 未提供正式度')

    diff = abs(inferred_old - new_f)
    if diff == 0:
        return ('🟢', f'正式度一致: {new_f}')
    elif diff == 1:
        return ('🟡', f'正式度轻微差异: Markdown推断={inferred_old}, Claude={new_f}')
    else:
        return ('🔴', f'正式度严重冲突: Markdown推断={inferred_old}, Claude={new_f}')


def compare_item(old_item, claude_item):
    """对比单件衣服: 返回差异列表"""
    diffs = []

    # 颜色对比
    if 'color' in claude_item:
        level, detail = compare_colors(old_item['color_text'], claude_item['color'])
        diffs.append({'field': '颜色', 'level': level, 'detail': detail})

    # 图案对比
    if 'pattern' in claude_item:
        level, detail = compare_pattern(old_item['style_text'], old_item['features'], claude_item['pattern'])
        diffs.append({'field': '图案', 'level': level, 'detail': detail})

    # 面料对比
    if 'fabric' in claude_item:
        level, detail = compare_fabric(old_item['features'], claude_item['fabric'])
        diffs.append({'field': '面料', 'level': level, 'detail': detail})

    # 正式度对比
    if 'formality' in claude_item:
        level, detail = compare_formality(old_item['style_text'], old_item['features'], claude_item.get('formality'))
        diffs.append({'field': '正式度', 'level': level, 'detail': detail})

    # 品牌识别 (新增字段，仅记录)
    if 'brand' in claude_item and claude_item['brand'].get('name'):
        b = claude_item['brand']
        conf = b.get('confidence', '未知')
        coll = f" ({b['collection']})" if b.get('collection') else ''
        diffs.append({'field': '品牌', 'level': '🆕', 'detail': f"Claude识别: {b['name']}{coll} [{conf}]"})

    # Claude 补充的信息
    if claude_item.get('silhouette', {}).get('fit'):
        diffs.append({'field': '廓形', 'level': '🆕', 'detail': f"Claude新增: fit={claude_item['silhouette']['fit']}"})
    if claude_item.get('silhouette', {}).get('shoulder_effect'):
        diffs.append({'field': '肩部效果', 'level': '🆕', 'detail': f"Claude新增: {claude_item['silhouette']['shoulder_effect']}"})
    if claude_item.get('silhouette', {}).get('torso_effect'):
        diffs.append({'field': '躯干效果', 'level': '🆕', 'detail': f"Claude新增: {claude_item['silhouette']['torso_effect']}"})
    if claude_item.get('fabric', {}).get('weight'):
        diffs.append({'field': '面料厚度', 'level': '🆕', 'detail': f"Claude新增: {claude_item['fabric']['weight']}"})
    if claude_item.get('fabric', {}).get('texture'):
        diffs.append({'field': '面料纹理', 'level': '🆕', 'detail': f"Claude新增: {claude_item['fabric']['texture']}"})
    if claude_item.get('style_modifiers'):
        diffs.append({'field': '修饰标签', 'level': '🆕', 'detail': f"Claude新增: {claude_item['style_modifiers']}"})
    if claude_item.get('fit_comment'):
        diffs.append({'field': '穿搭评价', 'level': '🆕', 'detail': f"Claude: {claude_item['fit_comment']}"})

    return diffs


# ============================================================
# 4. 合并逻辑
# ============================================================

def merge_tags(old_item, claude_item):
    """合并 Markdown 和 Claude 结果，生成最终标签 JSON"""
    merged = {
        'clothing_id': old_item['clothing_id'],
        'category': old_item['category'],
        'category_code': old_item['category_code'],
    }

    # 颜色: 优先 Claude
    if 'color' in claude_item and claude_item['color'].get('hue_name'):
        merged['color'] = claude_item['color']
    else:
        merged['color'] = {
            'hue_family': classify_color(old_item['color_text']),
            'hue_name': old_item['color_text'],
            'saturation': '中饱和',
            'lightness': '中明度',
            'is_neutral': classify_color(old_item['color_text']) == '中性',
            'friendly_for_pale_skin': '适合' in old_item.get('suitability', ''),
        }

    # 廓形: 优先 Claude，回退到默认
    merged['silhouette'] = claude_item.get('silhouette', {
        'fit': '合身',
        'shoulder_effect': '无特殊效果',
        'torso_effect': '无特殊效果',
        'length_ratio': '标准',
    })

    # 图案: 优先 Claude
    merged['pattern'] = claude_item.get('pattern', {
        'type': '纯色',
        'density': '无',
        'logo_visible': False,
    })

    # 面料: 优先 Claude
    merged['fabric'] = claude_item.get('fabric', {
        'primary': '棉',
        'texture': '平纹针织',
        'weight': '中厚',
        'seasonality': ['春', '夏', '秋'],
    })

    # 正式度
    merged['formality'] = claude_item.get('formality', 2)

    # 品牌信息
    merged['brand'] = claude_item.get('brand', {
        'name': '未知',
        'collection': None,
        'confidence': '未知',
    })

    # 修饰标签
    merged['style_modifiers'] = claude_item.get('style_modifiers', [])

    # 元数据
    merged['meta'] = {
        'is_key_piece': False,
        'is_statement_piece': False,
        'wear_count': 0,
        'last_worn': None,
        'claude_fit_comment': claude_item.get('fit_comment', ''),
    }

    return merged


# ============================================================
# 5. 主流程
# ============================================================

def main():
    do_merge = '--merge' in sys.argv
    report_only = '--report' in sys.argv

    print("=" * 60)
    print("🔍 服装标签对比工具")
    print("=" * 60)

    # 加载数据
    old_items = parse_wardrobe_md()
    claude_items = load_claude_results()

    if not claude_items:
        print("\n❌ 无 Claude 识别结果，无法对比。")
        print("   请在 claude.ai 按模板识别后，将 JSON 结果放入:")
        print(f"   {CLAUDE_RAW_DIR}")
        return

    # 对比
    print(f"\n📊 Markdown 档案: {len(old_items)} 件")
    print(f"📊 Claude 识别:  {len(claude_items)} 件")

    # 缺失检查
    missing_in_claude = set(old_items.keys()) - set(claude_items.keys())
    extra_in_claude = set(claude_items.keys()) - set(old_items.keys())

    if missing_in_claude:
        print(f"\n⚠️  Claude 缺失 {len(missing_in_claude)} 件: {', '.join(sorted(missing_in_claude))}")
    if extra_in_claude:
        print(f"\n⚠️  Claude 多出 {len(extra_in_claude)} 件: {', '.join(sorted(extra_in_claude))}")

    # 逐件对比
    print(f"\n{'='*60}")
    print("📋 对比结果")
    print(f"{'='*60}")

    stats = {'🔴': 0, '🟡': 0, '🟢': 0, '🆕': 0, '✅': 0}
    all_diffs = {}

    for cid in sorted(old_items.keys()):
        old = old_items[cid]
        claude = claude_items.get(cid)

        if not claude:
            all_diffs[cid] = [{'field': '—', 'level': '❌', 'detail': 'Claude 未识别此件'}]
            continue

        diffs = compare_item(old, claude)
        all_diffs[cid] = diffs

        # 统计
        has_red = any(d['level'] == '🔴' for d in diffs)
        has_yellow = any(d['level'] == '🟡' for d in diffs)
        has_new = any(d['level'] == '🆕' for d in diffs)

        if has_red:
            stats['🔴'] += 1
        elif has_yellow:
            stats['🟡'] += 1
        else:
            stats['✅'] += 1

        if has_new:
            stats['🆕'] += 1

        # 打印
        icon = '🔴' if has_red else ('🟡' if has_yellow else '✅')
        cat = old['category']
        color_text = old['color_text']
        print(f"\n{icon} {cid} ({cat}) — {color_text}")

        for d in diffs:
            if d['level'] != '🆕':  # 非新增字段都打印
                print(f"   {d['level']} [{d['field']}] {d['detail']}")
            else:
                print(f"   {d['level']} [{d['field']}] {d['detail']}")

    # 汇总
    print(f"\n{'='*60}")
    print("📊 汇总统计")
    print(f"{'='*60}")
    total = len(old_items)
    print(f"  🔴 冲突需审核: {stats['🔴']} 件 ({stats['🔴']*100//total}%)")
    print(f"  🟡 轻微差异:   {stats['🟡']} 件 ({stats['🟡']*100//total}%)")
    print(f"  ✅ 一致通过:   {stats['✅']} 件 ({stats['✅']*100//total}%)")
    print(f"  🆕 含新增字段: {stats['🆕']} 件")
    print(f"  📦 总计:       {total} 件")

    # 合并写入
    if do_merge:
        print(f"\n{'='*60}")
        print("📝 合并写入 tags/*.json")
        print(f"{'='*60}")

        os.makedirs(TAGS_OUT_DIR, exist_ok=True)
        merged_count = 0

        for cid in sorted(old_items.keys()):
            claude = claude_items.get(cid)
            if not claude:
                print(f"  ⏭️  {cid} 跳过 (无 Claude 数据)")
                continue

            merged = merge_tags(old_items[cid], claude)
            out_path = os.path.join(TAGS_OUT_DIR, f'{cid}.json')

            # 检查是否有 🔴 冲突
            has_conflict = any(d['level'] == '🔴' for d in all_diffs.get(cid, []))
            if has_conflict:
                merged['_needs_review'] = True
                merged['_conflicts'] = [
                    d['detail'] for d in all_diffs[cid] if d['level'] == '🔴'
                ]

            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            icon = '⚠️' if has_conflict else '✅'
            print(f"  {icon} {cid}.json")
            merged_count += 1

        print(f"\n✅ 已写入 {merged_count} 个标签文件 → {TAGS_OUT_DIR}")

        # 提示冲突项
        conflicts = [cid for cid, diffs in all_diffs.items()
                     if any(d['level'] == '🔴' for d in diffs)]
        if conflicts:
            print(f"\n⚠️  以下 {len(conflicts)} 件有冲突，已标记 _needs_review=true:")
            for cid in conflicts:
                for d in all_diffs[cid]:
                    if d['level'] == '🔴':
                        print(f"   {cid}: {d['detail']}")

        print(f"\n👉 请审核标记为 ⚠️ 的文件中的 _conflicts 字段")
        print(f"   确认后运行: python3 tools/tag_compare.py --finalize")

    elif not report_only:
        print(f"\n👉 查看完整报告后，运行以下命令生成标签文件:")
        print(f"   python3 tools/tag_compare.py --merge")


if __name__ == '__main__':
    main()
