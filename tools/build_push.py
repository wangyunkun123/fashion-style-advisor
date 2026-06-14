#!/usr/bin/env python3
"""
推送文案生成器 — 结合风格库百科数据，生成带冷知识/单品解释/备选风格的丰富推送。

用法:
  python3 tools/build_push.py <outfit_dir>
  python3 tools/build_push.py <outfit_dir> --preview   仅预览，不推送
"""

import os, sys, json, re, random, glob, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.join(BASE_DIR, '..')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
STYLES_UNI_DIR = os.path.join(PROJ_DIR, 'styles_universal')
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')

# jsDelivr base（动态获取最新 commit hash，绕过 CDN 缓存）
def _get_cdn_base():
    try:
        import subprocess, os
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                          capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))+'/..').stdout.strip()
        if h: return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}'
    except: pass
    return 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'
CDN_BASE = _get_cdn_base()

# 推送偏好设置 URL
def get_push_base_url():
    """从配置获取推送服务器地址"""
    cfg_path = os.path.join(PROJ_DIR, 'config', 'seedream.local.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r') as f:
                return json.load(f).get('push_base_url', 'http://localhost:8765')
        except:
            pass
    return 'http://localhost:8765'

# 天气模块
sys.path.insert(0, os.path.join(BASE_DIR))
try:
    from weather_advisor import fetch_weather, analyze_weather, weather_line, weather_advice
except ImportError:
    weather_line = weather_advice = analyze_weather = None
    def fetch_weather(loc): return None

# 风格实验室（B线探索引擎）
try:
    from style_lab import (
        load_state as load_lab_state,
        save_state as save_lab_state,
        should_use_bline,
        should_use_bold,
        find_anchor_items,
        analyze_item_appeal,
        generate_exploration_directions,
        find_companions,
        assemble_exploratory_outfit,
        generate_exploration_narrative,
        generate_alt_section,
        get_user_comfort_zone,
        increment_state as increment_lab_state,
        update_item_wear_count,
        load_all_clothing,
    )
    STYLE_LAB_AVAILABLE = True
except ImportError:
    STYLE_LAB_AVAILABLE = False


# ============================================================
# 1. 内容提取
# ============================================================

