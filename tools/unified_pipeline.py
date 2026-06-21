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

手机端入口: wechat_control.py → build_enhanced_prompt()
"""

import json
import os
import re
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

# ── 路径常量 ──
TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')
CONFIG_DIR = os.path.join(PROJ_DIR, 'config')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')
SCENE_FILE = os.path.join(CONFIG_DIR, 'scene_profiles.json')
STRATEGIES_FILE = os.path.join(CONFIG_DIR, 'explore_strategies.json')
LAB_STATE_FILE = os.path.join(CONFIG_DIR, 'style_lab_state.json')

# ── 品类映射（从 common 统一导入，消除重复定义）──
from tools.common import (
    CAT_CONFIG, cat_code_to_name, cat_emoji, cat_icon_key,
    CORE_CATS, ITEM_ID_PATTERN,
    get_git_commit, get_cdn_base, cdn_url,
    parse_outfit_md, get_banned_items, get_recent_outfits, get_wear_counts,
    load_all_clothing, load_score_cache, load_style_fingerprint,
)

# 兼容旧代码的本地别名
CAT_CODE_TO_NAME = {k: v['cn'] for k, v in CAT_CONFIG.items()}
CAT_EMOJI = {k: v['emoji'] for k, v in CAT_CONFIG.items()}


# ============================================================
# 风格 → 摄影参数映射表（用于 Seedream prompt 优化）
# ============================================================

STYLE_PHOTO_MAP = {
    'japanese_city_boy': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, film simulation, slight grain',
        'angle': 'eye-level slightly off-center, intimate street snap framing',
        'light': 'overcast soft diffused light, even skin tones, subtle shadow definition',
        'pose': 'hands in jacket pockets, relaxed weight shift to one leg, looking down at phone with quiet focus',
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
        'pose': 'leaning against a minimalist concrete wall, weight shifted to one leg, one hand adjusting cuff, direct gaze with quiet confidence',
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
        'pose': 'walking toward stadium entrance, mid-laugh with friends (out of frame), match-day energy',
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
        'pose': 'walking slowly along a moon gate corridor, one hand brushing bamboo leaves, pausing by koi pond with quiet contemplation',
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


def _get_persona_description():
    """从 config/user_profile.json 构建人物描述，替代硬编码"""
    up = load_json(os.path.join(CONFIG_DIR, 'user_profile.json'))
    body = up.get('body', {}) if up else {}
    lifestyle = up.get('lifestyle', {}) if up else {}
    gender = up.get('gender', '男') if up else '男'

    h = body.get('height_cm', '')
    w = body.get('weight_kg', '')
    age = body.get('age', '')
    bt = body.get('body_type', '')
    st = body.get('skin_tone', '')
    shoulder = body.get('shoulder_type', '')
    face = body.get('face_shape', '')
    occ = lifestyle.get('occupation', '')
    style_pref = lifestyle.get('style_preference', '')

    # 构建描述段落
    parts = []
    if age:
        parts.append(f'{age}岁')
    parts.append('男性' if gender == '男' else '女性')
    if h:
        parts.append(f'{h}cm')
    if w:
        parts.append(f'{w}kg')
    if bt:
        parts.append(f'{bt}体型')
    if st:
        parts.append(f'{st}肤色')
    if shoulder:
        parts.append(f'{shoulder}')

    base_desc = '一位 ' + '，'.join(parts) if parts else '一位亚洲成人'

    # 身形修饰策略
    modifier_lines = []
    if bt == '偏瘦':
        modifier_lines.append('偏瘦体型优先选增加肩宽/体量感的单品')
        if h and int(h) >= 175:
            modifier_lines.append(f'身高{h}cm偏瘦，适合落肩宽松剪裁增加横向视觉')
    elif bt == '偏胖':
        modifier_lines.append('偏胖体型优先选竖向线条、深色系拉长身形')
        modifier_lines.append('避开横条纹和过于紧身的单品')
    elif bt == '肌肉型':
        modifier_lines.append('肌肉型体型可选修身剪裁展示线条，也可选宽松款走休闲路线')
    if st and st in ('白皙', '偏白'):
        modifier_lines.append('肤色偏白对颜色包容度高，可驾驭浅色系和亮色系')
    elif st and st in ('小麦', '偏黄', '偏黑'):
        modifier_lines.append('肤色偏深优先选低饱和暖色调，避免荧光色')

    # 身材秘密（用户自述的身材痛点，直接注入 prompt）
    body_secrets = up.get('body_secrets', '') if up else ''
    if body_secrets:
        modifier_lines.insert(0, f'⚠️ 身材痛点（用户自述）: {body_secrets}')
        modifier_lines.append('请根据上述身材痛点，在选品时主动扬长避短：遮住或修饰用户提到的部位，用剪裁和面料转移视觉焦点')

    # 着装背景
    context_lines = []
    if occ:
        context_lines.append(f'职业: {occ}')
    if style_pref:
        context_lines.append(f'风格偏好: {style_pref}')

    modifier_text = '\n'.join(f'□ {x}' for x in modifier_lines) if modifier_lines else ''
    context_text = '\n'.join(context_lines) if context_lines else ''

    return base_desc, modifier_text, context_text


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
        f"  相机: {d.get('camera', 'Sony A7IV 50mm f/1.4')}\n"
        f"  构图: {d.get('angle', 'low angle, rule of thirds')}\n"
        f"  光影: {d.get('light', 'golden hour backlight, warm rim light')}\n"
        f"  姿势: {d.get('pose', 'walking mid-stride, natural movement')}\n"
        f"  场景: {d.get('scene', 'modern urban street, soft afternoon light')}\n"
        f"  情绪: {d.get('vibe', 'editorial fashion photography, candid energy')}\n"
        f"  表情: natural relaxed expression, slight smile or soft neutral, not stiff editorial blank stare\n"
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


# common 导入已在上方统一完成


def load_scene_profiles():
    return load_json(SCENE_FILE)


def load_strategies():
    return load_json(STRATEGIES_FILE)


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
    """计算新鲜度（同日渐进惩罚，跨日严格）"""
    today_str = time.strftime('%Y-%m-%d')
    score = 50  # 基础新鲜度

    # 区分同日/跨日 — 同日渐进式惩罚
    same_day_count = 0
    cross_day = False
    for dir_name, ids in recent_outfits:
        if clothing_id in ids:
            is_today = dir_name.startswith(today_str) or dir_name.startswith('🆕今天')
            if is_today:
                same_day_count += 1  # 累计同天出现次数
            else:
                cross_day = True
    if cross_day:
        score -= 20  # 跨日正常扣分
    # 同日渐进惩罚：第1次复用-5，第2次-15，第3次+-25
    if same_day_count >= 3:
        score -= 25
    elif same_day_count >= 2:
        score -= 15
    elif same_day_count >= 1:
        score -= 5

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


# ============================================================
# 单品热度 & 冷却系统（avoidance_rules_v2）
# ============================================================

def _get_item_last_worn(all_outfits_with_dates):
    """从 [(date_str, item_ids), ...] 计算每件单品最近穿着距今天数"""
    from datetime import datetime as _dt
    today = _dt.now()
    last_worn = {}
    for date_str, ids in all_outfits_with_dates:
        try:
            d = _dt.strptime(date_str, '%Y-%m-%d')
            for cid in ids:
                if cid not in last_worn or d > last_worn[cid]:
                    last_worn[cid] = d
        except Exception:
            pass
    result = {}
    for cid, last_date in last_worn.items():
        result[cid] = (today - last_date).days
    return result


def _get_three_star_counts():
    """统计每件单品在3星outfit中出现的次数"""
    counts = {}
    for d in sorted(os.listdir(OUTFITS_DIR)):
        rp = os.path.join(OUTFITS_DIR, d, 'rating.json')
        if not os.path.exists(rp):
            continue
        try:
            with open(rp) as f:
                r = json.load(f)
            if r.get('rating') != 3:
                continue
            md = os.path.join(OUTFITS_DIR, d, 'outfit.md')
            if os.path.exists(md):
                with open(md) as f:
                    content = f.read()
                ids = set(re.findall(
                    ITEM_ID_PATTERN,
                    content
                ))
                for cid in ids:
                    counts[cid] = counts.get(cid, 0) + 1
        except Exception:
            pass
    return counts


def calculate_item_heat(item_id, wear_counts, all_clothes, three_star_counts):
    """计算单品热度 → (heat_score: int, heat_level: 'hot'|'warm'|'cold')"""
    count = wear_counts.get(item_id, 0)
    item = all_clothes.get(item_id, {})
    occasions = item.get('occasions', []) or []
    stars = three_star_counts.get(item_id, 0)

    # 新衣服（0次穿着）默认温门，不加冷却限制
    if count == 0:
        return (40, 'warm')

    max_wears = max(wear_counts.values()) if wear_counts else 1
    wear_score = min(count / max(8, max_wears) * 100, 100)
    occasion_score = min(len(occasions) / 3 * 100, 100) if occasions else 30  # 无场合数据给基础分
    rating_score = min(stars * 25, 100)

    heat = wear_score * 0.70 + occasion_score * 0.15 + rating_score * 0.15

    if heat >= 50:
        return (round(heat), 'hot')
    elif heat >= 25:
        return (round(heat), 'warm')
    else:
        return (round(heat), 'cold')


def get_cooldown(item_id, heat_level, category_code, days_since_last, three_star_count,
                 is_same_day=False, same_day_count=0):
    """计算单品冷却状态
    返回: {
        'status': 'sameday'|'available'|'almost'|'cooling'|'awaken',
        'icon': '🔄'|'🟢'|'🟡'|'🔴'|'💡',
        'days_since': int,       # 距上次穿着天数
        'cooldown_days': int,    # 需要冷却的天数
        'heat_level': str,       # hot/warm/cold
    }
    """
    # 同日 → 渐进式限制（第1次复用宽松，第3次起强制换）
    if is_same_day:
        if same_day_count >= 3:
            return {
                'status': 'sameday_blocked', 'icon': '⚠️', 'days_since': 0,
                'cooldown_days': 1, 'heat_level': heat_level,
            }
        elif same_day_count >= 2:
            return {
                'status': 'sameday', 'icon': '🔄²', 'days_since': 0,
                'cooldown_days': 0, 'heat_level': heat_level,
            }
        else:
            return {
                'status': 'sameday', 'icon': '🔄', 'days_since': 0,
                'cooldown_days': 0, 'heat_level': heat_level,
            }

    BASE = {'hot': 2, 'warm': 4, 'cold': 6}
    CAT_MULT = {
        'SHOE': 0.8, 'PT': 1.0, 'SH': 1.0,
        'TS': 1.2, 'LS': 1.2, 'SHIRT': 1.2, 'TANK': 1.2,
        'JK': 1.0,
        'HAT': 0.7, 'BAG': 0.7, 'SUN': 0.7, 'ACC': 0.7, 'SOCK': 0.7,
    }

    base = BASE.get(heat_level, 4)
    mult = CAT_MULT.get(category_code, 1.0)
    bonus = min(three_star_count, 2)

    cooldown = max(1, int(base * mult - bonus))

    # 从未穿过 → 可用
    if days_since_last is None or days_since_last >= 365:
        status = 'awaken' if heat_level == 'cold' else 'available'
    elif days_since_last >= cooldown:
        status = 'awaken' if heat_level == 'cold' else 'available'
    elif days_since_last >= cooldown - 1:
        status = 'almost'
    else:
        status = 'cooling'

    icon = {'available': '🟢', 'almost': '🟡', 'cooling': '🔴', 'awaken': '💡🟢'}.get(status, '🟢')

    return {
        'status': status, 'icon': icon, 'days_since': days_since_last or 0,
        'cooldown_days': cooldown, 'heat_level': heat_level,
    }


def build_wardrobe_table(target_styles, occasion, recent_outfits, banned_items,
                         wear_counts=None, cache=None, temp_high=25):
    """构建数据增强版衣柜表格 — 每个单品带风格/场景/新鲜度/冷却五维数据
    temp_high: 最高温度，用于过滤不合适季节的单品
    """
    all_clothes = load_all_clothing()
    cache = cache or load_score_cache()
    scene_profiles = load_scene_profiles()
    today_str = time.strftime('%Y-%m-%d')

    # ── 评分历史 ──
    rating_history = []
    all_outfits_dates = []  # [(date_str, [item_ids]), ...]
    for d in sorted(os.listdir(OUTFITS_DIR), reverse=True):
        rp = os.path.join(OUTFITS_DIR, d, 'rating.json')
        md = os.path.join(OUTFITS_DIR, d, 'outfit.md')
        if not os.path.exists(md):
            continue
        try:
            with open(md) as f:
                ids = list(set(re.findall(
                    ITEM_ID_PATTERN,
                    f.read()
                )))
        except Exception:
            ids = []
        date_str = d[:10] if len(d) >= 10 else ''
        all_outfits_dates.append((date_str, ids))

        if os.path.exists(rp):
            try:
                with open(rp) as f:
                    r = json.load(f)
                rating_history.append({'rating': r.get('rating', 0), 'items': ids})
            except Exception:
                pass

    # ── 预计算: 最后穿着天数 / 3星次数 ──
    item_last_worn = _get_item_last_worn(all_outfits_dates)
    three_star_counts = _get_three_star_counts()

    # ── 区分同日 vs 跨日最近已穿 ──
    same_day_items = {}  # {cid: count} — 同天出现次数
    cross_day_items = {}
    for dir_name, ids in recent_outfits:
        is_today = dir_name.startswith(today_str) or dir_name.startswith('🆕今天')
        for cid in ids:
            if is_today:
                same_day_items[cid] = same_day_items.get(cid, 0) + 1
            else:
                cross_day_items[cid] = cross_day_items.get(cid, 0) + 1

    # ── 计算同日生成次数 ──
    same_day_count = sum(1 for dn, _ in recent_outfits if dn.startswith(today_str) or dn.startswith('🆕今天'))

    # ── 按品类组织 ──
    cats = {}
    all_cooldowns = {}  # 汇总冷却状态供 prompt 摘要用

    for cid, item in all_clothes.items():
        cat = item.get('category', '其他')
        if cat not in cats:
            cats[cat] = []

        # 五维数据
        style_matches = _get_style_match_data(cid, target_styles, cache)
        scene_fit = _get_scene_fit(cid, occasion, scene_profiles)
        freshness = _get_freshness(cid, recent_outfits, wear_counts)
        personal = _get_personal_affinity(cid, banned_items, rating_history)

        # ── 冷却计算 ──
        cat_code = item.get('category_code', '')
        days_since = item_last_worn.get(cid)  # None = 从未穿过
        is_same_day = cid in same_day_items
        sd_count = same_day_items.get(cid, 0)
        heat_score, heat_level = calculate_item_heat(cid, wear_counts or {}, all_clothes, three_star_counts)
        cd = get_cooldown(cid, heat_level, cat_code, days_since,
                          three_star_counts.get(cid, 0), is_same_day, same_day_count=sd_count)

        # 新鲜度调整：融入冷却状态
        if cd['status'] == 'awaken':
            freshness += 15  # 冷门唤醒加分
        elif cd['status'] == 'cooling':
            freshness -= 10  # 冷却中减分
        elif cd['status'] == 'almost':
            freshness -= 5
        elif cd['status'] == 'sameday_blocked':
            freshness -= 20  # 同日第3次+ — 强烈不推荐

        # 如果从未穿过但冷却已满 → 额外加分（连续未选越久越推）
        if days_since is not None and days_since >= 10 and cd['status'] in ('available', 'awaken'):
            freshness += 10

        # 最佳风格匹配分
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
            'cooldown': cd,
        })
        all_cooldowns[cid] = cd

    # ── 冷却摘要（注入 prompt）──
    cooldown_summary_lines = []
    # 同日 — 渐进式提示
    if same_day_items:
        # 分组：可复用 vs 已超限
        reusable = [cid for cid, cnt in same_day_items.items() if cnt < 3]
        blocked = [cid for cid, cnt in same_day_items.items() if cnt >= 3]
        if blocked:
            cooldown_summary_lines.append(
                f'⚠️ 同日已超限（强制换掉）: {"、".join(sorted(blocked)[:10])}'
            )
        if reusable:
            cooldown_summary_lines.append(
                f'🔄 同日可复用: {"、".join(sorted(reusable)[:10])}'
            )
        cooldown_summary_lines.append(
            f'📊 同日已生成 {same_day_count} 套'
        )
    # 冷却中
    cooling = [(cid, cd) for cid, cd in all_cooldowns.items() if cd['status'] == 'cooling']
    if cooling:
        items_str = '、'.join(f"{cid}{cd['icon']}" for cid, cd in cooling[:10])
        cooldown_summary_lines.append(f'🔴 冷却中（尽量不选）: {items_str}')
    # 唤醒
    awaken = [(cid, cd) for cid, cd in all_cooldowns.items() if cd['status'] == 'awaken']
    if awaken:
        items_str = '、'.join(f"{cid}💡" for cid, _ in awaken[:10])
        cooldown_summary_lines.append(f'💡 沉睡单品（优先唤醒）: {items_str}')

    # ── 同日建议 ──
    same_day_hint = ''
    blocked_items = [cid for cid, cnt in same_day_items.items() if cnt >= 3] if same_day_items else []
    if same_day_count >= 3:
        blocked_str = '、'.join(blocked_items[:8]) if blocked_items else ''
        same_day_hint = f'⚠️ 今天已生成{same_day_count}套。以下单品已出现≥3次，必须换掉: {blocked_str}。鞋子必须换，上衣/下装至少再换1件。'
    elif same_day_count >= 2:
        same_day_hint = '🔄 今天第2套，建议换掉≥1件核心单品以体现变化。'
    elif same_day_count >= 1:
        same_day_hint = '🔄 今天已有1套，可以参考但不必完全避开。'

    # ── 温度过滤：跳过不适合当前季节的单品 ──
    HOT_THRESHOLD = 25   # >25°C 跳过非夏季品类
    COLD_THRESHOLD = 15  # <15°C 确保保暖品类
    skipped_cats = []
    for cat in list(cats.keys()):
        items_in_cat = cats[cat]
        if temp_high >= HOT_THRESHOLD:
            # 炎热：跳过外套、长袖上衣
            if cat in ('外套', '长袖上衣'):
                skipped_cats.append(f'{cat}({len(items_in_cat)}件，天热跳过)')
                del cats[cat]
        elif temp_high <= COLD_THRESHOLD:
            # 寒冷：跳过背心、短裤
            if cat in ('背心', '短裤'):
                skipped_cats.append(f'{cat}({len(items_in_cat)}件，天冷跳过)')
                del cats[cat]
    if skipped_cats:
        skipped_str = '、'.join(skipped_cats)
        cooldown_summary_lines.insert(0, f'🌡️ 温度{temp_high}°C — 自动跳过: {skipped_str}')

    # ── 温度过低保险：确保外套和长袖存在 ──
    if temp_high <= COLD_THRESHOLD:
        if '外套' not in cats or len(cats.get('外套', [])) == 0:
            cooldown_summary_lines.insert(0, '🧥 低温保险: 请务必选择外套 + 长袖上衣')
        if '长袖上衣' not in cats or len(cats.get('长袖上衣', [])) == 0:
            cooldown_summary_lines.insert(0, '🧥 低温保险: 请务必选择长袖上衣 + 外套')

    # ── 表格输出 ──
    cat_order = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '长裤', '短裤',
                 '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
    lines = []
    for cat in cat_order:
        if cat not in cats:
            continue
        lines.append(f'## {cat}')
        # 合并评分列：风格40% + 场景30% + 新鲜30% → 综合分
        lines.append('| ID | 品牌 | 颜色·面料 | 场景用途 | 综合 | 冷却 |')
        lines.append('|-----|------|----------|---------|------|------|')
        for it in sorted(cats[cat], key=lambda x: -x['style_score']):
            brand = it['brand']
            if it['collection']:
                brand += ' ' + it['collection']
            # 综合分 = 风格×0.4 + 场景×0.3 + 新鲜×0.3
            composite = int(it['style_score'] * 0.4 + it['scene_fit'] * 0.3 + it['freshness'] * 0.3)
            key_mark = '⭐' if it['style_key'] else ''
            comp_str = f'{composite}{key_mark}'
            cd = it['cooldown']
            if cd['status'] == 'sameday_blocked':
                cd_str = '🚫同天'
            elif cd['status'] == 'cooling':
                cd_str = f"🔴{cd['cooldown_days']}d"
            elif cd['status'] == 'almost':
                cd_str = f"🟡{cd['cooldown_days']}d"
            elif cd['status'] == 'awaken':
                cd_str = '💡唤醒'
            else:
                cd_str = '🟢'
            lines.append(
                f'| {it["id"]} | {brand[:22]} | {it["color"]}·{it["fabric"][:8]} | '
                f'{it["scenes"][:12]} | {comp_str:>4} | {cd_str} |'
            )
        lines.append('')

    wardrobe_text = '\n'.join(lines)

    # ── 组装完整输出 ──
    prefix = ''
    if cooldown_summary_lines:
        prefix = '📌 冷却状态速览:\n' + '\n'.join(cooldown_summary_lines) + '\n'
        if same_day_hint:
            prefix += same_day_hint + '\n'
        prefix += '\n'

    return prefix + wardrobe_text


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
                          explore_level=0.0, target_styles=None, mandatory_items=None):
    """构建 Round 1「选品」prompt — 只做单品选择，不含叙事/生图

    mandatory_items: [(item_id, confidence, reason), ...] 用户指定必须使用的单品
    """

    today = time.strftime('%Y-%m-%d')

    # ── 0. 强制单品（用户指定）──
    mandatory_section = ''
    if mandatory_items:
        all_clothes = load_all_clothing()
        mandatory_lines = []
        for mid, conf, reason in mandatory_items:
            item = all_clothes.get(mid, {})
            brand = (item.get('brand') or {}).get('name', '—')
            color = (item.get('color') or {}).get('hue_name', '—')
            cat = item.get('category', '—')
            mandatory_lines.append(
                f'  🎯 {mid} | {brand} | {color}·{cat} | 匹配: {reason} (置信度{conf:.0%})'
            )
        if mandatory_lines:
            mandatory_section = (
                '🎯🎯🎯 用户指定单品（硬性要求 — 必须使用，不可替换）🎯🎯🎯\n' +
                '\n'.join(mandatory_lines) + '\n' +
                '⚠️ 以上单品必须出现在 items 数组中。请以它们为锚点，围绕它们搭配其他单品。\n'
                '⚠️ 如果指定的是鞋子/下装/上衣，该品类不得再选其他单品。\n\n'
            )

    # ── 1. 获取推荐风格 ──
    if target_styles is None:
        from tools.style_matcher import auto_suggest_style
        suggestions = auto_suggest_style(temp_high, weather_cond, occasion)
        target_styles = [s['style_id'] for s in suggestions[:3]]
    if not target_styles:
        target_styles = ['clean_fit', 'japanese_city_boy']

    # ── 1.5. 用户指定风格优先：如果 style_hint 匹配已知 style_id 或中文名，强制置顶 ──
    hint_lower = style_hint.lower().replace(' ', '_').replace('-', '_')
    matched_style = None
    _best_match_len = 0  # 最长中文匹配优先
    if os.path.exists(STYLES_DIR):
        for fn in sorted(os.listdir(STYLES_DIR)):
            if not fn.endswith('.json'):
                continue
            sid = fn[:-5]  # 去掉 .json
            # 英文ID匹配（精确匹配直接采用）
            if sid in hint_lower or hint_lower in sid:
                matched_style = sid
                break
            # 中文名匹配：提取 style_hint 中的中文片段
            try:
                sf = load_style_fingerprint(sid)
                name_zh = sf.get('name_zh', '')
            except Exception:
                name_zh = ''
            if name_zh:
                import re as _re
                cn_blocks = _re.findall(r'[一-鿿]+', style_hint)
                for block in cn_blocks:
                    for n in range(min(4, len(block)), 1, -1):
                        for i in range(len(block) - n + 1):
                            chunk = block[i:i+n]
                            if chunk in name_zh and len(chunk) > _best_match_len:
                                matched_style = sid
                                _best_match_len = len(chunk)
    if matched_style and matched_style not in target_styles:
        target_styles.insert(0, matched_style)
        target_styles = target_styles[:4]  # 最多4个

    # ── 2. 加载上下文数据 ──
    banned_items = get_banned_items()
    recent_outfits = get_recent_outfits(limit=7)
    # 获取穿着次数（近似值）
    wear_counts = get_wear_counts()

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
            recent_section = (
                '\n📌 最近已穿（严格避穿规则）:\n' +
                '\n'.join(recent_lines) + '\n' +
                '⚠️ 避穿规则：\n'
                '  1. 鞋子如果在最近2套中出现过 → 必须换掉（硬性要求）\n'
                '  2. 上衣+下装+鞋子三件核心单品，至少换掉2件\n'
                '  3. 同一件单品连续穿2天以上 → 扣分（新鲜度已反映）\n'
                '  4. 目标：让用户感受到每天的穿搭有明显变化\n'
            )

    # ── 8. 构建增强衣柜表 ──
    wardrobe_table = build_wardrobe_table(
        target_styles, occasion, recent_outfits, banned_items, wear_counts,
        temp_high=temp_high
    )

    # ── 0.5. 用户形象描述（从 config/user_profile.json 动态读取）──
    persona_desc, persona_modifier, persona_context = _get_persona_description()

    quality_checklist = f"""⚠️ 推荐质量检查（请在选品时逐项确认）：
