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

import json, os, re, sys, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)

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
    from tools.common import resolve_tags_dir, set_thread_user
    from tools.user_manager import get_user_gender
    _gender = get_user_gender(_USER_ID) or 'male'
    set_thread_user(_gender, _USER_ID)
    TAGS_DIR = resolve_tags_dir(_gender, _USER_ID)
else:
    TAGS_DIR = os.path.join(PROJ_DIR, 'wardrobe', 'tags')

# ── 路径常量 ──
CONFIG_DIR = os.path.join(PROJ_DIR, 'config')
STYLES_DIR = os.path.join(PROJ_DIR, 'styles')
OUTFITS_DIR = os.path.join(PROJ_DIR, 'outfits')
CACHE_FILE = os.path.join(TAGS_DIR, 'SCORE_CACHE.json')
SCENE_FILE = os.path.join(CONFIG_DIR, 'scene_profiles.json')
STRATEGIES_FILE = os.path.join(CONFIG_DIR, 'explore_strategies.json')
LAB_STATE_FILE = os.path.join(CONFIG_DIR, 'style_lab_state.json')

# ── 多用户目录解析（线程感知）──
def _resolve_outfits_dir():
    from tools.common import get_thread_user, resolve_outfits_dir
    gender, uid = get_thread_user()
    return resolve_outfits_dir(gender, uid) if uid else OUTFITS_DIR

def _resolve_tags_dir():
    from tools.common import get_thread_user, resolve_tags_dir
    gender, uid = get_thread_user()
    return resolve_tags_dir(gender, uid) if uid else TAGS_DIR