def load_encyclopedia(style_id):
    """从百科中提取冷知识、名人、品牌信息"""
    path = os.path.join(STYLES_UNI_DIR, style_id, 'encyclopedia.md')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 提取一句话定义
    one_liner = ''
    for line in text.split('\n'):
        if '一句话定义' in line:
            m = re.search(r'[：:]\s*(.+)', line)
            if m:
                one_liner = m.group(1).strip()
            break

    # 提取趣味冷知识（截短到适合推送）
    origin = ''
    in_origin = False
    for line in text.split('\n'):
        if '### 起源' in line or '## 📜' in line:
            in_origin = True
            continue
        if in_origin and line.strip() and not line.startswith('#') and not line.startswith('>'):
            candidate = line.strip().lstrip('- ').strip()
            if len(candidate) > 30:
                if len(candidate) > 140:
                    origin = candidate[:140] + '...'
                else:
                    origin = candidate
                break

    # 提取名人引用
    quote = ''
    for line in text.split('\n'):
        if line.strip().startswith('>') and len(line) > 20:
            quote = line.strip().lstrip('> ').strip()
            if '：' in quote or '——' in quote or '"' in quote:
                break

    # 提取品牌代表（从品牌章节取前3个核心品牌）
    brands = []
    in_brands = False
    for line in text.split('\n'):
        if '## 🏷️' in line or '代表品牌' in line:
            in_brands = True
            continue
        if in_brands and line.startswith('##'):
            break
        if in_brands:
            m = re.match(r'^- \*\*(.+?)\*\*.*?[—]\s*(.+)$', line)
            if m:
                brands.append({'name': m.group(1).strip(), 'desc': m.group(2).strip()[:60]})
            if len(brands) >= 3:
                break

    # 提取风格偶像（取前2个）
    icons = []
    in_icons = False
    for line in text.split('\n'):
        if '## 👤' in line or '风格偶像' in line:
            in_icons = True
            continue
        if in_icons and line.startswith('##'):
            break
        if in_icons:
            m = re.match(r'^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
            if m:
                icons.append({'name': m.group(1).strip(), 'role': m.group(2).strip(), 'why': m.group(3).strip()[:60]})
            if len(icons) >= 2:
                break

    return {
        'one_liner': one_liner, 'origin': origin, 'quote': quote,
        'brands': brands, 'icons': icons,
        'encyclopedia_url': f'https://htmlpreview.github.io/?{CDN_BASE}/styles_universal/{style_id}/encyclopedia.html',
    }


def load_style_fingerprint(style_id):
    """从个人指纹中取配色逻辑"""
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8')  as f:
        return json.load(f)


def load_outfit_data(outfit_dir):
    """解析穿搭目录"""
    # 读取 outfit.md
    md_path = os.path.join(outfit_dir, 'outfit.md')
    if not os.path.exists(md_path):
        return None

    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    data = {'items': [], 'style_id': None, 'weather': '', 'date': ''}

    # 提取日期
    m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(outfit_dir))
    if m:
        data['date'] = m.group(1)

    # 提取风格
    m = re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)', text)
    if m:
        data['style_raw'] = (m.group(1) or m.group(2)).strip()

    # 提取天气
    m = re.search(r'天气.*?[：:]\s*(.+)', text)
    if m:
        data['weather'] = m.group(1).strip()

    # 提取单品表格
    in_table = False
    for line in text.split('\n'):
        s = line.strip()
        if '单品清单' in s:
            in_table = True
            continue
        if in_table and s.startswith('##'):
            break
        if not in_table or not s.startswith('|') or '---' in s:
            continue
        cells = [c.strip().replace('**', '') for c in s.split('|')]
        if len(cells) < 5:
            continue
        cid = cells[2]
        if not re.match(r'^[A-Z]+-\d+', cid):
            continue
        name = cells[3]
        score_text = cells[4]
        reason = cells[5] if len(cells) > 5 else ''
        data['items'].append({'id': cid, 'name': name, 'score': score_text, 'reason': reason})

    return data


def match_style_id(outfit_data, outfit_dir):
    """从 outfits 目录名或内容推断 style_id"""
    name_to_id = {
        '日系CityBoy': 'japanese_city_boy', '日系 City Boy': 'japanese_city_boy', '日系': 'japanese_city_boy',
        'CleanFit': 'clean_fit', 'Clean Fit': 'clean_fit', 'clean_fit': 'clean_fit',
        '轻熟休闲': 'smart_casual', '轻熟': 'smart_casual',
        '运动休闲': 'athleisure_sport', '运动': 'athleisure_sport', 'Athleisure': 'athleisure_sport',
        '韩系简约': 'korean_minimal', '韩系': 'korean_minimal',
        '度假休闲': 'resort_vacation', '度假': 'resort_vacation', 'Resort': 'resort_vacation',
        '街头潮流': 'streetwear', '街头': 'streetwear',
        '国风质感': 'chinese_heritage_luxe',
    }
    # 先从 outfit.md 风格字段匹配
    style_raw = outfit_data.get('style_raw', '')
    if style_raw:
        for name, sid in name_to_id.items():
            if name.lower().replace(' ', '') in style_raw.lower().replace(' ', ''):
                return sid
    # 再从目录名匹配
    dirname = os.path.basename(outfit_dir)
    for name, sid in name_to_id.items():
        if name.lower().replace(' ', '') in dirname.lower().replace(' ', ''):
            return sid
    return None


def get_item_score(cid, style_id):
    """从缓存取单品风格分"""
    if not os.path.exists(CACHE_FILE):
        return None
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    item_cache = cache.get(cid, {})
    style_cache = item_cache.get(style_id, {})
    score = style_cache.get('score', 0)
    breakdown = style_cache.get('breakdown', {})
    return {'score': score, 'breakdown': breakdown}


