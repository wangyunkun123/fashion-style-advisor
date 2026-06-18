#!/usr/bin/env python3
"""
统一推荐管线 — AI 主导 · 数据支撑 · 规则验证

核心理念：
  AI 是造型师，数据是参考资料，规则是安全网。
  一条管线覆盖所有推荐场景（日常/探索/大胆），不再分 AB 线。

流程：
  Step 1: 上下文编译 → 数据增强 prompt
  Step 2: AI 创意选品 → 锚点+同伴 JSON
  Step 3: 规则自动验证 → 硬阻断/场景合规/质量检查
  Step 4: 穿搭评分卡 → outfit 级评分
  Step 5: AI 最终对齐 + 叙事生成

用法:
  from unified_pipeline import run_unified_pipeline

  result = run_unified_pipeline(
      style_hint="日常通勤",
      explore_level=0.0,   # 0.0=安全, 0.5=微调, 1.0=大胆
      occasion="通勤",
      temp_high=30,
      weather_cond="晴",
  )
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

# ── 路径常量 ──
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
CONFIG_DIR = os.path.join(PROJ_DIR, 'config')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')
RULES_FILE = os.path.join(CONFIG_DIR, 'recommendation_rules.json')
SCENE_FILE = os.path.join(CONFIG_DIR, 'scene_profiles.json')
STRATEGIES_FILE = os.path.join(CONFIG_DIR, 'explore_strategies.json')
DEFAULTS_FILE = os.path.join(CONFIG_DIR, 'style_defaults.json')
LAB_STATE_FILE = os.path.join(CONFIG_DIR, 'style_lab_state.json')

# ── 品类映射 ──
CAT_CODE_TO_NAME = {
    'TS': '短袖上衣', 'LS': '长袖上衣', 'SHIRT': '衬衣', 'TANK': '背心',
    'JK': '外套', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
    'BAG': '包', 'HAT': '帽子', 'SOCK': '袜子', 'SUN': '墨镜', 'ACC': '手部配饰',
}

CAT_EMOJI = {
    'TS': '👕', 'LS': '👕', 'SHIRT': '👔', 'TANK': '🎽',
    'JK': '🧥', 'PT': '👖', 'SH': '🩳', 'SHOE': '👟',
    'BAG': '🎒', 'HAT': '🧢', 'SOCK': '🧦', 'SUN': '🕶️', 'ACC': '💍',
}

CORE_CATS = {'TS', 'LS', 'TANK', 'SHIRT', 'JK', 'SH', 'PT', 'SHOE'}


# ============================================================
# 风格 → 摄影参数映射表（用于 Seedream prompt 优化）
# ============================================================

STYLE_PHOTO_MAP = {
    'japanese_city_boy': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, film simulation, slight grain',
        'angle': 'eye-level slightly off-center, intimate street snap framing',
        'light': 'overcast soft diffused light, even skin tones, subtle shadow definition',
        'pose': 'hands in jacket pockets, relaxed weight shift to one leg, looking down at phone with quiet focus, headphones visible',
        'scene': 'quiet Daikanyama residential street, clean minimal architecture, potted plants, soft afternoon',
        'vibe': 'effortlessly cool candid snap, Japanese magazine editorial, caught in a quiet moment',
    },
    'japanese_amekaji': {
        'camera': 'Leica M6 50mm Summicron, Kodak Portra 400 film look, warm grain',
        'pose': 'leaning against vintage motorcycle or brick wall, arms crossed, gazing off-frame with rugged calm',
        'scene': 'vintage Americana shop front, aged brick wall, worn leather textures, late afternoon',
        'vibe': 'timeless rugged charm, American heritage filtered through Japanese precision',
    },
    'japanese_yama': {
        'camera': 'Sony A7IV 24-70mm f/2.8, crisp outdoor rendering',
        'pose': 'walking on forest trail, one hand adjusting backpack strap, looking ahead at the path, mid-stride',
        'scene': 'wooded mountain trail, dappled sunlight through trees, fresh greenery, morning mist',
        'vibe': 'outdoor explorer energy, at peace in nature, functional yet stylish',
    },
    'korean_minimal': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, crisp modern rendering, clean bokeh',
        'pose': 'leaning against white gallery wall, one hand touching collar, direct but soft eye contact',
        'scene': 'minimalist gallery space, white walls, polished concrete floors, single art piece',
        'vibe': 'architectural editorial, sharp and clean, understated confidence',
    },
    'korean_light_mature': {
        'camera': 'Fujifilm X-T5 56mm f/1.2, soft portrait rendering',
        'angle': 'waist-level framing, slight Dutch angle for dynamic tension',
        'pose': 'sitting at outdoor cafe table, one hand holding coffee cup, looking up at someone entering frame, slight knowing smile',
        'scene': 'Seoul Garosu-gil cafe terrace, plane tree shade, afternoon light through leaves',
        'vibe': 'K-drama still cut, soft romantic warmth, mature yet approachable',
    },
    'clean_fit': {
        'camera': 'Sony A7IV 50mm f/1.4, clinically sharp, minimal color grade',
        'pose': 'standing with deliberate posture, weight evenly distributed, looking directly at camera with quiet confidence',
        'scene': 'modern minimalist architecture, white and grey tones, clean geometric lines, morning crisp light',
        'vibe': 'editorial precision, Scandinavian cool, nothing out of place',
    },
    'streetwear': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, wide street framing',
        'angle': 'low angle from ground level, making subject look commanding',
        'pose': 'walking confidently mid-stride, one hand in pocket, looking ahead with quiet swagger, wind catching oversized hoodie',
        'scene': 'Harajuku backstreet with colorful signage, or Shanghai art district with graffiti walls, urban texture',
        'vibe': 'papaprazzi-style spontaneous shot, caught mid-motion, alive and dynamic',
    },
    'american_ivy_league': {
        'camera': 'Leica M6 35mm, Kodak Ektar 100 film look, rich but natural colors',
        'pose': 'walking across university quad with books in one hand, looking at watch, purposeful stride, slight smile',
        'scene': 'university campus, ivy-covered brick buildings, oak trees, morning crisp light, students in background blurred',
        'vibe': 'timeless academic elegance, quiet privilege, effortless polish',
    },
    'american_workwear': {
        'camera': 'Fujifilm X-T5 35mm, desaturated warm tones',
        'pose': 'crouching to pick up tool bag, or wiping hands on a rag, rugged functional movement',
        'scene': 'industrial loft space or workshop, exposed brick, raw wood textures, late afternoon side light',
        'vibe': 'rugged authenticity, functional strength, blue-collar heritage elevated',
    },
    'athleisure_sport': {
        'camera': 'Sony A7IV 70-200mm f/2.8, fast action capable',
        'pose': 'mid-stride running or serving a tennis ball, athletic dynamic motion, muscles engaged, slight sweat glow',
        'scene': 'outdoor tennis court with blue surface, or running track with morning light, or basketball court',
        'vibe': 'peak performance energy, athletic grace, sport-meets-style',
    },
    'british_heritage': {
        'camera': 'Leica M6 50mm, moody desaturated rendering, English overcast',
        'pose': 'adjusting coat collar against light drizzle, looking back over shoulder, windswept hair',
        'scene': 'London mews lane, cobblestones, brick archways, grey overcast sky, classic black cab in distance',
        'vibe': 'understated British elegance, weather-beaten charm, heritage with an edge',
    },
    'smart_casual': {
        'camera': 'Sony A7IV 50mm f/1.4, clean corporate rendering',
        'pose': 'checking wristwatch while walking through modern lobby, leather bag across body, focused but relaxed expression',
        'scene': 'modern glass office building lobby, polished concrete and steel, morning rush hour energy, blurred professionals in background',
        'vibe': 'urban professional energy, polished but approachable, modern gentleman',
    },
    'scandi_minimalism': {
        'camera': 'Sony A7IV 35mm f/2.8, neutral color profile, crisp',
        'pose': 'sitting on a simple wooden bench, looking out of frame contemplatively, hands resting lightly on lap',
        'scene': 'Copenhagen waterfront, clean lines, muted earth tones, overcast soft light, bicycle leaning nearby',
        'vibe': 'quiet contemplation, less-but-better philosophy, effortless restraint',
    },
    'scene_blokecore': {
        'camera': 'Fujifilm X-T5 23mm, vibrant color, documentary style',
        'pose': 'walking toward stadium entrance, scarf swinging, mid-laugh with friends (out of frame), match-day energy',
        'scene': 'football stadium exterior on match day, crowd in team colors, overcast English sky, brick stadium facade',
        'vibe': 'terrace culture energy, authentic fan spirit, football-meets-fashion',
    },
    'retro_90s_hiphop': {
        'camera': 'Contax T2 38mm, 35mm film grain, 90s snapshot aesthetic',
        'pose': 'mid-dance move or adjusting baseball cap low over eyes, relaxed swagger, one shoulder dropped',
        'scene': 'Brooklyn basketball court, chain-link fence, boombox nearby, golden hour warm tones',
        'vibe': 'golden era energy, authentic hip-hop culture, street legend casual',
    },
    'chinese_heritage': {
        'camera': 'Fujifilm X-T5 35mm, muted warm tones, cultural documentary',
        'pose': 'standing in traditional garden courtyard, one hand touching wooden pillar, looking at koi pond, quiet contemplation',
        'scene': 'Suzhou classical garden, white walls with grey tile roofs, bamboo shadows, morning mist',
        'vibe': 'cultural depth and quiet confidence, heritage reimagined for modern life',
    },
    'resort_vacation': {
        'camera': 'Fujifilm X-T5 23mm, bright and airy, vacation snapshot',
        'pose': 'walking barefoot on beach edge, holding sandals in one hand, looking at horizon, slight laugh caught by sea breeze',
        'scene': 'tropical beach at golden hour, gentle waves, palm tree silhouettes, or infinity pool overlooking ocean',
        'vibe': 'complete relaxation, nothing-to-do-today, sun-kissed and carefree',
    },
    'contemporary_gorpcore': {
        'camera': 'Sony A7IV 24-70mm f/2.8, outdoor adventure crisp',
        'pose': 'checking map on phone while hiking, or adjusting technical jacket hood, functional movement in nature',
        'scene': 'mountain trail with city skyline visible in far distance, morning fog rolling in, technical outdoor gear visible',
        'vibe': 'urban-to-wilderness, functional tech meets nature, adventure-ready confidence',
    },
}

# 默认摄影参数（当风格无映射时使用）
DEFAULT_PHOTO_DIRECTION = {
    'camera': 'Fujifilm X-T5 35mm f/1.4, shallow DOF',
    'angle': 'low angle from knee height, rule of thirds',
    'light': 'golden hour backlight, warm rim light',
    'pose': 'walking mid-stride toward camera, one hand casually in pocket, natural movement',
    'scene': 'modern urban street, soft afternoon light, clean background',
    'vibe': 'editorial fashion photography, effortlessly cool, candid energy',
}


def get_photo_direction(style_ids):
    """根据目标风格返回摄影指导参数"""
    directions = []
    for sid in style_ids:
        if sid in STYLE_PHOTO_MAP:
            directions.append(STYLE_PHOTO_MAP[sid])
    if not directions:
        directions = [DEFAULT_PHOTO_DIRECTION]
    # 取第一个匹配的风格作为主方向
    d = directions[0]
    return (
        f"📷 摄影指导（用于 seedream_prompt 创作）：\n"
        f"  相机: {d['camera']}\n"
        f"  构图: {d.get('angle', 'low angle, rule of thirds')}\n"
        f"  光影: {d['light']}\n"
        f"  姿势: {d['pose']}\n"
        f"  场景: {d['scene']}\n"
        f"  情绪: {d['vibe']}\n"
        f"  ⚠️ 这些参数要融入 seedream_prompt，但不要逐字复制，要自然改写。\n"
        f"  ⚠️ 姿势必须动态（禁止 standing），场景必须具体有辨识度。"
    )


# ============================================================
# 数据加载
# ============================================================

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_clothing():
    """加载所有衣服标签"""
    items = {}
    for fname in sorted(os.listdir(TAGS_DIR)):
        if fname == 'SCORE_CACHE.json' or not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(TAGS_DIR, fname)) as f:
                d = json.load(f)
            cid = d.get('clothing_id', '')
            if cid and not (d.get('meta') or {}).get('archived'):
                items[cid] = d
        except Exception:
            pass
    return items


def load_score_cache():
    return load_json(CACHE_FILE)


def load_rules():
    return load_json(RULES_FILE)


def load_scene_profiles():
    return load_json(SCENE_FILE)


def load_strategies():
    return load_json(STRATEGIES_FILE)


def load_style_defaults():
    return load_json(DEFAULTS_FILE)


def load_style_fingerprint(style_id):
    path = os.path.join(STYLES_DIR, f'{style_id}.json')
    return load_json(path)


def load_lab_state():
    return load_json(LAB_STATE_FILE)


def save_lab_state(state):
    with open(LAB_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# Step 1: 上下文编译 — 数据增强 Prompt
# ============================================================

def _get_style_match_data(clothing_id, target_styles, cache=None):
    """获取单品对目标风格的匹配分"""
    if cache is None:
        cache = load_score_cache()
    results = {}
    for sid in target_styles:
        entry = cache.get(clothing_id, {}).get(sid, {})
        score = entry.get('score', 0)
        bd = entry.get('breakdown', {})
        key_bonus = bd.get('key_item_bonus', 0)
        results[sid] = {
            'score': score,
            'is_key': key_bonus > 0,
            'color': bd.get('color_compatibility', 0),
            'body': bd.get('body_modifier', 0),
        }
    return results


def _get_scene_fit(clothing_id, occasion, scene_profiles=None):
    """计算单品对场景的适配度"""
    if scene_profiles is None:
        scene_profiles = load_scene_profiles()
    profiles = scene_profiles.get('profiles', {})
    profile = profiles.get(occasion, profiles.get('日常', {}))
    if not profile:
        return {'score': 50, 'reason': '无场景数据'}

    item = load_all_clothing().get(clothing_id, {})
    if not item:
        return {'score': 30, 'reason': '未找到单品'}

    cat = item.get('category_code', '')
    score = 30  # 基础分

    reasons = []

    # 关键词匹配（最高优先）
    keywords = profile.get('keywords', [])
    item_tags = item.get('style_modifiers', []) + item.get('occasions', [])
    kw_match = any(kw in str(tag) for kw in keywords for tag in item_tags)
    if kw_match:
        score += profile.get('keyword_boost', 30)
        reasons.append('关键词匹配')

    # 必备品类
    if cat in profile.get('required', []):
        score += 20
        reasons.append('必备品类')

    # 品类加分
    boost = profile.get('category_boost', {}).get(cat, 0)
    if boost:
        score += boost
        reasons.append(f'品类+{boost}')

    # 避雷品类
    if cat in profile.get('avoid', []):
        score -= 15
        reasons.append('避雷品类')

    # 正式度匹配
    traits = profile.get('traits', {})
    formality_range = traits.get('formality', [1, 5])
    item_formality = item.get('formality', 3)
    if isinstance(item_formality, str):
        try:
            item_formality = int(item_formality)
        except Exception:
            item_formality = 3
    if min(formality_range) <= item_formality <= max(formality_range):
        score += 5
        reasons.append('正式度匹配')

    # 面料匹配
    pref_fabrics = traits.get('fabric', [])
    item_fabric = (item.get('fabric') or {}).get('primary', '')
    if any(f in item_fabric for f in pref_fabrics):
        score += 5
        reasons.append('面料匹配')

    return {'score': min(score, 100), 'reason': '/'.join(reasons) if reasons else '基础分'}


def _get_freshness(clothing_id, recent_outfits, wear_counts=None):
    """计算新鲜度"""
    score = 50  # 基础新鲜度

    # 7天内穿过 → 扣分
    for dir_name, ids in recent_outfits:
        if clothing_id in ids:
            score -= 20
            break

    # 从穿着次数统计
    if wear_counts and clothing_id in wear_counts:
        count = wear_counts[clothing_id]
        if count >= 10:
            score -= 15  # 穿过很多次
        elif count >= 5:
            score -= 5
        elif count <= 1:
            score += 15  # 几乎没穿过 → 新鲜

    # 从未被穿过
    if wear_counts and clothing_id not in wear_counts:
        score += 15

    return max(score, 0)


def _get_personal_affinity(clothing_id, banned_items, rating_history=None):
    """计算个人偏好分"""
    if clothing_id in banned_items:
        return -100  # 禁用

    score = 50

    # 从评分历史推断偏好
    if rating_history:
        for record in rating_history:
            if record.get('rating') == 3 and clothing_id in record.get('items', []):
                score += 10  # 3星好评中的单品
            elif record.get('rating') == 1 and clothing_id in record.get('items', []):
                score -= 20  # 1星差评中的单品（但未精准禁用）

    return max(score, 0)


def build_wardrobe_table(target_styles, occasion, recent_outfits, banned_items,
                         wear_counts=None, cache=None):
    """构建数据增强版衣柜表格 — AI 看到每件单品带四维数据"""
    all_clothes = load_all_clothing()
    cache = cache or load_score_cache()
    scene_profiles = load_scene_profiles()

    # 加载评分历史
    rating_history = []
    for d in sorted(os.listdir(OUTFITS_DIR), reverse=True):
        rp = os.path.join(OUTFITS_DIR, d, 'rating.json')
        if os.path.exists(rp):
            try:
                with open(rp) as f:
                    r = json.load(f)
                # 提取单品列表
                md = os.path.join(OUTFITS_DIR, d, 'outfit.md')
                if os.path.exists(md):
                    with open(md) as f:
                        ids = list(set(re.findall(
                            r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                            f.read()
                        )))
                    rating_history.append({'rating': r.get('rating', 0), 'items': ids})
            except Exception:
                pass

    # 按品类组织
    cats = {}
    for cid, item in all_clothes.items():
        cat = item.get('category', '其他')
        if cat not in cats:
            cats[cat] = []

        # 四维数据
        style_matches = _get_style_match_data(cid, target_styles, cache)
        scene_fit = _get_scene_fit(cid, occasion, scene_profiles)
        freshness = _get_freshness(cid, recent_outfits, wear_counts)
        personal = _get_personal_affinity(cid, banned_items, rating_history)

        # 最佳风格匹配分（取最高）
        best_style = max(style_matches.values(), key=lambda x: x['score']) if style_matches else {'score': 0, 'is_key': False}
        best_style_id = max(style_matches, key=lambda x: style_matches[x]['score']) if style_matches else '—'

        cats[cat].append({
            'id': cid,
            'brand': ((item.get('brand') or {}).get('name') or '—')[:20],
            'collection': ((item.get('brand') or {}).get('collection') or '')[:16],
            'color': (item.get('color') or {}).get('hue_name', '—'),
            'fabric': (item.get('fabric') or {}).get('primary', ''),
            'fit': (item.get('silhouette') or {}).get('fit', ''),
            'scenes': '、'.join(item.get('occasions', [])) or '日常',
            'style_score': best_style['score'],
            'style_key': best_style['is_key'],
            'best_style': best_style_id,
            'scene_fit': scene_fit['score'],
            'scene_reason': scene_fit['reason'],
            'freshness': freshness,
            'personal': personal,
        })

    # 按固定品类顺序输出
    cat_order = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '长裤', '短裤',
                 '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
    lines = []
    for cat in cat_order:
        if cat not in cats:
            continue
        lines.append(f'## {cat}')
        # 增强版表头：增加匹配分/场景/新鲜度
        lines.append('| ID | 品牌 | 颜色·面料 | 场景 | 风格匹配 | 场景适配 | 新鲜度 |')
        lines.append('|-----|------|----------|------|---------|---------|--------|')
        for it in sorted(cats[cat], key=lambda x: -x['style_score']):
            brand = it['brand']
            if it['collection']:
                brand += ' ' + it['collection']
            key_mark = '⭐' if it['style_key'] else ''
            fresh_icon = '🆕' if it['freshness'] >= 65 else ('🔄' if it['freshness'] <= 35 else '')
            lines.append(
                f'| {it["id"]} | {brand[:22]} | {it["color"]}·{it["fabric"][:6]} | '
                f'{it["scenes"][:12]} | {it["style_score"]}{key_mark} | '
                f'{it["scene_fit"]} | {it["freshness"]}{fresh_icon} |'
            )
        lines.append('')

    return '\n'.join(lines)


def get_strategy_prompt(strategy_id, boldness='micro'):
    """将探索策略转为 AI 创意方向提示"""
    strategies = load_strategies().get('strategies', [])
    strategy = next((s for s in strategies if s['id'] == strategy_id), None)
    if not strategy:
        return ''

    lines = [
        f'🎯 今日探索方向：{strategy["name"]}',
        f'策略思路：{strategy["description"]}',
        f'灵感来源：{strategy["source"]}',
        f'选品指引：{strategy.get("companion_rule", "")}',
    ]
    hint = strategy.get('anchor_hint', {})
    if hint.get('categories'):
        lines.append(f'锚点品类优先：{"、".join(hint["categories"])}')
    if hint.get('prefer'):
        lines.append(f'偏好特征：{hint["prefer"]}')

    if boldness == 'bold':
        lines.insert(0, '⚠️ 大胆模式：鼓励突破常规，尝试平时不穿的搭配方式。')
        lines.append('允许制造有控制的冲突感（如颜色碰撞、风格混搭），但要确保能穿出门。')

    return '\n'.join(lines)


def pick_strategy(explore_level, comfort_zone=None):
    """根据探索度选取策略"""
    if explore_level <= 0:
        return None, None

    strategies = load_strategies().get('strategies', [])

    if explore_level <= 0.5:
        # 微调：从 micro 策略中选
        micro = [s for s in strategies if s.get('boldness') == 'micro']
        if micro:
            import random
            return random.choice(micro), 'micro'

    # 大胆：从 bold 策略中选 1-2 个
    bold = [s for s in strategies if s.get('boldness') == 'bold']
    if bold:
        import random
        count = 2 if explore_level >= 1.0 else 1
        selected = random.sample(bold, min(count, len(bold)))
        return selected[0], 'bold'

    return None, None


def build_enhanced_prompt(style_hint, occasion='日常', temp_high=30, weather_cond='晴',
                          explore_level=0.0, target_styles=None):
    """构建数据增强的 AI prompt — Step 1 核心输出"""

    today = time.strftime('%Y-%m-%d')

    # ── 1. 获取推荐风格 ──
    if target_styles is None:
        from tools.style_matcher import auto_suggest_style
        suggestions = auto_suggest_style(temp_high, weather_cond, occasion)
        target_styles = [s['style_id'] for s in suggestions[:3]]
    if not target_styles:
        target_styles = ['clean_fit', 'japanese_city_boy']

    # ── 2. 加载上下文数据 ──
    banned_items = _get_banned_items()
    recent_outfits = _get_recent_outfits(limit=7)
    # 获取穿着次数（近似值）
    wear_counts = _get_wear_counts()

    # ── 3. 加载场景画像 ──
    scene_profiles = load_scene_profiles().get('profiles', {})
    scene_profile = scene_profiles.get(occasion, scene_profiles.get('日常', {}))
    scene_text = ''
    if scene_profile:
        required = ' + '.join(scene_profile.get('required', []))
        avoid = '、'.join(scene_profile.get('avoid', [])) or '无'
        boost = '、'.join(f"{k}(+{v})" for k, v in scene_profile.get('category_boost', {}).items()) or '无'
        fabrics = '、'.join(scene_profile.get('traits', {}).get('fabric', [])) or '不限'
        fits = '、'.join(scene_profile.get('traits', {}).get('fit', [])) or '不限'
        keywords = '、'.join(scene_profile.get('keywords', [])) or '无'
        scene_text = f"""
