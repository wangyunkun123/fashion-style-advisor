#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户管理器 — 创建/查询/列表，操作 users/_registry.json"""
import os, json, time, shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(BASE_DIR)
USERS_DIR = os.path.join(PROJ_DIR, 'users')
REGISTRY_FILE = os.path.join(USERS_DIR, '_registry.json')

os.makedirs(USERS_DIR, exist_ok=True)

# ── 性别默认值 ──────────────────────────────────────────
GENDER_DEFAULTS = {
    'male': {
        'body': {'height': '172', 'weight': '65', 'shape': 'rectangle', 'skin_tone': 'medium'},
        'default_styles': ['american_ivy_league', 'clean_fit', 'athleisure_sport'],  # 常春藤、干净合身、运动休闲
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
        'default_styles': ['WF-01', 'WF-05', 'WF-06'],  # 法式慵懒、美式休闲、极简
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
    """确保注册文件存在，不存在则创建空注册"""
    if not os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, 'w') as f:
            json.dump({}, f, indent=2)
    with open(REGISTRY_FILE, 'r') as f:
        return json.load(f)


def load_registry():
    """返回 {user_id: {created, last_active, status}}"""
    return _ensure_registry()


def save_registry(reg):
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def user_exists(user_id):
    reg = load_registry()
    return user_id in reg


def create_user(user_id, profile_data=None):
    """创建新用户：建目录 + 初始化 profile.json + 写注册表。
    返回 user_dir 路径。已存在则直接返回。
    """
    user_dir = os.path.join(USERS_DIR, user_id)

    # 建目录结构
    for sub in ['wardrobe', 'wardrobe/tags', 'wardrobe/enhanced',
                'outfits', 'discovered_styles', 'cache']:
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

    # 初始化 profile.json
    profile_path = os.path.join(user_dir, 'profile.json')
    if not os.path.exists(profile_path):
        default_profile = {
            'user_id': user_id,
            'gender': '',  # 待用户选择
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'onboarding_step': 0,  # Step 0 = 性别选择
            'onboarding_complete': False,
            'body': {},
            'style_prefs': [],
        }
        if profile_data:
            default_profile.update(profile_data)
        with open(profile_path, 'w') as f:
            json.dump(default_profile, f, ensure_ascii=False, indent=2)

    # 初始化 服装档案.md（空模板）— 🆕 从 CAT_CONFIG 动态生成，按性别筛选
    wardrobe_md = os.path.join(user_dir, 'wardrobe', '服装档案.md')
    if not os.path.exists(wardrobe_md):
        # 读取用户性别以确定品类列表
        user_gender = 'male'
        if os.path.exists(profile_path):
            try:
                with open(profile_path) as pf:
                    user_gender = json.load(pf).get('gender', 'male') or 'male'
            except Exception:
                pass
        # 从 CAT_CONFIG 获取品类：中性 + 匹配用户性别的专属品类
        try:
            from tools.common import CAT_CONFIG
        except ImportError:
            CAT_CONFIG = {}
        cats = []
        for code, cfg in sorted(CAT_CONFIG.items(), key=lambda x: x[1].get('sort', 99)):
            cat_gender = cfg.get('gender', 'both')
            if cat_gender == 'both' or cat_gender == user_gender:
                cats.append(cfg['cn'])
        # 如果 CAT_CONFIG 不可用，使用基础列表
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
    if user_id not in reg:
        reg[user_id] = {
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'last_active': None,
            'status': 'onboarding',
        }
        save_registry(reg)

    return user_dir


def get_user_dir(user_id):
    """获取用户目录路径（不创建）"""
    return os.path.join(USERS_DIR, user_id)


def list_users():
    """列出所有用户 ID"""
    reg = load_registry()
    return list(reg.keys())


def update_last_active(user_id):
    reg = load_registry()
    if user_id in reg:
        reg[user_id]['last_active'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save_registry(reg)
