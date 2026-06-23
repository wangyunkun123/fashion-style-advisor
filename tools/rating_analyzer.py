#!/usr/bin/env python3
"""
偏好分析引擎 — 分析用户打分数据，生成偏好报告

用法:
  python3 tools/rating_analyzer.py                   # 分析全部评分
  python3 tools/rating_analyzer.py --report          # 生成月度报告
  python3 tools/rating_analyzer.py --summary         # 简要统计
"""

import os, sys, json, glob, re
from datetime import datetime, timedelta
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')

# ── 多用户支持 ──
_USER_ID = None
for _i, _arg in enumerate(sys.argv):
    if _arg == '--user' and _i + 1 < len(sys.argv):
        _USER_ID = sys.argv[_i + 1]; break
    elif _arg.startswith('--user='):
        _USER_ID = _arg.split('=', 1)[1]; break
if _USER_ID:
    if PROJ_DIR not in sys.path:
        sys.path.insert(0, PROJ_DIR)
    from tools.common import resolve_outfits_dir, resolve_tags_dir, set_thread_user
    set_thread_user(_USER_ID)
    OUTFITS_DIR = resolve_outfits_dir(_USER_ID)
    TAGS_DIR = resolve_tags_dir(_USER_ID)
else:
    OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
    TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
PREFS_FILE = os.path.join(PROJ_DIR, 'config', 'user_prefs.json')

# 风格名映射（与 styles/*.json 的 style_id → name_zh 对应）
STYLE_NAMES = {
    'clean_fit': 'Clean Fit',
    'japanese_city_boy': '日系 City Boy',
    'smart_casual': '轻熟休闲',
    'athleisure_sport': '运动休闲',
    'korean_minimal': '韩系简约',
    'resort_vacation': '度假休闲',
    'streetwear': '街头潮流',
    'chinese_heritage': '国风质感',
    'american_ivy_league': '美式常春藤',
    'american_workwear': '美式工装',
    'british_heritage': '英伦遗产',
    'contemporary_gorpcore': '户外机能风',
    'japanese_amekaji': '日系阿美咔叽',
    'japanese_yama': '日系山系',
    'korean_light_mature': '韩式轻熟风',
    'retro_90s_hiphop': '90s嘻哈风',
    'scandi_minimalism': '北欧极简',
    'scene_blokecore': '足球看台风',
}
# 中文名反向映射（用于从 outfit.md 中提取的风格名反查 style_id）
STYLE_NAME_TO_ID = {v: k for k, v in STYLE_NAMES.items()}
# 关键词回退匹配（按特异性排序，优先匹配更具体的关键词）
STYLE_KEYWORDS = [
    ('blokecore', 'scene_blokecore'),
    ('city boy', 'japanese_city_boy'),
    ('clean fit', 'clean_fit'),
    ('clean', 'clean_fit'),
    ('gorpcore', 'contemporary_gorpcore'),
    ('athleisure', 'athleisure_sport'),
    ('scandi', 'scandi_minimalism'),
    ('北欧', 'scandi_minimalism'),
    ('极简', 'scandi_minimalism'),
    ('国风', 'chinese_heritage'),
    ('新中式', 'chinese_heritage'),
    ('网球', 'athleisure_sport'),
    ('跑步', 'athleisure_sport'),
    ('运动', 'athleisure_sport'),
    ('足球', 'scene_blokecore'),
    ('英伦', 'british_heritage'),
    ('british', 'british_heritage'),
    ('常春藤', 'american_ivy_league'),
    ('ivy', 'american_ivy_league'),
    ('工装', 'american_workwear'),
    ('workwear', 'american_workwear'),
    ('美式', 'american_ivy_league'),
    ('阿美咔叽', 'japanese_amekaji'),
    ('amekaji', 'japanese_amekaji'),
    ('山系', 'japanese_yama'),
    ('yama', 'japanese_yama'),
    ('户外', 'contemporary_gorpcore'),
    ('机能', 'contemporary_gorpcore'),
    ('韩系', 'korean_minimal'),
    ('韩式', 'korean_minimal'),
    ('轻熟', 'korean_light_mature'),
    ('日系', 'japanese_city_boy'),
    ('度假', 'resort_vacation'),
    ('热带', 'resort_vacation'),
    ('街头', 'streetwear'),
    ('潮流', 'streetwear'),
    ('嘻哈', 'retro_90s_hiphop'),
    ('hiphop', 'retro_90s_hiphop'),
    ('休闲', 'smart_casual'),
]