def get_random_images(style_id, count=3):
    """从风格图片库随机取N张参考图URL"""
    path = os.path.join(STYLES_UNI_DIR, style_id, 'references', 'images.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    all_imgs = []
    for cat_data in data.get('categories', {}).values():
        for img in cat_data.get('images', []):
            url = img.get('url', '')
            cap = img.get('caption', '')[:40]
            src = img.get('source', '')
            if url and not url.startswith('#'):
                all_imgs.append({'url': url, 'caption': cap, 'source': src})
    import random
    random.shuffle(all_imgs)
    return all_imgs[:count]


def get_key_item_reason(cid, style_id):
    """检查某件衣服是否为关键单品，返回原因"""
    style = load_style_fingerprint(style_id)
    if not style:
        return None
    cat = cid.split('-')[0] + '-'
    for ki in style.get('key_items', []):
        if ki.get('category_code') == cat:
            return ki.get('reason', '')
    return None


# ============================================================
# 2. 推送构建
# ============================================================

def build_push(outfit_dir, force_line=None, force_boldness=None):
    """主函数：生成丰富推送内容"""
    data = load_outfit_data(outfit_dir)
    if not data:
        return None, "无法解析 outfit.md", None

    style_id = match_style_id(data, outfit_dir) or 'japanese_city_boy'

    B = '\n\n'  # 段落间双换行
    parts = []

    # ━━━ 天气（只取一次，全函数复用）━━━
    wdata = fetch_weather('Beijing')
    analysis = analyze_weather(wdata) if wdata else None
    temp_high = analysis['forecast']['max'] if analysis else 30
    weather_cond = analysis['current']['desc'] if analysis else '晴'

    # ━━━ B线决策 ━━━
    is_bline = False
    is_bold = False
    boldness = 'micro'
    exploration_outfit = None
    comfort_zone = None
    bline_appeal = None       # 缓存：避免 prepare_bline_outfit 重复计算
    bline_narrative = None    # 缓存：避免重复生成叙事
    bline_encyc = None        # 缓存：避免重复加载百科

    if STYLE_LAB_AVAILABLE:
        state = load_lab_state()
        is_bline = (force_line == 'B') or (force_line is None and should_use_bline(state))
        if is_bline:
            is_bold = (force_boldness == 'bold') or (force_boldness is None and should_use_bold(state))
            boldness = 'bold' if is_bold else 'micro'

        if is_bline:
            try:
                all_clothing = load_all_clothing()
                comfort_zone = get_user_comfort_zone()

                anchor_strategy = 'bold' if is_bold else 'micro'
                anchors = find_anchor_items(state, min_statement_score=0.15, max_wear_count=2,
                                            count=5, strategy=anchor_strategy, comfort_zone=comfort_zone)
                if anchors:
                    anchor_data = anchors[0]
                    anchor_item = anchor_data['item']
                    bline_appeal = analyze_item_appeal(anchor_item)

                    directions = generate_exploration_directions(
                        anchor_item, temp_high, weather_cond, '日常', boldness, comfort_zone
                    )

                    if directions:
                        direction = directions[0]
                        companions = find_companions(anchor_item, direction, all_clothing, temp_high, weather_cond)
                        exploration_outfit = assemble_exploratory_outfit(direction, anchor_item, companions)
                        style_id = direction['target_style_id']
                        # 预加载百科（避免 prepare_bline_outfit 重复加载）
                        bline_encyc = load_encyclopedia(style_id)
                        # 预生成探索叙事
                        bline_narrative = generate_exploration_narrative(direction, anchor_item, companions)
            except Exception as e:
                is_bline = False
                is_bold = False
                exploration_outfit = None
    else:
        state = None

    # ━━━ 现有逻辑：风格匹配和百科加载 ━━━
    encyc = load_encyclopedia(style_id)
    style = load_style_fingerprint(style_id)
    main_items = [it for it in data['items'] if it['score'] and it['score'] != '—']
    acc_items = [it for it in data['items'] if it['score'] == '—' or not it['score']]
    style_name = style.get('name_zh', '日系CityBoy') if style else '今日推荐'

    # ━━━ A线风格笔记（无则生成并重跑排版）━━━
    if not is_bline:
        md_path = os.path.join(outfit_dir, 'outfit.md')
        with open(md_path, 'r') as f:
            md_text = f.read()
        if True:  # 每次都确保风格笔记最新
            # 先清除旧风格笔记
            if '## 风格笔记' in md_text:
                md_text = md_text.split('## 风格笔记')[0].rstrip()
                with open(md_path, 'w') as f:
                    f.write(md_text)
            # 从风格指纹提取关键特征
            style_desc = ''
            if encyc:
                style_desc = encyc.get('one_liner', '')
            if not style_desc and style:
                style_desc = style.get('description', '')
            # 清理括号内容，取前24字
            style_desc = re.sub(r'[（(][^）)]*[）)]', '', style_desc).strip()
            style_desc = style_desc[:24] if style_desc else ''
            silhouette = style.get('fingerprint', {}).get('silhouette', {}) if style else {}
            color_logic = style.get('fingerprint', {}).get('color_rules', {}).get('color_logic', '') if style else ''
            # 提取穿法要点
            wear_tips = []
            for it in data.get('items', [])[:2]:
                r = it.get('reason', '')
                if r:
                    wear_tips.append(r[:20])
            # 生成简洁笔记（每条尽量短以利卡片展示）
            notes = []
            notes.append(f'- {style_name}：{style_desc}' if style_desc else f'- {style_name}风格')
            if color_logic:
                notes.append(f'- {color_logic[:24]}')
            for tip in wear_tips:
                notes.append(f'- {tip}')
            notes_str = '\n'.join(notes)
            with open(md_path, 'a') as f:
                f.write(f'\n## 风格笔记\n\n{notes_str}\n')
            # 重跑排版
            import subprocess
            subprocess.run([sys.executable, os.path.join(BASE_DIR, 'composite_v2.py'), outfit_dir],
                          cwd=PROJ_DIR, capture_output=True, timeout=60)

    # ━━━ 标题区 ━━━
    outfit_name = os.path.basename(outfit_dir).split('_', 1)[-1] if '_' in os.path.basename(outfit_dir) else ''

    # B线标题加标记
    line_tag = ''
    if is_bline:
        line_tag = ' 🧪' if boldness == 'micro' else ' 🚀'

    header_lines = [
        f"👔 {outfit_name}{line_tag}",
        f"📅 {data.get('date', '')}",
    ]
    # 优先用实时天气，回退到md中的天气（已在函数顶部 fetch）
    if analysis:
        header_lines.append(weather_line(analysis))
        advice = weather_advice(analysis)
        if advice:
            header_lines.extend(advice)
    elif data.get('weather'):
        header_lines.append(f"🌤 {data['weather']}")
    parts.append('\n\n'.join(header_lines))

    # ━━━ 效果图 ━━━
    # B线：运行完整生图管线（豆包生图 → 抠图排版 → Git push → CDN）
    if is_bline and exploration_outfit:
        try:
            from style_lab import prepare_bline_outfit
            anchor = exploration_outfit['anchor_item']
            companions = exploration_outfit.get('companions', [])
            direction = exploration_outfit['direction']

            print(f"  [B线] 启动生图管线... 锚点: {anchor['clothing_id']}")
            outfit_dir, img_path, cdn_url = prepare_bline_outfit(
                anchor, companions, direction, temp_high, weather_cond,
                appeal=bline_appeal, narrative=bline_narrative, encyc=bline_encyc,
                all_clothing=all_clothing if is_bline else None
            )
            if img_path and cdn_url:
                parts.append(f"![风格实验室效果图]({cdn_url})")
            else:
                parts.append(f"🧪 本次风格实验围绕核心单品 **{anchor['clothing_id']}** 展开，搭配方案见下方。")
        except Exception as e:
            print(f"  [B线] 生图管线异常: {e}")
            parts.append(f"🧪 本次风格实验围绕核心单品 **{exploration_outfit['anchor_item']['clothing_id']}** 展开，搭配方案见下方。")
    else:
        ai_paths = sorted(glob.glob(os.path.join(outfit_dir, '上身效果', '*方案1.jpg')))
        if not ai_paths:
            ai_paths = sorted(glob.glob(os.path.join(outfit_dir, '上身效果', '*.jpg')))
        if ai_paths:
            rel = os.path.relpath(ai_paths[0], PROJ_DIR)
            parts.append(f"![效果图]({CDN_BASE}/{rel})")

    # ━━━ 风格故事 ━━━
    if encyc:
        story = []
        if encyc.get('origin'):
            story.append(encyc['origin'])
        if encyc.get('quote'):
            story.append(f"💬 {encyc['quote']}")
        if encyc.get('encyclopedia_url'):
            story.append(f"📚 [了解更多：{style_name}完整百科]({encyc['encyclopedia_url']})")
        if story:
            parts.append("━━━ 📖 风格故事 ━━━\n\n" + '\n\n'.join(story))

    # ━━━ 今日搭配 ━━━
    # B线：用探索方案重建搭配内容
    if is_bline and exploration_outfit:
        item_lines = []
        # 锚点单品
        anchor = exploration_outfit['anchor_item']
        cid = anchor['clothing_id']
        name = f"{anchor.get('brand', {}).get('name', '')} {anchor['color']['hue_name']}"
        emoji = {'SHIRT':'👔','TS':'👕','LS':'🧥','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','HAT':'🧢','SOCK':'🧦','BAG':'🎒','SUN':'🕶️','ACC':'💍','TANK':'🎽'}.get(cid.split('-')[0],'👔')
        item_lines.append(f"{emoji} **{name}** ⭐ 核心单品\n`{cid}` · 表现力 {exploration_outfit['direction'].get('anchor_score','?')}分")
        item_lines.append(f"*{bline_appeal.get('visual_signature', '') if bline_appeal else ''} · 探索基点*")

        # 同伴单品
        for comp in exploration_outfit.get('companions', [])[:5]:
            item = comp['item']
            cid2 = item['clothing_id']
            name2 = f"{item.get('brand', {}).get('name', '')} {item['color']['hue_name']}"
            emoji2 = {'SHIRT':'👔','TS':'👕','LS':'🧥','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','HAT':'🧢','SOCK':'🧦','BAG':'🎒','SUN':'🕶️','ACC':'💍','TANK':'🎽'}.get(cid2.split('-')[0],'👔')
            score2 = comp.get('style_score', '?')
            item_lines.append(f"{emoji2} **{name2}**\n`{cid2}` · 风格匹配 {score2}分")

        if item_lines:
            parts.append("━━━ 👔 今日搭配 ━━━\n\n" + '\n\n'.join(item_lines))

        # ━━━ 风格实验室叙事 ━━━
        narrative = bline_narrative or ''
        if narrative:
            parts.append("━━━ 🧪 风格实验室 ━━━\n\n" + narrative)

    else:
        # A线：原有的今日搭配逻辑
        item_lines = []
        for it in main_items:
            cid = it['id']  ;  name = it['name']
            score_info = get_item_score(cid, style_id)
            score = score_info['score'] if score_info else '?'
            key_reason = get_key_item_reason(cid, style_id)
            emoji = {'SHIRT':'👔','TS':'👕','LS':'🧥','JK':'🧥','PT':'👖','SH':'🩳','SHOE':'👟','HAT':'🧢','SOCK':'🧦','BAG':'🎒','SUN':'🕶️','ACC':'💍','TANK':'🎽'}.get(cid.split('-')[0],'👔')
            reason = key_reason or it.get('reason', '')
            score_str = f"{score}分" if isinstance(score, int) else str(score)
            item_lines.append(f"{emoji} **{name}**\n`{cid}` · 匹配度 {score_str}")
            if reason:
                item_lines.append(f"*{reason}*")
        if acc_items:
            for it in acc_items:
                e = {'HAT':'🧢','SOCK':'🧦','BAG':'🎒','SUN':'🕶️','ACC':'💍'}.get(it['id'].split('-')[0],'🔹')
                item_lines.append(f"{e} {it['name']} `{it['id']}`")
        if item_lines:
            parts.append("━━━ 👔 今日搭配 ━━━\n\n" + '\n\n'.join(item_lines))

        # A线推送也加入「今天也适合」（在参考图之后、配色之后）

    # ━━━ 参考图片 ━━━
    ref_imgs = get_random_images(style_id, 3)
    if ref_imgs:
        rlines = [f"📸 [{i['caption']}]({i['url']}) — {i['source']}" for i in ref_imgs]
        parts.append("━━━ 📸 风格参考图 ━━━\n\n" + '\n\n'.join(rlines))

    # ━━━ 配色 ━━━
    color_logic = style.get('fingerprint', {}).get('color_rules', {}).get('color_logic', '')
    # 从排版图中提取纯色块（无文字无背景）
    swatch_img_url = None
    try:
        from PIL import Image
        cache_file = os.path.join(outfit_dir, '上身效果', '.color_cache.json')
        colors = []
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                colors = [tuple(c) for c in json.load(f)]
        if colors:
            SZ = 40; GAP = 4; COUNT = len(colors)
            strip = Image.new('RGB', (COUNT*SZ + (COUNT-1)*GAP, SZ), (255,255,255))
            for i, rgb in enumerate(colors[:5]):
                for y in range(SZ):
                    for x in range(SZ):
                        strip.putpixel((i*(SZ+GAP)+x, y), rgb)
            swatch_path = os.path.join(outfit_dir, '上身效果', '_swatches.png')
            strip.save(swatch_path, 'PNG')
            rel = os.path.relpath(swatch_path, PROJ_DIR)
            swatch_img_url = f'{CDN_BASE}/{rel}'
            import subprocess as _sp
            _sp.run(['git', 'add', rel], cwd=PROJ_DIR, capture_output=True, timeout=10)
            _sp.run(['git', 'commit', '-m', '🎨 配色色块'], cwd=PROJ_DIR, capture_output=True, timeout=10)
            _sp.run(['git', 'push'], cwd=PROJ_DIR, capture_output=True, timeout=30)
    except Exception:
        pass

    if color_logic or swatch_img_url:
        color_parts = []
        if swatch_img_url:
            color_parts.append(f'![配色]({swatch_img_url})')
        if color_logic:
            color_parts.append(color_logic)
        parts.append("━━━ 🎨 配色 ━━━\n\n" + '\n\n'.join(color_parts))

    # ━━━ 今天也适合（动态生成）━━━
    if STYLE_LAB_AVAILABLE:
        alt_items = generate_alt_section(
            primary_line=('B' if is_bline else 'A'),
            is_bline=is_bline,
            is_bold=is_bold,
            primary_style_id=style_id,
            weather_temp=temp_high,
            weather_cond=weather_cond,
            occasion='日常',
            comfort_zone=comfort_zone,
        )
        if alt_items:
            alt_names = []
            base = get_push_base_url()
            for a in alt_items:
                url = f'{base}/try/{a["style_id"]}'
                alt_names.append(f"[{a['style_name']}]({url}) — {a['why']}")
            parts.append("━━━ 🔄 今天也适合 ━━━\n\n" + '\n\n'.join(alt_names))
        else:
            # 降级：硬编码备用
            base = get_push_base_url()
            alt_styles = [('korean_minimal','韩系简约'),('clean_fit','Clean Fit'),('smart_casual','轻熟休闲'),('athleisure_sport','运动休闲')]
            alt_names = [f"[{n}]({base}/try/{i})" for i,n in alt_styles if i != style_id]
            parts.append("━━━ 🔄 今天也适合 ━━━\n\n" + ' · '.join(alt_names[:3]))
    else:
        # 无 style_lab 时保持原有硬编码
        base = get_push_base_url()
        alt_styles = [('korean_minimal','韩系简约'),('clean_fit','Clean Fit'),('smart_casual','轻熟休闲'),('athleisure_sport','运动休闲')]
        alt_names = [f"[{n}]({base}/try/{i})" for i,n in alt_styles if i != style_id]
        parts.append("━━━ 🔄 今天也适合 ━━━\n\n" + ' · '.join(alt_names[:3]))

    # ━━━ 状态更新 ━━━
    if STYLE_LAB_AVAILABLE and state is not None:
        # 收集本套穿搭涉及的单品 ID
        outfit_item_ids = []
        if is_bline and exploration_outfit:
            outfit_item_ids.append(exploration_outfit['anchor_item']['clothing_id'])
            for c in exploration_outfit.get('companions', []):
                outfit_item_ids.append(c['item']['clothing_id'])
        else:
            for it in data['items']:
                outfit_item_ids.append(it['id'])

        state = increment_lab_state(state, is_bline, is_bold, outfit_item_ids)

        # 回写单品穿着次数
        for iid in set(outfit_item_ids):
            update_item_wear_count(iid)

        save_lab_state(state)

    return B.join(parts), style_name, outfit_name


# ============================================================
# 3. 命令行
# ============================================================

PREF_FILE = os.path.join(PROJ_DIR, 'config', 'push_preference.json')

def get_preference():
    """读取用户推送偏好"""
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, 'r') as f:
                return json.load(f).get('mode', 'both')
        except:
            pass
    return 'both'  # 默认首次推送两个版本