□ 三件套齐全：上衣 + 下装 + 鞋子，缺一不可
□ 配色协调：无红绿/橙蓝等冲突撞色，整体色调统一
□ 风格连贯：每件单品对目标风格的匹配分 ≥ 30
□ 廓形平衡：上宽下窄 或 外松内紧，避免全身同宽
□ 体型修饰：{persona_desc}
{persona_modifier}
□ 面料匹配场景：夏季上衣→透气(棉/麻/速干)，运动→速干，下装/鞋/配件不受面料限制
□ 衬肤色：根据用户肤色选择合适颜色
"""

    # ── 10. 组装 system prompt ──
    context_section = ''
    if persona_context:
        context_section = f'\n用户背景: {persona_context}'

    system_prompt = f"""你是一位专攻亚洲男性穿搭的 AI 时尚顾问。

你的任务是根据完整的衣柜数据（含风格匹配分、场景适配分、新鲜度），为一位用户（{persona_desc}）选出今日穿搭单品。{context_section}

选品原则：
1. 锚点优先：先确定今日的主角单品（表现力最强的核心件），再围绕它搭配同伴
2. 场景匹配：使用场景画像中的必备品类和品类加分指引
3. 新鲜感：避开最近已穿单品，优先选新鲜度高的
4. 颜色故事：确定主色调 → 辅助色 → 跳色（如有），避免冲突撞色
5. 廓形节奏：上宽下窄 或 外松内紧，保持整体节奏
6. 身形修饰：根据用户体型选择修饰策略（如上宽下窄、竖向线条等）

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
  "body_modifier": "身形修饰策略"
}}