# ── 品类映射（从 common 统一导入，消除重复定义）──
from tools.common import (
    CAT_CONFIG, cat_code_to_name, cat_emoji, cat_icon_key,
    CORE_CATS, ITEM_ID_PATTERN,
    get_git_commit, get_cdn_base, cdn_url,
    parse_outfit_md, get_banned_items, get_recent_outfits, get_wear_counts,
    load_all_clothing, load_score_cache, load_style_fingerprint,
    resolve_user_dir,
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
        'angle': 'eye-level, honest full-body framing, textural detail forward',
        'light': 'warm late-afternoon side light, soft Portra glow, gentle shadow',
        'pose': 'leaning against vintage motorcycle or brick wall, arms crossed, gazing off-frame with rugged calm',
        'scene': 'vintage Americana shop front, aged brick wall, worn leather textures, late afternoon',
        'vibe': 'timeless rugged charm, American heritage filtered through Japanese precision',
    },
    'japanese_yama': {
        'camera': 'Sony A7IV 24-70mm f/2.8, crisp outdoor rendering',
        'angle': 'slightly low dynamic trail angle, functional layering shown',
        'light': 'dappled forest sunlight through canopy, fresh morning-mist diffusion',
        'pose': 'walking on forest trail, one hand adjusting backpack strap, looking ahead at the path, mid-stride',
        'scene': 'wooded mountain trail, dappled sunlight through trees, fresh greenery, morning mist',
        'vibe': 'outdoor explorer energy, at peace in nature, functional yet stylish',
    },
    'korean_minimal': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, crisp modern rendering, clean bokeh',
        'angle': 'eye-level, clean centered gallery framing, negative space',
        'light': 'crisp even gallery light, soft clean shadow, architectural clarity',
        'pose': 'leaning against white gallery wall, one hand touching collar, direct but soft eye contact',
        'scene': 'minimalist gallery space, white walls, polished concrete floors, single art piece',
        'vibe': 'architectural editorial, sharp and clean, understated confidence',
    },
    'korean_light_mature': {
        'camera': 'Fujifilm X-T5 56mm f/1.2, soft portrait rendering',
        'light': 'soft afternoon light filtered through leaves, gentle romantic glow',
        'angle': 'waist-level framing, slight Dutch angle for dynamic tension',
        'pose': 'sitting at outdoor cafe table, one hand holding coffee cup, looking up at someone entering frame, slight knowing smile',
        'scene': 'Seoul Garosu-gil cafe terrace, plane tree shade, afternoon light through leaves',
        'vibe': 'K-drama still cut, soft romantic warmth, mature yet approachable',
    },
    'clean_fit': {
        'camera': 'Sony A7IV 50mm f/1.4, clinically sharp, minimal color grade',
        'angle': 'eye-level, clean minimalist framing, generous negative space',
        'light': 'crisp cool morning light, clean soft shadow, Scandinavian clarity',
        'pose': 'leaning against a minimalist concrete wall, weight shifted to one leg, one hand adjusting cuff, direct gaze with quiet confidence',
        'scene': 'modern minimalist architecture, white and grey tones, clean geometric lines, morning crisp light',
        'vibe': 'editorial precision, Scandinavian cool, nothing out of place',
    },
    'streetwear': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, wide street framing',
        'light': 'bright urban daylight, punchy street contrast, colorful sign glow',
        'angle': 'low angle from ground level, making subject look commanding',
        'pose': 'walking confidently mid-stride, one hand in pocket, looking ahead with quiet swagger, wind catching oversized hoodie',
        'scene': 'Harajuku backstreet with colorful signage, or Shanghai art district with graffiti walls, urban texture',
        'vibe': 'papaprazzi-style spontaneous shot, caught mid-motion, alive and dynamic',
    },
    'american_ivy_league': {
        'camera': 'Leica M6 35mm, Kodak Ektar 100 film look, rich but natural colors',
        'angle': 'eye-level candid, wholesome collegiate full-body',
        'light': 'crisp warm morning light, gentle golden campus glow, soft shadow',
        'pose': 'walking across university quad with books in one hand, looking at watch, purposeful stride, slight smile',
        'scene': 'university campus, ivy-covered brick buildings, oak trees, morning crisp light, students in background blurred',
        'vibe': 'timeless academic elegance, quiet privilege, effortless polish',
    },
    'american_workwear': {
        'camera': 'Fujifilm X-T5 35mm, desaturated warm tones',
        'angle': 'slightly low sturdy angle, rugged full-body, texture forward',
        'light': 'warm late-afternoon side light, honest workshop glow, defined shadow',
        'pose': 'crouching to inspect workbench, or wiping hands on a rag, rugged functional movement',
        'scene': 'industrial loft space or workshop, exposed brick, raw wood textures, late afternoon side light',
        'vibe': 'rugged authenticity, functional strength, blue-collar heritage elevated',
    },
    'athleisure_sport': {
        'camera': 'Sony A7IV 70-200mm f/2.8, fast action capable',
        'angle': 'slightly low dynamic action angle, athletic full-body in motion',
        'light': 'bright morning sport light, energetic clean highlights, crisp contrast',
        'pose': 'mid-stride running or serving a tennis ball, athletic dynamic motion, muscles engaged, slight sweat glow',
        'scene': 'outdoor tennis court with blue surface, or running track with morning light, or basketball court',
        'vibe': 'peak performance energy, athletic grace, sport-meets-style',
    },
    'british_heritage': {
        'camera': 'Leica M6 50mm, moody desaturated rendering, English overcast',
        'angle': 'eye-level, refined full-body, moody overcast framing',
        'light': 'soft grey overcast English light, muted diffused glow, gentle shadow',
        'pose': 'adjusting coat collar against light drizzle, looking back over shoulder, windswept hair',
        'scene': 'London mews lane, cobblestones, brick archways, grey overcast sky, classic black cab in distance',
        'vibe': 'understated British elegance, weather-beaten charm, heritage with an edge',
    },
    'smart_casual': {
        'camera': 'Sony A7IV 50mm f/1.4, clean corporate rendering',
        'angle': 'eye-level, sharp professional full-body framing',
        'light': 'clean cool morning office light, crisp even illumination, soft shadow',
        'pose': 'checking wristwatch while walking through modern lobby, focused but relaxed expression, purposeful stride',
        'scene': 'modern glass office building lobby, polished concrete and steel, morning rush hour energy, blurred professionals in background',
        'vibe': 'urban professional energy, polished but approachable, modern gentleman',
    },
    'scandi_minimalism': {
        'camera': 'Sony A7IV 35mm f/2.8, neutral color profile, crisp',
        'angle': 'eye-level, calm architectural framing, muted negative space',
        'light': 'soft overcast Nordic light, gentle diffused glow, minimal shadow',
        'pose': 'sitting on a simple wooden bench, looking out of frame contemplatively, hands resting lightly on lap',
        'scene': 'Copenhagen waterfront, clean lines, muted earth tones, overcast soft light, bicycle leaning nearby',
        'vibe': 'quiet contemplation, less-but-better philosophy, effortless restraint',
    },
    'scene_blokecore': {
        'camera': 'Fujifilm X-T5 23mm, vibrant color, documentary style',
        'angle': 'slightly low documentary angle, energetic match-day framing',
        'light': 'flat overcast English daylight, punchy documentary color, muted shadow',
        'pose': 'walking toward stadium entrance, mid-laugh with friends (out of frame), match-day energy',
        'scene': 'football stadium exterior on match day, crowd in team colors, overcast English sky, brick stadium facade',
        'vibe': 'terrace culture energy, authentic fan spirit, football-meets-fashion',
    },
    'retro_90s_hiphop': {
        'camera': 'Contax T2 38mm, 35mm film grain, 90s snapshot aesthetic',
        'angle': 'slightly low hero angle, 90s snapshot full-body',
        'light': 'warm golden-hour light, nostalgic film glow, punchy contrast',
        'pose': 'mid-dance move or adjusting baseball cap low over eyes, relaxed swagger, one shoulder dropped',
        'scene': 'Brooklyn basketball court, chain-link fence, boombox nearby, golden hour warm tones',
        'vibe': 'golden era energy, authentic hip-hop culture, street legend casual',
    },
    'chinese_heritage': {
        'camera': 'Fujifilm X-T5 35mm, muted warm tones, cultural documentary',
        'angle': 'eye-level, elegant full-body, cultural-scene framing',
        'light': 'soft morning-mist light, muted warm glow, gentle garden shadow',
        'pose': 'walking slowly along a moon gate corridor, one hand brushing bamboo leaves, pausing by koi pond with quiet contemplation',
        'scene': 'Suzhou classical garden, white walls with grey tile roofs, bamboo shadows, morning mist',
        'vibe': 'cultural depth and quiet confidence, heritage reimagined for modern life',
    },
    'resort_vacation': {
        'camera': 'Fujifilm X-T5 23mm, bright and airy, vacation snapshot',
        'angle': 'eye-level breezy full-body, airy vacation framing',
        'light': 'warm tropical golden light, soft sea-glare, bright airy backlight',
        'pose': 'walking barefoot on beach edge, looking at horizon, slight laugh caught by sea breeze, arms relaxed',
        'scene': 'tropical beach at golden hour, gentle waves, palm tree silhouettes, or infinity pool overlooking ocean',
        'vibe': 'complete relaxation, nothing-to-do-today, sun-kissed and carefree',
    },
    'contemporary_gorpcore': {
        'camera': 'Sony A7IV 24-70mm f/2.8, outdoor adventure crisp',
        'angle': 'slightly low dynamic angle, technical layering shown',
        'light': 'crisp cool mountain-morning light, fog diffusion, sharp gear detail',
        'pose': 'checking map on phone while hiking, or adjusting technical jacket hood, functional movement in nature',
        'scene': 'mountain trail with city skyline visible in far distance, morning fog rolling in, technical outdoor gear visible',
        'vibe': 'urban-to-wilderness, functional tech meets nature, adventure-ready confidence',
    },
    # ═══ 男性风格摄影指导补全 (2026-07-07, 覆盖新增50风格库, 每种忠实还原对应服装风格) ═══
    'american_preppy': {
        'camera': 'Leica M6 35mm, Kodak Ektar 100 film look, rich preppy colors, timeless clarity',
        'angle': 'eye-level candid, wholesome collegiate full-body',
        'light': 'crisp warm autumn-morning light, gentle golden campus glow',
        'pose': 'walking across the quad with a Shetland sweater knotted over shoulders, hand in chino pocket, genuine easy grin',
        'scene': 'Ivy League campus, brick buildings with climbing ivy, sailboat-flag banners, oak trees, crisp New England autumn',
        'vibe': 'inherited-privilege polish, wholesome collegiate charm, Nantucket-red-and-navy classicism',
    },
    'american_streetwear': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, punchy street film grade, gritty contrast',
        'angle': 'slightly low hero angle, confident streetwear full-body',
        'light': 'hard urban daylight, strong contrast, concrete-bounced light',
        'pose': 'posted against a subway-tiled wall, arms crossed, cap low, unbothered confident stare down the lens',
        'scene': 'NYC downtown block, bodega awnings, subway grates, graffiti tags, yellow-cab blur, gritty concrete',
        'vibe': 'OG street authenticity, hip-hop-rooted confidence, unapologetic city edge',
    },
    'american_western': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, warm dusty Western film grade, golden desert tones',
        'angle': 'slightly low confident angle, denim-and-boots full-body',
        'light': 'warm golden-hour desert sun, long shadows, dusty backlight',
        'pose': 'leaning on a wooden ranch fence, thumbs in belt near a silver buckle, hat tilted, squinting into the sun',
        'scene': 'dusty ranch at golden hour, weathered wooden fence, distant mesa, dry brush, warm amber sky',
        'vibe': 'rugged frontier spirit, denim-and-leather authenticity, sun-worn cowboy cool',
    },
    'australian_surf_casual': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, bright airy beach film grade, sun-soaked colors',
        'angle': 'eye-level relaxed full-body, breezy coastal framing',
        'light': 'bright warm coastal sun, sea-glare highlights, airy backlight',
        'pose': 'walking barefoot up the beach with a boardshort-and-linen look, hand running through salt-tousled hair, easy laid-back grin',
        'scene': 'Australian surf beach, pale sand, rolling waves, dune grass, surfboards leaning nearby, bright blue sky',
        'vibe': 'sun-kissed surf ease, salt-air laid-back cool, no-worries coastal freedom',
    },
    'british_mod': {
        'camera': 'Leica M6 50mm, 1960s Kodachrome film look, crisp saturated retro tones',
        'angle': 'eye-level sharp full-body, tailored mod silhouette emphasized',
        'light': 'crisp overcast London daylight, clean even light, sharp detail',
        'pose': 'standing beside a vintage Vespa, slim suit sharp, one hand adjusting a pointed-collar shirt cuff, cool composed look',
        'scene': 'swinging-sixties London street, Carnaby-style storefronts, vintage scooter, Union-Jack accents, grey-bright sky',
        'vibe': 'sharp mod precision, 60s-scooter-culture cool, tailored subcultural confidence',
    },
    'british_punk': {
        'camera': 'Leica M6 35mm, high-contrast gritty black-and-white film look, raw grain',
        'angle': 'slightly low confrontational angle, raw defiant framing',
        'light': 'hard raw flash-and-shadow light, gritty high contrast, underground grit',
        'pose': 'sneering against a flyer-covered wall, thumbs hooked in ripped tartan, chin up in confrontational defiance',
        'scene': 'grimy Camden alley, torn band posters, safety-pinned graffiti, chain-link, dim underground-club grit',
        'vibe': 'anti-fashion rebellion, safety-pin-and-tartan defiance, raw DIY confrontation',
    },
    'british_savile_row': {
        'camera': 'Leica M6 50mm, Kodak Ektar 100 film look, refined restrained tones, timeless rendering',
        'angle': 'eye-level dignified full-body, bespoke tailoring silhouette emphasized',
        'light': 'soft directional light through tall windows, refined warm glow, gentle shadow',
        'pose': 'standing in a tailoring atelier, one hand adjusting a bespoke jacket button, impeccable posture, quietly assured gaze',
        'scene': 'Savile Row tailoring house, wood-panelled fitting room, bolts of cloth, brass tape measures, refined heritage interior',
        'vibe': 'bespoke perfection, generational tailoring authority, quiet aristocratic precision',
    },
    'chinese_heritage_luxe': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, refined cinematic rendering, deep restrained grade',
        'angle': 'eye-level elegant three-quarter, textural detail emphasized',
        'light': 'soft moody light with warm accents, deep shadow, ink-wash atmosphere',
        'pose': 'seated at a dark-wood tea table, hand resting near a jade pendant, composed contemplative gaze, quiet cultural poise',
        'scene': 'modern oriental interior, dark wood and ink-grey tones, single ceramic tea set, calligraphy scroll, dim warm light',
        'vibe': 'understated cultural depth, new-oriental restraint, scholarly quiet confidence',
    },
    'chinese_new_traditional': {
        'camera': 'Sony A7IV 50mm f/1.4, crisp modern rendering with subtle warm grade',
        'angle': 'eye-level elegant angle, mandarin-collar and frog-button detail shown',
        'light': 'soft daylight through lattice screens, gentle even glow, warm accents',
        'pose': 'standing in a courtyard doorway, hand adjusting a stand-collar jacket, serene upright posture, quiet knowing look',
        'scene': 'contemporary Chinese courtyard, grey brick and red lattice, bamboo shadow, stone threshold, soft morning light',
        'vibe': 'new-Chinese cultural pride, tradition recoded for modern life, rooted elegant confidence',
    },
    'contemporary_genderless': {
        'camera': 'Sony A7IV 50mm f/1.4, clean neutral rendering, soft muted grade',
        'angle': 'eye-level, clean centered framing, silhouette-forward composition',
        'light': 'soft even studio-daylight, neutral shadow, calm illumination',
        'pose': 'standing relaxed in a fluid oversized silhouette, hands loose at sides, calm neutral gaze, unposed ease',
        'scene': 'minimalist concrete-and-white gallery space, soft diffused light, single sculptural bench, uncluttered negative space',
        'vibe': 'genderless fluidity, silhouette-over-labels calm, quiet contemporary neutrality',
    },
    'french_parisian_chic': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, soft warm Parisian tones, refined grain',
        'angle': 'eye-level candid three-quarter, effortless full-body',
        'light': 'soft golden-hour side light, warm Parisian glow, gentle diffusion',
        'pose': 'walking a Left-Bank street with a coat draped over shoulders, hand in trouser pocket, casual unstudied glance aside',
        'scene': 'Parisian boulevard, Haussmann facades, café terrace, iron balconies, plane trees, soft golden afternoon',
        'vibe': 'effortless Parisian refinement, undone-yet-considered chic, five-year-wardrobe timelessness',
    },
    'italian_sprezzatura': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, warm Italian tailoring tones',
        'angle': 'eye-level elegant three-quarter, soft-shoulder tailoring emphasized',
        'light': 'warm Mediterranean afternoon light, golden accents, soft shadow',
        'pose': 'leaning on a sunlit stone balustrade, one hand casually in trouser pocket, jacket slightly open, relaxed knowing smile',
        'scene': 'Florentine terrace, ochre palazzo walls, terracotta rooftops, potted lemon trees, warm Tuscan light',
        'vibe': 'studied nonchalance, Neapolitan soft-tailoring ease, the art of looking effortless',
    },
    'italian_pitti_uomo': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, sharp editorial rendering, rich sartorial grade',
        'angle': 'slightly low hero angle, full sartorial silhouette emphasized',
        'light': 'bright warm Florentine daylight, crisp highlights, editorial clarity',
        'pose': 'mid-stride across a cobblestone piazza, double-breasted jacket flowing, adjusting a pocket square, peacock-confident stride',
        'scene': 'Fortezza da Basso exterior at Pitti Uomo, ochre fortress walls, street-style crowd blurred behind, bright Florentine sun',
        'vibe': 'peacock sartorial theatre, global menswear stage confidence, dressed-to-be-photographed flair',
    },
    'japanese_techwear': {
        'camera': 'Sony A7IV 35mm f/1.4, cool technical rendering, muted urban grade, sharp clarity',
        'angle': 'slightly low angle, layered technical silhouette emphasized',
        'light': 'cool overcast city light, subtle rim light on technical fabric, sharp detail',
        'pose': 'standing under a concrete overpass adjusting a hidden jacket zip, composed alert stance, quiet functional confidence',
        'scene': 'rain-slicked Tokyo underpass, wet concrete, muted signage glow, steam vents, cool urban-night ambience',
        'vibe': 'quiet-black functional stealth, function-hidden-as-form restraint, Tokyo urban-tech calm',
    },
    'japanese_urahara': {
        'camera': 'Contax T2 38mm, 90s Ura-Hara street-snap film grain, warm faded tones',
        'angle': 'candid tilted street-snap angle, layered fit shown',
        'light': 'warm afternoon backstreet light, faded film glow, soft contrast',
        'pose': 'caught mid-stride in a Harajuku backstreet, hands in cargo pockets, glancing back over shoulder, effortless street cool',
        'scene': 'Ura-Harajuku backstreet, boutique shutters, vintage flyers, vending machines, narrow lane, faded afternoon light',
        'vibe': 'Ura-Hara street-culture cred, 90s Tokyo subcultural cool, curated-yet-casual layering',
    },
    'japanese_wabi_sabi': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, Classic Chrome film simulation, muted earthy tones, soft grain',
        'angle': 'eye-level, calm minimalist framing, textural detail forward',
        'light': 'soft diffused north light, gentle shadow, quiet natural glow',
        'pose': 'standing quietly by a paper-screen window, hands resting loosely, subtle downward gaze, meditative stillness',
        'scene': 'minimalist Japanese interior, tatami and raw plaster walls, single ikebana, weathered wood, soft filtered light',
        'vibe': 'wabi-sabi imperfect serenity, muted earthy restraint, meditative textural calm',
    },
    'korean_clean_fit': {
        'camera': 'Sony A7IV 50mm f/1.4, soft clean Korean-editorial rendering, warm-neutral grade',
        'angle': 'eye-level, full-body showing top-heavy layered proportion',
        'light': 'soft even daylight, warm creamy tones, gentle highlights',
        'pose': 'walking a quiet cafe street, hand adjusting an oversized sweater sleeve, relaxed youthful half-smile, easy gait',
        'scene': 'Seoul cafe district, minimal concrete-and-wood storefronts, potted plants, soft morning light, clean pavement',
        'vibe': 'Korean clean-fit softness, top-wide-bottom-slim proportion, youthful milky-toned ease',
    },
    'korean_kpop_street': {
        'camera': 'Sony A7IV 35mm f/1.4, punchy idol-editorial rendering, vivid saturated grade',
        'angle': 'slightly low hero angle, dynamic street full-body',
        'light': 'bright mixed street light, punchy contrast, cool trendy glow',
        'pose': 'striding off a crosswalk with layered street fit, adjusting a cap, confident idol-off-duty energy, sharp glance to camera',
        'scene': 'trendy Seoul street, neon-lit storefronts, glass facades, blurred crowd, energetic urban atmosphere',
        'vibe': 'K-pop idol-off-duty cool, layered street trend confidence, camera-ready charisma',
    },
    'poetcore': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, soft muted romantic tones, gentle grain',
        'angle': 'eye-level soft three-quarter, contemplative framing',
        'light': 'soft window light, gentle melancholic glow, quiet shadow',
        'pose': 'seated by a rain-streaked window with a book, chin resting on hand, distant pensive gaze, loose flowing shirt',
        'scene': 'worn study interior, floor-to-ceiling books, rain-streaked window, dim lamp, faded persian rug, melancholic quiet',
        'vibe': 'poetic wistful romance, ink-and-paper introspection, tender literary melancholy',
    },
    'quarter_zip_revival': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, clean warm rendering, soft intellectual grade',
        'angle': 'eye-level, relaxed collegiate full-body',
        'light': 'soft warm afternoon light, gentle even glow, mild shadow',
        'pose': 'walking out of a library adjusting a quarter-zip collar, tote bag on shoulder, thoughtful composed half-smile',
        'scene': 'university library steps, stone columns, autumn leaves, book carts, warm scholarly afternoon light',
        'vibe': 'intellectual quarter-zip revival, Gen-Z-recoded academia, understated smart-guy ease',
    },
    'regency_romantic': {
        'camera': 'Sony A7IV 85mm f/1.4, painterly romantic rendering, deep velvet-jewel grade',
        'angle': 'slightly low dramatic angle, high-collar-and-cravat silhouette emphasized',
        'light': 'soft candle-warm light, deep romantic shadow, gilded highlights',
        'pose': 'standing by a grand fireplace adjusting a cravat, one hand on a velvet lapel, poised aristocratic gaze',
        'scene': 'Regency-era drawing room, ornate fireplace, gilded mirror, velvet drapes, candlelight, dark polished wood',
        'vibe': 'Regency romantic drama, cravat-and-velvet poetry, aristocratic 19th-century recoded',
    },
    'retro_grunge': {
        'camera': 'Contax T2 38mm, faded 90s film grain, washed desaturated tones',
        'angle': 'slightly low candid angle, grungy layered framing',
        'light': 'flat overcast daylight, moody grey wash, muted shadow',
        'pose': 'slouching against a garage door, flannel open over a band tee, hands in ripped-jeans pockets, disaffected stare aside',
        'scene': 'Seattle-grunge alley, damp concrete, faded band posters, rusted dumpster, overcast Pacific-Northwest grey',
        'vibe': '90s grunge disaffection, flannel-and-boots authenticity, washed-out slacker cool',
    },
    'retro_rockabilly': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, saturated 50s film grade, punchy retro contrast',
        'angle': 'slightly low confident angle, cuffed-denim-and-leather silhouette',
        'light': 'warm neon-and-sun mixed light, punchy retro contrast, chrome glare',
        'pose': 'leaning on a classic car with rolled-up sleeves, hand smoothing back pomade hair, cocky vintage grin',
        'scene': 'retro American diner and classic car, chrome and neon, checkerboard floor, jukebox glow, warm 50s dusk',
        'vibe': 'rockabilly greaser cool, 50s-Americana rebellion, pomade-and-chrome vintage swagger',
    },
    'rugged_comfort': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, warm honest film grade, natural earthy tones',
        'angle': 'eye-level, relaxed sturdy full-body, texture forward',
        'light': 'warm natural daylight, soft honest glow, gentle shadow',
        'pose': 'standing by a woodpile in a chore jacket, hands in denim pockets, relaxed grounded stance, easy calm look',
        'scene': 'rustic cabin porch, weathered timber, flannel and canvas textures, autumn woods behind, warm natural light',
        'vibe': 'rugged everyday comfort, honest workwear ease, grounded outdoorsy calm',
    },
    'rugged_luxury': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, rich warm safari tones, refined grain',
        'angle': 'slightly low confident angle, safari-tailoring silhouette emphasized',
        'light': 'warm golden expedition light, refined glow, sculpted shadow',
        'pose': 'standing on a lodge terrace in a safari jacket, hand resting on a leather bag strap, poised adventurer confidence',
        'scene': 'luxury safari lodge terrace, warm timber and leather, savanna vista beyond, brass details, golden expedition light',
        'vibe': 'refined explorer luxury, safari-craft-meets-couture, polished adventurer confidence',
    },
    'scene_cocktail': {
        'camera': 'Sony A7IV 85mm f/1.4, cinematic evening rendering, deep moody grade',
        'angle': 'eye-level elegant full-body, sharp evening tailoring emphasized',
        'light': 'warm low-key cocktail-bar light, golden accents, dramatic soft shadow',
        'pose': 'standing at a bar holding a coupe glass (allowed prop), jacket sharp, relaxed sophisticated lean, charismatic evening look',
        'scene': 'upscale cocktail lounge, warm amber lighting, brass and velvet, backlit bottle shelf, intimate evening ambience',
        'vibe': 'evening-cocktail sophistication, dressed-to-impress charisma, golden-hour bar elegance',
    },
    'scene_tenniscore': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, crisp clean film grade, bright whites',
        'angle': 'eye-level, sporty-preppy full-body',
        'light': 'bright clean daylight, fresh high-key light, crisp shadow',
        'pose': 'walking off the court with a sweater over shoulders, racket in hand (allowed prop), bright wholesome smile',
        'scene': 'grass tennis club, white net and umpire chair, manicured green court, clubhouse hedges, bright morning',
        'vibe': 'tenniscore polish, country-club athletic elegance, wholesome crisp-white freshness',
    },
    'torpedo_sneakers': {
        'camera': 'Sony A7IV 35mm f/1.4, clean contemporary rendering, crisp natural grade',
        'angle': 'slightly low angle emphasizing sleek footwear, dynamic full-body',
        'light': 'bright clean urban light, crisp even illumination, sharp detail',
        'pose': 'mid-stride on a clean city street, glancing down at sleek low-profile sneakers, relaxed contemporary energy',
        'scene': 'modern minimalist city street, clean pavement, glass storefronts, muted concrete, bright even daylight',
        'vibe': 'sleek retro-runner revival, low-profile footwear statement, contemporary lightweight cool',
    },
    'detention_core': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, moody warm film grade, faded academic tones',
        'angle': 'slightly low candid angle, loosened-uniform silhouette',
        'light': 'warm late-afternoon classroom light, soft shadow, nostalgic glow',
        'pose': 'slouching on a classroom desk edge, tie loosened, sleeves pushed up, rebellious half-smirk aside',
        'scene': 'empty old classroom at dusk, wooden desks, chalkboard, warm slanting window light, faded academic atmosphere',
        'vibe': 'rebellious-senior charm, loosened-uniform defiance, nostalgic bad-boy academia',
    },
    'aesthetic_avant_garde': {
        'camera': 'Sony A7IV 50mm f/1.4, stark editorial rendering, high-contrast monochrome-leaning grade',
        'angle': 'straight-on dramatic angle, sculptural silhouette emphasized',
        'light': 'hard directional gallery light, deep sculpted shadow, dramatic contrast',
        'pose': 'standing in a stark pose within an art space, one arm creating an angular line, intense conceptual gaze',
        'scene': 'raw concrete art gallery, single dramatic light, sculptural installation, vast negative space, austere atmosphere',
        'vibe': 'avant-garde artistic statement, wearable-conceptual-art intensity, boundary-pushing austerity',
    },
    'aesthetic_deconstructed': {
        'camera': 'Sony A7IV 50mm f/1.4, muted editorial rendering, desaturated raw grade',
        'angle': 'slightly off-kilter angle, asymmetric layered silhouette emphasized',
        'light': 'flat diffused studio light, subtle shadow, raw unpolished mood',
        'pose': 'standing with weight off-center, exposed-seam garment draping asymmetrically, detached conceptual gaze',
        'scene': 'raw unfinished loft, exposed pipes and concrete, muslin drapes, industrial grit, flat grey light',
        'vibe': 'deconstructed anti-polish, exposed-seam intellectualism, Margiela-adjacent raw concept',
    },
    'whimsymaxxing': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, vibrant playful film grade, punchy joyful colors',
        'angle': 'eye-level lively full-body, accessory detail forward',
        'light': 'bright cheerful daylight, punchy saturated light, playful highlights',
        'pose': 'mid-laugh adjusting a colorful brooch on the lapel, mismatched socks flashing, joyful expressive gesture',
        'scene': 'colorful eclectic street, vintage shop windows, painted murals, flea-market stalls, bright joyful afternoon',
        'vibe': 'maximalist whimsical joy, more-is-more playfulness, anti-quiet-luxury exuberance',
    },
    # ═══ 女性风格摄影指导 (2026-06-26, 基于 nan 身形筛选的 core 风格) ═══
    'WF-01': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, soft warm tones, slight grain',
        'angle': 'eye-level candid three-quarter, effortless full-body framing',
        'light': 'soft golden-hour side light, warm Parisian glow, gentle diffusion',
        'pose': 'walking along Seine-side cobblestone path, tucking hair behind ear, caught mid-laugh looking back over shoulder, breeze in hair',
        'scene': 'Parisian café terrace at golden hour, wicker chairs, marble tabletop with espresso cup, plane tree shadows, soft breeze lifting hair',
        'vibe': 'effortlessly chic, undone perfection, the woman who never tries but always looks right',
    },
    'WF-04': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, crisp modern rendering with subtle warm grade',
        'angle': 'eye-level elegant three-quarter, mandarin-collar detail emphasized',
        'light': 'soft warm light filtered through rice-paper screens, gentle even glow',
        'pose': 'standing in elegant contrapposto, one hand lightly touching a carved wooden screen, head turned slightly to reveal mandarin collar detail, serene knowing smile',
        'scene': 'contemporary tea house interior, warm wood and soft cream tones, ink calligraphy scroll on wall, afternoon light filtered through rice paper screens',
        'vibe': 'cultural pride meets modern femininity, quiet elegance, rooted confidence',
    },
    'WF-06': {
        'camera': 'Sony A7IV 50mm f/1.4, clinically sharp, minimal color grade, clean rendering',
        'angle': 'eye-level, minimalist centered framing, generous negative space',
        'light': 'crisp even morning light, clean soft shadow, gallery-bright clarity',
        'pose': 'leaning against a white gallery wall, hands relaxed at sides, weight shifted to one leg creating subtle S-curve, direct calm gaze',
        'scene': 'minimalist loft with floor-to-ceiling windows, polished concrete floors, single sculptural piece, morning crisp light casting clean shadows',
        'vibe': 'architectural precision, less-is-more confidence, the power of restraint',
    },
    'WF-07': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, warm natural rendering, slight film simulation',
        'angle': 'eye-level candid, wholesome full-body framing',
        'light': 'crisp warm autumn-morning light, gentle golden glow, soft shadow',
        'pose': 'walking across university quad with books tucked under one arm, genuine smile caught mid-conversation with unseen friend, breeze in hair',
        'scene': 'Ivy League campus courtyard, brick buildings with climbing ivy, oak trees, students on blankets in distance, crisp autumn morning',
        'vibe': 'polished academia, wholesome confidence, classic charm never goes out of style',
    },
    'WF-08': {
        'camera': 'Sony A7IV 24-70mm f/2.8, fast action capable, vibrant natural colors',
        'angle': 'slightly low dynamic angle, athletic full-body in motion',
        'light': 'golden sunrise light through trees, warm energetic glow, crisp highlights',
        'pose': 'stretching quadriceps post-run, one hand on hip, slight sweat glow on skin, athletic grace in motion, looking towards running path ahead',
        'scene': 'urban park running track at sunrise, golden morning light through trees, modern skyline in soft focus background',
        'vibe': 'athletic energy meets feminine grace, strong but soft, peak wellness aesthetic',
    },
    'WF-10': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, digicam flash aesthetic, slight overexposure, early 2000s point-and-shoot vibe',
        'angle': 'candid slightly-high snapshot angle, playful framing',
        'light': 'direct on-camera flash, bright overexposed highlights, early-2000s mall lighting',
        'pose': 'sitting on mall bench, knees together feet apart, one hand resting on knee, looking up at camera with playful smirk, low-rise jeans visible',
        'scene': 'vintage shopping mall atrium, neon accents, glass elevator in background, late afternoon mall lighting',
        'vibe': 'nostalgic rebellion, playful self-awareness, the fun of dressing up without taking it seriously',
    },
    'WF-11': {
        'camera': 'Sony A7IV 35mm f/1.4, clean urban rendering, natural light capture',
        'angle': 'eye-level, purposeful full-body, clean urban framing',
        'light': 'bright morning city light, clean even illumination, crisp shadow',
        'pose': 'crossing modern plaza mid-stride, checking phone with slight smile, purposeful urban energy',
        'scene': 'downtown business district plaza, glass and steel architecture, morning rush hour, blurred professionals passing by, clean urban lines',
        'vibe': 'modern professional woman, capable and stylish, owns her city',
    },
    'WF-18': {
        'camera': 'Leica M6 50mm, Kodak Ektar 100 film look, rich but restrained colors, timeless rendering',
        'angle': 'eye-level elegant angle, regal full-body framing',
        'light': 'soft late-afternoon golden light, refined warm glow, gentle shadow',
        'pose': 'descending stone staircase of a manor house, one hand lightly touching the banister, regal posture, subtle knowing smile',
        'scene': 'English country estate garden, manicured hedges, stone terrace, late afternoon golden light, tea service visible on terrace table',
        'vibe': 'generational elegance, quiet wealth, nothing to prove — the clothes speak for themselves',
    },
    'WF-29': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, 90s film stock emulation, subtle warm grain',
        'angle': 'eye-level candid, relaxed cool full-body framing',
        'light': 'warm sunset backlight, neon-accent glow, nostalgic golden haze',
        'pose': 'leaning against vintage car door, one hand in high-waist jeans pocket, the other pushing hair back, looking off-frame with relaxed cool, wind catching loose hair',
        'scene': 'retro diner parking lot at sunset, neon sign glow reflecting on car chrome, palm trees silhouetted against orange sky',
        'vibe': 'effortless cool, borrowed-from-the-boys attitude, nostalgia that feels fresh',
    },
    # ═══ 女性风格摄影指导补全 (2026-07-07, 覆盖全部50风格, 每种忠实还原对应服装风格) ═══
    'WF-02': {
        'camera': 'Sony A7IV 35mm f/1.4, bright clean Korean-editorial rendering, soft pastel grade, airy highlights',
        'angle': 'eye-level, centered composition, full-body to show oversize-top-over-short-skirt proportion',
        'light': 'soft diffused daylight, bright and even, minimal shadow, high-key freshness',
        'pose': 'mid-step on a sunny sidewalk, hands tugging oversized hoodie hem, playful hop with knees slightly bent, bright candid smile',
        'scene': 'Seongsu-dong cafe street in Seoul, pastel storefronts, cherry-blossom trees, clean pavement, soft spring morning',
        'vibe': 'sweet-and-cool Korean girl energy, youthful bounce, effortless it-girl freshness',
    },
    'WF-03': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, Classic Chrome film simulation, muted earth tones, gentle grain',
        'angle': 'slightly low three-quarter angle, layered silhouette emphasized, soft focus background',
        'light': 'dappled forest light filtering through leaves, soft overcast diffusion, no harsh shadow',
        'pose': 'walking slowly through woodland path, one hand lightly holding cardigan edge, gaze drifting softly downward, dreamy and unhurried',
        'scene': 'misty forest clearing, moss-covered logs, ferns and wildflowers, soft morning fog between tree trunks',
        'vibe': 'gentle mori-girl softness, fairytale forest dweller, unhurried natural warmth',
    },
    'WF-05': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, warm Americana film tone, natural saturation',
        'angle': 'eye-level, relaxed full-body, rule of thirds',
        'light': 'bright afternoon sun, warm natural light, gentle contrast',
        'pose': 'walking down a small-town main street, thumbs in denim pockets, easy confident stride, genuine open smile',
        'scene': 'sunlit American small-town street, red-brick storefronts, vintage pickup truck, stars-and-stripes flag, leafy sidewalk',
        'vibe': 'all-American ease, denim-and-white-tee confidence, unpretentious warmth',
    },
    'WF-09': {
        'camera': 'Leica M6 50mm, Kodak Portra 800 film look, warm golden earthy tones, organic grain',
        'angle': 'low golden-hour angle, flowing fabric captured in motion, backlit',
        'light': 'strong golden-hour backlight, sun flare through hair and fabric, warm rim light',
        'pose': 'twirling barefoot in tall grass, arms loosely raised letting maxi dress flow, hair and fringe catching the breeze, head tilted to the sky',
        'scene': 'open desert festival field at sunset, dry golden grass, distant tents and string lights, Moroccan rug on the ground',
        'vibe': 'free-spirited gypsy romance, Woodstock wanderer, sun-soaked bohemian freedom',
    },
    'WF-12': {
        'camera': 'Sony A7IV 50mm f/1.4, moody low-key rendering, desaturated cool tones, rich shadow detail',
        'angle': 'three-quarter angle, chiaroscuro framing, subject emerging from shadow',
        'light': 'single-source Rembrandt window light, deep shadows, candle-warm accents, gothic contrast',
        'pose': 'standing among towering bookshelves holding an open leather-bound book, head bowed in contemplation, one hand resting on a wooden ladder',
        'scene': 'old university library, dark oak shelves to the ceiling, brass reading lamps, dust motes in a single shaft of light, gothic arched windows',
        'vibe': 'melancholic scholarly romance, Dickensian intellectual, brooding academic elegance',
    },
    'WF-13': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, Pro Neg Std film simulation, soft pastel naturals, fine grain',
        'angle': 'eye-level, soft-focus meadow foreground, dreamy full-body',
        'light': 'soft warm morning sun through wildflowers, hazy glow, gentle backlight',
        'pose': 'strolling through a wildflower meadow, floral dress hem lifted lightly by one hand, reaching to touch tall grasses, serene contented smile',
        'scene': 'blooming countryside meadow, wildflowers and long grass, rustic wooden fence, cottage rooftop in the distance, morning dew',
        'vibe': 'romantic pastoral idyll, slow-living cottage dream, tender reconnection with nature',
    },
    'WF-14': {
        'camera': 'Sony A7IV 85mm f/1.4 GM, soft romantic rendering, powder-pink grade, delicate highlights',
        'angle': 'slightly elevated, graceful lines emphasized, soft bokeh background',
        'light': 'soft north-facing studio light, gentle wraparound softness, ballet-warm glow',
        'pose': 'standing in soft ballet fourth position, one hand extended with dancer grace, chin lifted, poised serene expression, pointed toe',
        'scene': 'ballet rehearsal studio, worn wooden floor, floor-to-ceiling mirror, barre along the wall, soft daylight through tall windows',
        'vibe': 'balletcore grace, dancer poise meets girlish softness, ethereal romantic elegance',
    },
    'WF-15': {
        'camera': 'Sony A7IV 85mm f/1.4, dreamy romantic rendering, soft macaron-pastel grade',
        'angle': 'slightly high flattering angle, delicate detail-forward framing',
        'light': 'soft diffused pink-warm light, gentle glow, feminine highlights',
        'pose': 'seated at a dessert table, chin resting on laced hands, coy knowing glance up at camera, ribbon in hair, slight teasing smile',
        'scene': 'ornate rococo-inspired parlor, pastel patisserie, porcelain teacups, silk ribbons and fresh roses, soft candlelight',
        'vibe': 'coquette sweetness with a knowing wink, 18th-century flirt reborn, saccharine-yet-clever charm',
    },
    'WF-16': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, soft-focus dreamy filter, pastel bloom, gentle overexposure',
        'angle': 'eye-level youthful full-body, centered playful framing',
        'light': 'soft glowing daylight with pink filter, hazy highlights, anime-soft diffusion',
        'pose': 'sitting on pastel steps, knees together, both hands framing face in a cute gesture, high ponytail, bright innocent smile',
        'scene': 'pastel-colored street corner, candy-toned walls, fairy lights, soft-focus cherry blossoms, dreamy filtered atmosphere',
        'vibe': 'soft-girl anime sweetness, pastel-filtered innocence, cotton-candy dreaminess',
    },
    'WF-17': {
        'camera': 'Leica Q2 28mm, natural understated rendering, muted neutral grade, expensive softness',
        'angle': 'eye-level, minimalist clean composition, generous negative space',
        'light': 'soft diffused natural light through sheer curtains, quiet even illumination',
        'pose': 'standing relaxed by a window, one hand in wide-leg trouser pocket, cashmere draping naturally, calm assured gaze, minimal movement',
        'scene': 'high-end minimalist apartment, travertine and warm wood, sculptural furniture, sheer linen curtains, soft afternoon light',
        'vibe': 'quiet luxury, wealth that whispers, the confidence of impeccable fabric and cut',
    },
    'WF-19': {
        'camera': 'Sony A7IV 50mm f/1.4, crisp clean rendering, fresh natural grade, dewy skin tones',
        'angle': 'eye-level, clean centered framing, uncluttered background',
        'light': 'bright soft daylight, fresh even glow, glowing healthy-skin highlights',
        'pose': 'walking briskly with a matcha in one hand (allowed prop), slicked-back bun, adjusting large gold hoop, confident fresh half-smile',
        'scene': 'clean modern city sidewalk outside a pilates studio, minimalist storefronts, morning light, green plants in planters',
        'vibe': 'just-washed-face polish, effortless wellness-girl glow, expensive-minimal freshness',
    },
    'WF-20': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, warm sun-bleached coastal tones',
        'angle': 'eye-level, breezy full-body, soft ocean bokeh behind',
        'light': 'warm hazy coastal afternoon light, soft sea-glare, gentle backlight',
        'pose': 'walking a sandy boardwalk, linen sleeves rolled, cardigan over shoulders, hand shading eyes gazing at the sea, relaxed serene smile',
        'scene': 'New England coastal beach house exterior, weathered shingles, dune grass, driftwood, soft-focus ocean and pale sky',
        'vibe': 'Nancy-Meyers coastal grandmother ease, linen-and-sea-air serenity, moneyed relaxed elegance',
    },
    'WF-21': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, Velvia-warm Mediterranean saturation, sun-drenched tones',
        'angle': 'eye-level, lively full-body, vibrant market backdrop',
        'light': 'strong warm Mediterranean midday sun, vivid colors, crisp shadows',
        'pose': 'strolling through an open-air market, woven basket on arm (allowed prop), skirt swishing, laughing while glancing back over shoulder',
        'scene': 'Amalfi coast market street, crates of tomatoes and lemons, terracotta buildings, bougainvillea, bright blue sky',
        'vibe': 'Mediterranean summer joy, tomato-girl vibrancy, sun-ripened romance of southern Italy',
    },
    'WF-22': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, low-contrast desaturated grade, soft-focus vintage haze',
        'angle': 'eye-level, dreamy soft-focus meadow framing',
        'light': 'diffused post-rain overcast light, muted misty softness, no harsh shadow',
        'pose': 'sitting in tall grass among faded wildflowers, knees to chest, chin resting on knees, wistful faraway gaze, soft breeze in loose hair',
        'scene': 'foggy meadow at dawn, faded wildflowers, dew-heavy grass, muted grey-green mist softening the horizon',
        'vibe': 'dusty-hued meadowcore melancholy, faded-photograph nostalgia, gentle romantic wistfulness',
    },
    'WF-23': {
        'camera': 'Fujifilm X-T5 23mm f/1.4, faded 90s Tumblr film grade, washed desaturated tones, grain',
        'angle': 'slightly low candid angle, grungy off-center framing',
        'light': 'flat overcast daylight, moody grey wash, muted shadows',
        'pose': 'slouching against a graffiti wall, hands in ripped-jeans pockets, flannel tied at waist, moody disaffected stare off-frame',
        'scene': 'urban alley with faded graffiti, cracked concrete, chain-link fence, grey overcast sky, cigarette-stained aesthetic',
        'vibe': 'soft-grunge Tumblr melancholy, washed-out 90s disaffection, faded rebellious tenderness',
    },
    'WF-24': {
        'camera': 'point-and-shoot digicam with direct on-camera flash, harsh flash falloff, cool high-contrast grain, blown highlights',
        'angle': 'candid tilted party-snapshot angle, close and immediate',
        'light': 'harsh direct flash against dark background, deep black shadows, overexposed skin, nightlife grit',
        'pose': 'caught mid-laugh at a crowded party, leaning into frame, smudged eyeliner, holding a drink loosely, chaotic candid energy',
        'scene': 'dim underground party, dark walls, blurred crowd, string of cheap lights, 5am after-party grit',
        'vibe': 'indie-sleaze chaos, Cobrasnake-flash nightlife, glamorously-wrecked party-till-dawn energy',
    },
    'WF-25': {
        'camera': 'Leica M6 50mm, high-contrast black-and-white film look, sharp monochrome tonality',
        'angle': 'straight-on editorial angle, strong architectural framing',
        'light': 'hard directional side light, dramatic monochrome contrast, sculpted shadows',
        'pose': 'striding across an urban crosswalk, leather jacket collar up, one hand adjusting large sunglasses, cool detached forward gaze',
        'scene': 'moody downtown street, concrete and steel, stark shadows, monochrome urban geometry, overcast sky',
        'vibe': 'downtown-cool creative-director aura, off-duty model nonchalance, monochrome urban edge',
    },
    'WF-26': {
        'camera': 'Sony A7IV 50mm f/1.4, dark moody grade, cool desaturated forest tones, fine grain',
        'angle': 'low three-quarter angle, mystical layered framing, deep shadow',
        'light': 'dim moonlit-forest ambience, cool blue shadow, faint dappled glow through canopy',
        'pose': 'standing barefoot among mossy roots, torn lace shawl trailing, one hand touching a tree trunk, ethereal faraway gaze, wind in tangled hair',
        'scene': 'dark enchanted forest at dusk, moss and gnarled roots, mist between black trees, faint moonlight, damp earthy floor',
        'vibe': 'fairy-grunge woodland spirit, moonlit-forest sprite, ethereal-yet-decayed dark romance',
    },
    'WF-27': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, bright sporty film grade, punchy natural colors',
        'angle': 'eye-level, dynamic full-body showing skirt-and-socks proportion',
        'light': 'bright even daylight, clean sporty freshness, gentle contrast',
        'pose': 'jogging playfully across a football pitch sideline, pleated skirt bouncing, mid-laugh glancing back, ponytail with ribbon swinging',
        'scene': 'grassy football pitch edge, white goalpost, stadium seating soft-focus behind, bright afternoon, chalk sideline',
        'vibe': 'blokette sporty-sweet fusion, terrace-culture-meets-coquette, playful athletic femininity',
    },
    'WF-28': {
        'camera': 'Sony A7IV 35mm f/1.4, gritty urban grade, punchy street-editorial contrast',
        'angle': 'slightly low hero angle, confident streetwear full-body',
        'light': 'hard urban daylight, strong contrast, concrete-bounced light',
        'pose': 'posted up against a concrete wall, arms crossed, weight on one leg, cap low, unbothered confident stare down the lens',
        'scene': 'raw urban backdrop, concrete underpass, graffiti tags, chain-link, skate-spot grit, overcast city light',
        'vibe': 'women-streetwear cool, hip-hop-and-skate confidence, unapologetic urban edge',
    },
    'WF-30': {
        'camera': 'Sony A7IV 85mm f/1.4, glamorous rich rendering, deep warm grade, luxe contrast',
        'angle': 'slightly low powerful angle, opulent full-body, dramatic framing',
        'light': 'moody warm nightclub glow, golden accents, dramatic low-key luxe light',
        'pose': 'stepping out of a black car, faux-fur coat sliding off one shoulder, large sunglasses on, chin high, unbothered powerful glance',
        'scene': 'night city street outside an exclusive venue, black luxury car, warm doorway glow, wet pavement reflections, cigarette-smoke ambience',
        'vibe': 'mob-wife opulence, dangerous glamorous power, old-school gangster-moll drama',
    },
    'WF-31': {
        'camera': 'Sony A7IV 50mm f/1.4, rich jewel-tone grade, velvet-deep shadow, cinematic contrast',
        'angle': 'low commanding angle, powerful cinched-waist silhouette emphasized',
        'light': 'dramatic single-source warm light, deep sculpted shadow, film-noir contrast',
        'pose': 'standing with commanding posture, one hand on hip pushing back a tailored blazer, sharp downward gaze, femme-fatale confidence',
        'scene': 'dim luxurious interior, dark velvet drapes, mahogany and brass, single dramatic light, jewel-toned opulence',
        'vibe': 'dark-feminine femme fatale, queen-not-princess power, seductive commanding drama',
    },
    'WF-32': {
        'camera': 'Sony A7IV 85mm f/1.4, painterly romantic rendering, soft baroque grade, luminous highlights',
        'angle': 'slightly elevated regal framing, flowing gown captured fully',
        'light': 'soft candlelit-chandelier glow, warm gilded highlights, romantic diffusion',
        'pose': 'descending a grand staircase, one gloved hand on the marble banister, gown trailing, regal poised head-turn, serene noble expression',
        'scene': 'opulent Versailles-style ballroom, gilded mouldings, crystal chandeliers, marble staircase, silk drapes, candlelight',
        'vibe': 'royalcore fairytale grandeur, Bridgerton ballroom romance, aristocratic timeless elegance',
    },
    'WF-33': {
        'camera': 'Sony A7IV 24-70mm f/2.8, crisp technical rendering, cool outdoor grade, punchy gear colors',
        'angle': 'slightly low dynamic angle, functional layering emphasized',
        'light': 'bright crisp overcast daylight, cool clean light, sharp detail',
        'pose': 'striding across an urban plaza adjusting a technical backpack strap, shell-jacket zipped, purposeful outdoor-ready gait, alert forward look',
        'scene': 'city plaza with brutalist concrete, wet pavement, glass towers, urban-meets-outdoor grit, overcast technical mood',
        'vibe': 'gorpcore urban-utility, techwear-adjacent functionality as fashion, mountain-gear-in-the-city cool',
    },
    'WF-34': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, elegant warm Parisian tones, refined grain',
        'angle': 'eye-level chic three-quarter, poised full-body',
        'light': 'soft warm interior light with golden accents, flattering Parisian glow',
        'pose': 'seated elegantly on a velvet chair, legs crossed, one hand resting on tweed lapel, refined knowing gaze, subtle red-lip smile',
        'scene': 'grand Parisian apartment, black iron staircase, cream boiserie walls, gilded mirror, deep-blue velvet sofa, tall windows',
        'vibe': 'intentional Parisian elegance, opera-bound refinement, Chanel-tweed timeless chic',
    },
    'WF-35': {
        'camera': 'Sony A7IV 85mm f/1.4, vivid Mediterranean rendering, rich saturated grade',
        'angle': 'slightly low confident angle, leg-lengthening full-body',
        'light': 'bright warm Italian sun, vivid colors, glamorous highlights',
        'pose': 'stepping off a Vespa-lined curb, printed dress swishing, one hand lowering oversized sunglasses, radiant self-assured smile',
        'scene': 'sun-drenched Italian piazza, ochre palazzo facades, café awnings, fountain, vibrant blue sky',
        'vibe': 'Italian donna confidence, glamorous I-know-I-look-good radiance, vivid Mediterranean flair',
    },
    'WF-36': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, soft Scandinavian grade, cool-neutral tones, warm-minimal balance',
        'angle': 'eye-level, clean architectural framing, calm negative space',
        'light': 'soft diffused Nordic daylight, gentle cool-warm balance, even illumination',
        'pose': 'standing calmly by a large window, hand in wide wool-trouser pocket, structured blazer draping, composed serene gaze',
        'scene': 'Copenhagen apartment, pale wood floors, sunlight and a wool throw, sculptural chair, large windows, cool-grey sky beyond',
        'vibe': 'Scandinavian warm-minimalism, architectural-yet-cozy calm, sustainable design serenity',
    },
    'WF-37': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, warm tropical vacation tones, soft glow',
        'angle': 'eye-level breezy full-body, soft resort bokeh',
        'light': 'warm tropical golden light, soft sea-glare, gentle backlight through fabric',
        'pose': 'walking along a resort terrace, wide-brim hat held to head against the breeze, linen skirt flowing, relaxed sun-soaked smile',
        'scene': 'tropical resort terrace, whitewashed walls, palm fronds, turquoise sea beyond, woven loungers, warm afternoon',
        'vibe': 'endless-vacation ease, resort-escape serenity, wear-the-holiday relaxation',
    },
    'WF-38': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, crisp clean grade, bright whites, fresh natural colors',
        'angle': 'eye-level, sporty-preppy full-body, pleated-skirt proportion shown',
        'light': 'bright clean daylight, fresh high-key light, crisp shadows',
        'pose': 'walking off a tennis court, sweater draped over shoulders, one hand adjusting it, bright wholesome smile, athletic upright posture',
        'scene': 'grass tennis club, white net and umpire chair, manicured green court, clubhouse and hedges, bright Wimbledon-morning light',
        'vibe': 'tenniscore polish, sport-meets-old-money elegance, wholesome country-club freshness',
    },
    'WF-39': {
        'camera': 'Sony A7IV 50mm f/1.4, glossy high-glam rendering, rich warm grade, luxe gold highlights',
        'angle': 'slightly low hero angle, flashy confident full-body',
        'light': 'glossy studio-glam light with warm gold accents, punchy contrast, luxe glow',
        'pose': 'posted confidently with weight on one hip, adjusting a thick gold chain, chin up, unbothered rich-and-successful stare',
        'scene': 'upscale night street with luxury car, glossy black paint, neon-and-gold signage, wet reflective asphalt, VIP-entrance glow',
        'vibe': 'hip-hop-glam success flex, made-it opulence, loud-and-proud luxury statement',
    },
    'WF-40': {
        'camera': 'Sony A7IV 85mm f/1.4, cinematic operatic rendering, deep velvet-red grade, gilded highlights',
        'angle': 'slightly low dramatic angle, sweeping cloak captured in full',
        'light': 'warm theatrical spotlight glow, deep red-and-gold shadow, dramatic operatic contrast',
        'pose': 'sweeping a floor-length velvet cloak, gloved hand raised with theatrical grace, chin lifted, intense performer gaze',
        'scene': 'grand opera house interior, red-velvet seats, gilded balconies, crystal chandelier, dark polished stage, dramatic lighting',
        'vibe': 'romantic-opera theatricality, 19th-century diva just-off-stage, velvet-and-gold dramatic grandeur',
    },
    'WF-41': {
        'camera': 'Sony A7IV 50mm f/1.4, crisp corporate-editorial rendering, cool neutral grade, sharp clarity',
        'angle': 'slightly low powerful angle, cinched-waist tailored silhouette emphasized',
        'light': 'clean directional office light, cool sculpted shadow, sharp professional contrast',
        'pose': 'standing in a glass-walled office, one hand adjusting frameless glasses, pencil skirt sharp, poised commanding gaze that means business',
        'scene': 'high-floor corporate office, floor-to-ceiling glass, steel-grey city view, minimalist desk, cool daylight, power-suite ambience',
        'vibe': 'office-siren power, the-woman-who-runs-this-floor authority, sharp seductive competence',
    },
    'WF-42': {
        'camera': 'Leica M6 50mm, high-contrast black-and-white film look, gritty monochrome grain',
        'angle': 'slightly low edgy angle, leather-and-denim silhouette',
        'light': 'hard raw side light, deep monochrome shadow, backstage-grit contrast',
        'pose': 'leaning against a brick wall backstage, thumbs in skinny-jeans pockets, leather jacket open, tousled hair, cool defiant stare',
        'scene': 'concert backstage / gritty brick alley, amp cases and cables, string of bare bulbs, monochrome rock-venue grit',
        'vibe': 'rock-chic edge, rockstar-girlfriend cool, polished-but-defiant leather attitude',
    },
    'WF-43': {
        'camera': 'Leica M6 50mm, Kodak Ektar 100 film look, refined English autumn tones, timeless grain',
        'angle': 'eye-level elegant three-quarter, poised full-body',
        'light': 'soft overcast English daylight, gentle warm-neutral glow, refined softness',
        'pose': 'walking through a manor garden, trench belted, one hand adjusting a silk scarf, pearl earrings catching light, composed gracious smile',
        'scene': 'English country estate garden, clipped hedges, stone urns, rose beds, manor house behind, soft grey-gold autumn light',
        'vibe': 'British-lady refinement, Chelsea-flower-show grace, countryside-and-afternoon-tea elegance',
    },
    'WF-44': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, Classic Neg film simulation, warm faded workwear tones, honest grain',
        'angle': 'eye-level, honest full-body showing raw-denim-and-workwear layering',
        'light': 'warm natural window light, soft honest illumination, gentle shadow',
        'pose': 'standing in a vintage workshop, thumbs hooked in raw-denim belt loops, chore jacket squared on shoulders, calm unpretentious gaze',
        'scene': 'Japanese vintage workwear store / workshop, worn wooden shelves of denim, Red Wing boots on display, warm incandescent light, patina everywhere',
        'vibe': 'amekaji craftsmanship reverence, Japanese-perfected Americana, honest workwear soul',
    },
    'WF-45': {
        'camera': 'Fujifilm X-T5 35mm f/1.4, warm dusty Western film grade, golden desert tones',
        'angle': 'slightly low confident angle, fringe-and-boots full-body',
        'light': 'warm golden-hour desert light, long shadows, dusty backlight glow',
        'pose': 'walking through a festival ground, thumbs in belt near a silver buckle, cowboy hat tilted, fringe swaying, easy confident half-smile',
        'scene': 'desert music festival at golden hour, dry earth, wooden stage in the distance, string lights, dusty warm sky',
        'vibe': 'western-babe festival cool, country-music it-girl, dusty-boots-and-fringe confidence',
    },
    'WF-46': {
        'camera': 'Sony A7IV 85mm f/1.4, iridescent dreamy rendering, pearlescent blue-green grade, luminous glow',
        'angle': 'low ethereal angle, flowing fishtail silhouette, soft aquatic bokeh',
        'light': 'shimmering aqua-toned light, pearlescent highlights, dreamy underwater-like glow',
        'pose': 'emerging from shallow surf, wet hair swept back, hand trailing through water, iridescent skirt clinging, ethereal faraway gaze',
        'scene': 'rocky sea shore at blue hour, gentle surf, wet rocks with shells, iridescent spray, soft teal-and-pearl sky',
        'vibe': 'mermaidcore fantasy, half-transformed sea-princess, iridescent oceanic dream',
    },
    'WF-47': {
        'camera': 'Sony A7IV 50mm f/1.4, warm creamy rendering, vanilla-latte grade, soft glowing neutrals',
        'angle': 'eye-level, soft cozy framing, warm negative space',
        'light': 'soft warm golden interior light, cozy diffused glow, honeyed highlights',
        'pose': 'curled on a cream sofa holding a warm latte (allowed prop), cardigan draping, hair soft, content dreamy half-smile',
        'scene': 'cozy warm-neutral apartment, cream knit throws, honey-wood shelves, a candle, soft golden lamp light, vanilla-warm atmosphere',
        'vibe': 'vanilla-girl warmth, cozy-luxe softness, latte-and-candlelight comfort',
    },
    'WF-48': {
        'camera': 'Leica M6 50mm, Kodak Portra 400 film look, rich equestrian earth tones, refined grain',
        'angle': 'eye-level elegant angle, riding-boots-and-breeches silhouette',
        'light': 'soft warm stable-side daylight, gentle golden glow, refined natural light',
        'pose': 'standing beside a wooden stable door, one hand resting on the frame, tall riding boots planted, tweed blazer sharp, poised composed gaze',
        'scene': 'English equestrian stable yard, wooden stalls, hay bales, leather tack on hooks, green paddock beyond, soft golden light',
        'vibe': 'equestrian refinement, stable-to-runway elegance, tailored-and-earthy country poise',
    },
    'WF-49': {
        'camera': 'Sony A7IV 85mm f/1.4, refined soft rendering, rich muted jewel-and-earth grade',
        'angle': 'eye-level graceful full-body, flowing modest silhouette emphasized',
        'light': 'soft diffused elegant light, gentle wraparound glow, refined even illumination',
        'pose': 'walking gracefully with an ankle-length skirt flowing, one hand lightly holding a flowing sleeve, serene dignified gaze, composed poise',
        'scene': 'elegant architectural courtyard, warm stone arches, soft textiles, latticed screens casting gentle shadow, refined serene atmosphere',
        'vibe': 'modest-chic dignity, chosen-elegance empowerment, graceful covered refinement',
    },
    'WF-50': {
        'camera': 'Sony A7IV 35mm f/1.4, hyper-clean futuristic rendering, cool chrome-and-holographic grade, high clarity',
        'angle': 'slightly low sci-fi hero angle, deconstructed silhouette emphasized',
        'light': 'cool LED-and-laser lighting, chrome reflections, holographic color spill, high-tech glow',
        'pose': 'standing in a futuristic corridor, metallic garment catching light, alien-visor sunglasses on, sharp angular pose, cool detached forward stare',
        'scene': 'neo-futuristic interior, chrome and LCD-screen walls, laser accents, holographic reflections, cool blue-violet sci-fi lighting',
        'vibe': 'Y3K future-shock, 3000-AD fashion transmission, chrome-and-hologram sci-fi cool',
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


def _get_persona_description(user_id=None):
    """从用户 profile.json 构建人物描述，替代硬编码。
    user_id=None → 单用户模式，读 config/user_profile.json
    user_id='alice' → 多用户模式，读 users/alice/profile.json
    """
    import os as _os
    profile_path = _os.path.join(CONFIG_DIR, 'user_profile.json')
    if user_id:
        up_dir = resolve_user_dir(user_id=user_id)
        up_path = _os.path.join(up_dir, 'profile.json')
        if _os.path.exists(up_path):
            profile_path = up_path

    up = load_json(profile_path)
    body = up.get('body', {}) if up else {}
    lifestyle = up.get('lifestyle', {}) if up else {}
    gender = up.get('gender', 'female') if up else '男'

    h = body.get('height_cm', '')
    w = body.get('weight_kg', '')
    age = body.get('age', '')
    bt = body.get('body_type', '') or body.get('shape', '')
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
        # 翻译女性身形
        shape_cn = {
            'pear': '梨形身材（下半身较丰满）',
            'apple': '苹果形身材（腰腹较圆润）',
            'hourglass': '沙漏形身材（肩臀同宽腰细）',
            'rectangle': '直筒形身材（肩腰臀等宽）',
            'inverted_triangle': '倒三角身材（肩宽臀窄）',
        }
        bt_display = shape_cn.get(bt, f'{bt}体型')
        parts.append(bt_display)
    if st:
        skin_cn = {'cool_white': '冷白皮', 'warm_white': '暖白皮', 'natural': '自然肤色', 'wheat': '小麦色'}
        st_display = skin_cn.get(st, f'{st}肤色')
        parts.append(st_display)
    if shoulder:
        parts.append(f'{shoulder}')

    base_desc = '一位 ' + '，'.join(parts) if parts else '一位亚洲成人'

    # 身形修饰策略
    modifier_lines = []
    if gender == 'female' or up.get('gender') == 'female':
        # 女性身形修饰策略
        female_modifiers = {
            'pear': '梨形身材：上紧下松，用A字裙/阔腿裤修饰下半身，上半身选有设计感的上衣转移视觉重心',
            'apple': '苹果形身材：V领拉长颈部，高腰线+直筒裤，避免腰部有过多装饰',
            'hourglass': '沙漏形身材：突出腰线是关键，裹身裙/高腰裤最能展示优势',
            'rectangle': '直筒形身材：用腰带/A字裙制造腰线，层次叠穿增加曲线感',
            'inverted_triangle': '倒三角身材：弱化肩部，选V领/插肩袖，下半身选A字/阔腿增加量感',
        }
        if bt in female_modifiers:
            modifier_lines.append(female_modifiers[bt])
    else:
        if bt == '偏瘦':
            modifier_lines.append('偏瘦体型优先选增加肩宽/体量感的单品')
            if h and int(h) >= 175:
                modifier_lines.append(f'身高{h}cm偏瘦，适合落肩宽松剪裁增加横向视觉')
        elif bt == '偏胖':
            modifier_lines.append('偏胖体型优先选竖向线条、深色系拉长身形')
            modifier_lines.append('避开横条纹和过于紧身的单品')
        elif bt == '肌肉型':
            modifier_lines.append('肌肉型体型可选修身剪裁展示线条，也可选宽松款走休闲路线')
    if st and st in ('白皙', '偏白', 'cool_white', 'warm_white'):
        modifier_lines.append('肤色偏白对颜色包容度高，可驾驭浅色系和亮色系')
    elif st and st in ('小麦', '偏黄', '偏黑', 'wheat'):
        modifier_lines.append('肤色偏深优先选低饱和暖色调，避免荧光色')

    # 身材秘密（用户自述）
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
    """根据目标风格返回摄影指导参数。

    style_id 归一化：全系统事实主键是短 ID（clean_fit / WF-01）。
    容错：若传入长格式（WF-01_french_effortless）自动取 WF-XX 前缀再查，
    确保历史调用方或未来目录名格式都能命中。
    """
    def _lookup(sid):
        if sid in STYLE_PHOTO_MAP:
            return STYLE_PHOTO_MAP[sid]
        # 长格式 WF-01_xxx → 归一化为短 ID WF-01
        if sid.startswith('WF-') and '_' in sid:
            short = sid.split('_')[0]
            if short in STYLE_PHOTO_MAP:
                return STYLE_PHOTO_MAP[short]
        return None

    directions = []
    for sid in style_ids:
        d = _lookup(sid)
        if d:
            directions.append(d)
    if not directions:
        directions = [DEFAULT_PHOTO_DIRECTION]
    # 取第一个匹配的风格作为主方向
    d = directions[0]
    return (
        f"📷 摄影指导（HARD LOCK — seedream_prompt 必须忠实还原，不可替换）：\n"
        f"  相机: {d.get('camera', 'Sony A7IV 50mm f/1.4')}\n"
        f"  构图: {d.get('angle', 'low angle, rule of thirds')}\n"
        f"  光影: {d.get('light', 'golden hour backlight, warm rim light')}\n"
        f"  姿势: {d.get('pose', 'walking mid-stride, natural movement')}\n"
        f"  场景: {d.get('scene', 'modern urban street, soft afternoon light')}\n"
        f"  情绪: {d.get('vibe', 'editorial fashion photography, candid energy')}\n"
        f"  表情: natural relaxed expression, slight smile or soft neutral, not stiff editorial blank stare\n"
        f"  🔒 场景是硬性设定：seedream_prompt 的拍摄地点/环境必须就是上面『场景』描述的地方，"
        f"严禁替换成其他城市/街道（如北京街道、都市天际线等）——上文的天气仅用于决定穿什么，不是拍摄地点。\n"
        f"  🔒 相机/胶片/光影/构图同样是硬性设定：必须原样体现（如指定 Kodak Portra 胶片就要写进去），只能润色英文措辞，不能改换器材或风格。\n"
        f"  ⚠️ 姿势必须动态（禁止 standing），忠实使用上面『姿势』描述的动作。\n"
        f"  🚫 姿势/场景中若出现任何服饰配饰（包/墨镜/帽子/首饰等），一律不得画入——只呈现单品清单里的真实单品。"
    )


# ── 女性美妆方向映射（按集群）──
_BEAUTY_DIRECTION_CACHE = None


def _load_beauty_directions():
    """延迟加载美妆映射"""
    global _BEAUTY_DIRECTION_CACHE
    if _BEAUTY_DIRECTION_CACHE is None:
        bp = os.path.join(PROJ_DIR, 'config', 'beauty_direction_female.json')
        if os.path.exists(bp):
            _BEAUTY_DIRECTION_CACHE = load_json(bp).get('clusters', {})
        else:
            _BEAUTY_DIRECTION_CACHE = {}
    return _BEAUTY_DIRECTION_CACHE


def _resolve_beauty_cluster(style_id):
    """根据 style_id 解析所属美学集群。从 categories.json 查找。"""
    cp = os.path.join(PROJ_DIR, 'styles/female', 'categories.json')
    if not os.path.exists(cp):
        return None
    try:
        cats = load_json(cp)
        for cname, cinfo in cats.get('clusters', {}).items():
            if style_id in cinfo.get('styles', []):
                return cname
    except Exception:
        pass
    return None


def get_beauty_direction(style_ids, user_hair=None):
    """根据目标风格 + 用户发型档案，返回美妆指引（用于 seedream_prompt 增强）。
    user_hair: {'length': 'long', 'color': 'black', 'texture': 'straight'} 或 None

    Returns:
        beauty_context (str): 注入到 system prompt 的美妆指导文本
        beauty_en (str): 简短英文美妆描述，直接融入 seedream prompt
    """
    clusters = _load_beauty_directions()
    if not clusters:
        return '', ''

    # 找到主风格对应的集群
    matched_cluster = None
    for sid in style_ids:
        cname = _resolve_beauty_cluster(sid)
        if cname and cname in clusters:
            matched_cluster = clusters[cname]
            break

    if not matched_cluster:
        return '', ''

    hair_en = matched_cluster['hair']['en']
    hair_cn = matched_cluster['hair']['cn']
    makeup_en = matched_cluster['makeup']['en']
    makeup_cn = matched_cluster['makeup']['cn']
    vibe = matched_cluster.get('vibe', '')

    # ── 用户发型档案覆盖默认值 ──
    hair_overrides = []
    if user_hair:
        length_map = {'short': 'short hair', 'medium': 'medium-length hair', 'long': 'long hair'}
        color_map = {'black': 'black hair', 'brown': 'brown hair', 'blonde': 'blonde hair',
                     'red': 'red hair', 'gray': 'gray/silver hair'}
        texture_map = {'straight': 'straight texture', 'wavy': 'wavy/curly texture', 'curly': 'curly voluminous texture'}

        hl = length_map.get(user_hair.get('length', ''), '')
        hc = color_map.get(user_hair.get('color', ''), '')
        ht = texture_map.get(user_hair.get('texture', ''), '')

        if hl:
            hair_overrides.append(f'  用户发长: {hl} → 保持真实长度，在此基础上做造型')
        if hc:
            hair_overrides.append(f'  用户发色: {hc} → 不改变发色，保持自然')
        if ht:
            hair_overrides.append(f'  用户发质: {ht} → 保持真实发质纹理')

    override_text = '\n'.join(hair_overrides) if hair_overrides else ''

    # ── 构建中文指引（给 AI 看的）──
    beauty_context = f"""💇‍♀️💄 发型与妆容指导（女性专属 — 用于 seedream_prompt 创作）：

📌 风格美妆方向（{matched_cluster.get('label_zh', '')}集群）:
  发型: {hair_cn}
  妆容: {makeup_cn}
  氛围: {vibe}

⚠️ 用户真实特征（必须尊重，不可随意改变发色/发长/发质）:
{override_text if override_text else '  使用风格默认发型（用户未填写发质档案）'}

📌 要求:
  1. seedream_prompt 中必须包含 2-3 句发型和妆容的英文描述
  2. 发型描述要融入整体造型感（如 'soft waves cascading over shoulders' 或 'sleek low bun'）
  3. 妆容描述聚焦在整体效果，不要逐条列举（如 'dewy natural makeup with a soft pink lip'）
  4. 发型妆容必须与穿搭风格和场景协调
  5. ⚠️ 必须尊重用户的真实发长/发色/发质，不可用 Seedream 生成与用户完全不同的发色"""

    # ── 构建简短英文描述（用于 seedream prompt 融合）──
    beauty_en = f"hair: {hair_en}, makeup: {makeup_en}"

    return beauty_context, beauty_en


# ── 服装构造描述生成（女性生图优化）──
_FABRIC_VISUAL_CACHE = None
_GARMENT_TEMPLATES_CACHE = None


def _load_fabric_visual_map():
    """延迟加载面料→视觉属性映射"""
    global _FABRIC_VISUAL_CACHE
    if _FABRIC_VISUAL_CACHE is None:
        fp = os.path.join(PROJ_DIR, 'config', 'fabric_visual.json')
        if os.path.exists(fp):
            _FABRIC_VISUAL_CACHE = load_json(fp)
        else:
            _FABRIC_VISUAL_CACHE = {}
    return _FABRIC_VISUAL_CACHE


def _load_garment_templates():
    """延迟加载女性品类 Prompt 模板"""
    global _GARMENT_TEMPLATES_CACHE
    if _GARMENT_TEMPLATES_CACHE is None:
        gp = os.path.join(PROJ_DIR, 'config', 'garment_templates_female.json')
        if os.path.exists(gp):
            _GARMENT_TEMPLATES_CACHE = load_json(gp)
        else:
            _GARMENT_TEMPLATES_CACHE = {}
    return _GARMENT_TEMPLATES_CACHE


def build_garment_script(selection, all_clothes, is_female=False):
    """从单品标签提取服装构造细节，生成英文 garment reference 注入 seedream prompt 上下文。

    女装版型/面料/细节比男装复杂得多 —— 领型、袖型、腰线、裙型、面料垂感
    一旦出错整套穿搭就毁了。此函数从 JSON 标签自动提取结构化服装描述，
    供 Round 2 AI 在生成 seedream_prompt 时精确还原。

    Args:
        selection: Round 1 的 AI 输出 dict，含 items 列表
        all_clothes: {cid: tag_dict} 全衣柜标签
        is_female: 是否启用女性品类模板

    Returns:
        str: 英文服装构造参考块，注入到 user_prompt
    """
    if not is_female:
        return ''

    items = selection.get('items', [])
    if not items:
        return ''

    fabric_map = _load_fabric_visual_map()
    garment_templates = _load_garment_templates()

    if not garment_templates:
        return ''

    lines = ['👗 Garment Construction Reference — describe these EXACTLY in seedream_prompt:',
             '⚠️ Neckline, sleeve, waistline, skirt silhouette, and fabric texture errors will ruin the outfit.',
             '']

    for it in items:
        cid = it.get('id', '')
        detail = all_clothes.get(cid, {})
        if not detail:
            continue

        cat_code = detail.get('category_code', '')
        template = garment_templates.get(cat_code)
        if not template:
            continue

        cat = detail.get('category', cat_code)
        color = (detail.get('color') or {}).get('hue_name', '')
        pattern = (detail.get('pattern') or {}).get('type', '')
        fabric_cn = (detail.get('fabric') or {}).get('primary', '')
        fabric_weight = (detail.get('fabric') or {}).get('weight', '')

        # 配饰类不取版型/长度（鞋/包/帽/墨镜/袜/配饰无服装版型概念）
        _accessory_cats = {'SHOE', 'BAG', 'HAT', 'ACC', 'SOCK', 'SUN'}
        if cat_code in _accessory_cats:
            fit = ''
            length = ''
        else:
            fit = (detail.get('silhouette') or {}).get('fit', '')
            length = (detail.get('silhouette') or {}).get('length_ratio', '')
        fit_comment = (detail.get('meta') or {}).get('claude_fit_comment', '')

        # 颜色+图案
        color_str = color
        if pattern and pattern not in ('纯色', '无'):
            color_str = f'{color} {pattern}'

        # 面料视觉属性
        fabric_info = fabric_map.get(fabric_cn, fabric_map.get('_default', {}))
        fabric_en = fabric_info.get('en', fabric_cn)
        fabric_visual = fabric_info.get('visual', '')

        # 构建描述行
        desc_parts = [color_str, fabric_en]
        if fit:
            desc_parts.append(f'{fit} fit')
        desc_base = f'  {cid} ({cat}): {", ".join(desc_parts)}'
        if length:
            desc_base += f', {length} length'
        if fit_comment:
            desc_base += f' [{fit_comment}]'

        lines.append(desc_base)

        if fabric_visual:
            lines.append(f'    Fabric: {fabric_visual}')
        if fabric_weight and fabric_weight not in desc_base:
            lines.append(f'    Weight: {fabric_weight}')

        # 品类关键维度
        critical = template.get('critical_details', [])
        if critical:
            # 只取前 4 个最关键维度，避免信息过载
            key_dims = critical[:4]
            lines.append(f'    Describe: {"; ".join(key_dims)}')

        lines.append('')

    if len(lines) <= 3:
        return ''  # 无有效服装数据

    return '\n'.join(lines)


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


# ── 趋势分类映射（trend_category - 六维分类第6维）──
_trend_category_cache = None

def _load_trend_category_map():
    """加载 style_id → trend_category 映射（含缓存）。供 prompt 和 scoring 使用。"""
    global _trend_category_cache
    if _trend_category_cache is not None:
        return _trend_category_cache
    trend_map = {}
    for cat_path in [
        os.path.join(PROJ_DIR, 'styles_universal', 'categories.json'),
        os.path.join(PROJ_DIR, 'styles/female', 'categories.json'),
    ]:
        if os.path.exists(cat_path):
            try:
                with open(cat_path) as f:
                    data = json.load(f)
                for sid, info in data.get('style_registry', {}).items():
                    tc = info.get('trend_category')
                    if tc:
                        trend_map[sid] = tc
            except Exception:
                pass
    _trend_category_cache = trend_map
    return trend_map


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
    outfits_dir = _resolve_outfits_dir()
    for d in sorted(os.listdir(outfits_dir)):
        rp = os.path.join(outfits_dir, d, 'rating.json')
        if not os.path.exists(rp):
            continue
        try:
            with open(rp) as f:
                r = json.load(f)
            if r.get('rating') != 3:
                continue
            md = os.path.join(outfits_dir, d, 'outfit.md')
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
    outfits_dir = _resolve_outfits_dir()
    for d in sorted(os.listdir(outfits_dir), reverse=True):
        rp = os.path.join(outfits_dir, d, 'rating.json')
        md = os.path.join(outfits_dir, d, 'outfit.md')
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
    hot_alert_cats = []  # 高温标注但不删除（女性轻薄长袖/针织夏季可穿）
    for cat in list(cats.keys()):
        items_in_cat = cats[cat]
        if temp_high >= HOT_THRESHOLD:
            # 炎热：跳过厚外套（保留长袖上衣/针织衫—女性夏季有轻薄款）
            if cat in ('外套',):
                skipped_cats.append(f'{cat}({len(items_in_cat)}件，天热跳过)')
                del cats[cat]
            elif cat in ('长袖上衣', '针织衫'):
                hot_alert_cats.append(f'{cat}({len(items_in_cat)}件，优选轻薄面料)')
        elif temp_high <= COLD_THRESHOLD:
            # 寒冷：跳过背心、短裤
            if cat in ('背心', '短裤'):
                skipped_cats.append(f'{cat}({len(items_in_cat)}件，天冷跳过)')
                del cats[cat]
    if skipped_cats:
        skipped_str = '、'.join(skipped_cats)
        cooldown_summary_lines.insert(0, f'🌡️ 温度{temp_high}°C — 自动跳过: {skipped_str}')
    if hot_alert_cats:
        alert_str = '、'.join(hot_alert_cats)
        cooldown_summary_lines.insert(0, f'🌡️ 温度{temp_high}°C — {alert_str}')

    # ── 温度过低保险：确保外套和长袖存在 ──
    if temp_high <= COLD_THRESHOLD:
        if '外套' not in cats or len(cats.get('外套', [])) == 0:
            cooldown_summary_lines.insert(0, '🧥 低温保险: 请务必选择外套 + 长袖上衣')
        if '长袖上衣' not in cats or len(cats.get('长袖上衣', [])) == 0:
            cooldown_summary_lines.insert(0, '🧥 低温保险: 请务必选择长袖上衣 + 外套')

    # ── 表格输出 ──
    cat_order = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '针织衫', '连衣裙', '套装',
                 '长裤', '短裤', '短裙', '半身裙',
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
                          explore_level=0.0, target_styles=None, mandatory_items=None,
                          user_id=None,
                          parsed_city='北京',           # NEW: 用户指定的城市
                          new_item_context='',          # NEW: 最近入库单品提示
                          intent_activity=None,         # NEW: 具体活动描述
                          intent_vibe=None):            # NEW: 氛围/情绪
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

    # ── 0.8. 提前检测性别（target_styles 和 auto_suggest 需要）──
    _is_female_early = False
    if user_id:
        import os as _os
        _up_early = _os.path.join(resolve_user_dir(user_id=user_id), 'profile.json')
        if _os.path.exists(_up_early):
            _up_check_early = load_json(_up_early)
            _is_female_early = (_up_check_early.get('gender', 'female') == 'female')

    # ── 1. 获取推荐风格（性别感知）──
    # 确定 styles_dir 和默认风格（按性别）
    _styles_dir = os.path.join(PROJ_DIR, 'styles/female') if _is_female_early else os.path.join(PROJ_DIR, 'styles/male')
    _default_styles = ['WF-01', 'WF-05', 'WF-06'] if _is_female_early else ['clean_fit', 'japanese_city_boy']

    if target_styles is None:
        from tools.style_matcher import auto_suggest_style
        suggestions = auto_suggest_style(temp_high, weather_cond, occasion, gender=('female' if _is_female_early else 'male'))
        target_styles = [s['style_id'] for s in suggestions[:3]]
    if not target_styles:
        target_styles = _default_styles

    # ── 1.5. 用户指定风格优先：如果 style_hint 匹配已知 style_id 或中文名，强制置顶 ──
    hint_lower = style_hint.lower().replace(' ', '_').replace('-', '_')
    matched_style = None
    _best_match_len = 0  # 最长中文匹配优先
    # 搜索男性+女性两个目录
    for _search_dir in [_styles_dir, os.path.join(PROJ_DIR, 'styles/male'), os.path.join(PROJ_DIR, 'styles/female')]:
        if not os.path.isdir(_search_dir):
            continue
        for fn in sorted(os.listdir(_search_dir)):
            if fn.startswith('.') or fn.startswith('_'):
                continue
            # 支持 .json 文件和目录（女性风格是目录结构）
            _full_path = os.path.join(_search_dir, fn)
            if os.path.isdir(_full_path):
                sid = fn.split('_', 1)[0] if '_' in fn else fn
            elif fn.endswith('.json'):
                sid = fn[:-5]
            else:
                continue
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

    # ── 1.6. 推荐等级过滤：core(始终) / explore(≥0.5) / bold(≥0.8) ──
    # 用户主动指定的风格（matched_style）不受等级限制
    TIER_THRESHOLDS = {'core': 0.0, 'explore': 0.5, 'bold': 0.8}
    filtered_styles = []
    for sid in target_styles:
        if sid == matched_style:
            filtered_styles.append(sid)
            continue
        try:
            sf = load_style_fingerprint(sid)
            tier = sf.get('tier', 'core')
        except Exception:
            tier = 'core'
        threshold = TIER_THRESHOLDS.get(tier, 0.0)
        if explore_level >= threshold:
            filtered_styles.append(sid)
    # 大胆混搭模式：补充所有 bold 等级风格到候选池
    if explore_level >= 0.8:
        for _search_dir in [_styles_dir]:
            if not os.path.isdir(_search_dir):
                continue
            for fn in sorted(os.listdir(_search_dir)):
                if fn.startswith('.') or fn.startswith('_'):
                    continue
                _full_path = os.path.join(_search_dir, fn)
                if os.path.isdir(_full_path):
                    sid = fn.split('_', 1)[0] if '_' in fn else fn
                elif fn.endswith('.json'):
                    sid = fn[:-5]
                else:
                    continue
                if sid in filtered_styles or sid == matched_style:
                    continue
                try:
                    sf = load_style_fingerprint(sid)
                    if sf.get('tier') == 'bold':
                        filtered_styles.append(sid)
                except Exception:
                    pass
    target_styles = filtered_styles if filtered_styles else target_styles[:1]

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

    # ── 5. 加载趋势分类映射 ──
    trend_map = _load_trend_category_map()

    # ── 5.5. 加载风格描述（含趋势分类标签）──
    TREND_EMOJI = {'classic': '🏛️', 'popular_trend': '🔥', 'niche': '🎭'}
    style_descs = []
    for sid in target_styles[:3]:
        sf = load_style_fingerprint(sid)
        if sf:
            name = sf.get('name_zh', sid)
            desc = sf.get('description', '')[:60]
            color_logic = sf.get('fingerprint', {}).get('color_rules', {}).get('color_logic', '')
            tc = trend_map.get(sid, '')
            tc_emoji = TREND_EMOJI.get(tc, '')
            tc_label = {'classic':'经典','popular_trend':'流行','niche':'小众'}.get(tc, '')
            tc_tag = f' {tc_emoji}{tc_label}' if tc_label else ''
            style_descs.append(f'  🎯 {name} ({sid}){tc_tag}: {desc}')
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
    persona_desc, persona_modifier, persona_context = _get_persona_description(user_id)

    # 判断性别用于系统 prompt（复用早期检测结果）
    is_female = _is_female_early
    gender_audience = '亚洲女性穿搭' if is_female else '亚洲男性穿搭'

    quality_checklist = f"""⚠️ 推荐质量检查（请在选品时逐项确认）：
□ 核心单品齐全：{'女士：连衣裙/套装/连体裤+鞋子（一体式） 或 上衣+下装/半身裙+鞋子（分体式）' if is_female else '上衣+下装+鞋子（或连衣裙+鞋子），缺一不可'}
□ 配色协调：无红绿/橙蓝等冲突撞色，整体色调统一
□ 风格连贯：每件单品对目标风格的匹配分 ≥ 30
□ 廓形平衡：上宽下窄 或 外松内紧，避免全身同宽
□ 体型修饰：{persona_desc}
{persona_modifier}
□ 面料匹配场景：夏季上衣→透气(棉/麻/速干)，运动→速干，下装/鞋/配件不受面料限制
□ 衬肤色：根据用户肤色选择合适颜色
{'''□ ⚠️ 一体式单品规则：选了连衣裙(DRESS)/套装(SUIT)/连体裤(JMP)后，禁止再选裤子/裙子/上衣，只需鞋子+配件''' if is_female else ''}
"""

    # ── 10. 组装 system prompt ──
    context_section = ''
    if persona_context:
        context_section = f'\n用户背景: {persona_context}'

    system_prompt = f"""你是一位专攻{gender_audience}的 AI 时尚顾问。

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
- {'⚠️ 女士穿搭选品规则（重要）：' if is_female else ''}
- {'  1. 连衣裙(DRESS)/套装(SUIT)/连体裤(JMP) = 上衣+下装一体，选了它们就不要再选裤子/裙子/上衣，只需再配鞋子+配件' if is_female else ''}
- {'  2. 半身裙(SKIRT) = 下装，需要搭配上衣+鞋子' if is_female else ''}
- {'  3. 女士单品category字段请使用衣柜表格中显示的品类名（如"连衣裙""套装""半身裙"），不要统称"上衣""下装"' if is_female else ''}
- {'  4. 选了连衣裙/套装后，items数组只需包含该一体式单品+鞋子+配件，不要强行凑上衣+下装' if is_female else ''}
- {'每套必须包含上衣、下装、鞋子（硬性要求，缺一不可）。⚠️ 例外：选连衣裙/套装/连体裤时只需连衣裙+鞋子（连衣裙/套装/连体裤=上衣+下装一体）' if not is_female else ''}
- 针织衫/毛衣可作为上衣使用
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

    # ── 活动/氛围上下文 ──
    activity_context = ''
    if intent_activity or intent_vibe:
        parts = []
        if intent_activity:
            parts.append(f'活动：{intent_activity}')
        if intent_vibe:
            parts.append(f'氛围：{intent_vibe}')
        if parts:
            activity_context = '🎭 ' + ' · '.join(parts) + '\n'

    user_prompt = f"""今天是{today}，{parsed_city}天气：{temp_high}°C {weather_cond}。
{explore_header}{mandatory_section}{new_item_context}风格需求：「{style_hint}」
场合：{occasion}
{activity_context}{ban_section}{recent_section}
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
                          occasion, explore_level, temp_high, weather_cond, user_id=None,
                          user_hair=None):
    """构建 Round 2「创作」prompt — 基于已选单品，生成 seedream_prompt/穿搭技巧/推荐理由/关键词

    selection: Round 1 的 AI 输出 dict，含 items/color_story/silhouette/anchor/style
    user_id: 多用户上下文，用于确定性别
    user_hair: {'length': 'long', 'color': 'black', 'texture': 'straight'} 女性发型档案
    """
    all_clothes = load_all_clothing()
    today = time.strftime('%Y-%m-%d')

    # ── 性别感知 ──
    is_female = False
    if user_id:
        import os as _os
        up_path_check = _os.path.join(resolve_user_dir(user_id=user_id), 'profile.json')
        if _os.path.exists(up_path_check):
            up_check = load_json(up_path_check)
            is_female = (up_check.get('gender', 'female') == 'female')
    gender_label = '女性' if is_female else '男性'
    gender_en = 'woman' if is_female else 'man'

    # ── 女性美妆指引 ──
    beauty_context = ''
    beauty_en = ''
    if is_female:
        # 读取用户发型档案
        if not user_hair and user_id:
            try:
                up_path = os.path.join(resolve_user_dir(user_id=user_id), 'profile.json')
                if os.path.exists(up_path):
                    up = load_json(up_path)
                    user_hair = up.get('hair')
            except Exception:
                pass
        beauty_context, beauty_en = get_beauty_direction(target_styles, user_hair)
        if beauty_context:
            log_text = f"💇‍♀️ 美妆方向: {len(beauty_context)}字符"
        else:
            log_text = "💇‍♀️ 美妆方向: 无匹配集群"
        # log via print since we don't have the log function here
        print(log_text)

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

    # ── 女性服装构造描述（从标签自动提取，注入 seedream prompt 上下文）──
    garment_script = build_garment_script(selection, all_clothes, is_female=is_female)
    if garment_script:
        print(f"👗 服装构造参考: {len(garment_script)}字符")

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

    beauty_schema = ''
    beauty_note = ''
    if is_female and beauty_context:
        beauty_schema = ',\n  "beauty_direction": {{"hair": "2-3句英文发型描述（融入seedream_prompt）", "makeup": "2-3句英文妆容描述（融入seedream_prompt）"}}'
        beauty_note = '\n- ⚠️ seedream_prompt 必须自然融入发型和妆容描述（从 beauty_direction 的 hair/makeup 字段改写），不可省略。发型妆容是女性穿搭整体造型的关键组成部分'

    system_prompt = f"""你是专攻亚洲{gender_label}穿搭的 AI 时尚顾问（创作模式）。

你的任务是基于已选定的穿搭单品，生成面向消费者的穿搭叙事内容。单品已经确定，你不需要再选品。

输出严格的 JSON 格式（不要任何其他文字）：
{{
  "keywords": "3-6个风格特征词，用中文顿号分隔（如：宽松廓形、少年感、帆布鞋、白袜、日系休闲）。⚠️这是穿搭风格标签，不是用户指令！必须从搭配本身提取美学特征，严禁照抄用户输入",
  "reasoning": "整体搭配理由（100-200字）：搭配逻辑阐述，解释为什么这些单品能组合在一起",
  "rationale": "推荐理由（100-200字）：消费者视角的一段话，从场景/风格/体型/单品特征角度说明为什么这套穿搭适合用户。用自然口语化句子，不编号不要点，强调「穿上为什么好看/合适」。与reasoning区别：reasoning是搭配逻辑，rationale是消费者话术",
  "dressing_tips": ["穿搭技巧1：基于所选单品的独特特征（特定颜色/面料/廓形/品牌设计细节/鞋型/领型），而非通用建议", "穿搭技巧2：必须与技巧1来自不同类别，数组长度1-2"],
  "seedream_prompt": "英文 Seedream 生图提示词(250-400字符)，必须忠实还原下方📷摄影指导中的相机/构图/光影/姿势/场景/情绪/表情。🔒场景锁定：拍摄地点必须就是摄影指导『场景』写的那个地方，严禁改成其他城市/街道（尤其禁止写成北京街道/都市天际线）；🔒器材锁定：摄影指导指定的相机/胶片/光影必须原样写进 prompt（如 Kodak Portra 400 film look）。你只能润色英文措辞让句子通顺，不能替换地点或器材。⚡姿势必须动态(禁止standing)，用摄影指导『姿势』的具体动作。👟构图必须为全身照(full body shot from head to toe)，确保鞋子完整可见不被裁切。😊表情必须自然松弛（slight smile或relaxed neutral），严禁死板面瘫脸。🚫【严禁虚构配饰】只能描述上方「单品清单」中真实存在的服饰单品，绝对禁止添加清单中没有的任何包/手袋/斜挎包、帽子、墨镜/眼镜、项链/耳环/手表/首饰、围巾、腰带等配饰——即使摄影指导的姿势里提到手持或佩戴某物，也必须改写成不涉及该物品的动作(如'手插口袋'/'拨头发'/'扶栏杆')。画面中人物携带/佩戴的每一件东西都必须能在单品清单里找到对应ID。{'💇‍♀️💄必须自然融入下方发型与妆容指导中的发型和妆容描述。' if is_female else ''}{'👗必须精确还原下方 Garment Construction Reference 中每件单品的服装构造：领型、袖型、腰线、裙型/裤型、面料质感必须与描述一致，不可随意改变。' if is_female else ''}详细描述服装细节和场景氛围，营造时尚大片的摄影感"{beauty_schema}
}}

注意：
- 推荐理由(rationale)必须面向消费者，强调「穿上为什么好看」，不是搭配逻辑阐述
- ⚠️ 穿搭技巧(dressing_tips)关键规则：
  1. 两条技巧必须来自不同类别（见下方技巧类型池），严禁同类重复
  2. 严禁使用「下摆塞前腰1/3」或任何形式的塞衣摆——这是最偷懒的通用技巧，除非该上衣的设计本身就是为塞入穿着（如正式衬衫配西裤）。绝大多数休闲T恤/衬衫应该自然垂坠或仅在特定姿势下微塞
  3. 每条技巧必须引用所选单品的具体特征：颜色名、面料、廓形、品牌设计细节、鞋型、领型等。不能说「上衣塞进去」，要说「因为TS-009是落肩宽松版型，自然垂坠的下摆刚好在臀围线上方，配合直筒牛仔裤能拉长腿部比例」
  4. 优先选择最能体现这套穿搭独特性的技巧，而非百搭通用技巧{beauty_note}

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
    user_prompt = f"""今天是{today}。当前天气：{temp_high}°C {weather_cond}（⚠️ 天气只用于判断穿着舒适度，不是拍摄地点；实际拍摄场景以下方📷摄影指导为准）。