def set_preference(mode):
    """保存用户推送偏好"""
    os.makedirs(os.path.dirname(PREF_FILE), exist_ok=True)
    with open(PREF_FILE, 'w') as f:
        json.dump({'mode': mode, 'updated': time.strftime('%Y-%m-%d %H:%M')}, f, ensure_ascii=False)


def build_simple(outfit_dir):
    """生成简约版推送内容"""
    data = load_outfit_data(outfit_dir)
    if not data:
        return None, None, None
    outfit_name = os.path.basename(outfit_dir).split('_', 1)[-1] if '_' in os.path.basename(outfit_dir) else ''
    lines = [f"👔 {outfit_name}", f"📅 {data.get('date','')}"]
    if data.get('weather'):
        lines.append(f"🌤 {data['weather']}")
    # 单品
    for it in data['items']:
        lines.append(f"{it['id']} {it['name']}")
    # 效果图
    ai_paths = sorted(glob.glob(os.path.join(outfit_dir, '上身效果', '*方案1.jpg')))
    if not ai_paths:
        ai_paths = sorted(glob.glob(os.path.join(outfit_dir, '上身效果', '*.jpg')))
    if ai_paths:
        rel = os.path.relpath(ai_paths[0], PROJ_DIR)
        lines.append(f"![效果图]({CDN_BASE}/{rel})")
    return '\n\n'.join(lines), '简约版', outfit_name