注意：
- 每套必须包含上衣、下装、鞋子（硬性要求，缺一不可）
- 配件按场景需要选择，有理由才加，不铺满全身（例：运动→帽+包/晴天户外→墨镜/商务→手表/寒冷→保暖配件/日常休闲→0-1件，非穷举，根据实际场景灵活判断）
- ⚠️ 严禁添加第二件上衣（如长袖/衬衫/外套叠穿），除非场景明确需要（如寒冷天气）
- 运动场景（网球/跑步/健身）只选1件上衣+1件下装+1双运动鞋，可叠加功能性配件（帽子/运动包/运动墨镜/运动袜）
- 所有ID必须从衣柜表格中选取，严禁编造
- 永远不要输出 UNAVAILABLE 作为ID"""

    # ── 11. 组装 user prompt ──
    explore_header = ''
    if explore_level > 0:
        emoji = '🚀' if explore_level >= 0.8 else '🧪'
        explore_header = f'\n{emoji} 探索模式 | 探索度: {explore_level}\n'

    user_prompt = f"""今天是{today}，北京天气：{temp_high}°C {weather_cond}。
{explore_header}{mandatory_section}风格需求：「{style_hint}」
场合：{occasion}
{ban_section}{recent_section}
目标风格参考：
{chr(10).join(style_descs)}
{scene_text}
{strategy_text}
─── 衣柜档案（含风格匹配分/场景适配/新鲜度）───