def load_all_ratings():
    """加载所有评分数据"""
    ratings = []
    for d in sorted(os.listdir(OUTFITS_DIR)):
        rpath = os.path.join(OUTFITS_DIR, d, 'rating.json')
        if not os.path.exists(rpath):
            continue
        try:
            with open(rpath, 'r') as f:
                r = json.load(f)
            # 补充 style_id（从 outfit.md 解析）
            if 'style_id' not in r:
                md = os.path.join(OUTFITS_DIR, d, 'outfit.md')
                if os.path.exists(md):
                    with open(md) as f2:
                        txt = f2.read()
                    # 匹配三种格式：**风格**: xxx / 风格: xxx / YAML frontmatter style: xxx
                    m = re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)|^style[：:]\s*(.+)', txt, re.MULTILINE)
                    if m:
                        raw = (m.group(1) or m.group(2) or m.group(3)).strip()
                        # 1) 直接匹配 style_id（如 frontmatter 写 style: japanese_city_boy）
                        if raw in STYLE_NAMES:
                            r['style_id'] = raw
                        else:
                            # 2) 中文名直接查表
                            found = False
                            for zh_name, sid in STYLE_NAME_TO_ID.items():
                                if zh_name.lower().replace(' ', '') in raw.lower().replace(' ', ''):
                                    r['style_id'] = sid
                                    found = True
                                    break
                            # 3) 英文名模糊匹配（如 style: clean_fit）
                            if not found:
                                for sid in STYLE_NAMES:
                                    if sid.lower().replace('_', '') in raw.lower().replace('_', '').replace(' ', ''):
                                        r['style_id'] = sid
                                        found = True
                                        break
                            # 4) 关键词回退（freeform 描述如"美式复古休闲"→american_ivy_league）
                            if not found:
                                raw_lower = raw.lower().replace(' ', '')
                                for kw, sid in STYLE_KEYWORDS:
                                    if kw.replace(' ', '') in raw_lower:
                                        r['style_id'] = sid
                                        found = True
                                        break
            if 'style_id' not in r:
                r['style_id'] = 'unknown'
            ratings.append(r)
        except:
            pass
    return ratings


def analyze(ratings):
    """分析评分数据"""
    if not ratings:
        return {'error': '暂无评分数据'}

    total = len(ratings)
    by_score = Counter(r['rating'] for r in ratings)
    by_style = defaultdict(lambda: {'total': 0, 'ratings': [], 'avg': 0})
    items_liked = Counter()
    items_disliked = Counter()

    for r in ratings:
        sid = r.get('style_id', 'unknown')
        by_style[sid]['total'] += 1
        by_style[sid]['ratings'].append(r['rating'])
        by_style[sid]['avg'] = round(sum(by_style[sid]['ratings']) / len(by_style[sid]['ratings']), 1)

        # 提取物品
        oid = r.get('outfit_id', '')
        md = os.path.join(OUTFITS_DIR, oid, 'outfit.md')
        if os.path.exists(md):
            with open(md) as f:
                txt = f.read()
            item_ids = re.findall(r'\b([A-Z]+-\d+)\b', txt)
            for iid in item_ids:
                if r['rating'] >= 3:
                    items_liked[iid] += 1
                elif r['rating'] <= 1:
                    items_disliked[iid] += 1

    # 1星反馈分析
    feedback_reasons = Counter()
    for r in ratings:
        if r['rating'] == 1 and r.get('feedback'):
            feedback_reasons[r['feedback'].get('reason', 'unknown')] += 1

    return {
        'total': total,
        'by_score': dict(by_score),
        'satisfaction_rate': round(by_score.get(3, 0) / total * 100),
        'neutral_rate': round(by_score.get(2, 0) / total * 100),
        'disappoint_rate': round(by_score.get(1, 0) / total * 100),
        'avg_rating': round(sum(r['rating'] for r in ratings) / total, 1),
        'by_style': dict(by_style),
        'items_liked': dict(items_liked.most_common(10)),
        'items_disliked': dict(items_disliked.most_common(5)),
        'feedback_reasons': feedback_reasons,
    }


