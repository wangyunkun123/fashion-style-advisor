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

# jsDelivr base for encyclopedia links
CDN_BASE = 'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@main'

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

def build_push(outfit_dir):
    """主函数：生成丰富推送内容"""
    data = load_outfit_data(outfit_dir)
    if not data:
        return None, "无法解析 outfit.md"

    style_id = match_style_id(data, outfit_dir) or 'japanese_city_boy'
    encyc = load_encyclopedia(style_id)
    style = load_style_fingerprint(style_id)
    main_items = [it for it in data['items'] if it['score'] and it['score'] != '—']
    acc_items = [it for it in data['items'] if it['score'] == '—' or not it['score']]
    style_name = style.get('name_zh', '日系CityBoy') if style else '今日推荐'

    B = '\n\n'  # 段落间双换行
    parts = []

    # ━━━ 标题区 ━━━
    outfit_name = os.path.basename(outfit_dir).split('_', 1)[-1] if '_' in os.path.basename(outfit_dir) else ''
    header_lines = [
        f"👔 {outfit_name}",
        f"📅 {data.get('date', '')}",
    ]
    # 优先用实时天气，回退到md中的天气
    wdata = fetch_weather('Beijing')
    analysis = analyze_weather(wdata) if wdata else None
    if analysis:
        header_lines.append(weather_line(analysis))
        # 天气预警紧跟在天气行下面
        advice = weather_advice(analysis)
        if advice:
            header_lines.extend(advice)
    elif data.get('weather'):
        header_lines.append(f"🌤 {data['weather']}")
    parts.append('\n\n'.join(header_lines))

    # ━━━ 效果图 ━━━
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

    # ━━━ 参考图片 ━━━
    ref_imgs = get_random_images(style_id, 3)
    if ref_imgs:
        rlines = [f"📸 [{i['caption']}]({i['url']}) — {i['source']}" for i in ref_imgs]
        parts.append("━━━ 📸 风格参考图 ━━━\n\n" + '\n\n'.join(rlines))

    # ━━━ 配色 ━━━
    color_logic = style.get('fingerprint', {}).get('color_rules', {}).get('color_logic', '')
    if color_logic:
        parts.append(f"━━━ 🎨 配色 ━━━\n\n{color_logic}")

    # ━━━ 换个风格 ━━━
    alt_styles = [('korean_minimal','韩系简约'),('clean_fit','Clean Fit'),('smart_casual','轻熟休闲'),('athleisure_sport','运动休闲')]
    alt_names = [f"[{n}](https://htmlpreview.github.io/?{CDN_BASE}/styles_universal/{i}/encyclopedia.html)" for i,n in alt_styles if i != style_id]
    parts.append("━━━ 🔄 今天也适合 ━━━\n\n" + ' · '.join(alt_names[:3]))

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
        print("用法: python3 tools/build_push.py <outfit_dir> [--preview] [--simple|--rich|--both]")
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

    mode = force_mode or get_preference()

    sys.path.insert(0, os.path.join(BASE_DIR))
    from wechat_control import push_wechat

    if mode == 'both':
        # 发送两个版本
        rich_content, rich_name, outfit_name = build_push(outfit_dir)
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
            print("📱 百科版预览")
            print("=" * 50)
            print(rich_content)
        else:
            base = get_push_base_url()
            outfit_id = os.path.basename(outfit_dir)
            rate_link = f'[⭐ 给这套穿搭评分]({base}/rate?id={outfit_id})'
            simple_desc = '不想费心，每天一套穿好就走 👌'
            rich_desc = '想跟AI一起探索风格，越穿越懂自己 🧠✨'
            footer = f'\n\n---\n{rate_link}\n💡 选择推送模式：\n[🅰️ {simple_desc}]({base}/setpref?mode=simple) | [🅱️ {rich_desc}]({base}/setpref?mode=rich)'
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
        content, style_name, outfit_name = build_push(outfit_dir)
        if content is None:
            print(f"❌ {style_name}"); return
        push_title = outfit_name if outfit_name else style_name
        base = get_push_base_url()
        outfit_id = os.path.basename(outfit_dir)
        rate_footer = f'\n\n---\n[⭐ 给这套穿搭评分]({base}/rate?id={outfit_id})'
        if preview:
            print("=" * 50)
            print("📱 百科版预览")
            print("=" * 50)
            print(content)
        else:
            push_wechat(push_title, content + rate_footer)
            print("✅ 百科版已推送")


if __name__ == '__main__':
    main()