{wardrobe_table}

─── 请输出 JSON 格式的穿搭方案（只需 items/color_story/silhouette/anchor/body_modifier，本轮不需要 seedream_prompt 或穿搭技巧）。───"""

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
        'target_styles': target_styles,
        'banned_items': banned_items,
        'recent_outfits': recent_outfits,
        'occasion': occasion,
        'scene_profile': scene_profile,
        'explore_level': explore_level,
        'photo_direction': photo_direction,  # 保留给 Round 2 使用
    }


# ============================================================
# Round 2: 创作 Prompt（基于已选单品生成叙事/技巧/生图）
# ============================================================

def build_creation_prompt(selection, photo_direction, target_styles, style_hint,
                          occasion, explore_level, temp_high, weather_cond):
    """构建 Round 2「创作」prompt — 基于已选单品，生成 seedream_prompt/穿搭技巧/推荐理由/关键词

    selection: Round 1 的 AI 输出 dict，含 items/color_story/silhouette/anchor/style
    """
    all_clothes = load_all_clothing()
    today = time.strftime('%Y-%m-%d')

    # ── 构建单品详情文本 ──
    item_lines = []
    for it in selection.get('items', []):
        cid = it['id']
        detail = all_clothes.get(cid, {})
        brand = (detail.get('brand') or {}).get('name', '')
        collection = (detail.get('brand') or {}).get('collection', '') or ''
        color = (detail.get('color') or {}).get('hue_name', '')
        fabric = (detail.get('fabric') or {}).get('primary', '')
        fit = (detail.get('silhouette') or {}).get('fit', '')
        comment = (detail.get('meta') or {}).get('claude_fit_comment', '')
        occasions = detail.get('occasions', [])
        cat = it.get('category', '')

        brand_str = f'{brand} {collection}'.strip()
        item_lines.append(
            f'  {cat} | {cid} | {brand_str} | {color} | {fabric} | 版型:{fit} | '
            f'场景:{"、".join(occasions) if occasions else "日常"} | {comment} | '
            f'选品理由: {it.get("reason", "")}'
        )

    items_text = '\n'.join(item_lines)
    color_story = selection.get('color_story', '')
    silhouette = selection.get('silhouette', '')
    anchor = selection.get('anchor', {})
    anchor_text = f'{anchor.get("id", "")} — {anchor.get("role", "")}' if anchor else '无'

    # ── 风格描述 ──
    style_descs = []
    for sid in target_styles[:3]:
        sf = load_style_fingerprint(sid)
        if sf:
            style_descs.append(f'  🎯 {sf.get("name_zh", sid)} ({sid}): {sf.get("description", "")[:80]}')

    # ── 探索度 ──
    explore_note = ''
    if explore_level > 0:
        emoji = '🚀' if explore_level >= 0.8 else '🧪'
        explore_note = f'\n{emoji} 探索度: {explore_level} — 鼓励创意发挥\n'

    system_prompt = f"""你是专攻亚洲男性穿搭的 AI 时尚顾问（创作模式）。