📋 场景画像：{occasion}
- 必备品类：{required}
- 品类加分：{boost}
- 避雷品类：{avoid}
- 偏好面料：{fabrics}
- 偏好版型：{fits}
- 关键词匹配加分：{keywords}（单品标签含这些词优先选）
"""

    # ── 4. 选取探索策略 ──
    strategy_text = ''
    if explore_level > 0:
        strategy, boldness = pick_strategy(explore_level)
        if strategy:
            strategy_text = '\n' + get_strategy_prompt(strategy['id'], boldness) + '\n'

    # ── 5. 加载风格描述 ──
    style_descs = []
    for sid in target_styles[:3]:
        sf = load_style_fingerprint(sid)
        if sf:
            name = sf.get('name_zh', sid)
            desc = sf.get('description', '')[:60]
            color_logic = sf.get('fingerprint', {}).get('color_rules', {}).get('color_logic', '')
            style_descs.append(f'  🎯 {name} ({sid}): {desc}')
            if color_logic:
                style_descs.append(f'     配色逻辑: {color_logic[:50]}')

    # ── 5.5. 摄影指导（基于风格自动匹配）──
    photo_direction = get_photo_direction(target_styles)

    # ── 6. 构建禁用文本 ──
    ban_section = ''
    if banned_items:
        ban_section = f'\n🚫 一星差评禁用单品（严禁使用）: {"、".join(banned_items)}\n'

    # ── 7. 最近已穿 ──
    recent_section = ''
    if recent_outfits:
        recent_lines = []
        for dir_name, ids in recent_outfits:
            label = dir_name.split('_', 1)[-1] if '_' in dir_name else dir_name[:10]
            recent_lines.append(f"  {label}: {'、'.join(ids[:8])}")
        if recent_lines:
            recent_section = '\n📌 最近7天已穿（请至少换掉上衣/下装/鞋子中的两件）:\n' + '\n'.join(recent_lines) + '\n'

    # ── 8. 构建增强衣柜表 ──
    wardrobe_table = build_wardrobe_table(
        target_styles, occasion, recent_outfits, banned_items, wear_counts
    )

    # ── 9. 加载推荐规则的质量检查清单 ──
    rules = load_rules()
    quality_checklist = """