def main():
    if len(sys.argv) < 2:
        print("用法: python3 tools/build_push.py <outfit_dir> [--preview] [--simple|--rich|--both] [--bline|--explore] [--bold|--adventure]")
        print("  B线触发词(微调): 探索 新尝试 新鲜 微调 不一样 换个口味 挖掘 冷门 尝鲜")
        print("  B线触发词(大胆): 大胆 另类 冒险 突破 跨界 出格 惊喜 前卫 个性 疯狂")
        print("  偏好设置: python3 tools/build_push.py --set simple|rich|both")
        return

    # 设置偏好
    if sys.argv[1] == '--set':
        if len(sys.argv) > 2 and sys.argv[2] in ('simple', 'rich', 'both'):
            set_preference(sys.argv[2])
            print(f"✅ 推送偏好已设为: {sys.argv[2]}")
        else:
            print(f"当前偏好: {get_preference()}")
            print("用法: --set simple|rich|both")
        return

    outfit_dir = sys.argv[1]
    if not os.path.isabs(outfit_dir):
        outfit_dir = os.path.join(PROJ_DIR, outfit_dir)
    outfit_dir = os.path.abspath(outfit_dir)

    preview = '--preview' in sys.argv
    force_mode = None
    for arg in sys.argv[2:]:
        if arg in ('--simple', '--rich', '--both'):
            force_mode = arg.lstrip('--')

    # B线参数：CLI 标志 + 触发词检测
    force_line = None
    force_boldness = None
    if '--bline' in sys.argv or '--explore' in sys.argv:
        force_line = 'B'
    if '--bold' in sys.argv or '--adventure' in sys.argv:
        force_line = 'B'
        force_boldness = 'bold'
    # 从 outfit 目录名自动检测触发词
    if force_line is None:
        try:
            from style_lab import detect_bline_trigger
            dir_name = os.path.basename(outfit_dir)
            is_bl, is_bd = detect_bline_trigger(dir_name)
            if is_bl:
                force_line = 'B'
                if is_bd:
                    force_boldness = 'bold'
        except ImportError:
            pass

    mode = force_mode or get_preference()

    sys.path.insert(0, os.path.join(BASE_DIR))
    from wechat_control import push_wechat

    if mode == 'both':
        # 发送两个版本
        rich_content, rich_name, outfit_name = build_push(outfit_dir, force_line, force_boldness)
        simple_content, _, _ = build_simple(outfit_dir)
        if not rich_content or not simple_content:
            print("❌ 生成失败")
            return

        push_title = outfit_name if outfit_name else '穿搭推荐'

        if preview:
            print("=" * 50)
            print("📱 简约版预览")
            print("=" * 50)
            print(simple_content)
            print("\n" + "=" * 50)
            print("📱 时尚版预览")
            print("=" * 50)
            print(rich_content)
        else:
            base = get_push_base_url()
            outfit_id = os.path.basename(outfit_dir)
            rate_link = f'[⭐ 给这套穿搭评分]({base}/rate?id={outfit_id})'
            simple_desc = '🅰️ 简约版：不想费心，每天一套穿好就走 👌'
            rich_desc = '🅱️ 时尚版：想跟AI一起探索风格，越穿越懂自己 🧠✨'
            footer = f'\n\n---\n{rate_link}\n💡 选择推送模式：\n[{simple_desc}]({base}/setpref?mode=simple)\n[{rich_desc}]({base}/setpref?mode=rich)'
            r1 = push_wechat(f'🅰️ {push_title}', simple_content + footer)
            r2 = push_wechat(f'🅱️ {push_title}', rich_content + footer)
            if r1 and r2:
                print(f"✅ 双版本已推送")
            else:
                print("❌ 推送失败")

    elif mode == 'simple':
        content, _, outfit_name = build_simple(outfit_dir)
        if content is None:
            print("❌ 生成失败"); return
        push_title = outfit_name if outfit_name else '穿搭推荐'
        if preview:
            print(content)
        else:
            push_wechat(push_title, content)
            print("✅ 简约版已推送")

    elif mode == 'rich':
        content, style_name, outfit_name = build_push(outfit_dir, force_line, force_boldness)
        if content is None:
            print(f"❌ {style_name}"); return
        push_title = outfit_name if outfit_name else style_name
        base = get_push_base_url()
        outfit_id = os.path.basename(outfit_dir)
        rate_footer = f'\n\n---\n[⭐ 给这套穿搭评分]({base}/rate?id={outfit_id})'
        if preview:
            print("=" * 50)
            print("📱 时尚版预览")
            print("=" * 50)
            print(content)
        else:
            push_wechat(push_title, content + rate_footer)
            print("✅ 时尚版已推送")


if __name__ == '__main__':
    main()