你的任务是基于已选定的穿搭单品，生成面向消费者的穿搭叙事内容。单品已经确定，你不需要再选品。

输出严格的 JSON 格式（不要任何其他文字）：
{{
  "keywords": "3-6个风格特征词，用中文顿号分隔（如：宽松廓形、少年感、帆布鞋、白袜、日系休闲）。⚠️这是穿搭风格标签，不是用户指令！必须从搭配本身提取美学特征，严禁照抄用户输入",
  "reasoning": "整体搭配理由（100-200字）：搭配逻辑阐述，解释为什么这些单品能组合在一起",
  "rationale": "推荐理由（100-200字）：消费者视角的一段话，从场景/风格/体型/单品特征角度说明为什么这套穿搭适合用户。用自然口语化句子，不编号不要点，强调「穿上为什么好看/合适」。与reasoning区别：reasoning是搭配逻辑，rationale是消费者话术",
  "dressing_tips": ["穿搭技巧1：基于所选单品的独特特征（特定颜色/面料/廓形/品牌设计细节/鞋型/领型），而非通用建议", "穿搭技巧2：必须与技巧1来自不同类别，数组长度1-2"],
  "seedream_prompt": "英文 Seedream 生图提示词(200-350字符)，必须融合下方📷摄影指导中的相机/构图/光影/姿势/场景/情绪/表情，用自己的语言自然改写。⚡姿势必须动态(禁止standing)，场景必须具体有辨识度。👟构图必须为全身照(full body shot from head to toe)，确保鞋子完整可见不被裁切。😊表情必须自然松弛（slight smile或relaxed neutral），严禁死板面瘫脸。详细描述服装细节和场景氛围，营造时尚大片的摄影感"
}}