def filter_ratings_by_days(ratings, days=7):
    """只保留最近 N 天的评分（按 outfit 目录日期前缀筛选）"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    filtered = []
    for r in ratings:
        oid = r.get('outfit_id', '')
        # outfit_id 即目录名，如 "2026-06-15_夏日CleanFit"
        date_prefix = oid[:10] if len(oid) >= 10 else ''
        if date_prefix >= cutoff:
            filtered.append(r)
    return filtered


def generate_weekly_report():
    """生成周报（近7天数据，轻量格式）"""
    all_ratings = load_all_ratings()
    if not all_ratings:
        return "📊 暂无评分数据，无法生成周报"

    ratings = filter_ratings_by_days(all_ratings, 7)
    if not ratings:
        # 尝试扩大范围到14天，如果7天没数据
        ratings = filter_ratings_by_days(all_ratings, 14)
        if not ratings:
            return "📊 近两周暂无新评分，周报暂不生成"

    analysis = analyze(ratings)

    # 上周对比（8-14天前的数据）
    prev_ratings = filter_ratings_by_days(all_ratings, 14)
    prev_ratings = [r for r in prev_ratings if r not in ratings]  # 减去本周的
    prev_analysis = analyze(prev_ratings) if prev_ratings else None

    # 日期范围
    if ratings:
        dates = sorted(set(r.get('outfit_id', '')[:10] for r in ratings))
        date_range = f"{dates[0]} → {dates[-1]}" if len(dates) > 1 else dates[0]
    else:
        date_range = "近7天"

    lines = [
        f"📊 穿搭周报",
        f"📅 {date_range} | 本周 {analysis['total']} 次评分",
        "",
        "━━━ 📈 本周满意度 ━━━",
        f"❤️ 满意: {analysis['satisfaction_rate']}% ({analysis['by_score'].get(3,0)}次)",
        f"🤔 一般: {analysis['neutral_rate']}% ({analysis['by_score'].get(2,0)}次)",
        f"💔 失望: {analysis['disappoint_rate']}% ({analysis['by_score'].get(1,0)}次)",
        f"📊 平均分: {analysis['avg_rating']}/3",
    ]

    # 趋势对比
    if prev_analysis and prev_analysis['total'] >= 1:
        trend = analysis['avg_rating'] - prev_analysis['avg_rating']
        if trend > 0.2:
            lines.append(f"📈 较上周 ↑ {trend:+.1f}（进步中）")
        elif trend < -0.2:
            lines.append(f"📉 较上周 ↓ {trend:+.1f}（需关注）")
        else:
            lines.append(f"📊 较上周持平（{trend:+.1f}）")

    # 本周风格
    if analysis['by_style']:
        lines.append("")
        lines.append("━━━ 🎯 本周风格 ━━━")
        sorted_styles = sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])
        for sid, data in sorted_styles[:3]:
            name = STYLE_NAMES.get(sid, sid)
            lines.append(f"  {name}: {data['avg']}分 ({data['total']}次)")

    # 最爱单品 Top 3
    if analysis['items_liked']:
        lines.append("")
        lines.append("━━━ 👔 本周最爱 ━━━")
        for iid, cnt in list(analysis['items_liked'].items())[:3]:
            tag_path = os.path.join(TAGS_DIR, f'{iid}.json')
            name = iid
            if os.path.exists(tag_path):
                with open(tag_path) as f:
                    tag = json.load(f)
                name = f"{iid} ({tag.get('color',{}).get('hue_name','')} {tag.get('brand',{}).get('name','')})"
            lines.append(f"  👍 {name} — {cnt}次满意")

    # 简短的月度入口引导
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("💡 查看完整月度报告？在手机端说「偏好报告」即可")

    return '\n'.join(lines)


def find_neutral_patterns(ratings):
    """分析连续2星评价的共同点"""
    neutral = [r for r in ratings if r['rating'] == 2]
    if len(neutral) < 3:
        return None

    styles = Counter()
    all_items = Counter()
    for r in neutral:
        sid = r.get('style_id', '')
        if sid:
            styles[sid] += 1
        oid = r.get('outfit_id', '')
        md = os.path.join(OUTFITS_DIR, oid, 'outfit.md')
        if os.path.exists(md):
            with open(md) as f:
                txt = f.read()
            for iid in re.findall(r'\b([A-Z]+-\d+)\b', txt):
                all_items[iid] += 1

    patterns = []
    common_styles = [s for s, c in styles.most_common(2) if c >= 2]
    common_items = [i for i, c in all_items.most_common(5) if c >= 2]

    if common_styles:
        patterns.append(f"🔍 {len(neutral)}次'一般'评价中，{', '.join(common_styles)} 风格重复出现（建议降低推荐频率）")
    if common_items:
        patterns.append(f"🔍 重复出现单品: {', '.join(common_items[:5])}（检查是否搭配不当）")
    if not patterns:
        patterns.append("🔍 2星评价暂无显著重合模式，需更多数据")

    return {'count': len(neutral), 'common_styles': common_styles, 'common_items': common_items, 'summary': patterns}


def generate_report():
    """生成月度偏好报告"""
    ratings = load_all_ratings()
    if not ratings:
        return "📊 暂无评分数据，无法生成报告"

    analysis = analyze(ratings)
    neutral = find_neutral_patterns(ratings)

    lines = [
        f"📊 穿搭偏好月度报告",
        f"📅 {datetime.now().strftime('%Y年%m月')} | 共 {analysis['total']} 次评分",
        "",
        "━━━ 📈 满意度分布 ━━━",
        f"❤️ 满意: {analysis['satisfaction_rate']}% ({analysis['by_score'].get(3,0)}次)",
        f"🤔 一般: {analysis['neutral_rate']}% ({analysis['by_score'].get(2,0)}次)",
        f"💔 失望: {analysis['disappoint_rate']}% ({analysis['by_score'].get(1,0)}次)",
        f"📊 平均分: {analysis['avg_rating']}/3",
        "",
        "━━━ 🎯 风格偏好 ━━━",
    ]

    for sid, data in sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg']):
        name = STYLE_NAMES.get(sid, sid)
        bar = '█' * int(data['avg'] * 3) + '░' * (9 - int(data['avg'] * 3))
        lines.append(f"  {name:10s} {bar} {data['avg']}分 ({data['total']}次)")

    lines.append("")
    lines.append("━━━ 👔 最爱单品 Top 5 ━━━")
    for iid, cnt in list(analysis['items_liked'].items())[:5]:
        tag_path = os.path.join(TAGS_DIR, f'{iid}.json')
        name = iid
        if os.path.exists(tag_path):
            with open(tag_path) as f:
                tag = json.load(f)
            name = f"{iid} ({tag.get('color',{}).get('hue_name','')} {tag.get('brand',{}).get('name','')})"
        lines.append(f"  {'👍':4s} {name} — {cnt}次满意")

    if analysis['items_disliked']:
        lines.append("")
        lines.append("━━━ ⚠️ 需注意的单品 ━━━")
        for iid, cnt in list(analysis['items_disliked'].items())[:3]:
            lines.append(f"  {'👎':4s} {iid} — {cnt}次不满意")

    lines.append("")
    lines.append("━━━ 🔍 中立模式分析 ━━━")
    if neutral:
        for s in neutral['summary']:
            lines.append(s)
    else:
        lines.append("  暂无足够2星数据")

    if analysis['feedback_reasons']:
        lines.append("")
        lines.append("━━━ 💔 1星反馈原因 ━━━")
        reason_names = {'style_mismatch': '风格不匹配', 'scene_mismatch': '场景不适用',
                        'combo_dislike': '搭配不喜欢', 'item_issue': '单品不合适'}
        for reason, cnt in analysis['feedback_reasons'].most_common():
            lines.append(f"  {reason_names.get(reason, reason)}: {cnt}次")

    lines.append("")
    lines.append("━━━ 💡 AI 建议 ━━━")
    if analysis['satisfaction_rate'] >= 60:
        lines.append("  ✅ 整体满意度良好，继续当前推荐策略")
    elif analysis['satisfaction_rate'] >= 40:
        lines.append("  ⚠️ 满意度中等，建议调整推荐权重")
    else:
        lines.append("  ❌ 满意度偏低，需要重新评估风格匹配")

    # 风格建议
    sorted_styles = sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])
    if sorted_styles:
        best = sorted_styles[0]
        worst = sorted_styles[-1]
        if best[0] != worst[0] and worst[1]['avg'] < 2:
            lines.append(f"  💡 建议增加 {STYLE_NAMES.get(best[0], best[0])} 推荐，减少 {STYLE_NAMES.get(worst[0], worst[0])}")

    return '\n'.join(lines)


def main():
    if '--weekly' in sys.argv:
        print(generate_weekly_report())
    elif '--report' in sys.argv:
        print(generate_report())
    elif '--summary' in sys.argv:
        ratings = load_all_ratings()
        a = analyze(ratings)
        print(f"总评分: {a['total']}次 | 满意度: {a['satisfaction_rate']}% | 平均: {a['avg_rating']}/3")
    else:
        ratings = load_all_ratings()
        a = analyze(ratings)
        print(json.dumps(a, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