⚠️ 推荐质量检查（请在选品时逐项确认）：
□ 三件套齐全：上衣 + 下装 + 鞋子，缺一不可
□ 配色协调：无红绿/橙蓝等冲突撞色，整体色调统一
□ 风格连贯：每件单品对目标风格的匹配分 ≥ 30
□ 廓形平衡：上宽下窄 或 外松内紧，避免全身同宽
□ 体型修饰：偏瘦体型优先选增加肩宽/体量感的单品（179cm偏瘦白皙）
□ 面料舒适：优先棉/麻/亚麻等亲肤面料
□ 衬肤色：偏白肤色优先选低饱和冷色调
"""

    # ── 10. 组装 system prompt ──
    system_prompt = f"""你是一位专攻亚洲男性穿搭的 AI 时尚顾问。

你的任务是根据完整的衣柜数据（含风格匹配分、场景适配分、新鲜度），为一位 30岁亚洲男性（179cm偏瘦白皙）推荐穿搭方案。

选品原则：
1. 锚点优先：先确定今日的主角单品（表现力最强的核心件），再围绕它搭配同伴
2. 场景匹配：使用场景画像中的必备品类和品类加分指引
3. 新鲜感：避开最近已穿单品，优先选新鲜度高的
4. 颜色故事：确定主色调 → 辅助色 → 跳色（如有），避免冲突撞色
5. 廓形节奏：上宽下窄 或 外松内紧，保持整体节奏
6. 身形修饰：偏瘦体型选有体量感的单品增加肩宽/胸围视觉