注意：
- 推荐理由(rationale)必须面向消费者，强调「穿上为什么好看」，不是搭配逻辑阐述
- ⚠️ 穿搭技巧(dressing_tips)关键规则：
  1. 两条技巧必须来自不同类别（见下方技巧类型池），严禁同类重复
  2. 严禁使用「下摆塞前腰1/3」或任何形式的塞衣摆——这是最偷懒的通用技巧，除非该上衣的设计本身就是为塞入穿着（如正式衬衫配西裤）。绝大多数休闲T恤/衬衫应该自然垂坠或仅在特定姿势下微塞
  3. 每条技巧必须引用所选单品的具体特征：颜色名、面料、廓形、品牌设计细节、鞋型、领型等。不能说「上衣塞进去」，要说「因为TS-009是落肩宽松版型，自然垂坠的下摆刚好在臀围线上方，配合直筒牛仔裤能拉长腿部比例」
  4. 优先选择最能体现这套穿搭独特性的技巧，而非百搭通用技巧

技巧类型池（两条技巧必须从不同类别选取）：
🎨 颜色呼应：上下装配色逻辑、同色系跳色、补色碰撞、鞋与上衣/帽子的颜色链
👖 裤脚处理：卷边宽度与鞋型关系、堆叠vs九分的场景选择、裤线与鞋帮的衔接
👟 鞋袜搭配：鞋带系法、袜长与鞋帮高度配合、袜色作为跳色、特定鞋型的穿法（如高帮帆布鞋不系最上两颗扣）
🧥 廓形节奏：宽松与修身的上下比例、衣长与裤长的视觉分割点、袖口翻卷露出小臂的显瘦原理
🔗 配饰用法：帽子正戴/反戴的场景逻辑、包带长度与背法、墨镜/手表/项链的画龙点睛位置
🏷️ 品牌/设计细节：特定单品的隐藏穿法（如可拆卸标签、双面穿、隐藏口袋）、设计师意图的体现
🏃 场景专属：运动时配件的功能用法、雨天材质保护、户外防晒/防风的具体操作
📐 面料处理：亚麻的自然褶皱感、丹宁的折痕养成、速干面料的透气穿法"""

    sep = chr(10)
    user_prompt = f"""今天是{today}，北京天气：{temp_high}°C {weather_cond}。
风格需求：「{style_hint}」| 场合：{occasion}{explore_note}
目标风格参考：
{sep.join(style_descs)}

─── 已选穿搭方案 ───
锚点: {anchor_text}
配色: {color_story}
廓形: {silhouette}

单品清单：
{items_text}

{photo_direction}

