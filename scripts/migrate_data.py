#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1: 数据迁移脚本 — 将项目从 flat 结构迁移到 users/<gender>/<user_id>/ 结构

用法:
  python3 scripts/migrate_data.py --dry-run    # 预览模式，不实际执行
  python3 scripts/migrate_data.py              # 执行迁移

迁移映射:
  wardrobe/          → users/male/kun/wardrobe/
  outfits/           → users/male/kun/outfits/
  profile/           → users/male/kun/profile/
  config/user_profile.json → users/male/kun/profile.json (数据源)
  users/alice/       → users/female/nan/
  users/becca/       → users/male/becca/
  styles/*.json      → styles/male/*.json
  styles_women/WF-*/ → styles/female/WF-*/

安全策略:
  - 只复制不删除，旧目录保留到 Phase 9 手动清理
  - --dry-run 模式预览所有操作
  - 目标已存在时跳过（不覆盖）
"""

import os, sys, json, shutil, time, argparse

PROJ_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DRY_RUN = False
COPIED = 0
SKIPPED = 0


def log(msg):
    prefix = '[DRY-RUN] ' if DRY_RUN else ''
    print(f'{prefix}{msg}')


def ensure_dir(path):
    if not DRY_RUN:
        os.makedirs(path, exist_ok=True)
    else:
        log(f'  mkdir: {path}')


def copy_tree(src, dst, ignore_patterns=None):
    """递归复制目录，跳过已存在的文件"""
    global COPIED, SKIPPED
    if not os.path.exists(src):
        log(f'  ⚠️  源不存在，跳过: {src}')
        return

    if DRY_RUN:
        # 统计会复制多少文件
        count = 0
        for root, dirs, files in os.walk(src):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), src)
                dst_file = os.path.join(dst, rel)
                if not os.path.exists(dst_file):
                    count += 1
        log(f'  copy: {src} → {dst} ({count} 个文件)')
        return

    if not os.path.exists(dst):
        os.makedirs(dst, exist_ok=True)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d, ignore_patterns)
        else:
            if os.path.exists(d):
                SKIPPED += 1
            else:
                shutil.copy2(s, d)
                COPIED += 1


def copy_file(src, dst):
    """复制单个文件"""
    global COPIED, SKIPPED
    if not os.path.exists(src):
        log(f'  ⚠️  源文件不存在，跳过: {src}')
        return

    if DRY_RUN:
        if os.path.exists(dst):
            log(f'  skip (已存在): {dst}')
        else:
            log(f'  copy: {src} → {dst}')
        return

    if os.path.exists(dst):
        SKIPPED += 1
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        COPIED += 1


def write_json(path, data):
    if DRY_RUN:
        log(f'  write JSON: {path}')
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 迁移步骤
# ═══════════════════════════════════════════════════════════════

def migrate_kun():
    """迁移主用户 kun（原根级数据）→ users/male/kun/"""
    log('\n📦 迁移主用户: kun (male)')

    # 1. wardrobe/
    log('  衣橱数据...')
    copy_tree(
        os.path.join(PROJ_DIR, 'wardrobe'),
        os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'wardrobe'),
        ignore_patterns=['.DS_Store']
    )

    # 2. outfits/
    log('  穿搭记录...')
    copy_tree(
        os.path.join(PROJ_DIR, 'outfits'),
        os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'outfits'),
        ignore_patterns=['.DS_Store', '.proto_ready']
    )

    # 3. profile/ (个人照片)
    log('  个人照片...')
    copy_tree(
        os.path.join(PROJ_DIR, 'profile'),
        os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'profile'),
        ignore_patterns=['.DS_Store']
    )

    # 4. 从 config/user_profile.json 生成 profile.json
    log('  用户档案...')
    old_profile_path = os.path.join(PROJ_DIR, 'config', 'user_profile.json')
    if os.path.exists(old_profile_path):
        with open(old_profile_path, 'r') as f:
            old = json.load(f)

        # 转换旧格式到新格式
        body = old.get('body', {})
        profile = {
            'user_id': 'kun',
            'gender': 'male',
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'onboarding_step': 4,
            'onboarding_complete': True,
            'onboarding_done_at': old.get('updated_at', ''),
            'body': {
                'height': str(body.get('height_cm', '179')),
                'weight': str(body.get('weight_kg', '68')),
                'shape': 'rectangle' if body.get('body_type') == '偏瘦' else body.get('body_type', 'rectangle'),
                'skin_tone': 'light' if '偏白' in str(body.get('skin_tone', '')) else 'medium',
                'age': str(body.get('age', '31')),
                'shoulder_type': body.get('shoulder_type', '标准'),
                'face_shape': body.get('face_shape', '椭圆脸'),
                'concern': '',
            },
            'style_prefs': ['american_ivy_league', 'clean_fit', 'athleisure_sport'],
            'body_secrets': old.get('body_secrets', ''),
            'lifestyle': old.get('lifestyle', {}),
            'photos': {
                'full_body_front': 'users/male/kun/profile/photos/user_full_front.jpg',
                'full_body_side': 'users/male/kun/profile/photos/user_side.jpg',
                'face_closeup': 'users/male/kun/profile/photos/user_face.jpg',
            },
            'use_my_image': old.get('use_my_image', True),
        }
        write_json(
            os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'profile.json'),
            profile
        )

    # 5. 复制 config.json
    log('  配置文件...')
    old_config = os.path.join(PROJ_DIR, 'config', 'new_items.json')
    if os.path.exists(old_config):
        copy_file(
            old_config,
            os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'config', 'new_items.json')
        )

    # 6. cache 目录
    ensure_dir(os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'cache'))
    ensure_dir(os.path.join(PROJ_DIR, 'users', 'male', 'kun', 'discovered_styles'))


def migrate_nan():
    """迁移 Alice → Nan (female)"""
    log('\n📦 迁移用户: nan (female, 原 alice)')

    src = os.path.join(PROJ_DIR, 'users', 'alice')
    dst = os.path.join(PROJ_DIR, 'users', 'female', 'nan')

    # 复制全部内容
    copy_tree(src, dst, ignore_patterns=['.DS_Store'])

    # 更新 profile.json
    profile_path = os.path.join(dst, 'profile.json')
    if os.path.exists(profile_path):
        with open(profile_path, 'r') as f:
            profile = json.load(f)

        profile['user_id'] = 'nan'
        profile['gender'] = 'female'
        profile['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')

        # 更新照片路径
        if 'photos' in profile:
            for key in profile['photos']:
                old_path = profile['photos'][key]
                if 'users/alice/' in old_path:
                    profile['photos'][key] = old_path.replace('users/alice/', 'users/female/nan/')

        write_json(profile_path, profile)
        log(f'  已更新 profile.json (user_id=nan, gender=female)')

    # 确保必要目录存在
    for sub in ['cache', 'discovered_styles', 'config']:
        ensure_dir(os.path.join(dst, sub))


def migrate_becca():
    """迁移 Becca → users/male/becca/"""
    log('\n📦 迁移用户: becca (male)')

    src = os.path.join(PROJ_DIR, 'users', 'becca')
    dst = os.path.join(PROJ_DIR, 'users', 'male', 'becca')

    copy_tree(src, dst, ignore_patterns=['.DS_Store'])

    # 确保 profile.json 中 gender 正确
    profile_path = os.path.join(dst, 'profile.json')
    if os.path.exists(profile_path):
        with open(profile_path, 'r') as f:
            profile = json.load(f)
        profile['gender'] = 'male'
        write_json(profile_path, profile)

    # 确保必要目录存在
    for sub in ['wardrobe/tags', 'wardrobe/enhanced', 'outfits', 'cache', 'discovered_styles', 'config']:
        ensure_dir(os.path.join(dst, sub))


def migrate_styles():
    """迁移样式库"""
    log('\n📦 迁移样式库')

    # styles/*.json → styles/male/
    src_male = os.path.join(PROJ_DIR, 'styles')
    dst_male = os.path.join(PROJ_DIR, 'styles', 'male')
    log('  男性风格指纹...')
    for f in os.listdir(src_male):
        if f.endswith('.json'):
            copy_file(os.path.join(src_male, f), os.path.join(dst_male, f))

    # styles_women/WF-*/ → styles/female/
    src_female = os.path.join(PROJ_DIR, 'styles_women')
    dst_female = os.path.join(PROJ_DIR, 'styles', 'female')
    log('  女性风格指纹...')
    for item in os.listdir(src_female):
        s = os.path.join(src_female, item)
        if os.path.isdir(s) and item.startswith('WF-'):
            copy_tree(s, os.path.join(dst_female, item))

    # 复制 categories.json
    for fname in ['categories.json', 'README.md', '_shared']:
        s = os.path.join(src_female, fname)
        if os.path.exists(s):
            d = os.path.join(dst_female, fname)
            if os.path.isdir(s):
                copy_tree(s, d)
            else:
                copy_file(s, d)


def create_registry():
    """生成新的 users/_registry.json"""
    log('\n📦 生成用户注册表')

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    registry = {
        'male': {
            'kun': {
                'created': now,
                'last_active': None,
                'status': 'active',
                '_migrated_from': 'root wardrobe/outfits/',
            },
            'becca': {
                'created': '2026-06-23T09:53:46Z',
                'last_active': '2026-06-25T00:51:17Z',
                'status': 'active',
                '_migrated_from': 'users/becca/',
            },
        },
        'female': {
            'nan': {
                'created': '2026-06-23T09:54:27Z',
                'last_active': '2026-06-25T05:33:49Z',
                'status': 'active',
                '_migrated_from': 'users/alice/',
            },
        },
    }

    write_json(os.path.join(PROJ_DIR, 'users', '_registry.json'), registry)
    log(f'  male: {list(registry["male"].keys())}')
    log(f'  female: {list(registry["female"].keys())}')


def verify_migration():
    """验证迁移完整性"""
    if DRY_RUN:
        log('\n✅ [DRY-RUN] 预览完成（未实际执行）')
        return

    log('\n🔍 验证迁移...')
    errors = []

    # 检查 kun
    for sub in ['wardrobe/服装档案.md', 'wardrobe/tags', 'wardrobe/enhanced',
                'outfits', 'profile.json', 'cache', 'config']:
        p = os.path.join(PROJ_DIR, 'users', 'male', 'kun', sub)
        if not os.path.exists(p):
            errors.append(f'kun/{sub} 缺失')

    # 检查 nan
    for sub in ['wardrobe', 'outfits', 'profile.json', 'cache']:
        p = os.path.join(PROJ_DIR, 'users', 'female', 'nan', sub)
        if not os.path.exists(p):
            errors.append(f'nan/{sub} 缺失')

    # 检查 becca
    for sub in ['wardrobe', 'profile.json', 'cache']:
        p = os.path.join(PROJ_DIR, 'users', 'male', 'becca', sub)
        if not os.path.exists(p):
            errors.append(f'becca/{sub} 缺失')

    # 检查样式库
    male_styles = os.path.join(PROJ_DIR, 'styles', 'male')
    female_styles = os.path.join(PROJ_DIR, 'styles', 'female')
    if not os.path.exists(male_styles):
        errors.append('styles/male/ 缺失')
    else:
        n = len([f for f in os.listdir(male_styles) if f.endswith('.json')])
        if n < 18:
            errors.append(f'styles/male/ 只有 {n} 个 JSON（预期 ≥18）')

    if not os.path.exists(female_styles):
        errors.append('styles/female/ 缺失')
    else:
        n = len([d for d in os.listdir(female_styles) if d.startswith('WF-')])
        if n < 50:
            errors.append(f'styles/female/ 只有 {n} 个 WF 目录（预期 ≥50）')

    # 检查注册表
    reg_path = os.path.join(PROJ_DIR, 'users', '_registry.json')
    if not os.path.exists(reg_path):
        errors.append('_registry.json 缺失')

    if errors:
        log(f'❌ {len(errors)} 个问题:')
        for e in errors:
            log(f'   - {e}')
    else:
        log(f'✅ 迁移验证通过！')
        log(f'   复制了 {COPIED} 个文件，跳过 {SKIPPED} 个已存在文件')
        log(f'   旧数据仍在原位置，Phase 9 时手动清理')


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(description='Fashion 项目数据迁移 (Flat → users/<gender>/<user_id>/)')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际执行')
    args = parser.parse_args()

    DRY_RUN = args.dry_run

    log('=' * 60)
    log('Fashion 数据迁移: Flat → users/<gender>/<user_id>/')
    if DRY_RUN:
        log('⚠️  DRY-RUN 模式 — 不会实际修改文件')
    log('=' * 60)

    # 确保目标根目录存在
    ensure_dir(os.path.join(PROJ_DIR, 'users', 'male'))
    ensure_dir(os.path.join(PROJ_DIR, 'users', 'female'))
    ensure_dir(os.path.join(PROJ_DIR, 'styles', 'male'))
    ensure_dir(os.path.join(PROJ_DIR, 'styles', 'female'))

    # 执行迁移
    migrate_kun()
    migrate_nan()
    migrate_becca()
    migrate_styles()
    create_registry()
    verify_migration()

    if not DRY_RUN:
        log(f'\n📊 统计: 复制 {COPIED} 个文件, 跳过 {SKIPPED} 个已存在文件')

    log('\n💡 提示: 旧目录 (wardrobe/, outfits/, users/alice/, users/becca/, styles/, styles_women/)')
    log('   将在 Phase 9 手动删除。在此之前新旧路径共存。')


if __name__ == '__main__':
    main()