{quality_checklist}

输出严格的 JSON 格式（不要任何其他文字）：
{{
  "anchor": {{"id": "PT-004", "role": "今日主角 — 微喇西裤增加下身量感"}},
  "style": "风格标签",
  "items": [
    {{"category": "上衣", "id": "TS-xxx", "name": "品牌+颜色描述", "color": "颜色", "reason": "为什么选这件"}},
    {{"category": "下装", "id": "PT-xxx", "name": "...", "color": "...", "reason": "..."}},
    {{"category": "鞋子", "id": "SHOE-xxx", "name": "...", "color": "...", "reason": "..."}}
  ],
  "color_story": "主色调+辅助色+跳色的完整配色逻辑",
  "silhouette": "廓形节奏描述",
  "body_modifier": "身形修饰策略",
  "reasoning": "整体搭配理由（100-200字）",
  "seedream_prompt": "英文 Seedream 生图提示词(200-350字符)，必须融合上方📷摄影指导中的相机/构图/光影/姿势/场景/情绪，但用自己的语言自然改写，不要逐字复制。⚡姿势必须动态(禁止standing)，场景必须具体有辨识度。详细描述服装细节和场景氛围，营造时尚大片的摄影感"
}}

注意：
- 每套必须包含上衣、下装、鞋子（硬性要求，缺一不可）
- 帽子、包、袜子、墨镜、配饰酌情添加（不是必须）
- 所有ID必须从衣柜表格中选取，严禁编造
- 永远不要输出 UNAVAILABLE 作为ID"""

    # ── 11. 组装 user prompt ──
    explore_header = ''
    if explore_level > 0:
        emoji = '🚀' if explore_level >= 0.8 else '🧪'
        explore_header = f'\n{emoji} 探索模式 | 探索度: {explore_level}\n'

    user_prompt = f"""今天是{today}，北京天气：{temp_high}°C {weather_cond}。
{explore_header}
风格需求：「{style_hint}」
场合：{occasion}
{ban_section}{recent_section}
目标风格参考：
{chr(10).join(style_descs)}
{scene_text}
{strategy_text}
{photo_direction}
─── 衣柜档案（含风格匹配分/场景适配/新鲜度）───