─── 请基于以上已确定的单品，输出 JSON 格式的创作内容（keywords/reasoning/rationale/dressing_tips/seedream_prompt）。───"""

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
    }


# ============================================================
# Step 3: 规则自动验证
# ============================================================

def validate_outfit(items, occasion='日常', temp_high=30, weather_cond='晴', all_clothes=None):
    """验证 AI 选品是否通过所有规则门"""
    violations = []
    warnings = []

    if not items:
        return False, ['无任何单品'], []

    # 加载单品详情（支持外部传入复用）
    if all_clothes is None:
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
    top_count = sum(1 for c in cat_codes if c in ('TS', 'LS', 'SHIRT', 'TANK'))
    if jk_count > 1:
        violations.append('禁止两件外套')
    if shoe_count > 1:
        violations.append('禁止两双鞋')
    if top_count > 1:
        violations.append(f'禁止{top_count}件上衣（只能选1件上衣，不要叠穿长短袖/衬衫）')
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

        # 运动场景 + 长袖 = 不合理（即使晚上也不需要长袖运动）
        if occasion in ('网球', '跑步', '健身', '篮球', '足球', '羽毛球', '运动') and cat in ('LS', 'SHIRT'):
            if temp_high >= 25:
                violations.append(f'{cid}: 运动场景+气温≥25°C禁止长袖/衬衫')

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
        if occasion in ('跑步', '网球', '运动', '健身', '篮球', '足球', '羽毛球'):
            if cat == 'SHOE':
                # 检查鞋子的场合标签是否包含运动相关
                shoe_occasions = d['detail'].get('occasions', []) or []
                shoe_styles = d['detail'].get('style_modifiers', []) or []
                shoe_tags = ' '.join(shoe_occasions + shoe_styles).lower()
                # 非运动鞋的特征词
                non_sport_keywords = ['拖鞋', '凉鞋', '工装', '帆布', '皮鞋', '靴子', '沙滩', '居家', '板鞋', '高帮', '布鞋']
                is_non_sport = any(kw in shoe_tags for kw in non_sport_keywords)
                # 运动鞋的特征词
                sport_keywords = ['网球', '跑步', '运动', '训练', '健身', '篮球', '足球', '羽毛球', 'court', 'run', 'train', 'sport']
                is_sport = any(kw in shoe_tags for kw in sport_keywords)
                if is_non_sport and not is_sport:
                    violations.append(f'{cid}: 运动场景必须有功能运动鞋，不可选拖鞋/凉鞋/皮鞋/靴子/帆布鞋/工装靴')
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

def score_outfit(items, target_styles, occasion, temp_high, weather_cond, all_clothes=None):
    """对整套穿搭打分（outfit 级评分）"""
    if not items:
        return {'total': 0, 'label': '无效'}

    if all_clothes is None:
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

# _get_banned_items / _get_recent_outfits / _get_wear_counts
# 已迁移至 tools/common.py，通过顶部 import 直接使用 get_banned_items() 等函数


def find_items_by_description(description, all_clothes=None):
    """从用户自然语言描述中匹配衣柜单品 → [(item_id, confidence, reason), ...]

    支持: 品牌名/颜色/品类/面料/图案/昵称/穿着场景 的模糊匹配
    例: "大黄靴" → [(SHOE-007, 0.85, "Timberland·小麦棕·工装靴"), ...]
    """
    if all_clothes is None:
        all_clothes = load_all_clothing()

    desc = description.strip()
    if not desc:
        return []

    # ── 品类关键词映射 ──
    CAT_KEYWORDS = {
        '靴': ['靴', 'boot', '工装靴', '切尔西', '靴子'],
        '鞋': ['鞋', 'shoe', '运动鞋', '帆布鞋', '篮球鞋', '足球鞋', '网球鞋', '跑鞋', '德比鞋', '乐福鞋', '老爹鞋', '拖鞋'],
        '外套': ['外套', '夹克', 'jacket', '风衣', '大衣', '西装', '卫衣', '棒球服', '冲锋衣', '连帽'],
        '上衣': ['上衣', 'T恤', 't恤', 'tee', '短袖', '长袖', '衬衫', '衬衣', 'polo', 'POLO', '亨利衫', '卫衣', 'hoodie', '背心', '球衣'],
        '裤': ['裤', 'pant', '牛仔裤', '西裤', '工装裤', '短裤', '运动裤', '卫裤', '休闲裤', '直筒', '束脚'],
        '包': ['包', 'bag', '背包', '托特', 'tote', '斜挎'],
        '帽': ['帽', 'hat', 'cap', '棒球帽', '渔夫帽', 'bucket'],
        '墨镜': ['墨镜', '太阳镜', 'sunglass'],
        '配饰': ['手表', '手链', '手串', '项链', '戒指', '手环', 'watch'],
    }

    # ── 颜色关键词映射 ──
    COLOR_KEYWORDS = {
        '黄': ['黄', '姜黄', '焦糖', '小麦', '卡其', '驼', '橙', '荧光橙'],
        '红': ['红', '正红', '深红', '酒红', '粉', '玫红', '砖红'],
        '蓝': ['蓝', '藏青', '牛仔蓝', '灰蓝', '水洗蓝', '深蓝', '浅蓝', '靛蓝', '天蓝'],
        '绿': ['绿', '军绿', '墨绿', '深绿', '牛油果绿', '橄榄绿', '灰绿', '草绿'],
        '白': ['白', '米白', '象牙白', '奶油', '纯白', '灰白'],
        '黑': ['黑', '纯黑', '深黑', '暗黑'],
        '灰': ['灰', '麻灰', '深灰', '浅灰', '灰褐', '炭灰', '灰蓝'],
        '棕': ['棕', '褐', '深棕', '浅棕', '咖啡', '巧克力'],
        '紫': ['紫', '紫罗兰', '薰衣草'],
    }

    results = []

    for cid, item in all_clothes.items():
        score = 0.0
        reasons = []

        brand = (item.get('brand') or {}).get('name', '')
        collection = (item.get('brand') or {}).get('collection', '') or ''
        cat = item.get('category', '')
        cat_code = item.get('category_code', '')
        color = item.get('color') or {}
        hue_name = color.get('hue_name', '')
        hue_family = color.get('hue_family', '')
        fabric_primary = (item.get('fabric') or {}).get('primary', '')
        pattern_type = (item.get('pattern') or {}).get('type', '')
        occasions = item.get('occasions', [])
        style_mods = item.get('style_modifiers', [])
        fit_comment = (item.get('meta') or {}).get('claude_fit_comment', '')
        design_features = (item.get('design_features') or {})

        # ── 1. 品牌匹配（精确+模糊）──
        if brand and brand != '未知':
            brand_lower = brand.lower()
            if brand_lower in desc.lower():
                score += 0.40
                reasons.append(f'品牌:{brand}')
            # 品牌中英文昵称
            BRAND_ALIASES = {
                'timberland': ['踢不烂', '大黄靴', 'timberland'],
                'converse': ['匡威', 'converse', 'all star', 'chuck taylor'],
                'nike': ['耐克', 'nike', 'aj', 'air jordan'],
                'adidas': ['阿迪', '阿迪达斯', 'adidas', '三叶草'],
                'jordan': ['乔丹', 'jordan', 'aj'],
                'uniqlo': ['优衣库', 'uniqlo'],
                'fila': ['斐乐', 'fila'],
                'puma': ['彪马', 'puma'],
                'hla': ['海澜之家', 'hla'],
                'cdg': ['cdg', 'comme des', '川久保玲', 'play'],
                'merrell': ['merrell', '迈乐'],
            }
            for brand_key, aliases in BRAND_ALIASES.items():
                if any(a in desc.lower() for a in aliases):
                    if brand_key in brand_lower:
                        score += 0.40
                        reasons.append(f'昵称:{brand}')
                        break

        # ── 2. 品类匹配 ──
        cat_matched = False
        for cat_group, keywords in CAT_KEYWORDS.items():
            for kw in keywords:
                if kw in desc:
                    # 检查 item 的品类是否属于这一组
                    if kw in cat or any(cat_kw in cat for cat_kw in keywords):
                        score += 0.25
                        reasons.append(f'品类:{kw}')
                        cat_matched = True
                        break
            if cat_matched:
                break

        # ── 3. 颜色匹配 ──
        if hue_name or hue_family:
            all_color_text = f'{hue_name} {hue_family} {fabric_primary} {fit_comment}'
            for color_group, color_kws in COLOR_KEYWORDS.items():
                # 用户描述中有该颜色词
                if any(kw in desc for kw in color_kws):
                    # 单品颜色属于该色系
                    if any(kw in all_color_text for kw in color_kws):
                        score += 0.20
                        reasons.append(f'颜色:{color_group}({hue_name})')
                        break

        # ── 4. 面料/材质匹配 ──
        FABRIC_KEYWORDS = ['帆布', '皮质', '牛仔', '棉', '麻', '羊毛', '丝', '针织', '速干',
                           '灯芯绒', '合成', '木质', '皮革', '皮']
        for fkw in FABRIC_KEYWORDS:
            if fkw in desc and fkw in fabric_primary:
                score += 0.15
                reasons.append(f'面料:{fkw}')
                break

        # ── 5. 昵称/俗称匹配（从 fit_comment 中搜）──
        NICKNAMES = {
            '大黄靴': ['大黄靴', '大黄'],
            '小白鞋': ['小白鞋'],
            '老爹鞋': ['老爹鞋'],
            '马丁靴': ['马丁靴', '马丁'],
            '切尔西': ['切尔西', 'chelsea'],
            '椰子': ['椰子', 'yeezy'],
            '空军一号': ['空军一号', 'air force'],
            'aj': ['aj', 'air jordan', '乔丹'],
            '匡威': ['匡威', 'converse', 'all star'],
            '德比': ['德比', 'derby'],
            '渔夫帽': ['渔夫帽', 'bucket hat'],
            '棒球帽': ['棒球帽'],
        }
        search_text = f'{brand} {collection} {hue_name} {fabric_primary} {fit_comment} {" ".join(occasions)} {" ".join(style_mods)}'
        for _, aliases in NICKNAMES.items():
            for alias in aliases:
                if alias in desc.lower() and alias in search_text.lower():
                    score += 0.30
                    reasons.append(f'俗称:{alias}')
                    break

        # ── 6. 场景匹配 ──
        for occ in occasions:
            if occ in desc:
                score += 0.10
                reasons.append(f'场景:{occ}')
                break

        # ── 7. 运动专项匹配（网球/篮球/足球/跑步）──
        SPORT_KEYWORDS = {
            '网球': ['网球', 'tennis', 'court lite'],
            '篮球': ['篮球', 'basketball', 'aj', 'air jordan', 'jordan', '勇士'],
            '足球': ['足球', 'football', 'soccer', '曼联', 'man united', '曼城', '猎鹰', 'predator'],
            '跑步': ['跑步', 'running', 'run', '跑鞋'],
            '健身': ['健身', 'gym', '训练', 'train', '举铁'],
        }
        for sport, sport_kws in SPORT_KEYWORDS.items():
            if any(kw in desc.lower() for kw in sport_kws):
                if any(kw in search_text.lower() for kw in sport_kws):
                    score += 0.18
                    reasons.append(f'运动:{sport}')
                    break

        # ── 8. 图案/纹理匹配（条纹/格纹/印花等）──
        PATTERN_KEYWORDS = ['条纹', '格纹', '格子', '印花', '素色', '迷彩', '拼接', '菠萝纹', '椰树']
        for pkw in PATTERN_KEYWORDS:
            if pkw in desc and pkw in search_text:
                score += 0.18
                reasons.append(f'图案:{pkw}')
                break

        # ── 9. 风格特征匹配（工装/机能/复古/宽松等）──
        STYLE_FREE_KEYWORDS = ['工装', '机能', '复古', '宽松', '修身', '合身', '落肩',
                               '高帮', '低帮', '厚底', '束脚', '直筒', '连帽', '立领']
        for skw in STYLE_FREE_KEYWORDS:
            if skw in desc and skw in search_text:
                score += 0.12
                reasons.append(f'特征:{skw}')
                break

        # ── 10. 自由文本命中（fit_comment 和 collection 中搜用户关键词）──
        # 对2字以上的中文词在 fit_comment 中做自由搜索
        import re as _re
        free_words = _re.findall(r'[一-鿿]{2,}', desc)
        for word in free_words:
            # 跳过已匹配的通用词
            if word in ('我想', '今天', '穿什么', '怎么穿', '推荐', '穿搭', '一套', '搭配',
                        '晚上', '早上', '白天', '明天', '今天穿', '想穿', '需要'):
                continue
            if word in fit_comment:
                score += 0.10
                reasons.append(f'描述命中:{word}')
                break

        if score > 0:
            results.append((cid, min(score, 0.99), ' | '.join(reasons)))

    # 按分数降序排列
    results.sort(key=lambda x: -x[1])
    return results


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


