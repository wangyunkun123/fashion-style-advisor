#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户管理器 v2 — 创建/查询/列表，操作 users/<gender>/<user_id>/ 结构

注册表: users/_registry.json → {gender: {user_id: {created, last_active, status}}}
数据目录: users/<gender>/<user_id>/ 下包含 profile.json, wardrobe/, outfits/, cache/, config/ 等
"""

import os, json, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)
USERS_DIR = os.path.join(PROJ_DIR, 'users')
REGISTRY_FILE = os.path.join(USERS_DIR, '_registry.json')

os.makedirs(USERS_DIR, exist_ok=True)

# ── 性别默认值 ──────────────────────────────────────────
GENDER_DEFAULTS = {
    'male': {
        'body': {'height': '172', 'weight': '65', 'shape': 'rectangle', 'skin_tone': 'medium'},
        'default_styles': ['american_ivy_league', 'clean_fit', 'athleisure_sport'],
        'body_shapes': [
            {'id': 'inverted_triangle', 'emoji': '🔻', 'name': '倒三角', 'desc': '肩宽臀窄·运动型'},
            {'id': 'rectangle', 'emoji': '📏', 'name': '矩形', 'desc': '肩臀腰相近·匀称'},
            {'id': 'trapezoid', 'emoji': '🔷', 'name': '梯形', 'desc': '肩略宽·腰腹平坦'},
            {'id': 'oval', 'emoji': '🟤', 'name': '椭圆', 'desc': '腰腹丰满·四肢细'},
            {'id': 'lean', 'emoji': '📐', 'name': '瘦长型', 'desc': '骨架窄·偏瘦'},
        ],
    },
    'female': {
        'body': {'height': '160', 'weight': '55', 'shape': 'pear', 'skin_tone': 'medium'},
        'default_styles': ['WF-01', 'WF-05', 'WF-06'],
        'hair': {'length': 'long', 'color': 'black', 'texture': 'straight'},
        'body_shapes': [
            {'id': 'hourglass', 'emoji': '⌛', 'name': '沙漏型', 'desc': '肩臀同宽·腰细'},
            {'id': 'pear', 'emoji': '🍐', 'name': '梨型', 'desc': '肩窄臀宽'},
            {'id': 'apple', 'emoji': '🍎', 'name': '苹果型', 'desc': '腰腹丰满'},
            {'id': 'rectangle', 'emoji': '📏', 'name': '矩形', 'desc': '肩臀腰相近'},
            {'id': 'inverted_triangle', 'emoji': '🔻', 'name': '倒三角', 'desc': '肩宽臀窄'},
            {'id': 'petite', 'emoji': '🌸', 'name': '小个子', 'desc': '160cm 以下'},
        ],
    },
}


def _ensure_registry():
    """确保注册文件存在，不存在则创建空注册（嵌套结构）"""
    if not os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, 'w') as f:
            json.dump({}, f, indent=2)
    with open(REGISTRY_FILE, 'r') as f:
        return json.load(f)


def load_registry():
    """返回 {gender: {user_id: {created, last_active, status}}}"""
    return _ensure_registry()


def save_registry(reg):
    """原子写入：先写临时文件再 rename，防止并发读取截断空文件"""
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(REGISTRY_FILE), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, REGISTRY_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def user_exists(user_id, gender=None):
    """检查用户是否存在。gender 为 None 时跨所有 gender 查找。"""
    reg = load_registry()
    if gender:
        return user_id in reg.get(gender, {})
    for g_users in reg.values():
        if user_id in g_users:
            return True
    return False


def get_user_gender(user_id):
    """从注册表查找用户属于哪个 gender。返回 'male'/'female'/None。"""
    reg = load_registry()
    for gender, users in reg.items():
        if user_id in users:
            return gender
    return None


def create_user(gender, user_id, profile_data=None):
    """创建新用户：建目录 + 初始化 profile.json + 写注册表。

    Args:
        gender: 'male' 或 'female'（必填）
        user_id: 用户 ID（必填）
        profile_data: 可选的 profile 覆盖数据

    Returns:
        user_dir 路径。已存在则直接返回。

    Raises:
        ValueError: gender 无效
    """
    if gender not in ('male', 'female'):
        raise ValueError(f"Invalid gender: '{gender}'. Must be 'male' or 'female'.")

    user_dir = os.path.join(USERS_DIR, gender, user_id)

    # 建目录结构
    for sub in ['wardrobe', 'wardrobe/tags', 'wardrobe/enhanced',
                'outfits', 'discovered_styles', 'cache', 'config']:
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

    # 初始化 profile.json
    profile_path = os.path.join(user_dir, 'profile.json')
    if not os.path.exists(profile_path):
        defaults = GENDER_DEFAULTS.get(gender, {})
        default_profile = {
            'user_id': user_id,
            'gender': gender,
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'onboarding_step': 0,
            'onboarding_complete': False,
            'body': defaults.get('body', {}),
            'style_prefs': defaults.get('default_styles', []),
        }
        if profile_data:
            default_profile.update(profile_data)
        with open(profile_path, 'w') as f:
            json.dump(default_profile, f, ensure_ascii=False, indent=2)

    # 初始化 服装档案.md（按性别筛选品类）
    wardrobe_md = os.path.join(user_dir, 'wardrobe', '服装档案.md')
    if not os.path.exists(wardrobe_md):
        try:
            from tools.common import CAT_CONFIG
        except ImportError:
            CAT_CONFIG = {}
        cats = []
        for code, cfg in sorted(CAT_CONFIG.items(), key=lambda x: x[1].get('sort', 99)):
            cat_gender = cfg.get('gender', 'both')
            if cat_gender == 'both' or cat_gender == gender:
                cats.append(cfg['cn'])
        if not cats:
            cats = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '长裤', '短裤',
                    '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
        lines = ['# 服装档案', '', '> AI 自动入库，人工审核中', '']
        for cat in cats:
            lines.append(f'## {cat}')
            lines.append('| ID | 文件名 | 颜色 | 品牌·面料 | 风格标签 | 搭配提示 | 适用场景 |')
            lines.append('|---|---|---|---|---|---|---|')
            lines.append('')
        with open(wardrobe_md, 'w') as f:
            f.write('\n'.join(lines))

    # 初始化 config.json
    config_path = os.path.join(user_dir, 'config.json')
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump({'push_enabled': False}, f, indent=2)

    # 注册
    reg = load_registry()
    if gender not in reg:
        reg[gender] = {}
    if user_id not in reg[gender]:
        reg[gender][user_id] = {
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'last_active': None,
            'status': 'onboarding',
        }
        save_registry(reg)

    return user_dir


def get_user_dir(gender, user_id):
    """获取用户目录路径（不创建）→ users/<gender>/<user_id>/"""
    return os.path.join(USERS_DIR, gender, user_id)


def get_user_profile(gender, user_id):
    """读取用户的 profile.json，返回 dict。不存在返回 None。"""
    profile_path = os.path.join(USERS_DIR, gender, user_id, 'profile.json')
    if not os.path.exists(profile_path):
        return None
    with open(profile_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_user_profile(gender, user_id, profile):
    """保存用户的 profile.json"""
    user_dir = os.path.join(USERS_DIR, gender, user_id)
    os.makedirs(user_dir, exist_ok=True)
    profile_path = os.path.join(user_dir, 'profile.json')
    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def list_users(gender=None):
    """列出所有用户 ID。指定 gender 时只返回该性别的用户。"""
    reg = load_registry()
    if gender:
        return list(reg.get(gender, {}).keys())
    result = []
    for g_users in reg.values():
        result.extend(g_users.keys())
    return result


def list_users_by_gender():
    """返回 {gender: [user_ids]}"""
    reg = load_registry()
    return {g: list(users.keys()) for g, users in reg.items()}


def update_last_active(user_id):
    """更新用户最后活跃时间。跨所有 gender 查找。"""
    reg = load_registry()
    for gender, users in reg.items():
        if user_id in users:
            reg[gender][user_id]['last_active'] = \
                time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            save_registry(reg)
            return True
    return False