{wardrobe_table}

─── 请输出 JSON 格式的穿搭方案。───"""

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
        'target_styles': target_styles,
        'banned_items': banned_items,
        'recent_outfits': recent_outfits,
        'occasion': occasion,
        'scene_profile': scene_profile,
        'explore_level': explore_level,
    }


# ============================================================
# Step 3: 规则自动验证
# ============================================================

def validate_outfit(items, occasion='日常', temp_high=30, weather_cond='晴'):
    """验证 AI 选品是否通过所有规则门"""
    violations = []
    warnings = []

    if not items:
        return False, ['无任何单品'], []

    # 加载单品详情
    all_clothes = load_all_clothing()
    outfit_details = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        if not detail:
            violations.append(f'{cid} 不在衣柜中')
            continue
        outfit_details.append({'id': cid, 'item': it, 'detail': detail})

    cat_codes = [d['detail'].get('category_code', '') for d in outfit_details]

    # ── 1. 三件套齐全 ──
    has_top = any(c in CORE_CATS.intersection({'TS', 'LS', 'TANK', 'SHIRT', 'JK'}) for c in cat_codes)
    has_bottom = any(c in {'SH', 'PT'} for c in cat_codes)
    has_shoe = any(c == 'SHOE' for c in cat_codes)

    if not has_top:
        violations.append('缺少上衣')
    if not has_bottom:
        violations.append('缺少下装')
    if not has_shoe:
        violations.append('缺少鞋子')

    # ── 2. 重复品类检查 ──
    jk_count = cat_codes.count('JK')
    shoe_count = cat_codes.count('SHOE')
    pt_count = cat_codes.count('PT')
    sh_count = cat_codes.count('SH')
    if jk_count > 1:
        violations.append('禁止两件外套')
    if shoe_count > 1:
        violations.append('禁止两双鞋')
    if pt_count > 1 and sh_count > 0:
        warnings.append('同时有长裤和短裤，建议只选一种下装')
    if pt_count > 1 or sh_count > 1:
        if pt_count > 1:
            violations.append('禁止两条长裤')
        if sh_count > 1:
            violations.append('禁止两条短裤')

    # ── 3. 温度硬阻断 ──
    for d in outfit_details:
        cid = d['id']
        cat = d['detail'].get('category_code', '')
        fabric = (d['detail'].get('fabric') or {}).get('primary', '')

        # ≥35°C 禁长袖上衣
        if temp_high >= 35 and cat in ('LS', 'SHIRT'):
            violations.append(f'{cid}: 气温≥35°C禁止长袖上衣')

        # ≥35°C 禁止任何外套
        if temp_high >= 35 and cat == 'JK':
            violations.append(f'{cid}: 气温≥35°C禁止外套')

        # ≥32°C 禁止靴子
        if temp_high >= 32 and cat == 'SHOE' and '靴' in fabric:
            violations.append(f'{cid}: 气温≥32°C禁止靴子')

        # ≥30°C 禁止厚外套
        if temp_high >= 30 and cat == 'JK':
            if any(w in fabric for w in ['羊毛', '皮质', '灯芯绒']):
                if occasion not in ('商务', '约会'):
                    violations.append(f'{cid}: 气温≥30°C禁止厚外套')

        # ≤12°C 禁止短裤
        if temp_high <= 12 and cat == 'SH':
            violations.append(f'{cid}: 气温≤12°C禁止短裤')

        # ≤8°C 禁止帆布鞋
        if temp_high <= 8 and cat == 'SHOE' and '帆布' in fabric:
            violations.append(f'{cid}: 气温≤8°C禁止帆布鞋')

    # ── 4. 天气硬阻断 ──
    if weather_cond in ('雨', '暴雨', '雷雨', '雪'):
        for d in outfit_details:
            cid = d['id']
            cat = d['detail'].get('category_code', '')
            color = (d['detail'].get('color') or {}).get('hue_name', '')
            fabric = (d['detail'].get('fabric') or {}).get('primary', '')

            if cat in ('SH', 'PT') and any(w in color for w in ['白色', '米白', '米白色', '象牙白', '奶油色', '浅米色']):
                violations.append(f'{cid}: 雨天禁止白色/浅色下装')

            if cat == 'SHOE' and ('皮质' in fabric or '皮' in fabric):
                violations.append(f'{cid}: 雨天禁止皮质鞋')

    # ── 5. 场合硬阻断 ──
    for d in outfit_details:
        cid = d['id']
        cat = d['detail'].get('category_code', '')

        # 商务/正式
        if occasion in ('商务', '正式'):
            if cat == 'SH':
                violations.append(f'{cid}: 商务场合禁止短裤')
            if cid in ('SHOE-003', 'SHOE-008'):
                violations.append(f'{cid}: 商务场合禁止运动鞋')
            if cid in ('TS-007', 'JK-001'):
                violations.append(f'{cid}: 商务场合禁止球衣/运动外套')

        # 运动
        if occasion in ('跑步', '网球', '运动', '健身'):
            if cat == 'SHOE' and cid in ('SHOE-001', 'SHOE-002', 'SHOE-004', 'SHOE-006', 'SHOE-007', 'SHOE-009'):
                violations.append(f'{cid}: 运动场景必须有功能运动鞋，不可选皮鞋/靴子/帆布鞋')
            if cid in ('ACC-001', 'ACC-002'):
                violations.append(f'{cid}: 运动场景禁戴手串')
            if cat == 'PT' and cid in ('PT-001', 'PT-005', 'PT-006'):
                violations.append(f'{cid}: 运动场景禁止牛仔裤/西裤')

        # 约会
        if occasion == '约会':
            if cid == 'TS-007':
                violations.append(f'{cid}: 约会禁止穿球衣')
            # 约会禁止只穿背心（无外套叠穿时）
            if cat == 'TANK' and not any(c == 'JK' or c == 'SHIRT' for c in cat_codes):
                violations.append(f'{cid}: 约会禁止只穿背心（需要外套或衬衫叠穿）')

    # ── 6. 场景合规 ──
    scene_profiles = load_scene_profiles().get('profiles', {})
    scene = scene_profiles.get(occasion, scene_profiles.get('日常', {}))

    if scene:
        # 必备品类检查
        required = scene.get('required', [])
        for req_cat in required:
            if req_cat not in cat_codes:
                warnings.append(f'场景"{occasion}"缺少必备品类: {req_cat}')

        # 避雷品类检查
        avoid = scene.get('avoid', [])
        for d in outfit_details:
            cat = d['detail'].get('category_code', '')
            if cat in avoid:
                violations.append(f'{d["id"]}: 场景"{occasion}"避雷品类{cat}')

    # ── 7. 风格匹配最低分检查 ──
    cache = load_score_cache()
    # 从 style_hint 或 target_styles 中提取主风格
    for d in outfit_details:
        cid = d['id']
        cat = d['detail'].get('category_code', '')
        if cat in CORE_CATS:
            # 检查是否有至少一个风格匹配分 ≥ 20
            style_entries = cache.get(cid, {})
            if style_entries:
                best = max(e.get('score', 0) for e in style_entries.values() if not isinstance(e, str))
                if best < 20:
                    warnings.append(f'{cid}: 风格匹配分偏低({best})')

    # ── 8. 基本颜色冲突检测 ──
    colors = []
    for d in outfit_details:
        color = d['detail'].get('color', {})
        hue = color.get('hue_name', '')
        if hue:
            colors.append(hue)

    # 红+绿冲突
    reds = [c for c in colors if any(r in c for r in ['红', '橙', '粉'])]
    greens = [c for c in colors if '绿' in c]
    if reds and greens:
        warnings.append(f'颜色冲突: 红色系({"/".join(reds)})与绿色系({"/".join(greens)})')

    passed = len(violations) == 0
    return passed, violations, warnings


# ============================================================
# Step 4: 穿搭评分卡
# ============================================================

def score_outfit(items, target_styles, occasion, temp_high, weather_cond):
    """对整套穿搭打分（outfit 级评分）"""
    if not items:
        return {'total': 0, 'label': '无效'}

    all_clothes = load_all_clothing()
    cache = load_score_cache()

    # ── 1. 单品平均质量 (40%) ──
    item_scores = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        cat = detail.get('category_code', '')
        if cat not in CORE_CATS:
            continue  # 配饰不纳入平均

        # 取对目标风格的最佳匹配分
        best_score = 0
        for sid in target_styles:
            entry = cache.get(cid, {}).get(sid, {})
            s = entry.get('score', 0)
            if s > best_score:
                best_score = s
        item_scores.append(best_score)

    avg_item_score = sum(item_scores) / len(item_scores) if item_scores else 50

    # ── 2. 颜色协调度 (25%) ──
    colors = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        color = detail.get('color', {})
        if color:
            colors.append({
                'hue': color.get('hue_name', ''),
                'hue_family': color.get('hue_family', ''),
                'saturation': color.get('saturation', ''),
                'lightness': color.get('lightness', ''),
            })

    color_score = 70  # 基础分
    if colors:
        # 同色系加分
        hue_families = [c['hue_family'] for c in colors if c['hue_family']]
        if len(set(hue_families)) <= 2:
            color_score += 15
        elif len(set(hue_families)) <= 3:
            color_score += 5

        # 无彩色多 → 更安全
        neutrals = sum(1 for c in colors if c['hue_family'] in ('无彩色',))
        if neutrals >= len(colors) * 0.5:
            color_score += 10

    # ── 3. 廓形平衡 (15%) ──
    fits = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        fit = (detail.get('silhouette') or {}).get('fit', '')
        if fit:
            fits.append(fit)

    silhouette_score = 60
    if fits:
        fit_set = set(fits)
        if len(fit_set) >= 2:
            silhouette_score += 15  # 有变化，不是全身同宽

    # ── 4. 身形修饰覆盖 (10%) ──
    body_modifiers = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        modifiers = detail.get('style_modifiers', [])
        body_modifiers.extend([m for m in modifiers if any(kw in str(m) for kw in ['增加', '显', '拉长', '遮盖', '修饰'])])

    body_score = min(len(set(body_modifiers)) * 15, 100) if body_modifiers else 50

    # ── 5. 综合 ──
    total = round(
        avg_item_score * 0.40 +
        color_score * 0.25 +
        silhouette_score * 0.15 +
        body_score * 0.10
    )

    # 标签
    if total >= 80:
        label = '🔥 AI 高信心推荐'
    elif total >= 70:
        label = '👍 值得一试'
    elif total >= 60:
        label = '🧪 探索向，可能惊喜可能翻车'
    else:
        label = '⚠️ 评分偏低，建议重新选品'

    return {
        'total': total,
        'label': label,
        'breakdown': {
            'avg_item': round(avg_item_score),
            'color': round(color_score),
            'silhouette': round(silhouette_score),
            'body': round(body_score),
        }
    }


# ============================================================
# Step 7: AI 最终对齐 — 叙事生成
# ============================================================

def generate_narrative(items, target_styles, explore_level, outfit_score):
    """生成穿搭叙事（风格故事/搭配逻辑/穿法建议）"""
    all_clothes = load_all_clothing()
    lines = []

    # 风格背景
    style_names = []
    for sid in target_styles[:2]:
        sf = load_style_fingerprint(sid)
        if sf:
            style_names.append(sf.get('name_zh', sid))
    if style_names:
        lines.append(f'**风格基调**：{" × ".join(style_names)}')

    # 锚点介绍
    anchor = None
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        brand = (detail.get('brand') or {}).get('name', '')
        color = (detail.get('color') or {}).get('hue_name', '')
        comment = (detail.get('meta') or {}).get('claude_fit_comment', '')
        reason = it.get('reason', '')
        if anchor is None:
            anchor = f'**主角单品**：{brand} {color} — {reason or comment}'

    if anchor:
        lines.append(anchor)

    # 颜色故事
    color_story_parts = []
    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        color = (detail.get('color') or {}).get('hue_name', '')
        cat = CAT_CODE_TO_NAME.get(detail.get('category_code', ''), '')
        if color:
            color_story_parts.append(f'{color}({cat})')
    if color_story_parts:
        lines.append(f'**配色逻辑**：{" → ".join(color_story_parts)}')

    # 穿法建议
    wear_tips = []
    for it in items:
        reason = it.get('reason', '')
        if reason and len(reason) > 10:
            wear_tips.append(f'- {reason[:50]}')
    if wear_tips:
        lines.append(f'**穿法建议**\n{chr(10).join(wear_tips[:4])}')

    # 探索说明
    if explore_level > 0:
        emoji = '🚀' if explore_level >= 0.8 else '🧪'
        lines.append(f'{emoji} 探索度 {explore_level} | 穿搭评分 {outfit_score["total"]}分 — {outfit_score["label"]}')

    return '\n\n'.join(lines)


# ============================================================
# 辅助函数
# ============================================================

def _get_banned_items():
    """获取一星差评禁用的单品清单"""
    banned = []
    for d in os.listdir(OUTFITS_DIR):
        dp = os.path.join(OUTFITS_DIR, d)
        if not os.path.isdir(dp):
            continue
        rating_file = os.path.join(dp, 'rating.json')
        if not os.path.exists(rating_file):
            continue
        try:
            with open(rating_file, 'r') as f:
                rating_data = json.load(f)
            if rating_data.get('rating') == 1:
                # 精准禁用：优先使用用户标记的 banned_items
                feedback = rating_data.get('feedback', {}) or {}
                precise_banned = feedback.get('banned_items', [])
                if precise_banned and isinstance(precise_banned, list):
                    banned.extend(precise_banned)
                else:
                    # 旧数据兼容：没有 banned_items 则全部禁用
                    md = os.path.join(dp, 'outfit.md')
                    if os.path.exists(md):
                        with open(md, 'r') as f:
                            content = f.read()
                        ids = re.findall(
                            r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                            content
                        )
                        banned.extend(ids)
        except Exception:
            pass
    return list(set(banned))


def _get_recent_outfits(limit=7):
    """获取最近 N 套穿搭的核心单品"""
    today = time.strftime('%Y-%m-%d')
    recent = []
    for d in sorted(os.listdir(OUTFITS_DIR), reverse=True):
        dp = os.path.join(OUTFITS_DIR, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        if d.startswith(today):
            continue
        md = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md):
            continue
        try:
            with open(md, 'r') as f:
                content = f.read()
            ids = list(set(re.findall(
                r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                content
            )))
            core = [i for i in ids if i.split('-')[0] in CORE_CATS]
            if core:
                recent.append((d, core))
        except Exception:
            pass
        if len(recent) >= limit:
            break
    return recent


def _get_wear_counts():
    """统计每件单品的穿着次数"""
    counts = {}
    for d in os.listdir(OUTFITS_DIR):
        dp = os.path.join(OUTFITS_DIR, d)
        md = os.path.join(dp, 'outfit.md')
        if not os.path.exists(md):
            continue
        try:
            with open(md, 'r') as f:
                content = f.read()
            ids = re.findall(
                r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                content
            )
            for i in set(ids):
                counts[i] = counts.get(i, 0) + 1
        except Exception:
            pass
    return counts


def determine_explore_level(style_hint, force_explore=None):
    """根据用户输入确定探索度"""
    if force_explore is not None:
        return force_explore

    # 检测手动触发词
    micro_words = ['探索', '新尝试', '新鲜', '微调', '不一样', '换个口味', '挖掘', '冷门', '尝鲜']
    bold_words = ['大胆', '另类', '冒险', '突破', '跨界', '出格', '惊喜', '前卫', '个性', '疯狂']

    hint_lower = style_hint.lower()
    if any(w in hint_lower for w in bold_words):
        return 1.0

    if any(w in hint_lower for w in micro_words):
        return 0.5

    # 自动轮换：每4次触发1次微调
    state = load_lab_state()
    total = state.get('total_recommendations', 0)
    if total > 0 and total % 4 == 0:
        return 0.5

    return 0.0  # 安全模式


def update_lab_state(items):
    """更新推荐状态计数器"""
    state = load_lab_state()
    state['total_recommendations'] = state.get('total_recommendations', 0) + 1
    state['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')

    # 更新单品穿着次数
    if 'item_wear_counts' not in state:
        state['item_wear_counts'] = {}
    for it in items:
        cid = it.get('id', '')
        if cid:
            state['item_wear_counts'][cid] = state['item_wear_counts'].get(cid, 0) + 1

    save_lab_state(state)
    return state


# ============================================================
# 主入口
# ============================================================

def run_unified_pipeline(style_hint, occasion='日常', temp_high=30, weather_cond='晴',
                         explore_level=None, target_styles=None, call_ai_fn=None):
    """
    统一推荐管线主入口。

    参数:
      style_hint: 风格提示词（如 "日常通勤"）
      occasion: 场合 (运动/通勤/约会/聚会/度假/户外/居家/日常)
      temp_high: 最高温度
      weather_cond: 天气状况
      explore_level: 探索度 (None=自动检测, 0.0=安全, 0.5=微调, 1.0=大胆)
      target_styles: 手动指定风格列表
      call_ai_fn: AI调用函数 fn(system_prompt, user_prompt) -> str

    返回:
      {
        'plan': {...},           # AI 选品结果
        'validation': {...},     # 验证结果
        'outfit_score': {...},   # 穿搭评分
        'narrative': '...',      # 叙事文本
        'prompt_data': {...},    # 构建的 prompt（调试用）
        'explore_level': 0.0,    # 实际探索度
      }
    """
    # ── 确定探索度 ──
    if explore_level is None:
        explore_level = determine_explore_level(style_hint)

    # ── Step 1: 构建数据增强 prompt ──
    prompt_data = build_enhanced_prompt(
        style_hint=style_hint,
        occasion=occasion,
        temp_high=temp_high,
        weather_cond=weather_cond,
        explore_level=explore_level,
        target_styles=target_styles,
    )

    # ── Step 2: AI 创意选品 ──
    # 如果没传 AI 函数，使用默认的豆包调用
    if call_ai_fn is None:
        from tools.wechat_control import call_doubao_chat, extract_json
        content = call_doubao_chat([
            {'role': 'system', 'content': prompt_data['system_prompt']},
            {'role': 'user', 'content': prompt_data['user_prompt']},
        ], max_tokens=4096, timeout=180)
        plan = extract_json(content)
    else:
        content = call_ai_fn(prompt_data['system_prompt'], prompt_data['user_prompt'])
        # 尝试解析 JSON
        try:
            plan = json.loads(content)
        except Exception:
            m = re.search(r'\{.*\}', content, re.DOTALL)
            plan = json.loads(m.group(0)) if m else None

    if not plan:
        return {'error': 'AI 选品失败，无法解析 JSON', 'prompt_data': prompt_data}

    # 安全检查：如果 AI 返回 UNAVAILABLE，标记错误
    items = plan.get('items', [])
    unavailable = [it for it in items if it.get('id', '') == 'UNAVAILABLE']
    if unavailable:
        return {'error': f'AI 返回了 UNAVAILABLE: {[it.get("category","") for it in unavailable]}',
                'prompt_data': prompt_data}

    # ── Step 3: 规则验证 ──
    passed, violations, warnings = validate_outfit(items, occasion, temp_high, weather_cond)

    # 如果验证失败，构建反馈供 AI 修正
    validation = {
        'passed': passed,
        'violations': violations,
        'warnings': warnings,
    }

    # ── Step 4: 穿搭评分 ──
    outfit_score = score_outfit(items, prompt_data['target_styles'], occasion, temp_high, weather_cond)

    # ── Step 5: 生成叙事 ──
    narrative = generate_narrative(items, prompt_data['target_styles'], explore_level, outfit_score)

    # ── 更新状态 ──
    update_lab_state(items)

    return {
        'plan': plan,
        'validation': validation,
        'outfit_score': outfit_score,
        'narrative': narrative,
        'prompt_data': {'target_styles': prompt_data['target_styles'],
                        'explore_level': explore_level,
                        'occasion': occasion},
        'explore_level': explore_level,
    }


# ============================================================
# 命令行接口
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/unified_pipeline.py <style_hint> [--explore 0.5] [--occasion 通勤]")
        print("  python3 tools/unified_pipeline.py --validate <outfit_dir>")
        print()
        print("探索度: 0.0=安全 0.5=微调 1.0=大胆")
        return

    if sys.argv[1] == '--validate' and len(sys.argv) > 2:
        # 验证模式
        outfit_dir = sys.argv[2]
        md_path = os.path.join(outfit_dir, 'outfit.md')
        if not os.path.exists(md_path):
            print(f"outfit.md 不存在: {md_path}")
            return
        with open(md_path, 'r') as f:
            content = f.read()
        # 提取单品ID
        ids = list(set(re.findall(
            r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
            content
        )))
        items = [{'id': i} for i in ids]
        passed, violations, warnings = validate_outfit(items)
        print(f"验证{'通过 ✅' if passed else '未通过 ❌'}")
        if violations:
            print(f"违规: {violations}")
        if warnings:
            print(f"警告: {warnings}")
        if passed:
            score = score_outfit(items, ['clean_fit'], '日常', 30, '晴')
            print(f"穿搭评分: {score['total']}分 — {score['label']}")
        return

    # 推荐模式
    style_hint = sys.argv[1]
    explore_level = None
    occasion = '日常'

    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == '--explore' and i + 1 < len(sys.argv):
            explore_level = float(sys.argv[i + 1])
        elif arg == '--occasion' and i + 1 < len(sys.argv):
            occasion = sys.argv[i + 1]

    print(f"🚀 统一推荐管线启动")
    print(f"   风格: {style_hint} | 场合: {occasion} | 探索度: {explore_level}")

    result = run_unified_pipeline(style_hint, occasion=occasion, explore_level=explore_level)

    if 'error' in result:
        print(f"❌ {result['error']}")
        return

    plan = result['plan']
    validation = result['validation']
    score = result['outfit_score']

    print(f"\n{'='*60}")
    print(f"👔 {plan.get('style', '穿搭方案')}")
    print(f"{'='*60}")

    print(f"\n📋 单品清单:")
    for it in plan.get('items', []):
        emoji = CAT_EMOJI.get(it.get('id', '').split('-')[0], '👔')
        print(f"  {emoji} {it.get('id', '')} | {it.get('name', '')} | {it.get('color', '')}")
        if it.get('reason'):
            print(f"     → {it['reason'][:60]}")

    print(f"\n🧠 AI 搭配理由:")
    print(f"  {plan.get('reasoning', '')[:200]}")

    print(f"\n{'✅ 验证通过' if validation['passed'] else '❌ 验证未通过'}")
    if validation['violations']:
        for v in validation['violations']:
            print(f"  ❌ {v}")
    if validation['warnings']:
        for w in validation['warnings']:
            print(f"  ⚠️ {w}")

    print(f"\n📊 穿搭评分: {score['total']}分 — {score['label']}")
    bd = score['breakdown']
    print(f"  单品质量:{bd['avg_item']} | 颜色:{bd['color']} | 廓形:{bd['silhouette']} | 身形:{bd['body']}")

    print(f"\n📖 叙事:\n{result['narrative'][:300]}")


if __name__ == '__main__':
    main()