风格需求：「{style_hint}」| 场合：{occasion}{explore_note}
目标风格参考：
{sep.join(style_descs)}

─── 已选穿搭方案 ───
锚点: {anchor_text}
配色: {color_story}
廓形: {silhouette}

单品清单：
{items_text}

{garment_script}
{photo_direction}
{beauty_context}

─── 请基于以上已确定的单品，输出 JSON 格式的创作内容（keywords/reasoning/rationale/dressing_tips/seedream_prompt{'/beauty_direction' if is_female else ''}）。
🔒 再次强调：seedream_prompt 的拍摄场景必须忠实还原上方📷摄影指导的『场景』，相机/胶片/光影必须原样体现，严禁替换成北京街道或其他都市场景。───"""

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
        'beauty_en': beauty_en,
    }


# ============================================================
# Step 3: 规则自动验证
# ============================================================

def validate_outfit(items, occasion='日常', temp_high=30, weather_cond='晴', all_clothes=None,
                    mandatory_items=None, target_styles=None, explore_level=0.0):
    """验证 AI 选品是否通过所有规则门

    mandatory_items: [(item_id, confidence, reason), ...] 用户指定必须使用的单品
    """
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
    # 连衣裙/套装/连体裤可替代上衣+下装
    has_dress = any(c == 'DRESS' for c in cat_codes)
    has_suit = any(c == 'SUIT' for c in cat_codes)
    has_jmp = any(c == 'JMP' for c in cat_codes)
    has_top = any(c in {'TS', 'LS', 'TANK', 'SHIRT', 'JK', 'KNIT', 'BLOUSE'} for c in cat_codes)
    has_bottom = any(c in {'SH', 'PT', 'SKIRT'} for c in cat_codes)
    has_shoe = any(c == 'SHOE' for c in cat_codes)

    if has_dress or has_suit or has_jmp:
        # 连衣裙/套装/连体裤 = 上衣 + 下装一体，只需再配鞋子
        pass  # 不要求单独的上衣/下装
    else:
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
    skirt_count = cat_codes.count('SKIRT')
    onepiece_count = sum(1 for c in cat_codes if c in ('DRESS', 'SUIT', 'JMP'))
    # 上衣品类：含针织衫(KNIT)与女士衬衫(BLOUSE)，与 has_top 口径一致，避免叠穿漏检
    top_count = sum(1 for c in cat_codes if c in ('TS', 'LS', 'SHIRT', 'TANK', 'KNIT', 'BLOUSE'))
    # 下装品类：长裤/短裤/半身裙合计
    bottom_count = pt_count + sh_count + skirt_count

    if jk_count > 1:
        violations.append('禁止两件外套')
    if shoe_count > 1:
        violations.append('禁止两双鞋')

    # ── 2.1 一体式单品互斥（连衣裙/套装/连体裤 = 上衣+下装一体）──
    if onepiece_count > 1:
        violations.append(f'禁止{onepiece_count}件一体式单品（连衣裙/套装/连体裤只能选1件）')
    if has_dress or has_suit or has_jmp:
        # 选了一体式，就不该再出现独立上衣/下装
        if has_top:
            violations.append('禁止一体式单品（连衣裙/套装/连体裤）再叠穿独立上衣——连衣裙已含上衣，请去掉上衣或改用分体式')
        if has_bottom:
            violations.append('禁止一体式单品（连衣裙/套装/连体裤）再叠穿独立下装——连衣裙已含下装，请去掉下装或改用分体式')
    else:
        # ── 2.2 分体式：上衣/下装各不超过1件 ──
        if top_count > 1:
            violations.append(f'禁止{top_count}件上衣（只能选1件上衣，不要叠穿长短袖/衬衫/针织衫）')
        if bottom_count > 1:
            _parts = []
            if pt_count > 1:
                _parts.append(f'{pt_count}条长裤')
            if sh_count > 1:
                _parts.append(f'{sh_count}条短裤')
            if skirt_count > 1:
                _parts.append(f'{skirt_count}条半身裙')
            _mix = [n for n, c in (('长裤', pt_count), ('短裤', sh_count), ('半身裙', skirt_count)) if c > 0]
            if _parts:
                violations.append(f'禁止{" + ".join(_parts)}（下装只能选1件）')
            elif len(_mix) > 1:
                violations.append(f'禁止同时选 {" + ".join(_mix)}（下装只能选1件，长裤/短裤/半身裙三选一）')

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

    # ── 4.5. 面料季节硬阻断（高温禁秋冬面料）──
    for d in outfit_details:
        cid = d['id']
        cat = d['detail'].get('category_code', '')
        fabric = d['detail'].get('fabric', {}) or {}
        seasonality = fabric.get('seasonality', [])
        fabric_primary = fabric.get('primary', '')
        fabric_weight = fabric.get('weight', '')

        # ≥28°C 禁止纯秋冬面料（羊毛/灯芯绒/羊绒/呢子/厚针织）
        winter_fabrics = ['羊毛', '灯芯绒', '羊绒', '呢子', '羊毛混纺', '厚针织', '抓绒']
        is_winter_fabric = any(w in fabric_primary for w in winter_fabrics)
        is_winter_weight = fabric_weight in ('厚', '中厚', '加厚')
        is_cold_season = seasonality and all(s in ('秋', '冬') for s in seasonality)

        if temp_high >= 28:
            if is_cold_season and cat in ('PT', 'SH', 'JK', 'TS', 'LS', 'SHIRT', 'KNIT', 'TANK'):
                violations.append(f'{cid}: 气温≥28°C禁止纯秋冬面料（{fabric_primary}/seasonality={seasonality}），请选春夏透气单品')
            elif is_winter_fabric and cat in ('PT', 'JK'):
                violations.append(f'{cid}: 气温≥28°C禁止{fabric_primary}面料下装/外套，高温不适用')
            elif is_winter_weight and cat in ('PT', 'JK'):
                violations.append(f'{cid}: 气温≥28°C禁止{fabric_weight}面料下装/外套，请选轻薄款')

        # ≥30°C 进一步收窄：仅允许春夏面料
        if temp_high >= 30 and cat in ('TS', 'LS', 'SHIRT', 'KNIT', 'TANK'):
            if is_cold_season:
                violations.append(f'{cid}: 气温≥30°C上衣必须是春夏面料（{fabric_primary}/seasonality={seasonality}不适合）')

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

    # ── 5.5. 女性特有规则 (2026-06-26) ──
    _is_female_outfit = any(c in {'DRESS', 'SKIRT', 'BLOUSE'} for c in cat_codes)
    if _is_female_outfit:
        for d in outfit_details:
            cid = d['id']
            cat = d['detail'].get('category_code', '')
            fabric = (d['detail'].get('fabric') or {}).get('primary', '')
            color_hue = (d['detail'].get('color') or {}).get('hue_name', '')

            # 正式场合 + 连衣裙/半身裙：裙长应及膝或更长
            if occasion in ('晚宴', '商务', '下午茶', '婚礼') and cat in ('DRESS', 'SKIRT'):
                # 如果标签中有裙长信息，检查是否过短
                skirt_len = d['detail'].get('length', '')
                if skirt_len in ('超短', '短款', 'mini'):
                    violations.append(f'{cid}: {occasion}场合裙长不宜过短(当前:{skirt_len})')

            # 商务/通勤 + 露肤度：禁止吊带/露背/露脐
            if occasion in ('商务', '通勤') and cat in ('TANK',):
                violations.append(f'{cid}: 商务/通勤场合禁止吊带背心单穿（需配外套）')

            # 晚宴/正式场合：高跟鞋推荐
            if occasion in ('晚宴', '下午茶') and cat == 'SHOE':
                heel_type = d['detail'].get('heel_type', '')
                if heel_type in ('平底', 'flat', '运动'):
                    warnings.append(f'{cid}: {occasion}场合建议高跟鞋或精致平底鞋(当前:{heel_type})')

            # 晚宴禁止运动鞋
            if occasion in ('晚宴') and cat == 'SHOE':
                shoe_style = d['detail'].get('style', '')
                if any(kw in str(shoe_style).lower() for kw in ['运动', '跑鞋', 'sneaker', '篮球']):
                    violations.append(f'{cid}: 晚宴场合禁止运动鞋')

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

    # ── 7. 风格匹配最低分检查（2026-07-07 增强：按探索度分级 + 目标风格定向）──
    cache = load_score_cache()

    # 阈值按探索度分级：指定风格 ≥30 / 微调 ≥20 / 大胆混搭 ≥10
    if explore_level <= 0:
        STYLE_MATCH_MIN = 30   # 安全推荐/指定风格：严格匹配
    elif explore_level < 0.5:
        STYLE_MATCH_MIN = 20   # 微调探索：适度放宽
    else:
        STYLE_MATCH_MIN = 10   # 大胆混搭：大幅放宽

    if target_styles:
        # 定向检查：核心单品对目标风格的匹配分
        for d in outfit_details:
            cid = d['id']
            cat = d['detail'].get('category_code', '')
            if cat not in CORE_CATS:
                continue
            style_entries = cache.get(cid, {})
            if not style_entries:
                warnings.append(f'{cid}: 无风格匹配数据，无法验证')
                continue
            # 取对目标风格的最佳匹配分
            best_target = 0
            best_target_name = ''
            for sid in target_styles:
                entry = style_entries.get(sid, {})
                s = entry.get('score', 0) if isinstance(entry, dict) else 0
                if s > best_target:
                    best_target = s
                    best_target_name = sid
            if best_target < STYLE_MATCH_MIN:
                # 检查这件单品真正适合什么风格（提供诊断信息）
                real_styles = sorted(
                    [(k, v.get('score', 0)) for k, v in style_entries.items()
                     if isinstance(v, dict) and v.get('score', 0) >= 40],
                    key=lambda x: -x[1]
                )[:3]
                real_hint = f'（实际适合: {", ".join(f"{s}={sc}" for s,sc in real_styles)}）' if real_styles else ''
                mode_label = '指定风格' if explore_level <= 0 else ('微调探索' if explore_level < 0.5 else '大胆混搭')
                violations.append(
                    f'{cid}: 对目标风格"{best_target_name}"仅{best_target}分 < {STYLE_MATCH_MIN}分'
                    f'（{mode_label}阈值）{real_hint}'
                )
    else:
        # 无目标风格时，保持旧的宽松检查：任意风格最低分 ≥ 20
        for d in outfit_details:
            cid = d['id']
            cat = d['detail'].get('category_code', '')
            if cat in CORE_CATS:
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

    # ── 8.5. Formality 一致性检查（2026-07-07 新增）──
    formality_scores = []
    for d in outfit_details:
        cid = d['id']
        cat = d['detail'].get('category_code', '')
        if cat in CORE_CATS:
            f = d['detail'].get('formality')
            if f is not None:
                formality_scores.append((cid, cat, f))

    if len(formality_scores) >= 2:
        f_min = min(formality_scores, key=lambda x: x[2])
        f_max = max(formality_scores, key=lambda x: x[2])
        f_spread = f_max[2] - f_min[2]

        if f_spread > 2:
            violations.append(
                f'Formality断层({f_spread}级): {f_min[0]}(formality={f_min[2]}) ↔ {f_max[0]}(formality={f_max[2]})，'
                f'跨度过大导致穿搭逻辑不自洽'
            )
        elif f_spread == 2:
            # 极低+极高搭配警告（如 formality=1 运动鞋 + formality=4 西裤）
            if f_min[2] <= 1 and f_max[2] >= 4:
                violations.append(
                    f'Formality冲突({f_spread}级): {f_min[0]}(formality={f_min[2]})为纯运动/居家 ↔ '
                    f'{f_max[0]}(formality={f_max[2]})为半正式，风格完全冲突'
                )
            else:
                warnings.append(
                    f'Formality跨度({f_spread}级): {f_min[0]}(formality={f_min[2]}) ↔ {f_max[0]}(formality={f_max[2]})，'
                    f'建议缩小差距'
                )

    # ── 9. 强制单品校验（用户显式指定的单品必须出现在输出中）──
    if mandatory_items:
        outfit_ids = {it.get('id', '') for it in items}
        for mid, conf, reason in mandatory_items:
            if mid not in outfit_ids:
                violations.append(
                    f'缺少用户指定单品: {mid} ({reason}，置信度{conf:.0%})'
                )

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

    # ── Phase 0: 精确 ID 匹配（用户显式指定单品 ID，最高优先级）──
    # 使用中文兼容版正则（不用 \b，因 Python 3.x 中 CJK 字符属于 \w 导致 \b 失效）
    _ID_PAT = re.compile(
        r'(?<![A-Za-z0-9])(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+'
        r'|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+'
        r'|DRESS-\d+|SKIRT-\d+|JMP-\d+|BLOUSE-\d+|KNIT-\d+)(?![A-Za-z0-9])'
    )
    exact_ids = list(dict.fromkeys(_ID_PAT.findall(desc)))  # 去重保序
    if exact_ids:
        exact_results = []
        for cid in exact_ids:
            if cid in all_clothes:
                item = all_clothes[cid]
                brand = (item.get('brand') or {}).get('name', '—')
                cat = item.get('category', '—')
                color = (item.get('color') or {}).get('hue_name', '')
                reason = f'ID精确匹配: {cid} | {brand} {color}·{cat}'
                exact_results.append((cid, 0.99, reason))
        if exact_results:
            return exact_results  # 精确匹配短路，不走模糊匹配

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


def determine_daily_mode(style_hint, user_id=None):
    """
    每日自动推荐的模式决策 — 基于时间节奏 + 用户状态 + 天气 + 模式轮换。

    返回: (explore_level, mode_label, reason)
      - explore_level: 0.0(日常穿搭) / 0.5(改变自己) / 1.0(大胆跨界)
      - mode_label: 中文标签
      - reason: 决策原因（用于日志）
    """
    import datetime
    today = datetime.date.today()
    weekday = today.weekday()  # 0=Mon, 6=Sun
    month = today.month

    # ── 1. 获取用户状态 ──
    state = load_lab_state()
    total = state.get('total_recommendations', 0)
    try:
        from style_lab import _get_user_rating_profile
        profile = _get_user_rating_profile()
    except Exception:
        profile = {'is_new_user': True, 'recent_3star_streak': 0, 'recent_1star_streak': 0,
                   'exploration_appetite': 0.0, 'unexplored_ratio': 1.0}

    # ── 2. 新用户保护 ──
    if profile.get('is_new_user'):
        return 0.0, '日常穿搭', '新用户（<5条评分），建立舒适区基线'

    # ── 3. 1星惩罚冷却 ──
    if profile.get('recent_1star_streak', 0) >= 2:
        return 0.0, '日常穿搭', f'连续{profile["recent_1star_streak"]}次1星，退回安全区冷却'

    # ── 4. 检测风格疲劳 (最近3天同风格) ──
    try:
        recent_outfits = get_recent_outfits(limit=3)
        if len(recent_outfits) >= 3:
            recent_styles = [d[0].split('_', 1)[-1] if '_' in d[0] else d[0] for d in recent_outfits]
            if len(set(recent_styles)) == 1 and total > 5:
                # 风格疲劳 → 至少推改变自己
                if profile.get('exploration_appetite', 0) > 0:
                    return 1.0, '大胆跨界', f'连续3天同风格({recent_styles[0]})，用户探索欲高→大胆突破'
                return 0.5, '改变自己', f'连续3天同风格({recent_styles[0]})，强制换风格'
    except Exception:
        pass

    # ── 5. 获取天气影响（天气只做安全兜底，不主动推高模式）──
    weather_force_safe = False  # 极端天气强制降为日常
    weather_note = ''
    try:
        from weather_advisor import fetch_weather
        weather = fetch_weather('Beijing')
        temp = weather.get('temp_high', 25)
        cond = weather.get('condition', '晴')
        if temp > 35 or temp < 5 or cond in ('雨', '雪', '雾霾'):
            weather_force_safe = True
            weather_note = f'{cond} {temp}°C 极端天气→强制日常'
        elif month in (3, 4, 9, 10):
            weather_note = f'换季月 {temp}°C（模式由周节奏决定）'
        else:
            weather_note = f'{cond} {temp}°C'
    except Exception:
        pass

    # ── 6. 周节奏基础模式 ──
    if weekday in (5,):  # 周六
        base_level = 1.0
        base_label = '大胆跨界'
        base_reason = '周六 — 周末实验场'
    elif weekday in (4,):  # 周五
        base_level = 0.5
        base_label = '改变自己'
        base_reason = '周五 — 周末前奏，尝试新风格'
    elif weekday in (3,):  # 周四
        base_level = 0.5
        base_label = '改变自己'
        base_reason = '周四 — 周中换新，打破单调'
    elif weekday in (6,):  # 周日
        base_level = 0.0
        base_label = '日常穿搭'
        base_reason = '周日 — 舒适重置日'
    else:  # 周一~周三
        base_level = 0.0
        base_label = '日常穿搭'
        base_reason = f'工作日（周{weekday+1}）— 稳定可靠'

    # ── 7. 极端天气安全阀（宜人天气不改变模式）──
    if weather_force_safe:
        adjusted_level = 0.0
        base_reason += f' | ⚠️ {weather_note}'
    else:
        adjusted_level = base_level
        if weather_note:
            base_reason += f' | {weather_note}'

    # ── 8. 用户探索欲调整 ──
    appetite = profile.get('exploration_appetite', 0)
    if appetite > 0.5 and adjusted_level < 1.0:
        adjusted_level = min(1.0, adjusted_level + 0.5)
        base_reason += f' + 用户探索欲高({appetite})'
    elif appetite < -0.3:
        adjusted_level = max(0.0, adjusted_level - 0.5)

    # ── 9. 模式轮换检查：避免连续3天同模式 ──
    try:
        history = load_lab_state().get('daily_mode_history', [])
        if len(history) >= 2:
            last_two = [h.get('explore_level', -1) for h in history[-2:]]
            if all(l == adjusted_level for l in last_two):
                # 同模式连2天 → 第3天强制变化
                if adjusted_level >= 0.5:
                    adjusted_level = 0.0
                    base_reason += ' | 轮换：已连续2天探索→回归日常'
                else:
                    adjusted_level = 0.5
                    base_reason += ' | 轮换：已连续2天日常→尝试改变'
    except Exception:
        pass

    # ── 10. 确定最终标签 ──
    if adjusted_level >= 0.8:
        mode_label = '大胆跨界'
    elif adjusted_level >= 0.3:
        mode_label = '改变自己'
    else:
        mode_label = '日常穿搭'

    # 拼接理由（weather_note 已嵌入 base_reason）
    full_reason = base_reason
    full_reason += f' | 总推荐:{total} 倾向:{appetite}'

    return adjusted_level, mode_label, full_reason


def _record_daily_mode(explore_level, mode_label, reason):
    """记录每日模式选择到状态文件，供轮换检查"""
    state = load_lab_state()
    history = state.setdefault('daily_mode_history', [])
    history.append({
        'date': time.strftime('%Y-%m-%d'),
        'explore_level': explore_level,
        'mode': mode_label,
        'reason': reason,
    })
    # 只保留最近 14 天
    state['daily_mode_history'] = history[-14:]
    save_lab_state(state)


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


