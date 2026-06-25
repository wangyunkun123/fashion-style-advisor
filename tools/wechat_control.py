#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
穿搭助手 — 手机远程控制服务（交互式聊天版）

架构:
  手机浏览器 → HTML聊天面板(ngrok) → HTTP API → Claude管线 → 面板实时显示结果
  同时推送到微信作为备份通知

依赖: 纯 Python 标准库
启动: bash tools/start_wechat_control.sh
"""

import io
import json
import os
import re
import sys
import shutil
import subprocess
import threading
import time
import mimetypes
import collections
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，避免单请求阻塞整个服务"""
    daemon_threads = True  # 主线程退出时自动清理
from urllib.parse import parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
# 确保项目根目录在 sys.path（daemon 线程可能需要）
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'seedream.local.json')

# ── 基础设施层导入（TaskManager/日志/信号/线程安全）──
from tools.server_infra import (
    PROJECT_DIR as _INFRA_PRJ,  # 同值，仅作交叉验证
    LOG_FILE,
    log,
    safe_daemon,
    install_excepthook,
    state as shared_state,  # SharedState 全局实例（别名避免与 do_GET 内的 load_state() 冲突）
    TaskManager,
    setup_signal_handlers,
    collect_health_data,
)
install_excepthook()

# 兼容旧代码的别名（逐步迁移中）
_proto_rebuild_lock = shared_state.proto_rebuild_lock

# ── 天气模块 ──────────────────────────────────────────
from tools.weather_advisor import fetch_weather, analyze_weather

# ── 加载配置 ──────────────────────────────────────────
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

# ── 品类到目录/前缀映射（本地特有，非通用映射）──
CATEGORY_MAP = {
    '短袖上衣': {'dir': '短袖上衣', 'prefix': '上衣'},
    '长袖上衣': {'dir': '长袖上衣', 'prefix': '上衣'},
    '衬衣':     {'dir': '衬衣',     'prefix': '上衣'},
    '背心':     {'dir': '背心',     'prefix': '上衣'},
    '外套':     {'dir': '外套',     'prefix': '外套'},
    '长裤':     {'dir': '长裤',     'prefix': '下装'},
    '短裤':     {'dir': '短裤',     'prefix': '下装'},
    '鞋子':     {'dir': '鞋子',     'prefix': '鞋子'},
    '帽子':     {'dir': '帽子',     'prefix': '帽子'},
    '包':       {'dir': '包',       'prefix': '包'},
    '墨镜':     {'dir': '墨镜',     'prefix': '墨镜'},
    '手部配饰': {'dir': '手部配饰', 'prefix': '配饰'},
    '袜子':     {'dir': '袜子',     'prefix': '袜子'},
    # 🆕 女性品类
    '连衣裙':   {'dir': '连衣裙',   'prefix': '连衣裙'},
    '半身裙':   {'dir': '半身裙',   'prefix': '下装'},
    '连体裤':   {'dir': '连体裤',   'prefix': '连体裤'},
    '女士衬衫': {'dir': '女士衬衫', 'prefix': '上衣'},
    '针织衫':   {'dir': '针织衫',   'prefix': '上衣'},
}

# ── 品类映射（从 common 统一导入）──
from tools.common import (
    CAT_CONFIG, cat_code_to_name as _cat_cn, cat_emoji as _cat_emoji,
    CORE_CATS, ITEM_ID_PATTERN,
    get_git_commit, get_cdn_base, cdn_url,
    get_banned_items as _get_banned_items,
    get_recent_outfits as _get_recent_outfits,
    get_wear_counts,
    parse_outfit_md, load_all_clothing as _load_all_clothing,
    resolve_category_code, add_category_alias,
)

# ── 多用户支持 ────────────────────────────────────────
from tools.user_manager import (
    load_registry as _load_user_registry,
    create_user as _create_user,
    update_last_active as _update_user_active,
)
from tools.common import resolve_user_dir, resolve_wardrobe_dir, resolve_outfits_dir, resolve_tags_dir, resolve_enhanced_dir, set_thread_user
from tools.image_cache import image_cache_get, image_cache_put, resize_image_bytes, pre_compress_dir
from tools.ai_api import call_doubao_chat, extract_json, resize_image_for_api
from tools.photo_utils import get_person_photos, remove_person_background, select_person_photos_for_prompt
from tools.history import load_history, save_history, HISTORY_FILE

# ── _safe_daemon / _global_excepthook 已迁移至 tools.server_infra ──
# 使用 safe_daemon(name, task_manager=tasks) 替代原 _safe_daemon(name)
# install_excepthook() 已在模块导入时调用

def _resolve_user_from_request(handler):
    """从请求中解析用户上下文。返回 (gender, user_id, need_onboarding)。
    优先级：1) URL ?user= + ?gender= 参数  2) Cookie fashion_user  3) 无上下文 → (None, None, False) 触发性别门

    - ?user=kun → 从注册表查 gender，返回 ('male', 'kun', False)
    - ?user=new_user&gender=female → ('female', 'new_user', True) 触发 onboarding
    - 无参数 → (None, None, False)，前端显示性别门
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    qs = parse_qs(parsed.query)
    user_id = qs.get('user', [None])[0]
    gender_from_url = qs.get('gender', [None])[0]

    # Cookie 回退：仅 API 调用不带 ?user= 时从 Cookie 读
    if not user_id:
        is_api = parsed.path.startswith('/api/')
        if is_api:
            cookie_header = handler.headers.get('Cookie', '')
            if cookie_header:
                import re as _re_c
                cm = _re_c.search(r'fashion_user=([^;\s]+)', cookie_header)
                if cm:
                    user_id = cm.group(1)

    # 无用户上下文 → 性别门
    if not user_id or user_id == 'default':
        return (None, None, False)

    # 安全校验
    import re
    if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', user_id):
        return (None, None, False)

    # 从注册表查 gender
    reg = _load_user_registry()
    for g, users in reg.items():
        if user_id in users:
            _update_user_active(user_id)
            return (g, user_id, False)

    # 用户不在注册表 → onboarding。如有 ?gender= 参数则使用
    if gender_from_url in ('male', 'female'):
        return (gender_from_url, user_id, True)

    # 用户不存在且无 gender → 性别门
    return (None, user_id, True)

CATEGORY_CODE_TO_NAME = {k: v['cn'] for k, v in CAT_CONFIG.items()}
CAT_EMOJI = {v['cn']: v['emoji'] for k, v in CAT_CONFIG.items()}
# 品类代码 → emoji 直接映射
CAT_CODE_EMOJI = {k: v['emoji'] for k, v in CAT_CONFIG.items()}

# _get_git_commit / get_banned_items / get_recent_outfit_items
# 已迁移至 tools/common.py，通过顶部 import 直接使用

def _find_item_asset(clothing_id, dir_globs):
    """通用单品资源查找：按优先级遍历 (目录, glob模式) 列表，返回首个匹配的相对路径"""
    import glob as _glob, os as _os
    for dir_spec, pattern_template in dir_globs:
        # 支持 callable（延迟遍历 outfits 子目录）
        if callable(dir_spec):
            for dp in dir_spec():
                if not _os.path.exists(dp): continue
                pattern = _os.path.join(dp, pattern_template.format(cid=clothing_id))
                matches = _glob.glob(pattern)
                if matches:
                    p = _os.path.relpath(matches[0], PROJECT_DIR)
                    return f'{p}?v={int(_os.path.getmtime(matches[0]))}'
        else:
            if not _os.path.exists(dir_spec): continue
            pattern = _os.path.join(dir_spec, pattern_template.format(cid=clothing_id))
            matches = _glob.glob(pattern)
            if matches:
                p = _os.path.relpath(matches[0], PROJECT_DIR)
                return f'{p}?v={int(_os.path.getmtime(matches[0]))}'
    return ''


def _outfit_items_dirs():
    """遍历 outfits/*/items/ 目录，最新优先（多用户感知）"""
    import os as _os
    from tools.common import get_thread_user
    gender, uid = get_thread_user()
    outfits_dir = resolve_outfits_dir(gender, uid) if uid else _os.path.join(PROJECT_DIR, 'outfits')
    if not _os.path.exists(outfits_dir): return
    for d in sorted(_os.listdir(outfits_dir), reverse=True):
        dp = _os.path.join(outfits_dir, d)
        if not _os.path.isdir(dp): continue
        items_dir = _os.path.join(dp, 'items')
        if _os.path.exists(items_dir):
            yield items_dir


def _find_item_thumb(clothing_id):
    """查找单品缩略图（enhanced 优先: cutout_thumb > thumb > cutout → 兜底 outfit items/"""
    import os as _os
    from tools.common import get_thread_user
    gender, uid = get_thread_user()
    if uid:
        enhanced_dir = resolve_enhanced_dir(gender, uid)
    else:
        enhanced_dir = _os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
    gl = [(enhanced_dir, '{cid}_*cutout_thumb*'),
          (enhanced_dir, '{cid}_thumb.*'),
          (enhanced_dir, '{cid}_*cutout.png'),
          (_outfit_items_dirs, '{cid}_*cutout*')]
    return _find_item_asset(clothing_id, gl)


def _find_item_cutout(clothing_id):
    """查找单品抠图大图（enhanced/ 优先 — 用户调整版为准 → 兜底 outfit items/）"""
    import os as _os
    from tools.common import get_thread_user
    gender, uid = get_thread_user()
    if uid:
        enhanced_dir = resolve_enhanced_dir(gender, uid)
    else:
        enhanced_dir = _os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
    gl = [(enhanced_dir, '{cid}_cutout.png'),        # 精确匹配完整抠图，排除缩略图
          (_outfit_items_dirs, '{cid}_*cutout*')]
    return _find_item_asset(clothing_id, gl)


def _find_report_item_thumbnail(item_id):
    """查找报告用的单品缩略图 URL，优先 CDN（多用户感知）"""
    from tools.common import get_thread_user
    gender, uid = get_thread_user()
    if uid:
        enhanced_dir = resolve_enhanced_dir(gender, uid)
        cdn_rel = f'users/{gender}/{uid}/wardrobe/enhanced'
    else:
        enhanced_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
        cdn_rel = 'wardrobe/enhanced'
    thumb_path = os.path.join(enhanced_dir, f'{item_id}_cutout_thumb.png')
    if os.path.exists(thumb_path):
        try:
            h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                             capture_output=True, text=True, cwd=PROJECT_DIR).stdout.strip()
            return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/{cdn_rel}/{item_id}_cutout_thumb.png'
        except Exception:
            return f'/{cdn_rel}/{item_id}_cutout_thumb.png'
    return ''


def _resolve_outfit_style(outfit_dir):
    """从 outfit.md 解析 style_id（与 rating_analyzer.load_all_ratings 逻辑一致）"""
    import re as _re
    md_path = os.path.join(PROJECT_DIR, 'outfits', outfit_dir, 'outfit.md')
    if not os.path.exists(md_path):
        return None
    try:
        from rating_analyzer import STYLE_NAMES, STYLE_NAME_TO_ID, STYLE_KEYWORDS
    except Exception:
        return None
    with open(md_path) as f:
        txt = f.read()
    m = _re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)|^style[：:]\s*(.+)', txt, _re.MULTILINE)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or m.group(3)).strip()
    # 1) 直接匹配 style_id
    if raw in STYLE_NAMES:
        return raw
    # 2) 中文名查表
    for zh_name, sid in STYLE_NAME_TO_ID.items():
        if zh_name.lower().replace(' ', '') in raw.lower().replace(' ', ''):
            return sid
    # 3) 英文名模糊匹配
    for sid in STYLE_NAMES:
        if sid.lower().replace('_', '') in raw.lower().replace('_', '').replace(' ', ''):
            return sid
    # 4) 关键词回退
    raw_lower = raw.lower().replace(' ', '')
    for kw, sid in STYLE_KEYWORDS:
        if kw.replace(' ', '') in raw_lower:
            return sid
    return None


def _find_report_style_image(style_id):
    """查找某风格评分最高的 outfit 效果图 CDN URL（全局扫描）"""
    best_img = ''
    best_rating = -1
    outfits_base = os.path.join(PROJECT_DIR, 'outfits')
    if not os.path.isdir(outfits_base):
        return ''
    for d in sorted(os.listdir(outfits_base), reverse=True):
        rpath = os.path.join(outfits_base, d, 'rating.json')
        img_path = os.path.join(outfits_base, d, '上身效果', '上身效果_1.png')
        if not os.path.exists(rpath) or not os.path.exists(img_path):
            continue
        try:
            with open(rpath) as f:
                r = json.load(f)
            # 从 outfit.md 解析 style_id（rating.json 中可能没有此字段）
            resolved = r.get('style_id') or _resolve_outfit_style(d)
            if resolved == style_id and r.get('rating', 0) > best_rating:
                best_rating = r['rating']
                try:
                    h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                     capture_output=True, text=True, cwd=PROJECT_DIR).stdout.strip()
                    best_img = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/outfits/{d}/上身效果/上身效果_1.png'
                except Exception:
                    best_img = f'/outfits/{d}/上身效果/上身效果_1.png'
        except Exception:
            pass
    return best_img


def _find_report_style_image_for_period(style_id, ratings):
    """从指定周期的评分中找到该风格最高分的 outfit，返回其效果图 CDN URL"""
    best_oid = None
    best_rating = -1
    for r in ratings:
        if r.get('style_id') == style_id and r.get('rating', 0) > best_rating:
            best_rating = r['rating']
            best_oid = r.get('outfit_id')
    if not best_oid:
        return ''
    img_path = os.path.join(PROJECT_DIR, 'outfits', best_oid, '上身效果', '上身效果_1.png')
    if not os.path.exists(img_path):
        return ''
    try:
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                         capture_output=True, text=True, cwd=PROJECT_DIR).stdout.strip()
        return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/outfits/{best_oid}/上身效果/上身效果_1.png'
    except Exception:
        return f'/outfits/{best_oid}/上身效果/上身效果_1.png'


# ── 任务管理器 ────────────────────────────────────────
# TaskManager 已迁移至 tools.server_infra，此处创建实例
tasks = TaskManager()

# ── 历史记录 ──────────────────────────────────────────
# ── 命令执行 ──────────────────────────────────────────
def run_cli(args, cwd=PROJECT_DIR, timeout=300):
    """执行命令并捕获输出"""
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        out = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"❌ 执行失败 (code={result.returncode})\n{err[:800] if err else out[:800]}"
        return out  # 成功但无输出时返回空串，避免噪音
    except subprocess.TimeoutExpired:
        return "⏰ 命令超时，请稍后重试"
    except FileNotFoundError as e:
        return f"❌ 命令未找到: {e}"

def match_command(message):
    """从用户消息中识别指令 → (action, extra)"""
    msg = message.strip()
    if not msg:
        return ('help', '')

    if re.search(r'^(帮助|help|功能|命令|菜单|\?)$', msg, re.I):
        return ('help', '')

    if re.search(r'^(衣橱|我的衣橱|衣柜|wardrobe)$', msg, re.I):
        return ('wardrobe', '')

    if re.search(r'^(今日穿搭|今天穿什么)$', msg, re.I):
        return ('today', '')

    if re.search(r'^(历史推荐|我的最爱|评分记录)$', msg, re.I):
        return ('favorites', '')

    if re.search(r'^(同步|推送|push|上传)$', msg, re.I):
        return ('sync', '')

    if re.search(r'^(状态|status|情况|检查)$', msg, re.I):
        return ('status', '')

    m = re.search(r'(?:生成|效果图|生图|来一张|画一张)(?:[：:\s]*(.+))?', msg)
    if m:
        style = (m.group(1) or '').strip()
        return ('generate', style)

    # 穿搭推荐请求 — 扩展关键词覆盖运动/场景类
    if re.search(r'推荐|穿搭|穿什么|怎么穿|搭配|今天穿|打|运动|约会|通勤|跑步|网球|健身|聚会|度假|户外', msg):
        return ('recommend', msg)

    # 短中文文本默认当作推荐请求（如"晚上打网球"）
    if len(msg) <= 20 and re.search(r'[一-鿿]', msg):
        return ('recommend', msg)

    return ('unknown', msg)

HELP_TEXT = """📱 **穿搭助手 - 指令菜单**
> **推荐穿搭** — AI分析衣柜+天气推荐
> **生成 风格名** — 完整生图流程
> **同步** — 推送到GitHub
> **状态** — 查看文件状态
> **帮助** — 显示本菜单"""

# ── Onboarding 4步向导 ──────────────────────────────────

ONBOARDING_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--navy:#1e3a5f;--navy-light:#2a5080;--text:#1a2838;--sub:#6b7d94;--muted:#94a3b5;--border:#e6ecf3;--bg:#e2e6ec;--white:#fff;--radius:14px;--radius-sm:10px}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;display:flex;justify-content:center}
#onboarding-app{max-width:500px;width:100%;background:#f8fafc;min-height:100vh;position:relative;overflow:hidden}
.progress-bar{position:sticky;top:0;z-index:100;height:4px;background:var(--border);width:100%}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--navy),var(--navy-light));transition:width .4s ease;width:0}
.step{max-width:420px;margin:0 auto;padding:32px 24px 100px;display:none;min-height:60vh}
.step.active{display:block}
.step h2{font-size:24px;font-weight:700;margin-bottom:8px;letter-spacing:-.4px;color:var(--text)}
.step .subtitle{font-size:14px;color:var(--sub);margin-bottom:28px;line-height:1.5}

/* Gender Selection */
.gender-cards{display:flex;gap:16px;margin-bottom:24px}
.gender-card{flex:1;border:2px solid var(--border);border-radius:var(--radius);padding:32px 16px;text-align:center;cursor:pointer;transition:all .2s;background:var(--white)}
.gender-card:hover{border-color:var(--navy-light)}
.gender-card.selected{border-color:var(--navy);background:#f0f4f8;box-shadow:0 2px 12px rgba(30,58,95,.1)}
.gender-card .gender-icon{font-size:56px;margin-bottom:12px;display:block}
.gender-card .gender-name{font-size:18px;font-weight:700;color:var(--text);margin-bottom:4px}
.gender-card .gender-desc{font-size:12px;color:var(--sub);line-height:1.4}

.form-group{margin-bottom:20px}
.form-group label{display:block;font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px;letter-spacing:.3px}
.form-group input,.form-group select{width:100%;padding:14px 16px;border:1.5px solid var(--border);border-radius:12px;font-size:16px;background:var(--white);color:var(--text);transition:border-color .2s;-webkit-appearance:none;appearance:none}
.form-group input:focus,.form-group select:focus{outline:none;border-color:var(--navy);box-shadow:0 0 0 3px rgba(30,58,95,.08)}
.form-row{display:flex;gap:12px}
.form-row .form-group{flex:1}
.shape-options{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.shape-card{border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 10px;text-align:center;cursor:pointer;transition:all .2s;background:var(--white)}
.shape-card:hover{border-color:var(--navy-light)}
.shape-card.selected{border-color:var(--navy);background:#f0f4f8;box-shadow:0 2px 12px rgba(30,58,95,.08)}
.shape-card .shape-icon{font-size:36px;margin-bottom:6px;display:block}
.shape-card .shape-name{font-size:13px;font-weight:600;color:var(--text)}
.shape-card .shape-desc{font-size:11px;color:var(--sub);margin-top:2px}
.style-cards{display:grid;grid-template-columns:1fr 1fr;gap:10px;max-height:420px;overflow-y:auto;padding:2px}
.style-card{border:2px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;cursor:pointer;transition:all .2s;background:var(--white);position:relative}
.style-card:hover{border-color:var(--navy-light)}
.style-card.selected{border-color:var(--navy);box-shadow:0 2px 12px rgba(30,58,95,.1)}
.style-card .card-img{width:100%;height:120px;object-fit:cover;background:#f0f4f8;display:block}
.style-card .card-img-placeholder{width:100%;height:120px;background:linear-gradient(135deg,#f0f4f8,#e6ecf3);display:flex;align-items:center;justify-content:center;font-size:32px;color:var(--muted)}
.style-card .card-info{padding:10px}
.style-card .card-name{font-size:14px;font-weight:700;color:var(--text);margin-bottom:2px}
.style-card .card-tc-badge{font-size:10px;padding:1px 6px;border-radius:8px;margin-right:4px;vertical-align:middle;background:#f0f0f0;color:#888}
.style-card .card-desc{font-size:11px;color:var(--sub);line-height:1.4}
.style-card .card-check{position:absolute;top:8px;right:8px;width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;display:none;align-items:center;justify-content:center;font-size:14px}
.style-card.selected .card-check{display:flex}
.style-limit{font-size:12px;color:var(--sub);text-align:center;margin-top:8px}
.upload-zone{border:2px dashed var(--border);border-radius:var(--radius);padding:40px 20px;text-align:center;cursor:pointer;transition:all .2s;background:var(--white);margin-bottom:16px}
.upload-zone:hover,.upload-zone.dragover{border-color:var(--navy);background:#f0f4f8}
.upload-zone .upload-icon{font-size:48px;margin-bottom:12px;display:block}
.upload-zone .upload-text{font-size:15px;font-weight:600;color:var(--text);margin-bottom:4px}
.upload-zone .upload-hint{font-size:12px;color:var(--sub)}
.upload-zone input[type=file]{display:none}
.upload-preview{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:16px}
.upload-thumb{aspect-ratio:1;border-radius:var(--radius-sm);object-fit:cover;width:100%;border:1px solid var(--border);background:#f0f4f8}
.upload-thumb-wrap{position:relative}
.upload-thumb-wrap .remove-btn{position:absolute;top:4px;right:4px;width:22px;height:22px;border-radius:50%;background:rgba(0,0,0,.6);color:#fff;border:none;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center;line-height:1}
.btn-primary{display:block;width:100%;padding:16px;border:none;border-radius:var(--radius-sm);font-size:17px;font-weight:700;cursor:pointer;background:var(--navy);color:#fff;letter-spacing:.5px;transition:opacity .2s,transform .1s}
.btn-primary:active{opacity:.85;transform:scale(.98)}
.btn-primary:disabled{opacity:.5;pointer-events:none}
.btn-skip{display:block;width:100%;padding:12px;border:none;border-radius:var(--radius-sm);font-size:14px;font-weight:500;cursor:pointer;background:transparent;color:var(--sub);text-align:center;letter-spacing:.3px;transition:color .2s}
.btn-skip:hover{color:var(--text)}
.skip-hint{font-size:12px;color:var(--muted);text-align:center;margin-top:12px;line-height:1.5;padding:0 8px}
.btn-secondary{display:block;width:100%;padding:14px;border:2px solid var(--navy);border-radius:var(--radius-sm);font-size:16px;font-weight:600;cursor:pointer;background:transparent;color:var(--navy);text-align:center;letter-spacing:.3px}
.btn-back{display:inline-flex;align-items:center;gap:6px;font-size:14px;color:var(--sub);cursor:pointer;padding:8px 0;border:none;background:none;margin-bottom:16px}
.waiting{text-align:center;padding:40px 20px}
.waiting .spinner{width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--navy);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 20px}
@keyframes spin{to{transform:rotate(360deg)}}
.waiting .wait-title{font-size:20px;font-weight:700;color:var(--text);margin-bottom:8px}
.waiting .wait-desc{font-size:14px;color:var(--sub);line-height:1.6}
.toast{position:fixed;bottom:100px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;padding:12px 24px;border-radius:24px;font-size:14px;font-weight:600;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none;white-space:nowrap}
.toast.show{opacity:1}
.step-nav{display:flex;gap:10px;margin-top:24px;padding-bottom:20px;align-items:stretch}
.step-nav .btn-secondary{flex:1;white-space:nowrap;padding:14px 16px}
.step-nav .btn-primary{flex:1;min-width:0;white-space:nowrap;padding:14px 16px}
.step-nav .btn-skip{flex:0 0 auto;width:auto;padding:12px 16px}
"""

ONBOARDING_JS = r"""
var currentStep=1;
var selectedGender='';
var selectedShape='';
var selectedStyles=[];
var uploadedFiles=[];
var MAX_STYLES=5;
var TOTAL_STEPS=4;

function showStep(n){
  document.querySelectorAll('.step').forEach(function(el){el.classList.remove('active')});
  var stepEl=document.getElementById('step'+n);
  if(stepEl)stepEl.classList.add('active');
  currentStep=n;
  // 进度条: Step 0 不算进度, Step 1-4 映射到 25%-100%
  var pct=n===0?0:((n)/TOTAL_STEPS*100);
  document.getElementById('progressFill').style.width=pct+'%';
  window.scrollTo(0,0);
}

function toast(msg){
  var t=document.getElementById('toast');
  t.textContent=msg;
  t.classList.add('show');
  clearTimeout(t._tid);
  t._tid=setTimeout(function(){t.classList.remove('show')},2500);
}

// ── Step 0: Gender Selection ──
function selectGender(g){
  selectedGender=g;
  document.querySelectorAll('.gender-card').forEach(function(c){c.classList.remove('selected')});
  var card=document.querySelector('.gender-card[data-gender="'+g+'"]');
  if(card)card.classList.add('selected');
}

function saveStep0(){
  if(!selectedGender){toast('请选择性别');return}
  document.getElementById('btnStep0').disabled=true;
  fetch('/api/onboarding/gender?user='+encodeURIComponent(USER_ID),{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({gender:selectedGender})
  }).then(function(r){return r.json()}).then(function(d){
    if(d.ok){
      // 加载性别对应的风格卡片到全局变量
      if(d.style_cards)STYLE_CARDS=d.style_cards;
      // 渲染身形选项
      if(d.body_shapes)renderBodyShapes(d.body_shapes);
      showStep(1);
    }
    else{toast(d.error||'保存失败')}
    document.getElementById('btnStep0').disabled=false;
  }).catch(function(){toast('网络错误');document.getElementById('btnStep0').disabled=false});
}

// ── Step 1: Body Profile ──
function renderBodyShapes(shapes){
  var container=document.getElementById('shapeOptions');
  if(!shapes||!shapes.length)return;
  var h='';
  shapes.forEach(function(s){
    h+='<div class="shape-card" data-shape="'+escAttr(s.id)+'" onclick="selectShape(\''+escAttr(s.id)+'\')">';
    h+='<span class="shape-icon">'+(s.emoji||'')+'</span>';
    h+='<span class="shape-name">'+escHtml(s.name)+'</span>';
    h+='<span class="shape-desc">'+escHtml(s.desc||'')+'</span>';
    h+='</div>';
  });
  container.innerHTML=h;
}

function selectShape(shape){
  selectedShape=shape;
  document.querySelectorAll('.shape-card').forEach(function(c){c.classList.remove('selected')});
  var card=document.querySelector('.shape-card[data-shape="'+shape+'"]');
  if(card)card.classList.add('selected');
}

function saveStep1(){
  var height=document.getElementById('inpHeight').value.trim();
  var weight=document.getElementById('inpWeight').value.trim();
  var skinTone=document.getElementById('inpSkinTone').value;
  var concern=document.getElementById('inpConcern').value.trim();
  if(!height){toast('请输入身高');return}
  if(!weight){toast('请输入体重');return}
  if(!selectedShape){toast('请选择身形');return}
  doSaveStep1({height:height,weight:weight,shape:selectedShape,skin_tone:skinTone,concern:concern});
}
function skipStep1(){
  // 使用性别默认值，提醒用户后续补充
  toast('已使用默认身形数据，之后可在「我」页面修改');
  var defaults=DEFAULT_BODY||{};
  doSaveStep1({height:defaults.height||'',weight:defaults.weight||'',shape:defaults.shape||'',skin_tone:defaults.skin_tone||'',concern:'',skip:true});
}
function doSaveStep1(data){
  document.getElementById('btnStep1').disabled=true;
  fetch('/api/onboarding/step1?user='+encodeURIComponent(USER_ID),{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)
  }).then(function(r){return r.json()}).then(function(d){
    if(d.ok){showStep(2);renderStep2()}
    else{toast(d.error||'保存失败')}
    document.getElementById('btnStep1').disabled=false;
  }).catch(function(){toast('网络错误');document.getElementById('btnStep1').disabled=false});
}

// ── Step 2: Style Preferences ──
function renderStep2(){
  var container=document.getElementById('step2Cards');
  if(container.innerHTML)return;
  var h='';
  // 分组标签映射
  var tcLabels={popular_trend:'🔥 流行',classic:'🏛️ 经典',niche:'🎭 小众'};
  STYLE_CARDS.forEach(function(s){
    var imgTag=s.img?'<img class="card-img" src="'+escAttr(s.img)+'" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">':'';
    var placeholder='<div class="card-img-placeholder"'+(s.img?' style="display:none"':'')+'>'+escHtml(s.name_zh.charAt(0))+'</div>';
    var tcBadge=s.tc&&tcLabels[s.tc]?'<span class="card-tc-badge">'+tcLabels[s.tc]+'</span>':'';
    h+='<div class="style-card" data-style-id="'+escAttr(s.id)+'" onclick="toggleStyle(\''+escAttr(s.id)+'\')">';
    h+=imgTag+placeholder;
    h+='<div class="card-check">&#10003;</div>';
    h+='<div class="card-info"><div class="card-name">'+tcBadge+escHtml(s.name_zh)+'</div><div class="card-desc">'+escHtml(s.desc)+'</div></div>';
    h+='</div>';
  });
  container.innerHTML=h;
}

function toggleStyle(styleId){
  var idx=selectedStyles.indexOf(styleId);
  if(idx>=0){selectedStyles.splice(idx,1)}
  else if(selectedStyles.length<MAX_STYLES){selectedStyles.push(styleId)}
  else{toast('最多选择 '+MAX_STYLES+' 个风格');return}
  document.querySelectorAll('.style-card').forEach(function(c){
    var sid=c.getAttribute('data-style-id');
    if(selectedStyles.indexOf(sid)>=0){c.classList.add('selected')}
    else{c.classList.remove('selected')}
  });
  document.getElementById('styleCount').textContent=selectedStyles.length;
}

function saveStep2(){
  document.getElementById('btnStep2').disabled=true;
  var data={style_ids:selectedStyles};
  if(selectedStyles.length===0){data.skip=true;data.style_ids=DEFAULT_STYLES||[]}
  fetch('/api/onboarding/step2?user='+encodeURIComponent(USER_ID),{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)
  }).then(function(r){return r.json()}).then(function(d){
    if(d.ok){showStep(3)}
    else{toast(d.error||'保存失败')}
    document.getElementById('btnStep2').disabled=false;
  }).catch(function(){toast('网络错误');document.getElementById('btnStep2').disabled=false});
}

// ── Step 3: Upload Wardrobe ──
function triggerUpload(){
  document.getElementById('fileInput').click();
}
function triggerCamera(){
  document.getElementById('cameraInput').click();
}

function handleFiles(files){
  if(!files||!files.length)return;
  for(var i=0;i<files.length;i++){
    var f=files[i];
    if(!f.type.match(/image\/(jpeg|png|webp|heic|heif)/)){toast(f.name+' 格式不支持');continue}
    if(uploadedFiles.length>=12){toast('最多上传12张');break}
    uploadedFiles.push(f);
    renderPreviews();
    uploadFile(f);
  }
}

function renderPreviews(){
  var container=document.getElementById('uploadPreviews');
  var h='';
  uploadedFiles.forEach(function(f,idx){
    var url=URL.createObjectURL(f);
    h+='<div class="upload-thumb-wrap"><img class="upload-thumb" src="'+url+'" alt=""><button class="remove-btn" onclick="removeFile('+idx+')">&times;</button></div>';
  });
  container.innerHTML=h;
}

function removeFile(idx){
  uploadedFiles.splice(idx,1);
  renderPreviews();
  updateUploadCount();
}

function updateUploadCount(){
  document.getElementById('uploadCount').textContent=uploadedFiles.length;
}

function uploadFile(file){
  var formData=new FormData();
  formData.append('file',file);
  fetch('/api/onboarding/wardrobe/add?user='+encodeURIComponent(USER_ID),{
    method:'POST',
    body:formData
  }).then(function(r){return r.json()}).then(function(d){
    if(!d.ok){toast('上传失败: '+(d.error||'未知'))}
  }).catch(function(){toast('上传出错')});
}

function saveStep3(){
  document.getElementById('btnStep3').disabled=true;
  showStep(4);
  if(uploadedFiles.length>0){
    fetch('/api/onboarding/analyze?user='+encodeURIComponent(USER_ID),{method:'POST'})
      .then(function(r){return r.json()})
      .then(function(d){
        if(d.ok){console.log('Analysis started:',d)}
      }).catch(function(e){console.error('Analyze request error:',e)});
  }else{
    // 跳过上传：提醒用户后续补充
    toast('已跳过 · 随时可在底部「➕添加」栏补充衣橱');
    fetch('/api/onboarding/complete?user='+encodeURIComponent(USER_ID),{method:'POST'})
      .then(function(r){return r.json()})
      .then(function(d){console.log('Onboarding complete:',d);startWaiting()})
      .catch(function(e){console.error(e);startWaiting()});
  }
  // startWaiting moved into callback above to avoid race condition
}

function startWaiting(){
  var dots=0;
  var statusEl=document.getElementById('waitStatus');
  window._waitTimer=setInterval(function(){
    dots=(dots+1)%4;
    var dotStr='';for(var i=0;i<dots;i++)dotStr+='.';
    statusEl.textContent='正在分析你的衣橱'+dotStr;
    fetch('/api/onboarding/status?user='+encodeURIComponent(USER_ID))
      .then(function(r){return r.json()})
      .then(function(d){
        if(d.complete){
          clearInterval(window._waitTimer);
          document.getElementById('progressFill').style.width='100%';
          statusEl.textContent='分析完成！';
          document.getElementById('waitDesc').textContent='AI 已了解你的风格，即将跳转...';
          setTimeout(function(){
            window.location.href='/?user='+encodeURIComponent(USER_ID)+'&t='+Date.now();
          },1500);
        }
      }).catch(function(){});
  },2000);
}

// ── Helpers ──
function escHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function escAttr(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

document.addEventListener('DOMContentLoaded',function(){
  showStep(CURRENT_STEP);
  if(CURRENT_STEP===2)renderStep2();

  document.getElementById('fileInput').addEventListener('change',function(){handleFiles(this.files);this.value=''});
  document.getElementById('cameraInput').addEventListener('change',function(){handleFiles(this.files);this.value=''});

  var dropZone=document.getElementById('dropZone');
  if(dropZone){
    dropZone.addEventListener('dragover',function(e){e.preventDefault();this.classList.add('dragover')});
    dropZone.addEventListener('dragleave',function(e){this.classList.remove('dragover')});
    dropZone.addEventListener('drop',function(e){e.preventDefault();this.classList.remove('dragover');handleFiles(e.dataTransfer.files)});
  }
});
"""


def _extract_style_info(styles_dir, d, sd):
    """从 fingerprint.json 或 encyclopedia.md 提取名称和简介"""
    import re as _re
    name_zh = sd.get('name_zh', '')
    desc = (sd.get('description', '') or '')[:50]
    # 如果 fingerprint.json 没有有效数据，从 encyclopedia.md 提取
    if not name_zh or name_zh == d:
        enc_path = os.path.join(styles_dir, d, 'encyclopedia.md')
        if os.path.exists(enc_path):
            try:
                with open(enc_path) as f:
                    first = f.readline().strip()
                if first.startswith('#'):
                    # 格式: # 中文名（English Name） 或 # 中文名
                    import re as _re
                    m = _re.match(r'^#\s+(.+?)(?:（.*）)?$', first)
                    if m:
                        name_zh = m.group(1).strip()
            except: pass
    if not desc:
        enc_path = os.path.join(styles_dir, d, 'encyclopedia.md')
        if os.path.exists(enc_path):
            try:
                with open(enc_path) as f:
                    in_overview = False
                    for line in f:
                        # 女性格式：一句话定义（优先级最高）
                        if '一句话定义' in line:
                            t = line.split('：', 1)[-1] if '：' in line else line.split(':', 1)[-1]
                            desc = _re.sub(r'[*_#\[\]\(\)]', '', t).strip()[:50]
                            break
                        # 核心美学概括
                        if '核心美学' in line and not desc:
                            t = line.split('：', 1)[-1] if '：' in line else line.split(':', 1)[-1]
                            t = _re.sub(r'\*\*|[*_#\[\]\(\)]', '', t).strip()
                            if len(t) > 8:
                                desc = t[:50]
                        # 男性格式：概述段落
                        if '## 📖 概述' in line:
                            in_overview = True
                            continue
                        if in_overview and not desc and line.strip() and len(line.strip()) > 20:
                            if not line.startswith('#') and not line.startswith('>') and not line.startswith('!') and not line.startswith('- '):
                                clean = _re.sub(r'\*\*|[*_#\[\]()`]', '', line.strip())
                                if not clean.startswith('发源') and not clean.startswith('最后') and not clean.startswith('状态'):
                                    # 去括号 + 取第一句或破折号后内容
                                    clean = _re.sub(r'（[^）]*）', '', clean)
                                    clean = _re.sub(r'\([^)]*\)', '', clean)
                                    m = _re.match(r'^.+?——(.+)$', clean)
                                    if m: clean = m.group(1).strip()
                                    desc = clean
                                    break
            except: pass
    # 精简至22字内，确保卡片完整显示
    desc = (desc or '').strip()
    # 破折号处理：取核心定义
    if '——' in desc:
        parts = desc.split('——')
        pre = parts[0].strip()
        post = parts[1].strip() if len(parts) > 1 else ''
        if len(pre) >= 8:
            desc = pre  # "看似不经意的精致感" 本身就是核心
        elif post:
            # 前段太短，拼接后段首句
            post1 = post.split('。')[0].split('，')[0]
            desc = pre + ' ' + post1
        else:
            desc = pre
    # 取第一句（在。；处断开）
    for sep in ['。', '；']:
        pos = desc.find(sep)
        if 10 < pos < 22:
            desc = desc[:pos]; break
    # 裁剪至22字
    MAX = 22
    if len(desc) > MAX:
        cut = MAX
        for sep in ['，', '、', ' ', '·']:
            pos = desc.rfind(sep, 0, MAX)
            if pos > 10:
                cut = pos; break
        desc = desc[:cut].rstrip('，、 ')
    return name_zh or d, desc

def _load_onboarding_html(user_id, step=1, gender=None):
    """Onboarding 向导 — 性别选择 + 身形 + 风格偏好 + 衣橱上传
    step=0: 性别选择（必须）
    step=1: 身形档案（可跳过）
    step=2: 风格偏好（可跳过）
    step=3: 上传衣橱（可跳过）
    step=4: 等待分析
    """
    import json as _json
    # 尝试从已有 profile 读取 gender（搜索 male 和 female 两个目录）
    if not gender:
        for _g in ('male', 'female'):
            _up = os.path.join(PROJECT_DIR, 'users', _g, user_id, 'profile.json')
            if os.path.exists(_up):
                with open(_up) as f:
                    p = _json.load(f)
                gender = p.get('gender', _g)
                break
    if not gender:
        gender = ''  # 未选择，显示 Step 0

    # 加载风格卡片（按性别路由），按趋势分类排序并精选
    cards = []
    if gender == 'male':
        styles_dir = os.path.join(PROJECT_DIR, 'styles_universal')
        cat_path = os.path.join(PROJECT_DIR, 'styles_universal', 'categories.json')
    else:
        styles_dir = os.path.join(PROJECT_DIR, 'styles/female')
        cat_path = os.path.join(PROJECT_DIR, 'styles/female', 'categories.json')

    # 读取 trend_category 映射
    tc_map = {}
    if os.path.exists(cat_path):
        try:
            with open(cat_path) as f:
                cat_data = _json.load(f)
            for sid, sinfo in cat_data.get('style_registry', {}).items():
                if 'trend_category' in sinfo:
                    tc_map[sid] = sinfo['trend_category']
        except: pass

    if os.path.isdir(styles_dir):
        for d in sorted(os.listdir(styles_dir)):
            if d.startswith('_') or d.startswith('.') or not os.path.isdir(os.path.join(styles_dir, d)):
                continue
            fp = os.path.join(styles_dir, d, 'fingerprint.json')
            sd = {}
            if os.path.exists(fp):
                with open(fp) as f:
                    sd = _json.load(f)
            sid = sd.get('style_id', d)
            # 过滤非风格目录：无 encyclopedia.md 的不展示
            enc_check = os.path.join(styles_dir, d, 'encyclopedia.md')
            if d in ('references', 'templates', 'images_meta.json', 'gallery.html') or not os.path.exists(enc_check):
                continue
            name_zh, desc = _extract_style_info(styles_dir, d, sd)
            # 封面图：优先 representative.jpg
            img = ''
            rep_path = os.path.join(styles_dir, d, 'representative_thumb.jpg')
            if not os.path.exists(rep_path):
                rep_path = os.path.join(styles_dir, d, 'representative.jpg')
            if os.path.exists(rep_path):
                img = f'/{os.path.relpath(styles_dir, PROJECT_DIR)}/{d}/{os.path.basename(rep_path)}'
            if not img:
                img_dir = os.path.join(styles_dir, d, 'images')
                if os.path.isdir(img_dir):
                    imgs = [x for x in os.listdir(img_dir) if x.lower().endswith(('.jpg','.png','.jpeg','.webp'))]
                    if imgs:
                        img = f'/{os.path.relpath(styles_dir, PROJECT_DIR)}/{d}/images/{imgs[0]}'
            cards.append({
                'id': sid,
                'name_zh': name_zh,
                'desc': desc,
                'img': img,
                'tc': tc_map.get(sid, ''),
            })

    # ── 精选展示：流行趋势优先，经典适量，小众点缀 ──
    popular = [c for c in cards if c['tc'] == 'popular_trend']
    classic = [c for c in cards if c['tc'] == 'classic']
    niche = [c for c in cards if c['tc'] == 'niche']
    # 未分类的也加载
    other = [c for c in cards if c['tc'] not in ('popular_trend', 'classic', 'niche')]

    # 精选数量：流行趋势最多 15 个，经典 5 个，小众 2 个
    curated = popular[:15] + classic[:5] + niche[:2] + other
    cards_json = _json.dumps(curated, ensure_ascii=False)

    # 默认风格（跳过时使用）：流行趋势前 3 个
    fallback = (popular[:3] or cards[:3])
    default_styles = [c['id'] for c in fallback]
    default_styles_json = _json.dumps(default_styles, ensure_ascii=False)

    # 身形默认值（按性别）
    if gender == 'male':
        default_body = {'height': '172', 'weight': '65', 'shape': 'rectangle', 'skin_tone': 'medium'}
        body_shapes = [
            {'id': 'inverted_triangle', 'emoji': '🔻', 'name': '倒三角', 'desc': '肩宽臀窄·运动型'},
            {'id': 'rectangle', 'emoji': '📏', 'name': '矩形', 'desc': '肩臀腰相近·匀称'},
            {'id': 'trapezoid', 'emoji': '🔷', 'name': '梯形', 'desc': '肩略宽·腰腹平坦'},
            {'id': 'oval', 'emoji': '🟤', 'name': '椭圆', 'desc': '腰腹丰满·四肢细'},
            {'id': 'lean', 'emoji': '📐', 'name': '瘦长型', 'desc': '骨架窄·偏瘦'},
        ]
        skin_options = [
            {'value': '', 'label': '请选择'},
            {'value': 'fair', 'label': '白皙'},
            {'value': 'light', 'label': '偏白'},
            {'value': 'medium', 'label': '自然'},
            {'value': 'warm', 'label': '暖黄'},
            {'value': 'tan', 'label': '小麦'},
        ]
    else:
        default_body = {'height': '160', 'weight': '55', 'shape': 'pear', 'skin_tone': 'medium'}
        body_shapes = [
            {'id': 'hourglass', 'emoji': '⌛', 'name': '沙漏型', 'desc': '肩臀同宽·腰细'},
            {'id': 'pear', 'emoji': '🍐', 'name': '梨型', 'desc': '肩窄臀宽'},
            {'id': 'apple', 'emoji': '🍎', 'name': '苹果型', 'desc': '腰腹丰满'},
            {'id': 'rectangle', 'emoji': '📏', 'name': '矩形', 'desc': '肩臀腰相近'},
            {'id': 'inverted_triangle', 'emoji': '🔻', 'name': '倒三角', 'desc': '肩宽臀窄'},
            {'id': 'petite', 'emoji': '🌸', 'name': '小个子', 'desc': '160cm 以下'},
        ]
        skin_options = [
            {'value': '', 'label': '请选择'},
            {'value': 'fair', 'label': '白皙'},
            {'value': 'light', 'label': '偏白'},
            {'value': 'medium', 'label': '自然'},
            {'value': 'warm', 'label': '暖黄'},
            {'value': 'tan', 'label': '小麦'},
            {'value': 'dark', 'label': '深色'},
        ]

    default_body_json = _json.dumps(default_body, ensure_ascii=False)
    body_shapes_json = _json.dumps(body_shapes, ensure_ascii=False)

    # Build skin tone options
    skin_opts_html = '\n'.join(
        f'<option value="{o["value"]}">{o["label"]}</option>'
        for o in skin_options
    )

    # Build body shape cards
    shapes_html = '\n'.join(
        f'<div class="shape-card" data-shape="{s["id"]}" onclick="selectShape(\'{s["id"]}\')">'
        f'<span class="shape-icon">{s["emoji"]}</span>'
        f'<span class="shape-name">{s["name"]}</span>'
        f'<span class="shape-desc">{s.get("desc","")}</span></div>'
        for s in body_shapes
    )

    # gender_label for display
    gender_label = {'male': '男性', 'female': '女性'}.get(gender, '')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Fashion Advisor · 欢迎</title>
<style>{ONBOARDING_CSS}</style>
</head>
<body>
<div id="onboarding-app">
<div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>

<!-- Step 0: 性别选择 -->
<div class="step" id="step0">
  <h2>👋 欢迎来到 Fashion Advisor</h2>
  <p class="subtitle">AI 时尚顾问，先告诉我你的性别，我会为你量身推荐</p>
  <div class="gender-cards">
    <div class="gender-card" data-gender="male" onclick="selectGender('male')">
      <span class="gender-icon">👨</span>
      <div class="gender-name">男性</div>
      <div class="gender-desc">亚洲男性穿搭</div>
    </div>
    <div class="gender-card" data-gender="female" onclick="selectGender('female')">
      <span class="gender-icon">👩</span>
      <div class="gender-name">女性</div>
      <div class="gender-desc">亚洲女性穿搭</div>
    </div>
  </div>
  <div class="step-nav">
    <button class="btn-primary" id="btnStep0" onclick="saveStep0()">开始 →</button>
  </div>
</div>

<!-- Step 1: 身形档案 -->
<div class="step" id="step1">
  <button class="btn-back" onclick="showStep(0)">← 返回修改</button>
  <h2>👤 认识你自己</h2>
  <p class="subtitle">告诉我你的基本信息，AI 才能精准推荐{gender_label and '（当前：' + gender_label + '）' or ''}</p>
  <div class="form-row">
    <div class="form-group"><label>身高 (cm)</label><input type="number" id="inpHeight" placeholder="如 {default_body['height']}" inputmode="decimal" value=""></div>
    <div class="form-group"><label>体重 (kg)</label><input type="number" id="inpWeight" placeholder="如 {default_body['weight']}" inputmode="decimal" value=""></div>
  </div>
  <div class="form-group"><label>肤色</label><select id="inpSkinTone">{skin_opts_html}</select></div>
  <div class="form-group"><label>身形类型</label>
    <div class="shape-options" id="shapeOptions">
      {shapes_html}
    </div>
  </div>
  <div class="form-group"><label>穿衣困扰（选填）</label><input type="text" id="inpConcern" placeholder="如：腿粗、没腰线、不会配色..."></div>
  <div class="step-nav">
    <button class="btn-primary" id="btnStep1" onclick="saveStep1()">下一步 →</button>
  </div>
  <button class="btn-skip" onclick="skipStep1()">跳过此步 · 使用默认值</button>
  <p class="skip-hint">💡 之后可在底部「我的」页面补充身形数据，有了准确数据 AI 才能给出更精准的推荐</p>
</div>

<!-- Step 2: 风格偏好 -->
<div class="step" id="step2">
  <button class="btn-back" onclick="showStep(1)">← 返回修改</button>
  <h2>🎨 你喜欢什么风格？</h2>
  <p class="subtitle">选 1~5 个喜欢的风格，也可以先跳过，后续 AI 会根据你的身形特征和衣橱单品自动匹配最适合的风格</p>
  <div class="style-cards" id="step2Cards"></div>
  <p class="style-limit">已选 <span id="styleCount">0</span>/5</p>
  <div class="step-nav">
    <button class="btn-secondary" onclick="showStep(1)">← 上一步</button>
    <button class="btn-primary" id="btnStep2" onclick="saveStep2()">下一步 →</button>
  </div>
  <button class="btn-skip" onclick="saveStep2()">跳过 · 让 AI 自动为我匹配</button>
</div>

<!-- Step 3: 上传衣橱 -->
<div class="step" id="step3">
  <button class="btn-back" onclick="showStep(2)">← 返回修改</button>
  <h2>👚 上传你的衣橱</h2>
  <p class="subtitle">拍几件常穿的衣服，AI 会记住它们为你搭配。这是唯一需要你亲自动手的环节，但也是最关键的——有了真实衣橱数据，推荐才真正属于你</p>
  <div class="upload-zone" id="dropZone" onclick="triggerUpload()">
    <span class="upload-icon">📸</span>
    <div class="upload-text">点击拍照或选择照片</div>
    <div class="upload-hint">支持 JPG/PNG/HEIC，每件一张平铺图效果最好<br>已上传 <span id="uploadCount">0</span> 件</div>
    <input type="file" id="fileInput" accept="image/*" multiple>
    <input type="file" id="cameraInput" accept="image/*" capture="environment">
  </div>
  <button class="btn-secondary" onclick="triggerCamera()" style="margin-bottom:12px">📷 拍照</button>
  <div class="upload-preview" id="uploadPreviews"></div>
  <div class="step-nav">
    <button class="btn-secondary" onclick="showStep(2)">← 上一步</button>
    <button class="btn-primary" id="btnStep3" onclick="saveStep3()">完成，开始分析 →</button>
  </div>
  <button class="btn-skip" onclick="saveStep3()">暂时跳过 · 之后在「添加」中随时补充</button>
  <p class="skip-hint">📸 这一步最花时间，但也最值得——衣服是你独有的，AI 需要认识它们。现在跳过的话，之后可以随时在底部「➕添加」栏一件一件录入</p>
</div>

<!-- Step 4: 等待分析 -->
<div class="step" id="step4">
  <div class="waiting">
    <div class="spinner"></div>
    <div class="wait-title">正在分析你的风格</div>
    <div class="wait-desc">
      <div id="waitStatus">正在分析你的衣橱...</div>
      <div id="waitDesc" style="margin-top:8px;font-size:13px;color:var(--sub)">AI 正在了解你的偏好<br>预计需要 30~60 秒</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>
</div>

<script>
var USER_ID = "{user_id}";
var CURRENT_STEP = {step};
var STYLE_CARDS = {cards_json};
var DEFAULT_STYLES = {default_styles_json};
var DEFAULT_BODY = {default_body_json};
var BODY_SHAPES = {body_shapes_json};
{ONBOARDING_JS}
</script>
</body>
</html>"""

# ── 管线核心 ──────────────────────────────────────────
def get_github_raw_url(file_path):
    rel = os.path.relpath(file_path, PROJECT_DIR)
    # 加时间戳避免浏览器/GitHub CDN 缓存旧图
    cache_buster = int(time.time())
    return f"https://raw.githubusercontent.com/wangyunkun123/fashion-style-advisor/main/{rel}?t={cache_buster}"

# get_banned_items / get_recent_outfit_items
# 已迁移至 tools/common.py，通过 _get_banned_items / _get_recent_outfits 使用

# ── 衣柜解析 ──────────────────────────────────────────
def parse_wardrobe():
    """解析 wardrobe/服装档案.md → {ID: {category, filename, color, name}}"""
    wardrobe_md = os.path.join(PROJECT_DIR, 'wardrobe', '服装档案.md')
    items = {}
    current_category = None
    with open(wardrobe_md, 'r') as f:
        for line in f:
            line = line.rstrip()
            # 匹配品类标题
            m = re.match(r'^## (.+)', line)
            if m:
                current_category = m.group(1).strip()
                continue
            # 匹配表格行: | ID | filename | color | ... | ... | remarks |
            m = re.match(
                r'^\|\s*(\w+-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|',
                line
            )
            if m and current_category:
                item_id = m.group(1)
                filename = m.group(2).strip()
                color = m.group(3).strip()
                # 提取单品名（从备注或颜色+品类推断）
                name = f"{color}{current_category.replace('上衣','').replace('下装','')}"
                items[item_id] = {
                    'category': current_category,
                    'filename': filename,
                    'color': color,
                    'name': name,
                }
    return items

def get_wardrobe_summary():
    """从 JSON 标签动态生成衣柜摘要，确保 AI 始终看到最新标签（单点真相）"""
    tags_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
    wardrobe_md = os.path.join(PROJECT_DIR, 'wardrobe', '服装档案.md')

    # 先从 markdown 读取文件名映射（保持向后兼容）
    filename_map = {}
    try:
        with open(wardrobe_md, 'r') as f:
            for line in f:
                m = re.match(r'^\|\s*(\w+-\d+)\s*\|\s*([^|]+?)\s*\|', line)
                if m:
                    filename_map[m.group(1)] = m.group(2).strip()
    except:
        pass

    # 从 JSON 标签读取所有单品
    cats = {}
    for fname in sorted(os.listdir(tags_dir)):
        if fname == 'SCORE_CACHE.json' or not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(tags_dir, fname)) as f:
                d = json.load(f)
        except:
            continue
        cid = d.get('clothing_id', '')
        if not cid:
            continue
        # 过滤已归档/删除的单品
        if (d.get('meta') or {}).get('archived'):
            continue
        cat = d.get('category', '其他')
        brand = (d.get('brand') or {}).get('name', '') or ''
        collection = (d.get('brand') or {}).get('collection', '') or ''
        color = (d.get('color') or {}).get('hue_name', '') or ''
        styles = d.get('style_modifiers', [])
        occasions = d.get('occasions', [])
        comment = (d.get('meta') or {}).get('claude_fit_comment', '') or ''
        filename = filename_map.get(cid, '')
        if cat not in cats:
            cats[cat] = []
        cats[cat].append({
            'id': cid, 'brand': brand, 'collection': collection,
            'color': color, 'styles': styles, 'occasions': occasions,
            'comment': comment, 'filename': filename,
        })

    # 按固定品类顺序输出
    cat_order = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '长裤', '短裤',
                 '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
    lines = []
    for cat in cat_order:
        if cat not in cats:
            continue
        lines.append(f'## {cat}')
        lines.append('| ID | 品牌·系列 | 颜色 | 风格标签 | 适用场景 | 穿搭提示 |')
        lines.append('|-----|----------|------|---------|---------|---------|')
        for it in cats[cat]:
            brand_str = it['brand']
            if it['collection']:
                brand_str += ' ' + it['collection']
            if not brand_str:
                brand_str = '—'
            # 截断品牌名避免表格过宽
            brand_str = brand_str[:24]
            # 风格标签：取风格修饰符中非身形相关的
            scene_tags = [s for s in it['styles']
                          if not any(kw in s for kw in ['增加', '显白', '显瘦', '拉长', '遮盖', '修饰', '无明显'])]
            styles_str = ' · '.join(scene_tags) if scene_tags else '—'
            # 适用场景：直接来自 occasions 字段
            occ_str = '、'.join(it['occasions']) if it['occasions'] else '日常'
            comment_short = it['comment'][:50] if it['comment'] else '—'
            lines.append(f'| {it["id"]} | {brand_str} | {it["color"]} | {styles_str} | {occ_str} | {comment_short} |')
        lines.append('')

    return '\n'.join(lines)

# ── 衣橱入库辅助函数 ──────────────────────────────────

def _id_exists_on_disk(cid, uid=None):
    """检查某个 clothing ID 的标签文件是否已存在（多用户感知）"""
    tags_dir = resolve_tags_dir(uid)
    tag_path = os.path.join(tags_dir, f'{cid}.json')
    return os.path.exists(tag_path)

def _get_next_id(category_code, uid=None):
    """扫描用户 wardrobe/tags/ 获取某品类下一个可用 ID"""
    existing = []
    tags_dir = resolve_tags_dir(uid)
    if os.path.isdir(tags_dir):
        for fn in os.listdir(tags_dir):
            if fn.startswith(f'{category_code}-') and fn.endswith('.json'):
                m = re.search(rf'{category_code}-(\d+)', fn)
                if m:
                    existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    return f'{category_code}-{next_num:03d}'


_wardrobe_lock = threading.Lock()  # 保护服装档案.md 和 new_items.json 的并发写入

def _ensure_wardrobe_md(user_dir, uid=None):
    """确保 服装档案.md 存在，不存在则自动生成（自愈）"""
    md_path = os.path.join(user_dir, 'wardrobe', '服装档案.md')
    if os.path.exists(md_path):
        return md_path
    # 自愈：从 CAT_CONFIG 动态生成品类列表
    log(f"🩹 自愈: 重建服装档案.md ({uid or 'default'})")
    try:
        from tools.user_manager import create_user as _cu
        _cu(uid) if uid else None
        # create_user 内部已处理 服装档案.md 的创建
        if os.path.exists(md_path):
            return md_path
    except Exception:
        pass
    # Fallback: 手动生成
    user_gender = 'male'
    profile_path = os.path.join(user_dir, 'profile.json')
    if os.path.exists(profile_path):
        try:
            with open(profile_path) as pf:
                user_gender = json.load(pf).get('gender', 'male') or 'male'
        except Exception:
            pass
    try:
        from tools.common import CAT_CONFIG
    except ImportError:
        CAT_CONFIG = {}
    cats = []
    for code, cfg in sorted(CAT_CONFIG.items(), key=lambda x: x[1].get('sort', 99)):
        cat_gender = cfg.get('gender', 'both')
        if cat_gender == 'both' or cat_gender == user_gender:
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
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, 'w') as f:
        f.write('\n'.join(lines))
    log(f"🩹 服装档案.md 已自动生成 ({len(cats)} 个品类)")
    return md_path


def _append_to_wardrobe_md(cid, category_name, filename, tag_data, uid=None):
    """向用户 wardrobe/服装档案.md 对应品类表格追加一行"""
    user_dir = resolve_user_dir(uid)
    md_path = os.path.join(user_dir, 'wardrobe', '服装档案.md')
    if not os.path.exists(md_path):
        md_path = _ensure_wardrobe_md(user_dir, uid)

    with _wardrobe_lock:
        with open(md_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 找到品类章节和其表格的 |---| 分隔行
        cat_header = f'## {category_name}'
        in_section = False
        insert_after = -1

        for i, line in enumerate(lines):
            if line.strip() == cat_header:
                in_section = True
                continue
            if in_section and line.startswith('|---'):
                insert_after = i
                # 往后找该表格的最后一行数据
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith('|') and not lines[j].startswith('|---'):
                        insert_after = j
                    elif not lines[j].startswith('|') and lines[j].strip():
                        break  # 遇到非表格内容，停止
                break

        if insert_after < 0:
            # 🆕 品类章节不存在 — 自动创建（支持新增品类）
            log(f"品类 {category_name} 章节不存在，自动创建", "INFO")
            # 构建新章节
            cat_emoji_str = _cat_emoji(cid.split('-')[0]) if '-' in cid else '👔'
            new_section = [
                f'\n## {category_name}\n',
                f'\n',
                f'| ID | 图片 | 颜色 | 品牌/面料 | 风格标签 | 适配说明 | 场景 |\n',
                f'|----|------|------|-----------|----------|----------|------|\n',
            ]
            # 追加到文件末尾
            lines.extend(['\n'] + new_section)
            insert_after = len(lines) - 1

        # 构建新行
        color_info = tag_data.get('color', {})
        color_str = color_info.get('hue_name', '未知')
        brand_info = tag_data.get('brand', {})
        fabric_info = tag_data.get('fabric', {})
        style_tags = '、'.join(tag_data.get('style_modifiers', [])) or '基础款'
        occasions = '、'.join(tag_data.get('occasions', [])) or '日常'
        fit_comment = tag_data.get('meta', {}).get('claude_fit_comment', '')
        fit_note = fit_comment[:40] if fit_comment else 'AI 识别入库'

        new_row = f'| {cid} | {filename} | {color_str} | {brand_info.get("name", "")} {fabric_info.get("primary", "")} | {style_tags} | {fit_note} | {occasions} |\n'

        lines.insert(insert_after + 1, new_row)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    log(f"已追加到服装档案: {cid}")


def _register_new_item(cid, category_name, uid=None):
    """注册新单品到用户 config/new_items.json"""
    user_dir = resolve_user_dir(uid)
    new_path = os.path.join(user_dir, 'config', 'new_items.json')
    with _wardrobe_lock:
        items = {}
        if os.path.exists(new_path):
            try:
                with open(new_path, 'r') as f:
                    items = json.load(f).get('items', {})
            except Exception as _e:
                # 损坏时备份，避免丢失所有注册记录
                _bak = new_path + '.bak.' + time.strftime('%Y%m%d%H%M%S')
                try:
                    shutil.copy2(new_path, _bak)
                    log(f"⚠️ new_items.json 损坏，已备份至 {_bak}", "WARN")
                except Exception:
                    pass
                log(f"⚠️ new_items.json 读取失败，重置为空: {_e}", "ERROR")
        items[cid] = {
            'added_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'category': category_name,
        }
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        with open(new_path, 'w') as f:
            json.dump({'items': items}, f, ensure_ascii=False, indent=2)


def _finalize_add_item(item_data):
    """执行完整的衣橱入库流程：复制图片 → 增强 → 写标签 → 更新档案 → 注册新单品"""
    cid = item_data.get('override_id') or item_data.get('suggested_id')
    if not cid:
        raise ValueError("缺少 clothing ID")

    # 多用户：从 item_data 或线程上下文获取 user_id
    _gender, uid = get_thread_user()
    uid = item_data.get('_user_id') or uid
    user_dir = resolve_user_dir(_gender, uid)
    wardrobe_dir = os.path.join(user_dir, 'wardrobe')
    tags__dir = os.path.join(wardrobe_dir, 'tags')
    enhanced__dir = os.path.join(wardrobe_dir, 'enhanced')

    # 🛡️ 防御：确保用户基础设施完备（自愈 onboarding 未完整创建的场景）
    _ensure_wardrobe_md(user_dir, uid)
    os.makedirs(tags__dir, exist_ok=True)
    os.makedirs(enhanced__dir, exist_ok=True)
    # 确保 config/ 目录和 new_items.json 存在
    _config_dir = os.path.join(user_dir, 'config')
    os.makedirs(_config_dir, exist_ok=True)
    _new_items_path = os.path.join(_config_dir, 'new_items.json')
    if not os.path.exists(_new_items_path):
        with open(_new_items_path, 'w') as _nf:
            json.dump({'items': {}}, _nf)

    # 防止多批次并发时的 ID 碰撞：入库前重新检查 ID 是否已被占用
    # 加锁确保 check → assign → write 在同一临界区内
    category_code = item_data.get('category_code', '')
    with _wardrobe_lock:
        if category_code and _id_exists_on_disk(cid, uid):
            prefix = category_code
            existing = []
            os.makedirs(tags__dir, exist_ok=True)
            for fn in os.listdir(tags__dir):
                if fn.startswith(f'{prefix}-') and fn.endswith('.json'):
                    m = re.search(rf'{prefix}-(\d+)', fn)
                    if m:
                        existing.append(int(m.group(1)))
            next_num = max(existing) + 1 if existing else 1
            new_cid = f'{prefix}-{next_num:03d}'
            log(f"⚠️ ID 碰撞: {cid} 已被占用，自动分配 {new_cid}")
            cid = new_cid
            item_data['suggested_id'] = cid

    category_name = item_data.get('category', '')

    # 获取品类目录名
    cat_info = CATEGORY_MAP.get(category_name, {})
    cat_dir = cat_info.get('dir', category_name)

    # 1. 复制原图到品类目录
    src_img = item_data.get('_temp_image_path', '')
    if not src_img or not os.path.exists(src_img):
        raise ValueError(f"临时图片不存在: {src_img}")

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    dest_dir = os.path.join(wardrobe_dir, cat_dir)
    os.makedirs(dest_dir, exist_ok=True)
    dest_filename = f'Image_{timestamp}_{cid}.jpg'
    dest_path = os.path.join(dest_dir, dest_filename)

    # 🆕 清理同一 ID 的旧图片（重新入库/覆盖场景），避免衣橱出现重复图
    try:
        for _old_fn in os.listdir(dest_dir):
            if _old_fn.endswith(f'_{cid}.jpg'):
                _old_path = os.path.join(dest_dir, _old_fn)
                if _old_path != dest_path:
                    os.remove(_old_path)
                    log(f"🗑️ 清理旧图: {_old_path}")
    except Exception:
        pass

    shutil.copy2(src_img, dest_path)
    log(f"图片已复制: {dest_path}")

    # 2. 基础图片处理（不跑 rembg 抠图——太耗内存/CPU，后台异步补做）
    _image_ok = True
    try:
        from PIL import Image as _PILImage, ImageOps as _ImageOps, ImageFile as _ImageFile
        _ImageFile.LOAD_TRUNCATED_IMAGES = True
        img = _PILImage.open(dest_path)
        img = _ImageOps.exif_transpose(img)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        # 🆕 AI 方向检测：用视觉模型判断领口朝向，精确旋转
        w, h = img.size
        _rotated = False
        try:
            from tools.auto_orient import ask_orientation
            _tmp_path = os.path.join(enhanced__dir, f'_orient_tmp_{cid}.jpg')
            img.save(_tmp_path, 'JPEG', quality=85)
            _orient = ask_orientation(_tmp_path)
            os.remove(_tmp_path) if os.path.exists(_tmp_path) else None
            if _orient in ('左', '右', '下'):
                _rotate_map = {'左': _PILImage.ROTATE_270, '右': _PILImage.ROTATE_90, '下': _PILImage.ROTATE_180}
                img = img.transpose(_rotate_map[_orient])
                if _orient in ('左', '右'):
                    w, h = h, w
                _rotated = True
                log(f"🧭 {cid} AI方向检测: 上端在{_orient} → 已旋转")
        except Exception:
            pass
        # 回退：AI 检测失败时用简单横竖判断
        if not _rotated and w > h:
            img = img.transpose(_PILImage.ROTATE_90)
            w, h = h, w
            log(f"🔄 {cid} 横图→竖图旋转 (回退)")
        # 🆕 亮度校正：仅调亮度，不动色相/白平衡
        try:
            import numpy as _np_bri
            _bri_arr = _np_bri.array(img).astype(float)
            _lum = 0.299 * _bri_arr[:,:,0] + 0.587 * _bri_arr[:,:,1] + 0.114 * _bri_arr[:,:,2]
            _avg_lum = _lum.mean()
            if _avg_lum < 100:
                _factor = min(1.25, 110 / max(_avg_lum, 1))
                _bri_arr = _np_bri.clip(_bri_arr * _factor, 0, 255)
                img = _PILImage.fromarray(_bri_arr.astype(np.uint8))
                log(f"🔆 {cid} 亮度校正: {_avg_lum:.0f} → {_avg_lum*_factor:.0f}")
        except Exception:
            pass
        # 缩放到最长边 1200px
        if max(w, h) > 1200:
            ratio = 1200 / max(w, h)
            img = img.resize((int(w*ratio), int(h*ratio)), _PILImage.LANCZOS)
        # 保存处理后的大图到 enhanced/
        os.makedirs(enhanced__dir, exist_ok=True)
        # 🆕 清理旧 enhanced 图（同 ID 覆盖场景）
        try:
            for _old_fn in os.listdir(enhanced__dir):
                if f'_{cid}' in _old_fn and (_old_fn.endswith('.jpg') or _old_fn.endswith('.png')):
                    os.remove(os.path.join(enhanced__dir, _old_fn))
        except Exception:
            pass
        enhanced_jpg = os.path.join(enhanced__dir, dest_filename)
        img.save(enhanced_jpg, 'JPEG', quality=85, optimize=True)
        # 生成缩略图（200px 宽）
        thumb_w = 200
        if w > thumb_w:
            ratio = thumb_w / w
            thumb = img.resize((thumb_w, int(h*ratio)), _PILImage.LANCZOS)
        else:
            thumb = img.copy()
        thumb_path = os.path.join(enhanced__dir, f'{cid}_cutout_thumb.png')
        thumb.save(thumb_path, 'PNG', optimize=True)
        log(f"图片处理完成: {cid} (缩略图 {os.path.getsize(thumb_path)//1024}KB)")
    except Exception as e:
        log(f"图片处理失败（非致命，标签已标记）: {e}", "WARN")
        _image_ok = False

    # 🆕 2.5 白底提取的透明 PNG → 保存到 enhanced/ 并重新生成透明缩略图
    _clean_png = item_data.get('_clean_png_bytes', b'')
    if _clean_png:
        try:
            cutout_path = os.path.join(enhanced__dir, f'{cid}_cutout.png')
            with open(cutout_path, 'wb') as _f:
                _f.write(_clean_png)
            # 用透明 PNG 重新生成缩略图（白底合成）
            _png_img = _PILImage.open(_io.BytesIO(_clean_png))
            _png_w, _png_h = _png_img.size
            _thumb_w = 200
            if _png_img.mode == 'RGBA':
                _white_bg = _PILImage.new('RGB', _png_img.size, (255, 255, 255))
                _white_bg.paste(_png_img, mask=_png_img.split()[3])
                _png_img = _white_bg
            if _png_w > _thumb_w:
                _ratio = _thumb_w / _png_w
                _png_thumb = _png_img.resize((_thumb_w, int(_png_h * _ratio)), _PILImage.LANCZOS)
            else:
                _png_thumb = _png_img.copy()
            _png_thumb.save(thumb_path, 'PNG', optimize=True)
            log(f"透明抠图已保存: {cid} (cutout.png + 白底缩略图)")
            _image_ok = True
        except Exception as _ce:
            log(f"透明抠图保存失败（非致命）: {_ce}", "WARN")
    else:
        # 🆕 产品图兜底：无 SegFormer 抠图 → 用 rembg 自动去背景
        try:
            from rembg import remove as _rembg_remove
            import io as _bg_io
            _bg_input = _bg_io.BytesIO()
            img.save(_bg_input, format='PNG')
            _bg_input.seek(0)
            _bg_output = _rembg_remove(_bg_input.read())
            _clean_png = _bg_output
            # 保存透明 PNG 并生成透明缩略图
            cutout_path = os.path.join(enhanced__dir, f'{cid}_cutout.png')
            with open(cutout_path, 'wb') as _f:
                _f.write(_bg_output)
            _png_img = _PILImage.open(_bg_io.BytesIO(_bg_output))
            _png_w, _png_h = _png_img.size
            _thumb_w = 200
            if _png_img.mode == 'RGBA':
                _white_bg = _PILImage.new('RGB', _png_img.size, (255, 255, 255))
                _white_bg.paste(_png_img, mask=_png_img.split()[3])
                _png_img = _white_bg
            if _png_w > _thumb_w:
                _ratio = _thumb_w / _png_w
                _png_thumb = _png_img.resize((_thumb_w, int(_png_h * _ratio)), _PILImage.LANCZOS)
            else:
                _png_thumb = _png_img.copy()
            _png_thumb.save(thumb_path, 'PNG', optimize=True)
            log(f"🎯 rembg 产品图抠图完成: {cid}")
            _image_ok = True
        except Exception as _rbe:
            log(f"rembg 抠图失败（非致命）: {_rbe}", "WARN")

    # 3. 构建标签 JSON
    tag_data = {
        'clothing_id': cid,
        'category': category_name,
        'category_code': category_code,
        'color': item_data.get('color', {}),
        'silhouette': item_data.get('silhouette', {}),
        'pattern': item_data.get('pattern', {}),
        'fabric': item_data.get('fabric', {}),
        'formality': item_data.get('formality', 3),
        'brand': item_data.get('brand', {}),
        'style_modifiers': item_data.get('style_modifiers', []),
        'meta': item_data.get('meta', {
            'is_key_piece': False,
            'is_statement_piece': False,
            'wear_count': 0,
            'last_worn': None,
            'claude_fit_comment': '',
        }),
        'occasions': item_data.get('occasions', []),
    }
    if not _image_ok:
        tag_data.setdefault('meta', {})['missing_images'] = True

    # 4. 写入标签 JSON（多用户感知路径）
    os.makedirs(tags__dir, exist_ok=True)
    tag_path = os.path.join(tags__dir, f'{cid}.json')
    with open(tag_path, 'w', encoding='utf-8') as f:
        json.dump(tag_data, f, ensure_ascii=False, indent=2)
    log(f"标签已写入: {tag_path}")
    # 🆕 Phase 3: 自动推荐匹配风格
    try:
        from wardrobe_cluster import recommend_styles_for_item as _auto_styles
        auto_styles = _auto_styles(tag_data)
        if auto_styles:
            tag_data['recommended_styles'] = auto_styles
            with open(tag_path, 'w', encoding='utf-8') as f:
                json.dump(tag_data, f, ensure_ascii=False, indent=2)
            log(f"自动推荐风格: {cid} → {auto_styles}")
    except Exception as _se:
        log(f"风格推荐跳过: {_se}", "WARN")


    # 5. 追加到服装档案
    _append_to_wardrobe_md(cid, category_name, dest_filename, tag_data, uid)

    # 6. 注册新单品
    _register_new_item(cid, category_name, uid)

    # 7. 返回结果（⚠️ 不在此处删临时图片——多件单品共享同源图时会互相踩踏）
    # 临时图片由调用方（confirm handler）统一清理

    return {
        'clothing_id': cid,
        'category': category_name,
        'name': f'{tag_data["brand"].get("name", "")} {tag_data["color"].get("hue_name", "")}{category_name}'.strip(),
        '_source_image': src_img,  # 返回源图路径供调用方统一清理
    }


def match_for_new_item(new_item_tags):
    """根据新衣标签，在现有衣橱中匹配可搭配的单品。

    参数:
        new_item_tags: dict, AI 分析出的新衣标签（与 tags JSON 同结构）

    返回:
        {category_code: [{id, name, brand, color, thumb, score, match_reasons}]}
    """
    # 多用户隔离：从当前线程上下文获取用户ID
    from tools.common import get_thread_user as _gtu
    _mgender, _muid = _gtu()
    tags_dir = resolve_tags_dir(_mgender, _muid) if _muid else os.path.join(PROJECT_DIR, 'wardrobe', 'tags')

    # 加载所有衣橱单品标签
    wardrobe_items = {}
    for fn in sorted(os.listdir(tags_dir)):
        if fn == 'SCORE_CACHE.json' or not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(tags_dir, fn)) as f:
                d = json.load(f)
        except:
            continue
        cid = d.get('clothing_id', '')
        if not cid or (d.get('meta') or {}).get('archived'):
            continue
        wardrobe_items[cid] = d

    # 确定新衣的品类和互补品类
    new_cat = new_item_tags.get('category', '')
    new_cat_code = new_item_tags.get('category_code', '')

    # 互补品类映射：新衣品类 → 需要匹配的品类
    complementary_cats = {
        'TS': ['PT', 'SH', 'SHOE', 'JK', 'HAT', 'BAG'],
        'LS': ['PT', 'SH', 'SHOE', 'JK', 'HAT', 'BAG'],
        'SHIRT': ['PT', 'SH', 'SHOE', 'JK', 'BAG'],
        'TANK': ['PT', 'SH', 'SHOE', 'HAT'],
        'JK': ['TS', 'LS', 'SHIRT', 'PT', 'SH', 'SHOE', 'BAG'],
        'PT': ['TS', 'LS', 'SHIRT', 'TANK', 'SHOE', 'JK', 'BAG'],
        'SH': ['TS', 'LS', 'SHIRT', 'TANK', 'SHOE', 'HAT'],
        'SHOE': ['TS', 'LS', 'SHIRT', 'PT', 'SH', 'JK', 'SOCK'],
        'BAG': ['TS', 'LS', 'SHIRT', 'JK', 'PT', 'SHOE'],
        'HAT': ['TS', 'LS', 'SHIRT', 'JK', 'PT', 'SH', 'SHOE'],
        'SOCK': ['SHOE', 'PT', 'SH'],
        'SUN': ['TS', 'LS', 'SHIRT', 'JK'],
        'ACC': ['TS', 'LS', 'SHIRT', 'JK'],
    }
    target_cats = complementary_cats.get(new_cat_code, ['TS', 'PT', 'SHOE'])

    # 提取新衣特征
    new_color = new_item_tags.get('color', {})
    new_hue_family = new_color.get('hue_family', '')
    new_hue_name = new_color.get('hue_name', '')
    new_saturation = new_color.get('saturation', '')
    new_lightness = new_color.get('lightness', '')
    new_styles = set(new_item_tags.get('style_modifiers', []))
    new_occasions = set(new_item_tags.get('occasions', []))
    new_fabric = new_item_tags.get('fabric', {})
    new_seasonality = set(new_fabric.get('seasonality', []))
    new_formality = new_item_tags.get('formality', 3)
    new_brand_name = (new_item_tags.get('brand') or {}).get('name', '')

    # 配色和谐评分
    def color_harmony_score(wardrobe_color):
        wh = wardrobe_color.get('hue_family', '')
        ws = wardrobe_color.get('saturation', '')
        wl = wardrobe_color.get('lightness', '')
        score = 50  # 基础分

        # 同色系和谐
        if wh and new_hue_family and wh == new_hue_family:
            score += 20
        # 中性色百搭
        if wardrobe_color.get('is_neutral'):
            score += 15
        if new_color.get('is_neutral'):
            score += 15
        # 饱和度搭配（一高一低更好）
        if new_saturation and ws:
            if new_saturation != ws:
                score += 10
        # 明度对比
        if new_lightness and wl:
            if new_lightness != wl:
                score += 8
        return min(score, 100)

    # 风格兼容评分
    def style_compatibility_score(w_styles, w_formality):
        score = 40
        w_styles_set = set(w_styles)
        # 风格标签重叠
        overlap = new_styles & w_styles_set
        score += len(overlap) * 12
        # 正式度匹配
        if new_formality and w_formality:
            diff = abs(new_formality - w_formality)
            if diff == 0:
                score += 15
            elif diff == 1:
                score += 8
        return min(score, 100)

    # 场景兼容评分
    def occasion_score(w_occasions):
        score = 30
        w_occ_set = set(w_occasions)
        overlap = new_occasions & w_occ_set
        score += len(overlap) * 15
        return min(score, 100)

    # 对所有衣橱单品打分
    results_by_cat = {}
    for cid, witem in wardrobe_items.items():
        w_cat_code = witem.get('category_code', '')
        if w_cat_code not in target_cats:
            continue

        w_color = witem.get('color', {})
        w_styles = witem.get('style_modifiers', [])
        w_occasions = witem.get('occasions', [])
        w_formality = witem.get('formality', 3)
        w_fabric = witem.get('fabric', {})
        w_seasonality = set(w_fabric.get('seasonality', []))

        # 三项评分
        color_score = color_harmony_score(w_color)
        style_score = style_compatibility_score(w_styles, w_formality)
        occ_score = occasion_score(w_occasions)

        # 季节加分
        season_bonus = 0
        if new_seasonality and w_seasonality:
            if new_seasonality & w_seasonality:
                season_bonus = 10

        # 综合分（加权）
        total = color_score * 0.35 + style_score * 0.35 + occ_score * 0.20 + season_bonus
        total = round(min(total, 100))

        # 匹配理由
        reasons = []
        if color_score >= 70:
            reasons.append('配色和谐')
        if style_score >= 70:
            reasons.append('风格兼容')
        if occ_score >= 60:
            reasons.append('场景匹配')
        if season_bonus > 0:
            reasons.append('季节合适')
        if new_brand_name and (witem.get('brand') or {}).get('name', '') == new_brand_name:
            reasons.append('同品牌')
            total = min(total + 5, 100)

        # 单品信息
        w_brand = (witem.get('brand') or {}).get('name', '') or ''
        w_comment = (witem.get('meta') or {}).get('claude_fit_comment', '') or ''
        thumb = _find_item_thumb(cid)

        result = {
            'id': cid,
            'category': witem.get('category', ''),
            'category_code': w_cat_code,
            'brand': w_brand,
            'color': w_color.get('hue_name', ''),
            'color_hex': _color_name_to_hex(w_color.get('hue_name', '')),
            'thumb': thumb,
            'score': total,
            'match_reasons': reasons,
            'comment': w_comment[:40],
        }

        if w_cat_code not in results_by_cat:
            results_by_cat[w_cat_code] = []
        results_by_cat[w_cat_code].append(result)

    # 每品类取 Top 5，按分数排序
    matched = {}
    cat_name_map = CATEGORY_CODE_TO_NAME
    for cat_code, items in results_by_cat.items():
        items.sort(key=lambda x: x['score'], reverse=True)
        top_items = items[:5]
        if top_items:
            matched[cat_code] = {
                'category_name': cat_name_map.get(cat_code, cat_code),
                'items': top_items,
            }

    # 按品类优先级排序（上衣类 > 下装类 > 鞋 > 配饰）
    priority_order = ['TS', 'LS', 'SHIRT', 'TANK', 'JK', 'PT', 'SH', 'SHOE', 'HAT', 'BAG', 'SOCK', 'SUN', 'ACC']
    ordered = {}
    for code in priority_order:
        if code in matched:
            ordered[code] = matched[code]

    return ordered


def _color_name_to_hex(name):
    """颜色名 → hex 色值"""
    m = {
        '红': '#c0392b', '橙': '#e67e22', '黄': '#f1c40f', '绿': '#27ae60',
        '青': '#1abc9c', '蓝': '#2980b9', '紫': '#8e44ad', '粉': '#e91e63',
        '棕': '#795548', '灰': '#95a5a6', '白': '#ecf0f1', '黑': '#2c3e50',
        '米': '#f5deb3', '卡其': '#c3b091', '藏青': '#1a3a5c', '酒红': '#722f37',
        '墨绿': '#1a4028', '驼': '#c19a6b', '焦糖': '#af6b3d', '浅灰': '#bdc3c7',
        '深灰': '#636e72', '银': '#bdc3c7', '金': '#d4a574', '杏': '#f5e6d3',
        '军绿': '#5c6e4a', '深蓝': '#1e3a5f', '浅蓝': '#7ea3c8', '天蓝': '#8bb8d6',
        '橙色': '#e67e22', '黄色': '#f1c40f', '绿色': '#27ae60', '蓝色': '#2980b9',
        '紫色': '#8e44ad', '粉色': '#e91e63', '白色': '#ecf0f1', '黑色': '#2c3e50',
    }
    if not name:
        return '#ccc'
    for k, v in m.items():
        if k in name:
            return v
    return '#999'


@safe_daemon('preview_outfit', task_manager=tasks)
def _run_preview_outfit(task_id, new_item, selected_ids, uid=None):
    """后台线程：以新衣为核心，AI 选品 + Seedream 生图预览"""
    try:
        # 设置线程本地用户上下文
        if uid and uid != 'default':
            from tools.common import set_thread_user as _set_thread_user
            from tools.user_manager import get_user_gender as _gug
            _g = _gug(uid) or 'male'
            _set_thread_user(_g, uid)

        tasks.update(task_id, status='running', message='正在AI选品搭配...')

        # ── 1. 加载衣橱标签 ──
        tags_dir = resolve_tags_dir(_g, uid) if uid else os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
        all_tags = {}
        for fn in sorted(os.listdir(tags_dir)):
            if fn == 'SCORE_CACHE.json' or not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(tags_dir, fn)) as f:
                    d = json.load(f)
            except:
                continue
            cid = d.get('clothing_id', '')
            if cid and not (d.get('meta') or {}).get('archived'):
                all_tags[cid] = d

        # ── 2. 确定新衣品类和互补需求 ──
        new_cat_code = new_item.get('category_code', 'TS')
        new_cat = new_item.get('category', '短袖上衣')

        # 品类 → 需要搭配的品类及数量
        outfit_template = {
            'TS': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SHOE',), ('HAT','BAG','SOCK','SUN')],
            'LS': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SHOE',), ('HAT','BAG','SOCK')],
            'SHIRT': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SHOE',), ('BAG','HAT','SOCK')],
            'TANK': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SHOE',), ('HAT','BAG')],
            'JK': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SHOE',), ('BAG','HAT')],
            'PT': [('LS','TS','SHIRT','TANK'), ('SHOE',), ('JK','BAG','HAT')],
            'SH': [('LS','TS','SHIRT','TANK'), ('SHOE',), ('HAT','BAG','SOCK')],
            'SHOE': [('LS','TS','SHIRT','TANK'), ('PT','SH'), ('SOCK','BAG')],
        }

        template = outfit_template.get(new_cat_code, [('TS',), ('PT','SH'), ('SHOE',)])

        # ── 3. 选品（优先用 selected_ids，否则 AI 自动选）──
        selected_items = []

        if selected_ids:
            # 用户手动选择
            for sid in selected_ids:
                if sid in all_tags:
                    selected_items.append(all_tags[sid])
        else:
            # 自动选品：用匹配分数最高的单品
            matches = match_for_new_item(new_item)
            for slot_idx, slot_cats in enumerate(template):
                # 跳过新衣自身所在品类
                if new_cat_code in slot_cats:
                    continue
                picked = None
                best_score = -1
                for cat_code in slot_cats:
                    if cat_code in matches:
                        for item in matches[cat_code].get('items', []):
                            mid = item['id']
                            if mid not in [s.get('clothing_id','') for s in selected_items]:
                                if item['score'] > best_score:
                                    best_score = item['score']
                                    picked = mid
                if picked and picked in all_tags:
                    selected_items.append(all_tags[picked])
                    if len(selected_items) >= 3:
                        break

        if not selected_items:
            tasks.update(task_id, status='error', message='未找到可搭配的单品，请先添加基础款到衣橱')
            return

        # ── 4. 构建穿搭方案 ──
        outfit_items = [new_item] + selected_items[:4]

        # 人物照（从用户形象读取）
        person_photos = get_person_photos()
        has_person = len(person_photos) > 0

        # ── 5. 创建任务专属临时目录（避免多任务互相覆盖 + 浏览器缓存碰撞）──
        preview_base = os.path.join(PROJECT_DIR, 'outfits', '_preview')
        preview_dir = os.path.join(preview_base, task_id)
        shengtu_dir = os.path.join(preview_dir, '豆包生图')
        for d in [preview_dir, shengtu_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)

        # 清理超过 1 小时的旧预览目录，防止磁盘堆积
        try:
            now_ts = time.time()
            for entry in os.listdir(preview_base):
                entry_path = os.path.join(preview_base, entry)
                if os.path.isdir(entry_path) and entry != task_id:
                    if now_ts - os.path.getmtime(entry_path) > 3600:
                        shutil.rmtree(entry_path)
        except Exception:
            pass

        # ── 6. 复制人物照（原图直出，不去背景）+ 单品参考图 ──
        reference_paths = []
        if has_person:
            # 只取全身正面 1 张原图
            preview_photos = person_photos[:1]
            for i, pp in enumerate(preview_photos):
                ext = os.path.splitext(pp)[1] or '.jpg'
                dst = os.path.join(shengtu_dir, f'人物_{i+1}{ext}')
                shutil.copy2(pp, dst)
                reference_paths.append(dst)
        else:
            log("👤 无人物参考照，仅用服装抠图生成", "WARN")

        cat_to_prefix = {
            '短袖上衣': '上衣', '长袖上衣': '上衣', '衬衣': '上衣', '背心': '上衣',
            '外套': '外套', '长裤': '下装', '短裤': '下装',
            '鞋子': '鞋子', '帽子': '帽子', '包': '包', '墨镜': '墨镜',
            '手部配饰': '配饰', '袜子': '袜子',
        }

        for oi in outfit_items:
            is_new = (oi is new_item)
            cat_name = oi.get('category', '')
            prefix = cat_to_prefix.get(cat_name, '配饰')
            oid = oi.get('suggested_id', oi.get('clothing_id', 'new'))

            if is_new:
                # 新衣使用原始照片
                src = oi.get('_temp_image_path', '')
                if src and os.path.exists(src):
                    dst = os.path.join(shengtu_dir, f'{prefix}_{oid}_new.jpg')
                    shutil.copy2(src, dst)
                    reference_paths.append(dst)
            else:
                # 衣橱单品使用抠图
                cutout = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced', f'{oid}_cutout.png')
                if os.path.exists(cutout):
                    dst = os.path.join(shengtu_dir, f'{prefix}_{oid}.png')
                    shutil.copy2(cutout, dst)
                    reference_paths.append(dst)

        tasks.update(task_id, status='running', message=f'已选 {len(outfit_items)} 件单品，正在生成效果图...')

        # ── 7. 构建 Seedream Prompt ──
        # 收集单品描述
        item_descs = []
        for oi in outfit_items:
            is_new = (oi is new_item)
            tag = '🆕新衣' if is_new else ''
            c = oi.get('color', {})
            b = oi.get('brand', {})
            color_name = c.get('hue_name', '') if isinstance(c, dict) else ''
            brand_name = b.get('name', '') if isinstance(b, dict) else ''
            cat = oi.get('category', '')
            item_descs.append(f"{tag}{brand_name} {color_name}{cat}".strip())

        prompt = f"""一位亚洲年轻男性，身高178cm偏瘦，肤色偏白。身穿{','.join(item_descs)}。
全身站立穿搭照，自然光线，干净简约背景，时尚杂志风格。
展示完整穿搭效果，包含上衣、下装、鞋子和配饰的搭配。
服装版型合身，配色协调，风格统一。
高画质，真实感强，专业时尚摄影。"""

        with open(os.path.join(shengtu_dir, '豆包提示词.txt'), 'w') as f:
            f.write(prompt)

        tasks.update(task_id, status='running', message='正在调用 AI 生图（约30秒）...')

        # ── 8. 调用 Seedream API ──
        import base64 as _b64
        from PIL import Image as PILImage
        import io as _io

        # 加载配置
        seedream_config_file = os.path.join(PROJECT_DIR, 'config', 'seedream.json')
        local_config_file = os.path.join(PROJECT_DIR, 'config', 'seedream.local.json')
        sd_config = {}
        for cfg_path in [seedream_config_file, local_config_file]:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    sd_config.update(json.load(f))

        # 编码参考图
        refs = []
        NEUTRAL_GRAY = (217, 217, 217)
        for rp in reference_paths:
            img = PILImage.open(rp)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                bg = PILImage.new('RGB', img.size, NEUTRAL_GRAY)
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ('RGB',):
                img = img.convert('RGB')
            w, h = img.size
            max_size = 1024
            if w > max_size or h > max_size:
                ratio = max_size / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format='JPEG', quality=70)
            b64 = _b64.b64encode(buf.getvalue()).decode('utf-8')
            refs.append(f"data:image/jpeg;base64,{b64}")
            img.close()

        payload = json.dumps({
            "model": sd_config.get('model', 'doubao-seedream-5.0-lite'),
            "prompt": prompt,
            "image": refs,
            "size": sd_config.get('size', '1024x1024'),
            "response_format": "url",
            "watermark": False,
            "max_images": 2,
        }).encode('utf-8')

        api_url = sd_config.get('api_url', '')
        api_key = sd_config.get('api_key', '')
        req = urllib.request.Request(api_url, data=payload, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        })

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            log(f"Seedream API 调用失败: {e}", "ERROR")
            tasks.update(task_id, status='error', message=f'生图失败: {str(e)[:80]}')
            return

        # ── 9. 下载结果 ──
        if 'data' not in result or not result['data']:
            log(f"Seedream 无图片返回: {json.dumps(result, ensure_ascii=False)[:300]}", "WARN")
            tasks.update(task_id, status='error', message='AI 生图未返回结果，请重试')
            return

        downloaded = []
        for i, item in enumerate(result['data']):
            url = item.get('url', '')
            if not url:
                continue
            fname = f'预览效果_{i+1}.png'
            spath = os.path.join(shengtu_dir, fname)
            try:
                urllib.request.urlretrieve(url, spath)
                downloaded.append(spath)
            except Exception as e:
                log(f"下载失败: {e}", "WARN")

        if not downloaded:
            tasks.update(task_id, status='error', message='图片下载失败')
            return

        # ── 10. 构建返回结果 ──
        outfit_detail = []
        for oi in outfit_items:
            is_new = (oi is new_item)
            c = oi.get('color', {})
            b = oi.get('brand', {})
            outfit_detail.append({
                'id': oi.get('suggested_id', oi.get('clothing_id', '')),
                'category': oi.get('category', ''),
                'color': (c.get('hue_name', '') if isinstance(c, dict) else ''),
                'brand': (b.get('name', '') if isinstance(b, dict) else ''),
                'is_new': is_new,
            })

        # 相对路径 → /api/image 压缩传输（手机端 ?w=900，体积减 90%+）
        # t=task_id 打破浏览器缓存：同一 URL = 同一任务，不同任务永不碰撞
        from urllib.parse import quote as _quote
        rel_images = [os.path.relpath(dp, PROJECT_DIR) for dp in downloaded]
        image_urls = [f'/api/image?f={_quote(p)}&w=900&t={task_id}' for p in rel_images]

        result_data = {
            'outfit_items': outfit_detail,
            'image_urls': image_urls,
            'prompt': prompt,
        }

        tasks.update(task_id, status='done', message=f'✅ 穿搭预览完成',
                     result=json.dumps(result_data, ensure_ascii=False),
                     image_path=rel_images[0],
                     image_url=image_urls[0])

    except Exception as e:
        log(f"预览生图失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        tasks.update(task_id, status='error', message=f'预览失败: {str(e)[:80]}')


@safe_daemon('add_analysis', task_manager=tasks)
def _run_add_analysis(task_id, image_b64_list, uid=None, req_id=None):
    """后台线程：调用豆包视觉 API 分析衣物图片（多用户感知 + 自动重试）"""
    _rid = f'[{req_id}]' if req_id else ''
    try:
        # 🛡️ 持久化 _user_id 到任务（崩溃恢复时重试队列依赖此字段）
        if uid and uid != 'default':
            tasks.update(task_id, _user_id=uid)
        tasks.update(task_id, status='running', message='正在保存图片...')

        # 设置线程本地用户上下文（子线程不继承父线程的 threading.local()）
        if uid and uid != 'default':
            from tools.common import set_thread_user as _set_thread_user
            from tools.user_manager import get_user_gender as _gug
            _g = _gug(uid) or 'male'
            _set_thread_user(_g, uid)

        # 1. 保存临时图片到用户目录
        user_dir = resolve_user_dir(_g, uid) if uid else PROJECT_DIR
        incoming_dir = os.path.join(user_dir, 'wardrobe', '_incoming')
        os.makedirs(incoming_dir, exist_ok=True)
        temp_paths = []
        import base64 as _b64
        from PIL import Image as PILImage
        import hashlib as _hashlib
        # 同批次 MD5 去重（同一 task 内重复的图只保留第一张）
        _batch_md5s = set()
        _dup_count = 0
        for i, b64_str in enumerate(image_b64_list):
            # 去掉可能的 data:image/...;base64, 前缀
            if ',' in b64_str and b64_str.startswith('data:'):
                b64_str = b64_str.split(',', 1)[1]
            img_bytes = _b64.b64decode(b64_str)
            _img_md5 = _hashlib.md5(img_bytes).hexdigest()
            if _img_md5 in _batch_md5s:
                _dup_count += 1
                log(f'{_rid} 🔄 图片{i+1} 同批次重复，跳过')
                continue
            _batch_md5s.add(_img_md5)
            temp_path = os.path.join(incoming_dir, f'img_{task_id}_{i}.jpg')
            with open(temp_path, 'wb') as f:
                f.write(img_bytes)
            temp_paths.append(temp_path)
        if _dup_count:
            log(f'{_rid} 🗑️ 去重过滤 {_dup_count} 张重复图片，实际处理 {len(temp_paths)} 张')

        tasks.update(task_id, status='running', message=f'正在AI智能识别 {len(temp_paths)} 张图片...')

        # 🆕 Phase 2: 布料解析 — 从真人/复杂照片中检测并裁剪每件服装单品
        all_crops = []  # [(crop_pil_image, source_img_index, category_hint, completeness, mask)]
        _parse_success = False
        try:
            from tools.cloth_parser import parse_clothing as _parse_clothing
            from tools.extract_clothing import extract_to_white_bg as _extract_white_bg, remove_white_background as _remove_white_bg
            tasks.update(task_id, status='running', message=f'正在检测服装单品...')
            for i, tp in enumerate(temp_paths):
                try:
                    # 🆕 皮肤检测：有皮肤→人像穿搭→SegFormer裁剪；无皮肤→单品图→原图直接送AI
                    # 2026-06-24 修复：草帽等暖色调材质（米色/卡其色）RGB接近肤色导致误判
                    # 方案：收紧RGB条件 + 色相约束(H≤35°排除黄橙色的草帽/皮革/卡其布)
                    # R须显著大于G和B（皮肤特有），排除R≈G≈B的暖色材质
                    _pil_img = PILImage.open(tp).convert('RGB')
                    # EXIF 方向校正：iPhone 竖拍照片可能存为横图+旋转标记
                    try:
                        from PIL import ImageOps as _ImageOps
                        _pil_img = _ImageOps.exif_transpose(_pil_img)
                    except Exception:
                        pass
                    import numpy as _np
                    _arr = _np.array(_pil_img).astype(float)
                    _r, _g, _b = _arr[:,:,0], _arr[:,:,1], _arr[:,:,2]
                    # HSV 色相计算（区分红调皮肤 vs 黄调材质）
                    _rn, _gn, _bn = _r/255, _g/255, _b/255
                    _cmax = _np.maximum(_np.maximum(_rn, _gn), _bn)
                    _cmin = _np.minimum(_np.minimum(_rn, _gn), _bn)
                    _cdelta = _cmax - _cmin
                    _h = _np.zeros_like(_rn)
                    _hmask_r = (_cmax == _rn) & (_cdelta != 0)
                    _hmask_g = (_cmax == _gn) & (_cdelta != 0)
                    _hmask_b = (_cmax == _bn) & (_cdelta != 0)
                    _h[_hmask_r] = 60 * ((_gn[_hmask_r] - _bn[_hmask_r]) / _cdelta[_hmask_r]) % 360
                    _h[_hmask_g] = 60 * ((_bn[_hmask_g] - _rn[_hmask_g]) / _cdelta[_hmask_g] + 2)
                    _h[_hmask_b] = 60 * ((_rn[_hmask_b] - _gn[_hmask_b]) / _cdelta[_hmask_b] + 4)
                    # 收紧的皮肤检测：R主导(>G+10, >B+10)，R-G>20，max-min>20，色相≤35°
                    # + 饱和度约束 0.1-0.55（排除高饱和红色布料/低饱和灰色材质）
                    _s = _cdelta / _np.maximum(_cmax, 0.001)
                    _skin = (_r > 95) & (_g > 40) & (_b > 20) & \
                            (_r > _g + 10) & (_r > _b + 10) & \
                            ((_r - _g) > 20) & \
                            ((_np.maximum(_np.maximum(_r,_g),_b) - _np.minimum(_np.minimum(_r,_g),_b)) > 20) & \
                            (_h <= 35) & \
                            (_s >= 0.1) & (_s <= 0.55)
                    _skin_pct = _skin.sum() / (_arr.shape[0] * _arr.shape[1]) * 100
                    _is_product_shot = _skin_pct < 3  # 皮肤<3%→无人→单品图

                    if _is_product_shot:
                        log(f'{_rid} 🔍 图片{i+1} 皮肤检测{_skin_pct:.1f}%→判定为单品图，跳过SegFormer直接原图分析')
                        all_crops.append((_pil_img, i, '??', 'full', None, False))
                        continue  # 跳过 SegFormer 处理

                    items = _parse_clothing(tp)
                    # 🆕 过滤面积过小的误检（< 3% 通常是背景噪点或皮肤碎片）
                    items = [it for it in items if it.get('area_pct', 0) >= 3.0]
                    if items:
                        for item in items:
                            # 🆕 白底重构：SegFormer 检测到服装 → Seedream 整件重构到纯白背景 → 程序化去白底
                            # 优于旧方案（灰底抠图+局部补全），产出专业电商商品图效果
                            was_completed = False
                            clean_img = None
                            try:
                                tasks.update(task_id, status='running',
                                           message=f'正在提取 {item["category_name"]} 到白底...')
                                white_result = _extract_white_bg(
                                    item['crop_image'],
                                    category_hint=item['category_code'],
                                    max_retries=1, timeout=120
                                )
                                if white_result.get('white_bg_image'):
                                    # 白底图直接作为入库图片（专业商品图效果）
                                    # 同时去白底生成透明PNG备用于 enhanced/ 缩略图
                                    clean_img = white_result['white_bg_image']
                                    was_completed = True
                                    # 后台去白底存透明PNG（给 enhanced/ 缩略图用）
                                    try:
                                        _cleaned = _remove_white_bg(white_result['white_bg_image'])
                                        item['_clean_png_bytes'] = _cleaned.get('cutout_bytes_png', b'')
                                    except Exception:
                                        item['_clean_png_bytes'] = b''
                                    log(f'{_rid} ✨ {item["category_code"]} 白底提取成功')
                                else:
                                    log(f'{_rid} ⚠️ {item["category_code"]} 白底提取未成功: {white_result.get("error","")[:80]}')
                            except Exception as _ce:
                                log(f'{_rid} ⚠️ {item["category_code"]} 白底提取异常: {_ce}')

                            # Fallback：Seedream 失败时用 SegFormer 抠图兜底
                            if clean_img is None:
                                try:
                                    from tools.cloth_parser import create_clean_cutout as _create_cutout
                                    cutout = _create_cutout(item['crop_image'], item['mask'])
                                    clean_img = cutout['cutout_jpg']
                                    log(f'{_rid} ↩️ {item["category_code"]} 回退到 SegFormer 抠图')
                                except Exception as _fe:
                                    clean_img = item['crop_image'].convert('RGB') if hasattr(item['crop_image'], 'convert') else item['crop_image']
                                    log(f'{_rid} ↩️ {item["category_code"]} 回退到原始裁剪图')

                            all_crops.append((clean_img, i, item['category_code'], item['completeness'], item.get('mask'), was_completed))
                        log(f'{_rid} 📐 图片{i+1} 检测到 {len(items)} 件服装 + 已抠图: '
                            f'{", ".join(it["category_code"]+"("+str(it["area_pct"])+"%)" for it in items)}')
                    else:
                        # 无检测结果 → 整张图作为 fallback（可能是干净背景单品图）
                        img = PILImage.open(tp).convert('RGB')
                        all_crops.append((img, i, '??', 'full', None, False))
                        log(f'{_rid} 📐 图片{i+1} 未检测到单品区域，使用整图分析')
                except Exception as _pe:
                    log(f'{_rid} ⚠️ 图片{i+1} 布料解析失败: {_pe}，使用整图分析')
                    img = PILImage.open(tp).convert('RGB')
                    all_crops.append((img, i, '??', 'full', None, False))
            _parse_success = len(all_crops) > 0
            if _parse_success and any(c[2] != '??' for c in all_crops):
                tasks.update(task_id, status='running', message=f'检测到 {len(all_crops)} 件服装，正在逐一分析...')
        except ImportError as _ie:
            log(f'{_rid} ⚠️ cloth_parser 不可用 ({_ie})，使用整图分析')
        except Exception as _pe:
            log(f'{_rid} ⚠️ 布料解析异常: {_pe}，回退到整图分析')

        # ═══ 图片类型分流 ═══
        # 1. 👤 人像穿搭: 皮肤检测≥3% → SegFormer裁剪 → Seedream白底重构 → AI逐件分析
        # 2. 🛍️ 单品图: 皮肤检测<3%（鞋/包/衣服平铺/配饰）→ 跳过SegFormer → 原图直接送AI
        # 3. 🛒 电商图: 水印/促销文字 → AI Prompt 层处理（忽略水印/提取品牌线索）
        # 4. 🖼️ 拼贴图: 多图面板 → AI Prompt 层处理（去重/只分析主体）
        # 如果解析成功且有有效品类检测，用裁剪图替换原始图；否则用原始图
        _has_valid_detections = _parse_success and any(c[2] != '??' for c in all_crops)
        if _has_valid_detections:
            # 用裁剪图构建新 temp_paths
            crop_temp_paths = []
            crop_source_map = {}  # crop_index → original temp_path index
            for ci, crop_data in enumerate(all_crops):
                crop_img, src_idx = crop_data[0], crop_data[1]
                cat_hint, completeness = crop_data[2], crop_data[3]
                was_completed = crop_data[5] if len(crop_data) > 5 else False
                crop_path = os.path.join(incoming_dir, f'crop_{task_id}_{ci}.jpg')
                crop_img.save(crop_path, 'JPEG', quality=85)
                crop_temp_paths.append(crop_path)
                crop_source_map[ci] = src_idx  # 记录裁剪图对应的原始图
            _analysis_images = crop_temp_paths
            _analysis_source_map = crop_source_map
            _used_parsing = True
        else:
            _analysis_images = temp_paths
            _analysis_source_map = {i: i for i in range(len(temp_paths))}
            _used_parsing = False

        # 2. 构建多模态 prompt（使用裁剪后的图片）
        content_blocks = []
        for i, tp in enumerate(_analysis_images):
            # 缩放并编码图片
            jpg_bytes = resize_image_for_api(tp)
            img_b64 = _b64.b64encode(jpg_bytes).decode('utf-8')
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
            content_blocks.append({
                "type": "text",
                "text": f"【图片 {i+1}】"
            })

        # 构建分析指令 — 🆕 品类自由输出 + fuzzy dedup + 电商图抗噪
        analysis_prompt = """你是一位专业的服装鉴定师。请仔细分析以上每张图片中的服装单品，输出严格的JSON格式结果。

🛒 图片类型识别（电商场景兼容）：
- 图片可能是：真人模特穿搭照 / 干净背景单品图 / 电商商品图（含水印、促销文字、价格标签）/ 多图拼贴
- 电商图中的水印文字、促销标签（如"满200减20"）、价格、尺码表、品牌Logo的叠印——这些都是干扰信息，不是服装的一部分
- 学会"看穿"这些叠印：品牌水印→可作为品牌字段的线索；促销文字/价格→忽略；店铺Logo→忽略
- 如果图片是多图拼贴（同一件衣服的正反面/细节），只分析主要展示的那件服装，不要重复计数
- 如果图片的服装上有其他物品遮挡（手机、手袋、头发），请识别出来并忽略遮挡物，只关注服装本身

对每件单品，按以下结构输出：
{
  "items": [
    {
      "category_code": "品类简称（建议填，但不确定可以填'??'），如 TS(短袖T恤), LS(长袖上衣), SHIRT(衬衣), TANK(背心), JK(外套/夹克), PT(长裤), SH(短裤), SHOE(鞋子), BAG(包), HAT(帽子), SOCK(袜子), SUN(墨镜), ACC(配饰), DRESS(连衣裙), SKIRT(半身裙), JMP(连体裤), BLOUSE(女士衬衫), KNIT(针织衫)。\n      如果不确定或品类不在以上列表中，填'??'，系统会自动归类。",
      "category": "中文品类名。这是最重要的字段，请尽量准确描述这是哪种服装，如：短袖上衣、连衣裙、百褶裙、针织开衫、阔腿裤、连体短裤、雪纺衬衫。系统会根据此字段自动分类。",
      "color": {
        "hue_family": "暖色/冷色/中性色",
        "hue_name": "具体颜色名，如 藏青色、米白色、焦糖色、浅灰色",
        "saturation": "高饱和/中饱和/低饱和/无彩色",
        "lightness": "高明度/中明度/低明度",
        "is_neutral": false,
        "friendly_for_pale_skin": false
      },
      "brand": {
        "name": "品牌名。优先级：1)服装上的Logo 2)图片水印中的品牌名 3)标志性款式。没有则填'未知'。不要把电商店铺名当成品牌名",
        "collection": "系列名或空",
        "confidence": "确定/推测/未知"
      },
      "fabric": {
        "primary": "主要面料，如 棉、聚酯纤维、羊毛、亚麻、牛仔布、皮革、尼龙",
        "texture": "面料质感，如 平纹针织、斜纹、帆布、网眼、光滑、磨毛",
        "weight": "轻薄/适中/中厚/厚重",
        "seasonality": ["春","夏"]
      },
      "silhouette": {
        "fit": "合身/宽松/修身/oversize/直筒/锥形/阔腿/A字/收腰",
        "shoulder_effect": "无特殊效果/增加肩宽/落肩/插肩",
        "torso_effect": "无特殊效果/显瘦/遮盖腹部/拉长比例",
        "length_ratio": "标准/短款/长款/及膝/过膝/及踝"
      },
      "pattern": {
        "type": "纯色/条纹/格纹/印花/Logo/迷彩/扎染/拼接/文字",
        "density": "无/稀疏/适中/密集",
        "logo_visible": false
      },
      "style_modifiers": ["风格标签1", "风格标签2"],
      "occasions": ["运动", "日常休闲"],
      "formality": 3,
      "meta": {
        "claude_fit_comment": "一句话总结版型与适配度",
        "image_type": "model_wearing/product_shot/ecommerce/collage"
      },
      "source_image": 1
    }
  ]
}

注意：
- 严格只输出JSON，不要包含markdown代码块标记或解释文字
- 如果图片中没有服装单品，返回 {"items": []}
- source_image 必须是该单品所在图片的编号（1-based，对应【图片 N】标注），一件单品只能属于一张图片
- category字段必须填准确的中文品类名，系统会用此字段自动分类到衣橱
- 对于女性服装，请区分：连衣裙(一件式连身裙) vs 半身裙(只有下半身)；连体裤(上下连身) vs 背心+长裤(两件分开)
- 针织衫/毛衣/开衫请归类为"针织衫"，雪纺/真丝/荷叶边女士衬衫归类为"女士衬衫"
- 如果服装有遮挡或不完整，在 meta.claude_fit_comment 中注明"部分遮挡"或"不完整可见"
- 🛒 电商图：促销文字、价格、尺码信息不是服装属性，不要填进颜色/图案/面料字段
- 🛒 水印中的品牌名可作为 brand.name 的线索（confidence=推测），但水印本身不是服装图案
- 🛒 多图拼贴：只分析主要展示的那件服装，不要重复计数同一件衣服的不同角度
- 🛒 image_type 字段：model_wearing(模特穿着)/product_shot(单品平铺)/ecommerce(电商商品图)/collage(多图拼贴)"""

        content_blocks.append({"type": "text", "text": analysis_prompt})

        messages = [{"role": "user", "content": content_blocks}]

        tasks.update(task_id, status='running', message='AI正在识别品类/颜色/品牌/面料...')

        # 3. 调用豆包视觉 API（带智能重试：超时/5xx重试，4xx不重试）
        response_text = None
        import traceback as _tb
        for _retry in range(3):
            try:
                response_text = call_doubao_chat(messages, max_tokens=16384, timeout=120)
                if response_text:
                    break
                log(f'{_rid} ⚠️ AI 返回空, 重试 {_retry+1}/3')
            except Exception as _api_err:
                err_str = str(_api_err)
                # HTTP 4xx = 客户端错误（图片太大/格式不对），重试无意义
                if 'HTTP 4' in err_str or 'HTTP 413' in err_str or 'HTTP 429' in err_str:
                    log(f'{_rid} ❌ API 客户端错误 (不重试): {err_str[:200]}')
                    tasks.update(task_id, status='error', message=f'ERR_ANALYSIS: {err_str[:80]}')
                    return
                log(f'{_rid} ⚠️ API 调用失败 (重试 {_retry+1}/3): {err_str[:200]}')
                if _retry < 2:
                    time.sleep(2 ** _retry)  # 1s, 2s 退避
        if not response_text:
            tasks.update(task_id, status='error', message='ERR_ANALYSIS: AI 服务暂不可用，请稍后重试')
            return

        # 4. 解析 JSON
        analysis = extract_json(response_text)
        if not analysis or 'items' not in analysis:
            log(f"AI 返回无法解析: {response_text[:300]}", "WARN")
            tasks.update(task_id, status='error', message='AI 识别结果格式异常，请重试')
            return

        items = analysis.get('items', [])
        if not items:
            tasks.update(task_id, status='error', message='未在图片中识别到服装单品')
            return

        # 5. 为每件单品分配建议 ID 和补充信息（同批次去重）
        # 🆕 Phase 1: 品类 fuzzy dedup — AI 输出自由品类名，系统自动标准化
        assigned_ids = set()
        for i, item in enumerate(items):
            cc = item.get('category_code', '??')
            raw_category = item.get('category', '')

            # Step 1: 尝试验证 AI 给的 category_code
            if cc in CATEGORY_CODE_TO_NAME and cc != '??':
                item['category_code'] = cc
                item['category'] = CATEGORY_CODE_TO_NAME[cc]
            else:
                # Step 2: 用 fuzzy resolver 根据中文品类名匹配标准代码
                # 读取用户性别以优化匹配
                _gender = 'male'
                if uid and uid != 'default':
                    try:
                        _profile_path = os.path.join(resolve_user_dir(uid), 'profile.json')
                        if os.path.exists(_profile_path):
                            with open(_profile_path) as _pf:
                                _gender = json.load(_pf).get('gender', 'male')
                    except Exception:
                        pass
                resolved_cc, resolved_cn, confidence = resolve_category_code(raw_category, _gender)

                if resolved_cc and resolved_cc in CATEGORY_CODE_TO_NAME:
                    item['category_code'] = resolved_cc
                    item['category'] = resolved_cn
                    if confidence == 'unknown' or confidence == 'keyword':
                        # 低置信度匹配，标记给前端提示用户核对
                        item['meta'] = item.get('meta', {})
                        item['meta']['category_confidence'] = confidence
                        item['meta']['category_original'] = raw_category
                elif raw_category:
                    # 完全无法匹配，尝试用品类名首词猜测
                    item['category'] = raw_category
                    # 根据性别给默认品类
                    item['category_code'] = 'DRESS' if _gender == 'female' and '裙' in raw_category else 'TS'
                    item['meta'] = item.get('meta', {})
                    item['meta']['category_confidence'] = 'unknown'
                    item['meta']['category_original'] = raw_category
                else:
                    item['category_code'] = 'TS'
                    item['category'] = '短袖上衣'

            cc = item['category_code']
            sid = _get_next_id(cc, uid)
            # 同批次多件同品类时确保 ID 不重复（批量分析可能同时识别多件长裤/上衣等）
            while sid in assigned_ids or _id_exists_on_disk(sid, uid):
                prefix, num = sid.rsplit('-', 1)
                sid = f'{prefix}-{int(num)+1:03d}'
            assigned_ids.add(sid)
            item['suggested_id'] = sid
            # 根据 AI 返回的 source_image 字段映射到正确的临时图片
            # 🆕 cloth parsing 模式下，使用裁剪图（非原图）作为入库图片
            src_idx = item.get('source_image', 1) - 1  # AI 返回 1-based
            if _used_parsing and 0 <= src_idx < len(_analysis_images):
                item['_temp_image_path'] = _analysis_images[src_idx]
            elif 0 <= src_idx < len(temp_paths):
                item['_temp_image_path'] = temp_paths[src_idx]
            elif temp_paths:
                item['_temp_image_path'] = temp_paths[0]  # fallback
            else:
                item['_temp_image_path'] = ''
            # 🆕 如使用 cloth parsing，标记分割来源和完整性
            if _used_parsing and _analysis_source_map:
                item['meta'] = item.get('meta', {})
                item['meta']['cloth_parsed'] = True
                # 从 all_crops 获取完整性信息
                if all_crops and src_idx < len(all_crops):
                    _cp = all_crops[src_idx]
                    item['meta']['completeness'] = _cp[3]  # 'full' or 'partial'
                    item['meta']['ai_completed'] = _cp[5] if len(_cp) > 5 else False
                    if _cp[3] == 'partial':
                        item['meta']['claude_fit_comment'] = (
                            item['meta'].get('claude_fit_comment', '') + ' [⚠️部分遮挡]').strip()
            # 补充默认值
            if 'color' not in item: item['color'] = {}
            if 'brand' not in item: item['brand'] = {'name': '未知', 'collection': None, 'confidence': '未知'}
            if 'fabric' not in item: item['fabric'] = {'primary': '未知', 'texture': '未知', 'weight': '适中', 'seasonality': ['春', '秋']}
            if 'silhouette' not in item: item['silhouette'] = {'fit': '合身', 'shoulder_effect': '无特殊效果', 'torso_effect': '无特殊效果', 'length_ratio': '标准'}
            if 'pattern' not in item: item['pattern'] = {'type': '纯色', 'density': '无', 'logo_visible': False}
            if 'style_modifiers' not in item: item['style_modifiers'] = []
            if 'occasions' not in item: item['occasions'] = ['日常休闲']
            if 'formality' not in item: item['formality'] = 3
            if 'meta' not in item: item['meta'] = {
                'is_key_piece': False, 'is_statement_piece': False,
                'wear_count': 0, 'last_worn': None,
                'claude_fit_comment': '',
            }

        # 保存临时分析结果（包含 user_id 以便 confirm 步骤路由）
        analysis_path = os.path.join(incoming_dir, f'analysis_{task_id}.json')
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump({'items': items, '_task_id': task_id, '_user_id': uid or 'default'}, f, ensure_ascii=False, indent=2)

        tasks.update(task_id, status='done', message=f'识别完成，共 {len(items)} 件单品',
                     result=json.dumps({'items': items, '_task_id': task_id}, ensure_ascii=False))
        log(f"衣物分析完成: {task_id} → {len(items)} 件")

        # ⚠️ 不在此清理裁剪图 — confirm 阶段需要用裁剪图作为单品入库图片
        # 裁剪图由 confirm handler 统一清理（_cleanup_crops_for_task）

    except Exception as e:
        log(f'{_rid} 衣物分析失败: {e}', "ERROR")
        tasks.update(task_id, status='error', message=f'ERR_ANALYSIS: {str(e)[:80]}')
        # 清理临时文件，避免磁盘泄漏
        for _i in range(len(image_b64_list)):
            _tp = os.path.join(incoming_dir, f'img_{task_id}_{_i}.jpg')
            try:
                if os.path.exists(_tp):
                    os.remove(_tp)
            except Exception:
                pass
        # 🆕 也清理裁剪图
        try:
            for _fn in os.listdir(incoming_dir):
                if _fn.startswith(f'crop_{task_id}_'):
                    os.remove(os.path.join(incoming_dir, _fn))
        except Exception:
            pass


def _format_tips(tips):
    """Format dressing tips as markdown bullet list"""
    if not tips:
        return ''
    if isinstance(tips, str):
        return f'- {tips}'
    return '\n'.join(f'- {t}' for t in tips if t)


def execute_outfit_plan(plan, today, style_hint, user_id=None):
    """根据 AI 方案创建目录、写入文件、复制图片（多用户感知）"""
    wardrobe = _load_all_clothing()  # 从 JSON 标签读取（category_code + category 等完整数据）
    user_outfits = resolve_outfits_dir(user_id)
    outfit_dir = os.path.join(user_outfits, f'{today}_{style_hint}')
    shengtu_dir = os.path.join(outfit_dir, '豆包生图')
    items_dir = os.path.join(outfit_dir, 'items')

    # 创建目录（已存在则清理旧文件避免污染）
    for d in [shengtu_dir, items_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    items = plan.get('items', [])
    item_ids = [it['id'] for it in items]

    # ── 1. 写入 outfit.md ──
    items_table = '\n'.join(
        f"| {it['category']} | **{it['id']}** | {it['name']} | {it['color']} |"
        for it in items
    )
    outfit_md = f"""---
date: {today}
scene: {style_hint}
weather: {plan.get('weather_note', '晴/多云，22-34°C')}
style: {plan.get('style', style_hint)}
---

# {today} {style_hint}

## 单品清单

| 品类 | ID | 单品 | 颜色 |
|------|-----|------|------|
{items_table}

## 搭配理由

{plan.get('reasoning', '')}

## 配色逻辑

{plan.get('color_logic', '')}

## 推荐理由

{plan.get('rationale', '')}

## 穿搭技巧

{_format_tips(plan.get('dressing_tips', []))}

## 风格关键词

{plan.get('keywords', plan.get('style', '日常穿搭'))}
"""
    with open(os.path.join(outfit_dir, 'outfit.md'), 'w') as f:
        f.write(outfit_md)

    # ── 2. 写入豆包提示词.txt ──
    seedream_prompt = plan.get('seedream_prompt', '')
    with open(os.path.join(shengtu_dir, '豆包提示词.txt'), 'w') as f:
        f.write(seedream_prompt)

    # ── 3. 人物照片（原图直出，1张全身正面，不去背景）──
    person_photos_raw = get_person_photos()
    if person_photos_raw:
        # 只取全身正面照 1 张，不抠图不附加面部近照
        selected = person_photos_raw[:1]
        for i, pp in enumerate(selected):
            ext = os.path.splitext(pp)[1] or '.jpg'
            shutil.copy2(pp, os.path.join(shengtu_dir, f'人物_{i+1}{ext}'))
        log(f"👤 人物照: {len(selected)}张（原图）")
    else:
        log("👤 无人物参考照，仅用服装抠图生成", "WARN")

    # ── 4. 复制抠图到豆包生图/（用抠图做 Seedream 参考图，非原始照片）──
    user_enhanced = os.path.join(resolve_wardrobe_dir(user_id), 'enhanced')
    for it in items:
        item_id = it['id']
        w = wardrobe.get(item_id)
        if not w:
            log(f"⚠️ 找不到衣柜档案: {item_id}", "WARN")
            continue
        cat_info = CATEGORY_MAP.get(w['category'])
        if not cat_info:
            log(f"⚠️ 未知品类映射: {w['category']}", "WARN")
            continue
        # 使用抠图（去背景，干净轮廓），不用原始照片
        cutout_src = os.path.join(user_enhanced, f'{item_id}_cutout.png')
        if not os.path.exists(cutout_src):
            log(f"⚠️ 抠图不存在: {item_id}_cutout.png", "WARN")
            continue
        prefix = cat_info['prefix']
        dst_name = f"{prefix}_{item_id}.png"
        shutil.copy2(cutout_src, os.path.join(shengtu_dir, dst_name))

    # ── 5. 复制抠图到 items/（加 ID 前缀以匹配 composite_v2 的 find_img）──
    for it in items:
        item_id = it['id']
        w = wardrobe.get(item_id)
        if not w:
            continue
        # 抠图源文件命名格式: {ID}_cutout.png（如 ACC-004_cutout.png）
        cutout_src = os.path.join(user_enhanced, f'{item_id}_cutout.png')
        # 必须以 ID_ 前缀命名，composite_v2 的 find_img() 才能匹配
        if os.path.exists(cutout_src):
            dst_name = f"{item_id}_cutout.png"
            shutil.copy2(cutout_src, os.path.join(items_dir, dst_name))
        else:
            log(f"⚠️ 抠图不存在: {item_id}_cutout.png", "WARN")

    log(f"✅ 穿搭方案已创建: {outfit_dir}")
    return outfit_dir

def extract_occasion(style_hint):
    """从用户输入中提取场合/场景关键词，返回 (occasion, weather_note)"""
    hint = style_hint or ''

    # 场合关键词 → occasion 映射（按优先级排序）
    SCENE_KEYWORDS = [
        # 运动场景（精确匹配优先）
        (['网球', 'tennis'], '网球'),
        (['羽毛球', 'badminton'], '羽毛球'),
        (['跑步', 'running', '慢跑', '夜跑', '晨跑'], '跑步'),
        (['健身', 'gym', '健身房', '举铁', '力量训练'], '健身'),
        (['篮球', 'basketball'], '篮球'),
        (['足球', 'football', 'soccer'], '足球'),
        (['运动', '锻炼', '体育', 'sport'], '运动'),
        # 生活场景
        (['约会', 'date', '相亲', '见面', '聚餐'], '约会'),
        (['通勤', '上班', '工作', 'office', '开会', '商务', '正式', '面试'], '通勤'),
        (['聚会', '派对', 'party', '蹦迪', '夜店', '酒吧'], '聚会'),
        (['度假', '旅行', '旅游', 'vacation', '海边', '沙滩', '海岛', '泳池'], '度假'),
        (['户外', '爬山', '登山', '徒步', '露营', '野餐', 'hiking'], '户外'),
        (['居家', '在家', '宅', '家里'], '居家'),
    ]

    for keywords, occasion in SCENE_KEYWORDS:
        for kw in keywords:
            if kw in hint.lower():
                return occasion

    # 时间段提示
    time_hint = ''
    if any(w in hint for w in ['晚上', '夜晚', '晚间', '夜间', '傍晚']):
        time_hint = '晚上'
    elif any(w in hint for w in ['早上', '早晨', '清晨', '上午']):
        time_hint = '早上'

    return '日常'


def extract_mandatory_items(style_hint, min_confidence=0.40):
    """从用户输入中提取指定单品 → [(item_id, confidence, reason), ...]

    例: "大黄靴" → [(SHOE-007, 0.85, "昵称:Timberland | 俗称:大黄靴"), ...]
    只返回置信度 ≥ min_confidence 的结果。
    ⚠️ 阈值设为 0.40：场景词（如"网球"）只匹配 ~28%，不会误判为强制单品；
    明确指定单品（如"大黄靴"75%）才会被识别。
    """
    from tools.unified_pipeline import find_items_by_description
    matches = find_items_by_description(style_hint)
    # 过滤低置信度结果
    filtered = [(mid, conf, reason) for mid, conf, reason in matches if conf >= min_confidence]
    # 去重：每品类只保留置信度最高的1个，总共最多3个
    seen_cats = {}
    deduped = []
    for mid, conf, reason in filtered:
        cat = mid.split('-')[0] if '-' in mid else ''
        if cat not in seen_cats:
            seen_cats[cat] = (mid, conf, reason)
            deduped.append((mid, conf, reason))
    deduped = deduped[:3]
    if deduped:
        log(f"🔍 单品识别: {style_hint!r} → {[(m[0], f'{m[1]:.0%}') for m in deduped]}")
    return deduped


# ── 重试队列处理（启动恢复时自动重新提交分析任务）──
def _process_retry_queue(retry_queue):
    """读磁盘上的中断分析图片 → base64编码 → 重新提交 _run_add_analysis

    Args:
        retry_queue: [(tid, uid, img_paths), ...] 来自 TaskManager.recover_on_startup()
    """
    import base64 as _b64

    for tid, uid, img_paths in retry_queue:
        log(f"🔄 重试队列: 任务 {tid} (用户={uid}, {len(img_paths)} 张图片)")
        try:
            # 读图片 → base64
            b64_list = []
            for ip in img_paths:
                if not os.path.exists(ip):
                    log(f"⚠️ 重试: 图片不存在 {ip}", "WARN")
                    continue
                with open(ip, 'rb') as f:
                    img_bytes = f.read()
                b64_list.append(_b64.b64encode(img_bytes).decode('utf-8'))

            if not b64_list:
                tasks.update(tid, status='error', message='重试失败：图片文件丢失')
                continue

            # 更新任务状态，让前端看到进度
            tasks.update(tid, status='queued', message='服务恢复，正在重新分析...')

            # 后台线程提交分析
            t = threading.Thread(
                target=_run_add_analysis,
                args=(tid, b64_list, uid),
                daemon=True,
                name=f'retry-{tid}'
            )
            t.start()
            log(f"✅ 重试任务 {tid} 已提交")

        except Exception as e:
            log(f"❌ 重试任务 {tid} 提交失败: {e}", "ERROR")
            try:
                tasks.update(tid, status='error', message=f'重试提交失败: {str(e)[:100]}')
            except Exception:
                pass


@safe_daemon('pipeline', task_manager=tasks)
def run_pipeline(style_hint, task_id=None, user_id=None):
    """完整生图管线: 统一推荐(AI主导+数据支撑+规则验证) → Seedream生图 → 排版 → 推送"""
    import traceback as _tb

    # 防并发锁（SharedState 线程安全）
    if not shared_state.try_start_pipeline():
        log(f"⚠️ 管线忙碌，拒绝新请求: {style_hint}")
        if task_id:
            tasks.update(task_id, status='error', message='已有推荐任务运行中，请稍后重试')
        return None

    try:
        result = _run_pipeline_impl(style_hint, task_id, user_id)
        shared_state.update_pipeline_status(
            last_run=time.strftime('%Y-%m-%dT%H:%M:%S'),
            last_error=None
        )
        # total_runs 自增（读-改-写原子性由 SharedState 保证）
        st = shared_state.get_pipeline_status()
        shared_state.update_pipeline_status(total_runs=st.get('total_runs', 0) + 1)
        return result
    except Exception as _e:
        _err = f"管线异常: {_e}\n{_tb.format_exc()}"
        log(_err, "ERROR")
        shared_state.update_pipeline_status(last_error=str(_e)[:200])
        import sys as _sys
        _sys.stderr.write(_err + '\n')
        _sys.stderr.flush()
        if task_id:
            tasks.update(task_id, status='failed', message=f'管线失败: {_e}', log=_err[:500])
    finally:
        shared_state.end_pipeline()


def _build_admin_html():
    """构建管理员分析面板 HTML"""
    users_data = []
    reg = _load_user_registry()

    for gender, g_users in reg.items():
        for uid in g_users:
            u_dir = os.path.join(PROJECT_DIR, 'users', gender, uid)
        profile_path = os.path.join(u_dir, 'profile.json')
        outfits_dir = os.path.join(u_dir, 'outfits')

        profile = {}
        if os.path.exists(profile_path):
            with open(profile_path) as f:
                profile = json.load(f)

        total_outfits = 0
        ratings = []
        wore_count = 0
        for d in os.listdir(outfits_dir) if os.path.isdir(outfits_dir) else []:
            dp = os.path.join(outfits_dir, d)
            if not os.path.isdir(dp) or d.startswith('.'):
                continue
            rp = os.path.join(dp, 'rating.json')
            ap = os.path.join(dp, 'analytics.json')
            total_outfits += 1
            if os.path.exists(rp):
                with open(rp) as f:
                    r = json.load(f)
                ratings.append(r.get('rating', 0))
            if os.path.exists(ap):
                with open(ap) as f:
                    a = json.load(f)
                if a.get('user_wore'):
                    wore_count += 1

        onboard_step = profile.get('onboarding_step', 0)
        onboard_done = profile.get('onboarding_complete', False)
        status = 'active' if onboard_done else ('onboarding' if onboard_step > 0 else 'new')

        users_data.append({
            'id': uid,
            'status': status,
            'total_outfits': total_outfits,
            'avg_rating': round(sum(ratings)/len(ratings), 1) if ratings else 0,
            'rating_count': len(ratings),
            'wore_count': wore_count,
            'adoption_rate': f"{round(wore_count/total_outfits*100)}%" if total_outfits > 0 else 'N/A',
            'created': reg[uid].get('created', ''),
            'last_active': reg[uid].get('last_active', ''),
        })

    # 汇总核心指标
    active_users = [u for u in users_data if u['status'] == 'active']
    all_ratings = [u['avg_rating'] for u in users_data if u['rating_count'] > 0]

    total_rated = sum(u['rating_count'] for u in users_data)
    avg_all = round(sum(all_ratings)/len(all_ratings), 1) if all_ratings else 0
    total_wore = sum(u['wore_count'] for u in users_data)
    total_outfits_all = sum(u['total_outfits'] for u in users_data)
    adoption = f"{round(total_wore/total_outfits_all*100)}%" if total_outfits_all > 0 else 'N/A'

    # 计算复推率（7天内>=2次的用户）
    recurring = sum(1 for u in users_data if u['total_outfits'] >= 2)
    retention = f"{round(recurring/max(len(users_data),1)*100)}%"

    # 入库完成率（>=10件的用户）
    onboarding_done_count = sum(1 for u in users_data if u['status'] == 'active')
    completion = f"{round(onboarding_done_count/max(len(users_data),1)*100)}%"

    # 首次满意度
    first_ratings = []
    for uid in reg:
        outfits_dir = os.path.join(PROJECT_DIR, 'users', uid, 'outfits')
        if os.path.isdir(outfits_dir):
            dirs = sorted([d for d in os.listdir(outfits_dir) if os.path.isdir(os.path.join(outfits_dir, d)) and not d.startswith('.')])
            if dirs:
                rp = os.path.join(outfits_dir, dirs[0], 'rating.json')
                if os.path.exists(rp):
                    with open(rp) as f:
                        first_ratings.append(json.load(f).get('rating', 0))
    first_satisfaction = f"{round(sum(1 for r in first_ratings if r >= 3)/max(len(first_ratings),1)*100)}%"

    # 用户行
    user_rows = ''
    for u in users_data:
        status_icon = {'active': '🟢', 'onboarding': '🟡', 'new': '⚪'}.get(u['status'], '⚪')
        user_rows += f"""<tr>
            <td>{status_icon} {u['id']}</td>
            <td>{u['total_outfits']}套</td>
            <td>{u['avg_rating']} ({u['rating_count']}评)</td>
            <td>{u['wore_count']}</td>
            <td>{u['adoption_rate']}</td>
        </tr>"""

    # 统计性别分布
    male_count = 0; female_count = 0
    for uid in reg:
        try:
            up = os.path.join(PROJ_DIR, 'users', uid, 'profile.json')
            if os.path.exists(up):
                with open(up) as f:
                    g = json.load(f).get('gender', '')
                if g == 'male': male_count += 1
                elif g == 'female': female_count += 1
        except: pass
    unknown_count = len(users_data) - male_count - female_count

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fashion Advisor · 管理面板</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#e2e6ec;padding:20px;color:#1a2838}}
h1{{font-size:24px;margin-bottom:4px;color:#1a2838}}
.sub{{color:#6b7d94;font-size:14px;margin-bottom:24px}}
.gender-stats{{display:flex;gap:16px;margin-bottom:20px}}
.gender-stat{{background:#fff;border-radius:10px;padding:12px 20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.gender-stat .gs-num{{font-size:22px;font-weight:700;color:#1e3a5f}}
.gender-stat .gs-label{{font-size:11px;color:#6b7d94}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
.metric{{background:#fff;border-radius:12px;padding:16px;text-align:center;box-shadow:0 1px 6px rgba(0,0,0,.04)}}
.metric .value{{font-size:28px;font-weight:700;color:#1e3a5f}}
.metric .label{{font-size:12px;color:#6b7d94;margin-top:4px}}
.metric .target{{font-size:11px;color:#94a3b5}}
.metric.good .value{{color:#27ae60}}
.metric.warn .value{{color:#e67e22}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.04)}}
th,td{{padding:12px 16px;text-align:left;font-size:14px}}
th{{background:#f0f4f8;color:#1a2838;font-weight:600}}
td{{border-top:1px solid #e6ecf3}}
tr:hover{{background:#f8fafc}}
.refresh{{display:inline-block;margin-top:16px;color:#94a3b5;font-size:12px}}
</style>
</head>
<body>
<h1>👔 Fashion Advisor</h1>
<p class="sub">男女混合测试 · 数据看板 · {__import__('time').strftime('%Y-%m-%d %H:%M')}</p>
<div class="gender-stats">
<div class="gender-stat"><div class="gs-num">👨 {male_count}</div><div class="gs-label">男性用户</div></div>
<div class="gender-stat"><div class="gs-num">👩 {female_count}</div><div class="gs-label">女性用户</div></div>
<div class="gender-stat"><div class="gs-num">❓ {unknown_count}</div><div class="gs-label">未选择</div></div>
</div>

<div class="metrics">
<div class="metric {'good' if adoption.replace('%','') > '60' else 'warn'}">
<div class="value">{adoption}</div><div class="label">采纳率</div><div class="target">目标 &gt;60%</div></div>
<div class="metric {'good' if avg_all >= 3.5 else 'warn'}">
<div class="value">{avg_all}</div><div class="label">平均评分</div><div class="target">目标 &gt;3.5</div></div>
<div class="metric">
<div class="value">{retention}</div><div class="label">7天复推率</div><div class="target">目标 &gt;40%</div></div>
<div class="metric">
<div class="value">{completion}</div><div class="label">入库完成率</div><div class="target">目标 &gt;80%</div></div>
<div class="metric">
<div class="value">{first_satisfaction}</div><div class="label">首次满意度</div><div class="target">目标 &gt;70%</div></div>
<div class="metric">
<div class="value">{len(active_users)}/{len(users_data)}</div><div class="label">活跃/总用户</div></div>
</div>

<table>
<thead><tr><th>用户</th><th>推荐</th><th>评分</th><th>实穿</th><th>采纳率</th></tr></thead>
<tbody>{user_rows}</tbody>
</table>

<p class="refresh">自动刷新每5分钟 · 数据源: users/*/outfits/*/analytics.json</p>
<script>setTimeout(function(){{location.reload()}},300000);</script>
</body>
</html>"""


def _run_pipeline_impl(style_hint, task_id=None, user_id=None):
    """管线实现 — 独立函数以便 run_pipeline 捕获异常"""
    t_start = time.time()
    log(f"🚀 管线启动: {style_hint}")

    # ── 多用户上下文（必须在所有数据加载之前设置！后台线程不继承父线程的 threading.local()）──
    pipeline_user = user_id
    if pipeline_user and pipeline_user != 'default':
        from tools.common import set_thread_user as _set_thread_user
        from tools.user_manager import get_user_gender as _gug
        _pipeline_gender = pipeline_gender if 'pipeline_gender' in dir() else (_gug(pipeline_user) or 'male')
        _set_thread_user(_pipeline_gender, pipeline_user)

    # ── 🆕 统一意图解析（Phase 1 正则 + Phase 2 LLM）──
    from tools.intent_parser import parse_user_intent, get_recent_new_item_ids
    intent = parse_user_intent(style_hint)
    log(f"🎯 意图解析: occasion={intent['occasion']} city={intent.get('city_cn') or '默认'} "
        f"ids={intent['explicit_item_ids']} date_offset={intent['date_offset']} "
        f"new_items={intent['want_new_items']} explore={intent['explore_mood']} "
        f"({intent.get('_parse_time_ms', '?')}ms)")

    # ── Style hint 预处理 ──
    # ── 探测探索度 ──
    from tools.unified_pipeline import (
        determine_explore_level, determine_daily_mode, _record_daily_mode,
        build_enhanced_prompt, validate_outfit, score_outfit, update_lab_state
    )

    # 判断是否为每日自动推荐触发（cron / 定时任务）
    DAILY_TRIGGERS = ['今天穿什么', '今日穿搭', 'daily', 'auto_daily']
    is_daily_trigger = any(t in style_hint for t in DAILY_TRIGGERS)

    if is_daily_trigger:
        explore_level, explore_label, daily_reason = determine_daily_mode(style_hint, user_id)
        _record_daily_mode(explore_level, explore_label, daily_reason)
        explore_emoji = {'日常穿搭': '👔', '改变自己': '🧪', '大胆跨界': '🚀'}.get(explore_label, '')
        log(f"📅 每日自动推荐 → {explore_emoji} {explore_label}（{daily_reason}）")
    else:
        # 🆕 优先使用意图解析的 explore_mood
        mood_map = {'bold': 1.0, 'fresh': 0.5, 'normal': 0.0, 'safe': 0.0}
        intent_mood = intent.get('explore_mood', 'normal')
        if intent_mood != 'normal':
            explore_level = mood_map.get(intent_mood, 0.0)
            explore_label = {'bold': '大胆探索', 'fresh': '微调探索', 'safe': '安全推荐'}.get(intent_mood, '')
            explore_emoji = {'bold': '🚀', 'fresh': '🧪', 'safe': ''}.get(intent_mood, '')
            log(f"🎯 意图探索度: {explore_emoji} {explore_label}（来自 LLM 解析）")
        else:
            explore_level = determine_explore_level(style_hint)
            explore_emoji = '🚀' if explore_level >= 0.8 else ('🧪' if explore_level > 0 else '')
            explore_label = ('大胆探索' if explore_level >= 0.8 else ('微调探索' if explore_level > 0 else '安全推荐'))
            log(f"📍 探索度: {explore_label}{' '+explore_emoji if explore_emoji else ''}")
    log_lines = []
    # 统计
    _api_calls = 0
    _input_chars = 0

    def progress(msg):
        log(f"📍 {msg}")
        if task_id:
            log_lines.append(msg)
            tasks.update(task_id, status='running', message=msg, log='\n'.join(log_lines))

    def step_done():
        if log_lines:
            log_lines[-1] = '✅ ' + log_lines[-1]
        if task_id:
            tasks.update(task_id, status='running', log='\n'.join(log_lines))

    today = time.strftime('%Y-%m-%d')

    # ── 天气（使用意图解析的城市，而非硬编码 Beijing）──
    city = intent.get('city_en') or 'Beijing'
    city_display = intent.get('city_cn') or '北京'
    wdata = fetch_weather(city)
    analysis = analyze_weather(wdata) if wdata else None
    # 月份感知默认值：天气 API 失败时根据月份设定合理温度和天气
    _month = time.localtime().tm_mon
    _season_defaults = {
        1:(2,'多云'),2:(5,'多云'),3:(12,'晴'),4:(20,'晴'),5:(26,'晴'),6:(31,'晴'),
        7:(32,'多云'),8:(30,'晴'),9:(25,'晴'),10:(18,'晴'),11:(8,'多云'),12:(3,'多云')
    }
    _dt, _dw = _season_defaults.get(_month, (25, '晴'))
    temp_high = analysis['forecast']['max'] if analysis else _dt
    weather_cond = analysis['current']['desc'] if analysis else _dw
    log(f"📍 天气({city_display}): {temp_high}°C {weather_cond}{' (默认值)' if not analysis else ''}")

    # ── 衣橱数据（加载一次，管线内传递复用）──
    all_clothes = _load_all_clothing()

    # ── Step 0: 从意图解析获取场合 + 指定单品 ──
    occasion = intent['occasion']
    log(f"📍 场景: {style_hint!r} → occasion={occasion}" +
        (f" activity={intent['activity']}" if intent.get('activity') else '') +
        (f" vibe={intent['vibe']}" if intent.get('vibe') else ''))

    # 🆕 强制单品: 优先使用意图解析的 explicit_item_ids（置信度 0.99）
    mandatory_items = []
    if intent['explicit_item_ids']:
        for cid in intent['explicit_item_ids']:
            if cid in all_clothes:
                item = all_clothes[cid]
                brand = (item.get('brand') or {}).get('name', '—')
                cat = item.get('category', '—')
                reason = f'ID:{cid} | {brand} | {cat}'
                mandatory_items.append((cid, 0.99, reason))
            else:
                log(f"⚠️ 指定ID不存在于衣柜: {cid}", "WARN")
    # 无显式 ID 时回退到模糊匹配
    if not mandatory_items:
        mandatory_items = extract_mandatory_items(style_hint)
    if mandatory_items:
        log(f"📍 指定单品: {[(m[0], f'{m[1]:.0%}') for m in mandatory_items]}")

    # 🆕 新入库单品上下文
    new_item_context = ''
    if intent['want_new_items']:
        recent_new = get_recent_new_item_ids(pipeline_user, days=14)
        if recent_new:
            new_ids = [cid for cid, cat in recent_new]
            new_item_context = (
                f'\n🆕 用户最近入库的单品（优先考虑）: {", ".join(new_ids[:8])}\n'
                f'请优先从以上新单品中选择搭配。\n'
            )
            log(f"🆕 用户想要新品: {len(recent_new)}件最近入库单品 → {new_ids[:5]}")
        else:
            log(f"🆕 用户想要新品但最近14天无新入库单品")

    # ── 构建数据增强 prompt（统一管线）──
    prompt_data = build_enhanced_prompt(
        style_hint=style_hint,
        occasion=occasion,
        temp_high=temp_high,
        weather_cond=weather_cond,
        explore_level=explore_level,
        mandatory_items=mandatory_items if mandatory_items else None,
        user_id=pipeline_user,
        parsed_city=city_display,                  # 🆕 动态城市（中文名）
        new_item_context=new_item_context,      # 🆕 新入库单品提示
        intent_activity=intent.get('activity'), # 🆕 具体活动
        intent_vibe=intent.get('vibe'),         # 🆕 氛围/情绪
    )

    system_prompt = prompt_data['system_prompt']
    user_prompt = prompt_data['user_prompt']
    target_styles = prompt_data['target_styles']
    occasion = prompt_data['occasion']
    # 初始 token 估算（中文约 2 chars/token）
    _input_chars = len(system_prompt) + len(user_prompt)

    # ── 预估 ──
    est_tokens_init = _input_chars // 2
    progress(f'📊 预计 ~60-100s · ~{est_tokens_init} tokens')

    # ── Step 1: AI 选品 ──
    progress('🤖 AI 智能选品')

    try:
        # ── AI 创意选品（最多重试 JSON 解析）──
        plan = None
        for attempt in range(2):
            content = call_doubao_chat([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ], max_tokens=8192, timeout=180)
            _api_calls += 1

            plan = extract_json(content)
            if plan:
                break

            log(f"API 返回无法解析为 JSON (attempt {attempt+1}/2):\n{content[:500]}", "ERROR")
            if attempt == 0:
                user_prompt += "\n\n⚠️ 你的回复必须是纯 JSON，不要包含任何解释、markdown代码块标记或额外文字。以 { 开头，以 } 结尾。"
                _input_chars += 120  # 追加的 JSON 格式提醒
                log(f"🔄 JSON解析失败，重试中...")
                time.sleep(2)

        if not plan:
            raise ValueError("AI 穿搭分析返回格式异常，已重试1次仍失败，请稍后再试")

        # ⚠️ 硬拦截：检测 UNAVAILABLE
        items = plan.get('items', [])
        unavailable = [it for it in items if it.get('id', '') == 'UNAVAILABLE']
        if unavailable:
            log(f"⚠️ AI 返回了 UNAVAILABLE 单品，强制重试: {[it.get('category','') for it in unavailable]}", "WARN")
            user_prompt += "\n\n❌ 你上一次输出了 UNAVAILABLE。这是严重错误。衣柜中所有鞋子和裤子都可用。必须为上衣、下装、鞋子各选一个真实ID。"
            _input_chars += 120
            content = call_doubao_chat([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ], max_tokens=8192, timeout=180)
            _api_calls += 1
            plan = extract_json(content)
            if not plan:
                raise ValueError("AI 穿搭分析返回格式异常（UNAVAILABLE重试后JSON解析失败）")
            items2 = plan.get('items', [])
            unavailable2 = [it for it in items2 if it.get('id', '') == 'UNAVAILABLE']
            if unavailable2:
                log(f"⚠️ 重试后仍返回 UNAVAILABLE: {[it.get('category','') for it in unavailable2]}", "ERROR")
                raise ValueError("AI 两次返回 UNAVAILABLE，请稍后重试")

        # ── Step 3: 规则验证 ──
        items = plan.get('items', [])
        passed, violations, warnings = validate_outfit(items, occasion, temp_high, weather_cond, all_clothes=all_clothes, mandatory_items=mandatory_items)

        if not passed:
            log(f"⚠️ 验证未通过: {violations}", "WARN")
            # 构建修正反馈
            violation_feedback = '\n'.join(f'❌ {v}' for v in violations)
            user_prompt += f"\n\n⚠️ 你的选品有以下问题，请修正后重新输出 JSON：\n{violation_feedback}\n\n注意：所有单品必须来自衣柜表格，不要输出UNAVAILABLE。"
            _input_chars += 200
            content = call_doubao_chat([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ], max_tokens=8192, timeout=180)
            _api_calls += 1
            plan = extract_json(content)
            warnings2 = warnings  # 初始化默认值，防止 plan is None 时 2744 行 NameError
            if plan:
                items = plan.get('items', [])
                passed2, violations2, warnings2 = validate_outfit(items, occasion, temp_high, weather_cond, all_clothes=all_clothes, mandatory_items=mandatory_items)
                if not passed2:
                    log(f"⚠️ 修正后仍不通过: {violations2}", "WARN")
                    # 检查是否有致命违规（场景/天气相关），有则中止管线
                    critical_keywords = ['运动场景', '避雷品类', '禁止', '缺少']
                    critical = [v for v in violations2 if any(kw in v for kw in critical_keywords)]
                    if critical:
                        err_msg = f"AI 修正后仍有{len(critical)}项致命违规，中止管线: {'; '.join(critical)}"
                        log(err_msg, "ERROR")
                        raise ValueError(err_msg)
                    # 非致命违规继续但标记
                    violations.extend(violations2)
                else:
                    log(f"✅ 修正后验证通过")
                    violations = []
            warnings = warnings2 if plan else warnings

        if passed or not violations:
            log(f'✅ 验证通过' + (f' (⚠️ {len(warnings)}条提醒)' if warnings else ''))
        else:
            log(f'⚠️ 验证有{len(violations)}项违规（继续执行，请人工检查）')

        # ── R1 穿搭评分 ──
        outfit_score = score_outfit(items, target_styles, occasion, temp_high, weather_cond, all_clothes=all_clothes)
        log(f"📊 R1 选品评分: {outfit_score['total']}分 — {outfit_score['label']}")

        # ── Round 2: AI 创作（基于已选单品生成叙事/技巧/生图 prompt）──
        progress('✍️ AI 创作叙事+生图')
        from tools.unified_pipeline import build_creation_prompt
        photo_direction = prompt_data.get('photo_direction', '')
        # 加载用户发型档案（女性专属）
        _user_hair = None
        if pipeline_user and pipeline_user != 'default':
            try:
                _up_path = os.path.join(resolve_user_dir(pipeline_user), 'profile.json')
                if os.path.exists(_up_path):
                    with open(_up_path) as _f:
                        _up = json.load(_f)
                    if _up.get('gender') == 'female':
                        _user_hair = _up.get('hair')
            except Exception:
                pass

        r2_prompt = build_creation_prompt(
            plan, photo_direction, target_styles, style_hint,
            occasion, explore_level, temp_high, weather_cond, user_id=pipeline_user,
            user_hair=_user_hair
        )
        _beauty_en = r2_prompt.get('beauty_en', '')
        r2_content = call_doubao_chat([
            {'role': 'system', 'content': r2_prompt['system_prompt']},
            {'role': 'user', 'content': r2_prompt['user_prompt']},
        ], max_tokens=8192, timeout=120)
        _api_calls += 1

        r2_output = extract_json(r2_content)
        if r2_output and r2_output.get('seedream_prompt'):
            # 合并 R2 创作内容到 plan
            plan['keywords'] = r2_output.get('keywords', '')
            plan['reasoning'] = r2_output.get('reasoning', '')
            plan['rationale'] = r2_output.get('rationale', '')
            plan['dressing_tips'] = r2_output.get('dressing_tips', [])
            plan['seedream_prompt'] = r2_output['seedream_prompt']
            plan['color_logic'] = plan.get('color_story', '')
            # 美妆方向（女性专属）
            if r2_output.get('beauty_direction'):
                plan['beauty_direction'] = r2_output['beauty_direction']
            log(f"✅ R2 创作完成: seedream_prompt={len(plan['seedream_prompt'])}字符, tips={len(plan.get('dressing_tips',[]))}条" +
                (f", beauty={len(str(plan.get('beauty_direction', '')))}字符" if plan.get('beauty_direction') else ""))
        else:
            log(f"⚠️ R2 创作 JSON 解析失败，使用降级 prompt", "WARN")
            # 降级：基于 R1 输出构造可用的 seedream prompt
            _fallback_style = plan.get('style', '日常穿搭')
            plan['keywords'] = _fallback_style
            plan['reasoning'] = f'{plan.get("color_story", "")} · {plan.get("silhouette", "")}'
            plan['rationale'] = f'这套{_fallback_style}搭配适合{occasion}场景。'
            plan['dressing_tips'] = []
            # 女性用 beauty_en 增强 fallback，男性保持原样
            _gender_subject = 'A Chinese woman' if _user_hair else 'A Chinese male'
            _beauty_suffix = f', {_beauty_en}' if _beauty_en else ''
            plan['seedream_prompt'] = f'{_gender_subject}, {_fallback_style} style, {plan.get("color_story", "")}, full body shot, fashion photography, natural lighting{_beauty_suffix}'
            plan['color_logic'] = plan.get('color_story', '')
        step_done()

        # ── 更新状态 ──
        update_lab_state(items)

        # 执行文件操作（需 seedream_prompt 已填入 plan）
        outfit_dir = execute_outfit_plan(plan, today, style_hint, user_id=pipeline_user)

        # ── 自动记录 analytics.json ──
        try:
            pipeline_user = user_id
            items = plan.get('items', [])
            item_ids = [it['id'] for it in items]
            analytics_path = os.path.join(outfit_dir, 'analytics.json')
            analytics = {
                'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'user_id': pipeline_user or 'default',
                'items_used': item_ids,
                'style_matched': plan.get('style', ''),
                'occasion': occasion,
                'explore_level': explore_level,
                'user_tap': None,
                'user_rating': None,
                'user_wore': None,
                'generation_time_ms': int((time.time() - t_start) * 1000),
                'api_calls': _api_calls,
            }
            with open(analytics_path, 'w', encoding='utf-8') as f:
                json.dump(analytics, f, ensure_ascii=False, indent=2)
        except Exception as _ae:
            log(f"⚠️ analytics.json 写入失败（非致命）: {_ae}", "WARN")

        step_done()

        progress('🎨 Seedream AI 生图')
        _gen_cmd = ['python3', 'tools/generate.py', style_hint]
        if pipeline_user and pipeline_user != 'default':
            _gen_cmd += ['--user', pipeline_user]
        out2 = run_cli(_gen_cmd, timeout=300)
        # 检测生图失败：空输出/超时/错误标记
        if not out2 or '⏰' in out2 or '❌' in out2[:200] or '失败' in out2[:200]:
            raise RuntimeError(f'Seedream 生图失败: {out2[:300] if out2 else "无输出（可能超时）"}')
        step_done()

        # ── 预压缩：生图完成后立即生成 900w JPEG，手机首次加载秒开 ──
        progress('🎨 预压缩生图')
        sd_effect = os.path.join(outfit_dir, '上身效果')
        if os.path.exists(sd_effect):
            n = pre_compress_dir(sd_effect, widths=(900,), quality=85)
            if n:
                log(f'📐 预压缩: {n} 张 900w JPEG（上身效果）')

        progress('📤 推送 + 刷新')
        # 找生成的 AI 效果图（仅上身效果，豆包生图里是抠图素材非结果图）
        gen_img = None
        sd = os.path.join(outfit_dir, '上身效果')
        if os.path.exists(sd):
            # 优先：预压缩 900w > 上身效果_1（Pass1最佳图）> 方案图 > 任意图
            priority = [f for f in sorted(os.listdir(sd))
                       if f.endswith(('.jpg', '.png', '.webp')) and not f.startswith('.')]
            # 🆕 压缩版最优先（体积小 90%+）
            compressed = [f for f in priority if '_900w' in f and '上身效果_1' in f and '方案' not in f]
            preferred = [f for f in priority if '上身效果_1' in f and '方案' not in f and '_900w' not in f]
            fallback = [f for f in priority if '上身效果_1' in f and '_900w' not in f]
            pick = (compressed or preferred or fallback or priority)[:1]
            if pick:
                gen_img = os.path.join(sd, pick[0])

        # ── 统计摘要 ──
        elapsed = time.time() - t_start
        est_tokens = _input_chars // 2
        stats_line = f'⏱️ ~{elapsed:.0f}s · 📊 ~{est_tokens} tokens · 🔄 {_api_calls}次AI'

        # ── 立即返回本地图片 URL（手机秒看，不等 push）──
        local_img_url = None
        if gen_img:
            rel_path = os.path.relpath(gen_img, PROJECT_DIR)
            from urllib.parse import quote
            local_img_url = f'/api/image?f={quote(rel_path)}&w=900'

        if task_id:
                status_msg = f'✅ 全部完成 · {stats_line}'
                tasks.update(task_id, status='done', message=status_msg,
                             image_path=gen_img, image_url=local_img_url,
                             log='\n'.join(log_lines))
        # step_done 在 tasks.update 之前调用会覆盖 status
        # 这里手动补 done 标记
        if log_lines:
            log_lines[-1] = '✅ ' + log_lines[-1]

        # ── 后台推送（不阻塞用户看图）──
        def _background_push():
            _step_errors = []
            try:
                # ── Step 1: git add + commit + push（带重试）──
                run_cli(['git', 'add', '-A'], timeout=30)
                _commit_out = run_cli(['git', 'commit', '-m', f'🎨 {style_hint} — 远程操控'], timeout=30)
                if 'nothing to commit' not in _commit_out:
                    for _retry in range(3):
                        _push_out = run_cli(['git', 'push'], timeout=60)
                        if not _push_out.startswith('❌'):
                            log(f'📤 Git push 成功 (尝试 {_retry+1}/3)')
                            # 清除 git commit 缓存，后续 CDN URL 使用新 commit
                            from tools.common import invalidate_git_commit_cache
                            invalidate_git_commit_cache()
                            break
                        log(f'⚠️ Git push 重试 {_retry+1}/3: {_push_out[:100]}')
                        time.sleep(3 * (_retry + 1))  # 递增等待
                    else:
                        _step_errors.append(f'Git push 3次重试均失败')
                        log(f'❌ Git push 最终失败')
                else:
                    log(f'📝 无新文件需要提交')

                # ── Step 2: 重建原型（git push 成功后）──
                _pu = user_id  # 闭包捕获
                proto_updates = []
                # 主用户原型
                try:
                    _proto_out = run_cli(['python3', 'tools/build_prototype.py'], timeout=30)
                    log(f'📱 主原型: {"重建" if "Written" in _proto_out else "无变更"}')
                except Exception as _e:
                    _step_errors.append(f'主原型构建: {_e}')
                    log(f'⚠️ 主原型构建失败: {_e}')
                # 多用户原型
                if _pu and _pu != 'default':
                    try:
                        user_proto = os.path.join(PROJECT_DIR, 'users', _pu, 'cache', 'prototype.html')
                        _uproto_out = run_cli([sys.executable, os.path.join(PROJECT_DIR, 'tools', 'build_prototype.py'), '--user', _pu], timeout=60)
                        if os.path.exists(user_proto):
                            proto_updates.append(os.path.relpath(user_proto, PROJECT_DIR))
                            log(f'📱 用户原型({_pu}): 已重建')
                    except Exception as _e:
                        _step_errors.append(f'用户原型构建: {_e}')
                        log(f'⚠️ 用户原型构建失败: {_e}')

                # ── 写入 .proto_ready 标记，让 _load_chat_html 知道原型已更新 ──
                try:
                    _outfits_root = resolve_outfits_dir(_pu) if (_pu and _pu != 'default') else os.path.join(PROJECT_DIR, 'outfits')
                    if os.path.isdir(_outfits_root):
                        with open(os.path.join(_outfits_root, '.proto_ready'), 'w') as _rf:
                            _rf.write(time.strftime('%Y-%m-%dT%H:%M:%S'))
                except Exception:
                    pass

                # ── Step 4: 提交原型变更 ──
                proto_status = run_cli(['git', 'status', '--short', 'prototype/mobile-v2.html'], timeout=10)
                if proto_status.strip():
                    proto_updates.append('prototype/mobile-v2.html')
                if proto_updates:
                    run_cli(['git', 'add'] + proto_updates, timeout=10)
                    run_cli(['git', 'commit', '-m', '📱 重建原型'], timeout=10)
                    for _retry in range(2):
                        _push_out = run_cli(['git', 'push'], timeout=30)
                        if not _push_out.startswith('❌'):
                            break
                        time.sleep(2)

                # ── 汇总 ──
                if _step_errors:
                    _err_msg = '; '.join(_step_errors[-2:])
                    log(f'📤 后台推送完成 (有 {len(_step_errors)} 个警告): {_err_msg}')
                    # 回写 task 状态，让用户看到推送异常
                    if task_id:
                        tasks.update(task_id, status='done',
                                     message=f'⚠️ 后台同步异常: {_err_msg}',
                                     image_url=local_img_url)
                else:
                    log(f'📤 后台推送完成: {style_hint}')
            except Exception as e:
                log(f'❌ 后台推送致命错误: {e}', 'ERROR')

        threading.Thread(target=_background_push, daemon=True).start()

        # 保存历史记录
        save_history({
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'style': style_hint,
            'status': 'done',
            'image_url': local_img_url if gen_img else None,
            'stats': stats_line,
        })
    except Exception as e:
        if task_id:
            tasks.update(task_id, status='error', message=str(e)[:200], log='\n'.join(log_lines))

def _complete_onboarding(user_id, user_dir):
    """标记用户 onboarding 完成"""
    up = os.path.join(user_dir, 'profile.json')
    p = {}
    if os.path.exists(up):
        with open(up) as f:
            p = json.load(f)
    p['onboarding_step'] = 4
    p['onboarding_complete'] = True
    p['onboarding_done_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with open(up, 'w') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    # 更新注册表
    reg = _load_user_registry()
    if user_id in reg:
        reg[user_id]['status'] = 'active'
        reg[user_id]['last_active'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            from tools.user_manager import save_registry
            save_registry(reg)
        except Exception as _e:
            log(f"⚠️ save_registry 失败（非致命）: {_e}", "ERROR")
    log(f"✅ Onboarding 完成: {user_id}")

    # 后台构建用户原型
    def _bg_build_proto():
        try:
            log(f"🔨 构建用户原型: {user_id}")
            result = subprocess.run(
                [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'build_prototype.py'), '--user', user_id],
                capture_output=True, text=True, timeout=120,
                cwd=PROJECT_DIR
            )
            if result.returncode == 0:
                log(f"✅ 用户原型构建完成: {user_id}")
            else:
                log(f"⚠️ 用户原型构建失败: {user_id} — {result.stderr[:200] if result.stderr else 'unknown'}")
        except Exception as e:
            log(f"❌ 用户原型构建异常: {user_id} — {e}")
    threading.Thread(target=_bg_build_proto, daemon=True).start()

def _start_async_pipeline(action, extra, user_id=None):
    """启动异步穿搭管线，返回 task_id"""
    tid = tasks.create()
    style = extra if extra else "今日穿搭"
    threading.Thread(target=run_pipeline, args=(style, tid, user_id), daemon=True).start()
    return tid

def execute_action(action, extra, task_id=None):
    """执行指令并返回结果"""
    log(f"指令: {action} | {extra}")

    if action == 'help':
        return HELP_TEXT
    elif action == 'sync':
        return run_cli(['bash', 'sync.sh'], timeout=60)
    elif action == 'status':
        status_output = run_cli(['git', 'status', '--short'], timeout=30)
        branch_output = run_cli(['git', 'branch', '--show-current'], timeout=10)
        return f"📂 分支: {branch_output}\n📋 状态:\n{status_output if status_output else '(干净)'}"
    elif action == 'recommend':
        _start_async_pipeline(action, extra)
        return None  # 异步，结果通过 task 轮询
    elif action == 'generate':
        _start_async_pipeline(action, extra)
        return None
    elif action == 'unknown':
        return f"🤔 未识别的指令: 「{extra}」\n\n{HELP_TEXT}"
    return "❌ 未知错误"

def _render_encyclopedia_html(md_path, style_id, dir_name):
    """将 encyclopedia.md 渲染为移动端 HTML"""
    with open(md_path, 'r', encoding='utf-8') as f:
        md = f.read()

    # 提取标题（第一行 # xxx）
    title_match = re.match(r'^#\s+(.+?)(?:\s*（.*）)?\s*$', md.split('\n')[0])
    name_zh = title_match.group(1).strip() if title_match else dir_name

    # 提取状态行
    status_line = ''
    for line in md.split('\n'):
        if line.startswith('> **状态**'):
            status_line = line.strip().lstrip('>').strip()
            break

    # 简单 Markdown → HTML 转换
    html_lines = []
    in_table = False
    in_code = False
    in_list = False

    for line in md.split('\n')[1:]:  # skip title
        stripped = line.strip()

        # Skip cover image
        if stripped.startswith('![') and 'representative' in stripped:
            continue

        # Headers
        if stripped.startswith('## '):
            if in_table: html_lines.append('</table>'); in_table = False
            if in_list: html_lines.append('</ul>'); in_list = False
            html_lines.append(f'<h2>{stripped[3:]}</h2>')
            continue
        if stripped.startswith('### '):
            if in_table: html_lines.append('</table>'); in_table = False
            if in_list: html_lines.append('</ul>'); in_list = False
            html_lines.append(f'<h3>{stripped[4:]}</h3>')
            continue

        # Blockquote
        if stripped.startswith('>'):
            if in_table: html_lines.append('</table>'); in_table = False
            content = stripped.lstrip('>').strip()
            html_lines.append(f'<blockquote>{content}</blockquote>')
            continue

        # Horizontal rule
        if stripped == '---':
            if in_table: html_lines.append('</table>'); in_table = False
            if in_list: html_lines.append('</ul>'); in_list = False
            html_lines.append('<hr>')
            continue

        # Table
        if '|' in stripped and stripped.startswith('|'):
            if not in_table:
                html_lines.append('<table>')
                in_table = True
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if all(c.startswith('-') or c.startswith(':') for c in cells if c):
                continue  # skip separator row
            is_header = all(c.startswith('**') and c.endswith('**') for c in cells if c)
            tag = 'th' if is_header else 'td'
            row = ''.join(f'<{tag}>{c.strip("*")}</{tag}>' for c in cells)
            html_lines.append(f'<tr>{row}</tr>')
            continue
        elif in_table:
            html_lines.append('</table>')
            in_table = False

        # List items
        if stripped.startswith('- ') or stripped.startswith('  - '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = re.sub(r'^\s*-\s+', '', stripped)
            # Bold
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f'<li>{content}</li>')
            continue
        elif in_list and not stripped.startswith('-'):
            html_lines.append('</ul>')
            in_list = False

        # Bold + italic in paragraphs
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)

        if line:
            html_lines.append(f'<p>{line}</p>')
        elif not in_table:
            html_lines.append('<br>')

    if in_table: html_lines.append('</table>')
    if in_list: html_lines.append('</ul>')

    body = '\n'.join(html_lines)

    # 加载封面图
    rep_path = os.path.join(os.path.dirname(md_path), 'representative.jpg')
    cover_html = ''
    if os.path.exists(rep_path):
        commit = get_git_commit()
        base = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}'
        cover_url = f'{base}/styles/female/{dir_name}/representative.jpg'
        cover_html = f'<img src="{cover_url}" alt="{name_zh}" style="width:100%;max-width:400px;border-radius:12px;margin:16px auto;display:block">'

    css = '''
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#fff;color:#333;line-height:1.8;max-width:680px;margin:0 auto;padding:0 16px 40px}
h1{font-size:24px;font-weight:700;margin:32px 0 8px}
h2{font-size:18px;font-weight:700;margin:28px 0 10px;padding-left:8px;border-left:3px solid #d4a574}
h3{font-size:15px;font-weight:700;margin:20px 0 6px;color:#555}
p{font-size:15px;margin:6px 0}
ul{padding-left:18px;margin:8px 0}
li{font-size:15px;margin:4px 0}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
th,td{border:1px solid #eee;padding:8px 10px;text-align:left}
th{background:#faf8f5;font-weight:600}
tr:nth-child(even){background:#fdfcf9}
blockquote{background:#fdf8f3;border-left:3px solid #d4a574;margin:10px 0;padding:8px 14px;color:#8b7355;border-radius:0 6px 6px 0;font-size:13px}
hr{border:none;border-top:1px solid #f0f0f0;margin:24px 0}
strong{color:#444}
.status-bar{font-size:12px;color:#999;margin:8px 0 20px;padding:8px 12px;background:#faf8f5;border-radius:8px}
'''

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name_zh} — 风格百科</title>
<style>{css}</style>
</head>
<body>
<h1>{name_zh}</h1>
{cover_html}
<div class="status-bar">{status_line}</div>
{body}
</body>
</html>'''

def _style_has_image(style_id):
    """检查风格是否有代表性图片，返回 {thumb: CDN缩略图URL, full: CDN原图URL} 或 None"""
    img_path = os.path.join(PROJECT_DIR, 'styles_universal', style_id, 'representative.jpg')
    if os.path.exists(img_path):
        commit = get_git_commit()
        base = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}'
        rel_full = f'styles_universal/{style_id}/representative.jpg'
        rel_thumb = f'styles_universal/{style_id}/representative_thumb.jpg'
        thumb_path = os.path.join(PROJECT_DIR, 'styles_universal', style_id, 'representative_thumb.jpg')
        return {
            'thumb': f'{base}/{rel_thumb}' if os.path.exists(thumb_path) else f'{base}/{rel_full}',
            'full': f'{base}/{rel_full}',
        }
    return None

def _load_style_cards(include_universal=False, with_top_items=False, user_id=None):
    """加载风格卡片数据，返回 [{id, name_zh, name_en, description, category, has_encyclopedia, image, top_items?}]
    女性用户自动加载 styles/female/ 下的风格，男性用户加载 styles/male/ + styles_universal/"""
    styles = []

    # ── 判断用户性别 ──
    is_female = False
    if user_id and user_id != 'default':
        try:
            profile_path = os.path.join(resolve_user_dir(user_id), 'profile.json')
            if os.path.exists(profile_path):
                with open(profile_path) as f:
                    p = json.load(f)
                if p.get('gender', '').lower() == 'female':
                    is_female = True
        except:
            pass

    # ── 设置线程上下文（让 rank_items_for_style / load_all_clothing 找到用户衣橱）──
    if user_id and user_id != 'default':
        try:
            gender = 'female' if is_female else 'male'
            set_thread_user(gender, user_id)
        except Exception:
            pass

    # ── 女性用户：加载 styles/female/ ──
    if is_female:
        women_dir = os.path.join(PROJECT_DIR, 'styles/female')
        if os.path.isdir(women_dir):
            for d in sorted(os.listdir(women_dir)):
                if d.startswith('.') or d.startswith('_') or d == 'README.md':
                    continue
                dp = os.path.join(women_dir, d)
                if not os.path.isdir(dp):
                    continue
                # 尝试从 fingerprint.json 读取
                fp = os.path.join(dp, 'fingerprint.json')
                sid = d
                name_zh = d.split('_', 1)[-1] if '_' in d else d
                name_en = ''
                description = ''
                category = ''
                has_encyclopedia = os.path.exists(os.path.join(dp, 'encyclopedia.md'))
                if os.path.exists(fp):
                    try:
                        with open(fp) as f:
                            fd = json.load(f)
                        sid = fd.get('style_id', d)
                        name_zh = fd.get('name_zh', name_zh)
                        name_en = fd.get('name_en', '')
                        description = (fd.get('description', '') or '')[:120]
                        category = fd.get('category', '')
                    except:
                        pass
                # 首图逻辑对齐男士：优先 representative.jpg（CDN），其次 images/ 目录
                image_url = ''
                image_full = ''
                rep_path = os.path.join(dp, 'representative.jpg')
                rep_thumb_path = os.path.join(dp, 'representative_thumb.jpg')
                if os.path.exists(rep_path):
                    # 使用 CDN（与男士一致）
                    commit = get_git_commit()
                    base = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}'
                    image_url = f'{base}/styles/female/{d}/representative_thumb.jpg' if os.path.exists(rep_thumb_path) else f'{base}/styles/female/{d}/representative.jpg'
                    image_full = f'{base}/styles/female/{d}/representative.jpg'
                else:
                    img_dir = os.path.join(dp, 'images')
                    if os.path.isdir(img_dir):
                        imgs = sorted([x for x in os.listdir(img_dir) if not x.startswith('.')])
                        if imgs:
                            first_img = imgs[0]
                            name_noext, ext = os.path.splitext(first_img)
                            thumb_name = f'{name_noext}_thumb.jpg'
                            thumb_path = os.path.join(img_dir, thumb_name)
                            if os.path.exists(thumb_path):
                                image_url = f'/styles/female/{d}/images/{thumb_name}'
                            else:
                                image_url = f'/styles/female/{d}/images/{first_img}'
                            image_full = f'/styles/female/{d}/images/{first_img}'
                # ── 计算 top 关联单品（与男性路径一致）──
                top_items = []
                if with_top_items:
                    try:
                        sys.path.insert(0, os.path.join(PROJECT_DIR, 'tools'))
                        from style_matcher import rank_items_for_style
                        top = rank_items_for_style(sid, top_n=8, min_score=10)
                        def _thumb_url(cid):
                            rel = _find_item_thumb(cid)
                            if rel:
                                path = rel.split('?')[0]
                                commit = get_git_commit()
                                return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}/{path}'
                            return ''
                        def _cutout_url(cid):
                            from urllib.parse import quote
                            cutout = _find_item_cutout(cid)
                            if cutout:
                                path = cutout.split('?')[0]
                                return f'/api/image?f={quote(path)}'
                            return ''
                        top_items = [
                            {'clothing_id': t['clothing_id'], 'category_code': t.get('category', '')[:4],
                             'score': t['score'],
                             'thumb': _thumb_url(t['clothing_id']),
                             'cutout': _cutout_url(t['clothing_id'])}
                            for t in (top or [])[:3]
                        ]
                    except Exception:
                        pass
                styles.append({
                    'id': sid,
                    'name_zh': name_zh,
                    'name_en': name_en,
                    'description': description,
                    'category': category,
                    'has_encyclopedia': has_encyclopedia,
                    'image': image_url,
                    'image_full': image_full or image_url,
                    'top_items': top_items,
                })
        return styles

    # ── 男性/默认：加载 styles/male/ (风格指纹) ──
    styles_dir = os.path.join(PROJECT_DIR, 'styles/male')
    if os.path.isdir(styles_dir):
        for fn in sorted(os.listdir(styles_dir)):
            if not fn.endswith('.json'): continue
            fp = os.path.join(styles_dir, fn)
            try:
                with open(fp) as f:
                    d = json.load(f)
                sid = d.get('style_id', fn.replace('.json', ''))
                name_zh = d.get('name_zh', sid)
                img_info = _style_has_image(sid)
                card = {
                    'id': sid,
                    'name_zh': name_zh,
                    'name_en': d.get('name_en', ''),
                    'description': (d.get('description') or '')[:120],
                    'category': d.get('category', ''),
                    'has_encyclopedia': os.path.exists(os.path.join(
                        PROJECT_DIR, 'styles_universal', sid, 'encyclopedia.md')),
                    'image': img_info['thumb'] if img_info else '',
                    'image_full': img_info['full'] if img_info else '',
                }
                # 计算 top 3 关联单品
                if with_top_items:
                    try:
                        sys.path.insert(0, os.path.join(PROJECT_DIR, 'tools'))
                        from style_matcher import rank_items_for_style
                        top = rank_items_for_style(sid, top_n=8, min_score=10)
                        def _thumb_url(cid):
                            # Use CDN-friendly thumb path (same as wardrobe list)
                            rel = _find_item_thumb(cid)
                            if rel:
                                # _find_item_thumb returns 'path?v=mtime', strip v= for CDN
                                path = rel.split('?')[0]
                                commit = get_git_commit()
                                return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit}/{path}'
                            return ''
                        def _cutout_url(cid):
                            # 🆕 本地大图（抠图），用于弹窗查看细节
                            from urllib.parse import quote
                            cutout = _find_item_cutout(cid)
                            if cutout:
                                path = cutout.split('?')[0]
                                return f'/api/image?f={quote(path)}'
                            return ''
                        card['top_items'] = [
                            {'clothing_id': t['clothing_id'], 'category_code': t.get('category', '')[:4],
                             'score': t['score'],
                             'thumb': _thumb_url(t['clothing_id']),
                             'cutout': _cutout_url(t['clothing_id'])}
                            for t in (top or [])[:3]
                        ]
                    except Exception:
                        card['top_items'] = []
                styles.append(card)
            except: pass
    # Universal styles (not already in B-line)
    if include_universal:
        univ_dir = os.path.join(PROJECT_DIR, 'styles_universal')
        b_ids = {s['id'] for s in styles}
        if os.path.isdir(univ_dir):
            for d in sorted(os.listdir(univ_dir)):
                if d.startswith('.') or d.startswith('_') or d in b_ids: continue
                dp = os.path.join(univ_dir, d)
                if not os.path.isdir(dp): continue
                enc = os.path.join(dp, 'encyclopedia.md')
                if not os.path.exists(enc): continue
                try:
                    with open(enc) as f:
                        first_line = f.readline().strip()
                    name_zh = first_line.lstrip('# ').split('(')[0].strip() if first_line.startswith('#') else d
                    img_info = _style_has_image(d)
                    styles.append({
                        'id': d,
                        'name_zh': name_zh,
                        'name_en': d.replace('_', ' ').title(),
                        'description': '',
                        'category': '',
                        'has_encyclopedia': True,
                        'image': img_info['thumb'] if img_info else '',
                        'image_full': img_info['full'] if img_info else '',
                        'top_items': [],
                    })
                except: pass
    return styles


# ═══════════════════════════════════════════════════════════════
# Explore 个性化匹配 — 辅助函数
# ═══════════════════════════════════════════════════════════════

def _load_user_style_context(user_id):
    """加载用户个性化数据源，返回统一 context dict。
    包含: style_prefs (引导选择), gender, has_clothing, has_ratings"""
    ctx = {
        'style_prefs': [],
        'gender': 'male',
        'has_clothing': False,
        'has_ratings': False,
    }
    if not user_id or user_id == 'default':
        return ctx

    try:
        # 读取 profile.json
        profile_path = os.path.join(resolve_user_dir(user_id), 'profile.json')
        if os.path.exists(profile_path):
            with open(profile_path) as f:
                p = json.load(f)
            ctx['style_prefs'] = p.get('style_prefs', []) or []
            ctx['gender'] = p.get('gender', 'male')

        # 检查衣橱数据
        tags_dir = os.path.join(resolve_user_dir(user_id), 'wardrobe', 'tags')
        if os.path.isdir(tags_dir):
            jsons = [f for f in os.listdir(tags_dir) if f.endswith('.json') and f != 'SCORE_CACHE.json']
            ctx['has_clothing'] = len(jsons) > 0

        # 检查评分历史
        outfits_dir = os.path.join(resolve_user_dir(user_id), 'outfits')
        if os.path.isdir(outfits_dir):
            for d in os.listdir(outfits_dir):
                rp = os.path.join(outfits_dir, d, 'rating.json')
                if os.path.exists(rp):
                    ctx['has_ratings'] = True
                    break
    except Exception:
        pass

    return ctx


def _load_all_style_fingerprints(gender):
    """按性别加载全部风格指纹，返回 {style_id: fingerprint_dict}
    每个 fingerprint 包含 related_styles, conflicting_styles 等字段。
    替代 style_lab.load_all_styles()（旧路径已失效）。"""
    fps = {}
    if gender == 'female':
        women_dir = os.path.join(PROJECT_DIR, 'styles/female')
        if os.path.isdir(women_dir):
            for d in sorted(os.listdir(women_dir)):
                if d.startswith('.') or d.startswith('_'): continue
                dp = os.path.join(women_dir, d)
                if not os.path.isdir(dp): continue
                fp_path = os.path.join(dp, 'fingerprint.json')
                if os.path.exists(fp_path):
                    try:
                        with open(fp_path) as f:
                            fd = json.load(f)
                        sid = fd.get('style_id', d)
                        fps[sid] = fd
                    except Exception:
                        pass
    else:
        male_dir = os.path.join(PROJECT_DIR, 'styles/male')
        if os.path.isdir(male_dir):
            for fn in sorted(os.listdir(male_dir)):
                if not fn.endswith('.json'): continue
                fp_path = os.path.join(male_dir, fn)
                try:
                    with open(fp_path) as f:
                        fd = json.load(f)
                    sid = fd.get('style_id', fn.replace('.json', ''))
                    fps[sid] = fd
                except Exception:
                    pass
    return fps


def _compute_wardrobe_style_affinity(user_id, gender, style_ids):
    """计算用户衣橱与候选风格的匹配度。
    返回 {style_id: {'avg_score': float, 'item_count': int, 'top_items': list}}"""
    affinity = {}
    if not user_id or not style_ids:
        return affinity

    try:
        sys.path.insert(0, os.path.join(PROJECT_DIR, 'tools'))
        from style_matcher import rank_items_for_style
        for sid in style_ids:
            try:
                ranked = rank_items_for_style(sid, top_n=10, min_score=15)
                if ranked:
                    scores = [it['score'] for it in ranked]
                    affinity[sid] = {
                        'avg_score': round(sum(scores) / len(scores), 1),
                        'item_count': len(ranked),
                        'top_items': [it['clothing_id'] for it in ranked[:3]],
                    }
            except Exception:
                pass
    except Exception:
        pass

    return affinity


def _get_dynamic_mode_styles(mode, user_id=None):
    """根据用户个性化数据计算三种探索模式应展示的风格列表。

    mode: 'tweak' (日常穿搭) | 'transform' (改变自己) | 'cross' (大胆跨界)

    信号优先级: style_prefs (引导选择) > 评分舒适区 > 衣橱匹配 > 趋势fallback
    无任何数据时返回 {'styles': [], 'hint': '...'} 提示用户完成引导或上传衣服。
    """
    styles = _load_style_cards(with_top_items=True, user_id=user_id)

    # ── 1. 加载用户上下文 ──
    ctx = _load_user_style_context(user_id)
    gender = ctx.get('gender', 'male')
    style_prefs = set(ctx.get('style_prefs', []))

    # ── 2. 加载全部风格指纹（related/conflicting 关系）──
    all_fps = _load_all_style_fingerprints(gender)

    # ── 3. 加载 trend_category 映射 ──
    trend_map = {}
    for cat_path in [
        os.path.join(PROJECT_DIR, 'styles_universal', 'categories.json'),
        os.path.join(PROJECT_DIR, 'styles/female', 'categories.json'),
    ]:
        if os.path.exists(cat_path):
            try:
                with open(cat_path) as f:
                    cat_data = json.load(f)
                for sid, info in cat_data.get('style_registry', {}).items():
                    tc = info.get('trend_category')
                    if tc:
                        trend_map[sid] = tc
                        d = info.get('dir', '')
                        if d and d != sid:
                            trend_map[d] = tc
            except Exception:
                pass

    # ── 4. 加载评分舒适区 ──
    comfort_styles = set()
    explored_styles = set()
    unexplored_styles = set()
    disliked_styles = set()
    try:
        sys.path.insert(0, os.path.join(PROJECT_DIR, 'tools'))
        from style_lab import get_user_comfort_zone
        zone = get_user_comfort_zone()
        comfort_styles = set(zone.get('comfort_styles', []))
        explored_styles = set(zone.get('explored_styles', []))
        unexplored_styles = set(zone.get('unexplored_styles', []))
        disliked_styles = set(zone.get('disliked_styles', []))
    except Exception:
        pass

    # ── 5. 构建核心风格集 (core = style_prefs + comfort_styles) ──
    core = style_prefs | comfort_styles

    # 从指纹中解析 related_styles 和 conflicting_styles
    def _related_of(sid_set):
        rel = set()
        for sid in sid_set:
            fp = all_fps.get(sid, {})
            for rs in fp.get('related_styles', []):
                if rs not in sid_set and rs not in disliked_styles:
                    rel.add(rs)
        return rel

    def _conflicting_of(sid_set):
        conf = set()
        for sid in sid_set:
            fp = all_fps.get(sid, {})
            for cs in fp.get('conflicting_styles', []):
                if cs not in sid_set and cs not in disliked_styles:
                    conf.add(cs)
        return conf

    # ── 6. 判断数据可用性 ──
    has_any_data = bool(style_prefs) or ctx.get('has_clothing') or ctx.get('has_ratings')

    # ── 7. 按模式过滤 ──
    filtered = []

    if mode == 'tweak':
        candidate_ids = set()

        # Tier 1: style_prefs (引导阶段选择的风格)
        if style_prefs:
            candidate_ids |= style_prefs

        # Tier 2: comfort_styles (评分舒适区)
        if comfort_styles:
            candidate_ids |= comfort_styles

        # Tier 3: 衣橱高匹配
        if ctx.get('has_clothing') and not candidate_ids:
            all_ids = [s['id'] for s in styles]
            aff = _compute_wardrobe_style_affinity(user_id, gender, all_ids[:20])
            top = sorted(aff.items(), key=lambda x: -x[1]['avg_score'])[:5]
            candidate_ids |= {sid for sid, _ in top}

        # 过滤
        if candidate_ids:
            filtered = [s for s in styles if s['id'] in candidate_ids]
        else:
            filtered = [s for s in styles if trend_map.get(s['id']) == 'classic']

        for s in filtered:
            s['comfort_distance'] = 'adjacent'

    elif mode == 'transform':
        candidate_ids = set()

        # Tier 1: core 的 related_styles
        if core:
            candidate_ids |= _related_of(core)

        # Tier 2: popular_trend（排除已在 core 的）
        candidate_ids |= {s['id'] for s in styles
                          if trend_map.get(s['id']) == 'popular_trend'
                          and s['id'] not in core}

        # Tier 3: 衣橱中分匹配
        if ctx.get('has_clothing') and not candidate_ids:
            all_ids = [s['id'] for s in styles]
            aff = _compute_wardrobe_style_affinity(user_id, gender, all_ids[:20])
            sorted_aff = sorted(aff.items(), key=lambda x: -x[1]['avg_score'])
            mid = sorted_aff[3:10] if len(sorted_aff) > 3 else sorted_aff
            candidate_ids |= {sid for sid, _ in mid}

        if candidate_ids:
            filtered = [s for s in styles if s['id'] in candidate_ids
                        and s['id'] not in disliked_styles]
        else:
            filtered = [s for s in styles if trend_map.get(s['id']) == 'popular_trend']

        for s in filtered:
            is_related = core and s['id'] in _related_of(core)
            s['comfort_distance'] = 'step' if is_related else 'adjacent'

    elif mode == 'cross':
        candidate_ids = set()

        # Tier 1: core 的 conflicting_styles
        if core:
            candidate_ids |= _conflicting_of(core)

        # Tier 2: unexplored + niche
        candidate_ids |= set(unexplored_styles)
        candidate_ids |= {s['id'] for s in styles
                          if trend_map.get(s['id']) == 'niche'
                          and s['id'] not in core}

        # Tier 3: 衣橱低分匹配（远距离风格）
        if ctx.get('has_clothing') and not candidate_ids:
            all_ids = [s['id'] for s in styles]
            aff = _compute_wardrobe_style_affinity(user_id, gender, all_ids[:20])
            sorted_aff = sorted(aff.items(), key=lambda x: x[1]['avg_score'])  # 升序
            candidate_ids |= {sid for sid, _ in sorted_aff[:5]}

        # 排除不喜欢的
        candidate_ids -= disliked_styles

        if candidate_ids:
            filtered = [s for s in styles if s['id'] in candidate_ids]
        else:
            filtered = [s for s in styles if trend_map.get(s['id']) == 'niche']

        for s in filtered:
            s['comfort_distance'] = 'leap' if s['id'] in unexplored_styles else 'step'

    else:
        filtered = styles

    # ── 8. 最终兜底 ──
    if not filtered:
        filtered = styles[:6]

    # ── 9. 空状态提示 ──
    if not has_any_data:
        hints = {
            'tweak': '请先完成风格引导或上传衣服，系统才能了解您的风格偏好',
            'transform': '上传更多衣服后，系统会为您推荐相邻风格',
            'cross': '探索更多风格后，系统会推荐大胆跨界的组合',
        }
        return {'styles': filtered, 'hint': hints.get(mode, '')}

    return filtered


# ── 聊天界面 HTML（从 prototype/mobile-v2.html 加载）───


def _inject_empty_state(html, user_id):
    """新用户无穿搭时注入空状态引导 JS"""
    if not user_id or user_id == 'default':
        return html
    os.makedirs(resolve_outfits_dir(user_id), exist_ok=True)
    user_outfits = resolve_outfits_dir(user_id)
    has_outfits = False
    if os.path.isdir(user_outfits):
        for _d in os.listdir(user_outfits):
            if os.path.isdir(os.path.join(user_outfits, _d)) and not _d.startswith('.'):
                has_outfits = True
                break
    if not has_outfits:
        html = html.replace('<div class="page active" id="page-recommend">', '<div class="page active" id="page-recommend" data-new-user="true">')
        js_file = os.path.join(PROJECT_DIR, "tools", "empty_state.js")
        if os.path.exists(js_file):
            with open(js_file) as ef:
                empty_js = ef.read()
            html = html.replace("</body>", "<script>" + empty_js + "</script></body>")
    return html

def _load_gender_gate_html():
    """加载性别选择首页 HTML"""
    gate_path = os.path.join(PROJECT_DIR, 'prototype', 'gender_gate.html')
    if os.path.exists(gate_path):
        with open(gate_path, 'r', encoding='utf-8') as f:
            return f.read()
    # 最小回退
    return '<html><body><h1>Fashion Advisor</h1><p>Loading...</p></body></html>'

def _load_chat_html(user_id=None, gender=None):
    """Load prototype HTML from file, with caching. Multi-user loads from users/<gender>/<id>/cache/."""
    if user_id and user_id != 'default' and gender:
        proto_path = os.path.join(PROJECT_DIR, 'users', gender, user_id, 'cache', 'prototype.html')
        if os.path.exists(proto_path):
            # 检查原型是否过时：如果最新 outfit 比原型文件新，后台异步重建
            _outfits_dir = resolve_outfits_dir(gender, user_id)
            _proto_mtime = os.path.getmtime(proto_path)
            _latest_data_mtime = _proto_mtime
            if os.path.isdir(_outfits_dir):
                for _d in os.listdir(_outfits_dir):
                    _dp = os.path.join(_outfits_dir, _d)
                    if os.path.isdir(_dp) and not _d.startswith('.'):
                        _dp_mtime = os.path.getmtime(_dp)
                        if _dp_mtime > _latest_data_mtime:
                            _latest_data_mtime = _dp_mtime
            # 检查 .proto_ready 标记
            _ready_marker = os.path.join(_outfits_dir, '.proto_ready')
            _proto_is_fresh = False
            if os.path.exists(_ready_marker):
                _ready_mtime = os.path.getmtime(_ready_marker)
                if _ready_mtime >= _latest_data_mtime:
                    _proto_is_fresh = True
            if not _proto_is_fresh and _latest_data_mtime > _proto_mtime + 10:
                log(f"⏰ 原型过时 (滞后 {_latest_data_mtime - _proto_mtime:.0f}s)，后台重建: {user_id}")
                def _bg_rebuild_proto(_uid=user_id, _g=gender, _pp=proto_path):
                    try:
                        with _proto_rebuild_lock:
                            subprocess.run(
                                [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'build_prototype.py'), '--gender', _g, '--user', _uid],
                                capture_output=True, text=True, timeout=60, cwd=PROJECT_DIR)
                    except Exception: pass
                threading.Thread(target=_bg_rebuild_proto, daemon=True).start()
            with open(proto_path, "r", encoding="utf-8") as f:
                return _inject_empty_state(f.read(), user_id)
        # Fallback: build prototype on the fly for this user
        log(f"🔨 构建用户原型: {gender}/{user_id}")
        os.makedirs(resolve_outfits_dir(gender, user_id), exist_ok=True)
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'build_prototype.py'), '--gender', gender, '--user', user_id],
                capture_output=True, text=True, timeout=60,
                cwd=PROJECT_DIR
            )
            if result.returncode == 0 and os.path.exists(proto_path):
                with open(proto_path, "r", encoding="utf-8") as f:
                    return _inject_empty_state(f.read(), user_id)
        except Exception as e:
            log(f"⚠️ 构建用户原型失败: {user_id} — {e}")
    # Default / fallback — but for new users with no data, inject welcome prompt
    # Check if this is a specific user with no outfits
    proto_path = os.path.join(PROJECT_DIR, "prototype", "mobile-v2.html")
    if os.path.exists(proto_path):
        # 同样检查默认原型是否过时
        _outfits_dir = os.path.join(PROJECT_DIR, 'outfits')
        _proto_mtime = os.path.getmtime(proto_path)
        _latest_data_mtime = _proto_mtime
        if os.path.isdir(_outfits_dir):
            for _d in os.listdir(_outfits_dir):
                _dp = os.path.join(_outfits_dir, _d)
                if os.path.isdir(_dp) and not _d.startswith('.'):
                    _dp_mtime = os.path.getmtime(_dp)
                    if _dp_mtime > _latest_data_mtime:
                        _latest_data_mtime = _dp_mtime
        _ready_marker = os.path.join(_outfits_dir, '.proto_ready')
        _proto_is_fresh = False
        if os.path.exists(_ready_marker):
            _ready_mtime = os.path.getmtime(_ready_marker)
            if _ready_mtime >= _latest_data_mtime:
                _proto_is_fresh = True
        if not _proto_is_fresh and _latest_data_mtime > _proto_mtime + 10:
            log(f"⏰ 默认原型过时 (滞后 {_latest_data_mtime - _proto_mtime:.0f}s)，后台重建")
            def _bg_rebuild_main(_pp=proto_path):
                try:
                    with _proto_rebuild_lock:
                        subprocess.run(
                            [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'build_prototype.py')],
                            capture_output=True, text=True, timeout=60, cwd=PROJECT_DIR)
                except Exception: pass
            threading.Thread(target=_bg_rebuild_main, daemon=True).start()
        with open(proto_path, "r", encoding="utf-8") as f:
            return f.read()
    # Fallback minimal HTML
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>穿搭助手</title></head><body style="font-family:sans-serif;text-align:center;padding-top:60px"><h2>原型文件未找到</h2><p>请运行 python3 tools/build_prototype.py</p></body></html>"""


# ── 今日穿搭计数器 ───────────────────────────────────────
_TODAY_CLICKS = {}  # {date_str: count}

def _handle_today(handler):
    """智能今日穿搭：首次返回已有，后续生成新品"""
    today = time.strftime('%Y-%m-%d')
    click_count = _TODAY_CLICKS.get(today, 0) + 1
    _TODAY_CLICKS[today] = click_count

    # 多用户：使用用户的 outfits 目录
    uid = getattr(handler, 'user_id', 'default')
    user_outfits = resolve_outfits_dir(None if uid == 'default' else uid)

    # 检查今日是否已有 outfit
    existing = []
    if os.path.isdir(user_outfits):
        for d in sorted(os.listdir(user_outfits), reverse=True):
            if d.startswith(today):
                dp = os.path.join(user_outfits, d)
                md = os.path.join(dp, 'outfit.md')
                if os.path.exists(md):
                    existing.append(d)
    existing.sort(reverse=True)

    if click_count == 1 and existing:
        # 首次点击且有今日穿搭 → 返回已生成的
        latest = existing[0]
        dp = os.path.join(user_outfits, latest)
        # 找效果图
        img_url = ''
        for sub in ['上身效果', '豆包生图', 'generated']:
            for root, _, files in os.walk(os.path.join(dp, sub) if os.path.exists(os.path.join(dp, sub)) else dp):
                for f in files:
                    if ('方案' in f or '直角' in f) and f.endswith('.jpg'):
                        rel = os.path.relpath(os.path.join(root, f), PROJECT_DIR)
                        img_url = get_cdn_url(rel)
                        break
                if img_url:
                    break
            if img_url:
                break

        handler._json_resp(200, {
            "result": f'🎯 今日穿搭 #{click_count}<br><br>已为你准备好今日推荐：<b>{latest.split("_",1)[-1] if "_" in latest else latest}</b><br><br>不满意？再点一次「今日穿搭」换一套',
            "action": "today",
            "image_url": img_url,
        })
    else:
        # 首次但无今日 outfit，或第 N 次点击 → 生成新的
        extra = f'今日穿搭 第{click_count}版 请与之前不同'
        _uid = uid if uid != 'default' else None
        tid = _start_async_pipeline('recommend', extra, _uid)
        handler._json_resp(200, {"task_id": tid, "result": f'🔍 正在为你生成第 {click_count} 套今日穿搭…'})


def _handle_favorites(handler):
    """返回近10次三星好评穿搭"""
    favs = []
    uid = getattr(handler, 'user_id', 'default')
    outfits_dir = resolve_outfits_dir(None if uid == 'default' else uid)
    for d in sorted(os.listdir(outfits_dir), reverse=True):
        dp = os.path.join(outfits_dir, d)
        rp = os.path.join(dp, 'rating.json')
        if not os.path.exists(rp):
            continue
        try:
            with open(rp) as f:
                rating = json.load(f)
            if rating.get('rating') != 3:
                continue
        except:
            continue
        md = os.path.join(dp, 'outfit.md')
        style = d.split('_', 1)[-1] if '_' in d else d
        date_str = d[:10]
        items_str = ''
        if os.path.exists(md):
            with open(md) as f:
                content = f.read()
            ids = re.findall(r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)', content)
            items_str = '、'.join(list(dict.fromkeys(ids))[:5])
        favs.append({'dir': d, 'style': style, 'date': date_str, 'items': items_str})

    if not favs:
        handler._json_resp(200, {"result": '⭐ 暂无三星好评记录。<br><br>给满意的穿搭点 ⭐⭐⭐ 后会出现在这里', "action": "favorites"})
        return

    lines = ['⭐ 你最爱的穿搭 TOP ' + str(min(len(favs), 10))]
    for i, f in enumerate(favs[:10], 1):
        lines.append(f'{i}. <b>{f["style"]}</b> · {f["date"]}')
        if f['items']:
            lines.append(f'   <span style="font-size:12px;color:#9b8c7c">{f["items"]}</span>')

    handler._json_resp(200, {"result": '<br>'.join(lines), "action": "favorites"})


def get_cdn_url(rel_path):
    """构建 jsDelivr CDN URL"""
    h = get_git_commit()
    if h:
        import urllib.parse
        return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/{urllib.parse.quote(rel_path, safe="/")}'
    return ''


# ── HTTP 处理器 ───────────────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)

        # ── 多用户路由 v2 ──
        gender, user_id, need_onboarding = _resolve_user_from_request(self)
        self.user_id = user_id
        self.user_gender = gender
        self.user_dir = resolve_user_dir(gender, None if user_id == 'default' else user_id)
        # 设置线程本地用户上下文
        from tools.common import set_thread_user
        set_thread_user(gender, None if user_id == 'default' else user_id)

        # 性别门：无 gender 且非 API 请求 → 显示性别选择页
        if gender is None and not parsed.path.startswith('/api/') and not parsed.path.startswith('/static/'):
            self._html_resp(200, _load_gender_gate_html())
            return

        # 需要 onboarding（新用户或注册但未完成 onboarding）→ 展示向导
        need_onboarding_page = need_onboarding
        onboarding_step = 0
        onboarding_gender = gender or ''
        if not need_onboarding and user_id != 'default':
            # 已注册但可能未完成 onboarding
            try:
                up = os.path.join(self.user_dir, 'profile.json')
                if os.path.exists(up):
                    with open(up) as f:
                        up_data = json.load(f)
                    if not up_data.get('onboarding_complete', False):
                        need_onboarding_page = True
                        onboarding_step = up_data.get('onboarding_step', 0) or 0
                        onboarding_gender = up_data.get('gender', '')
            except:
                pass

        if need_onboarding_page and parsed.path in ('/', ''):
            self._html_resp(200, _load_onboarding_html(user_id, onboarding_step, onboarding_gender))
            return

        # 聊天面板（多用户传递 user_id 以加载对应用户的原型）
        if parsed.path in ('/', ''):
            uid = self.user_id if self.user_id != 'default' else None
            # 🛡️ 缓存破坏：无 v= 参数时 301 重定向到带版本号的 URL
            qs = parse_qs(parsed.query)
            if 'v' not in qs and not parsed.query.startswith('v='):
                proto_path = os.path.join(resolve_user_dir(uid), 'cache', 'prototype.html') if uid else os.path.join(PROJECT_DIR, 'prototype', 'mobile-v2.html')
                proto_ver = str(int(os.path.getmtime(proto_path))) if os.path.exists(proto_path) else '0'
                sep = '&' if parsed.query else ''
                new_query = f'{parsed.query}{sep}v={proto_ver}'
                self.send_response(301)
                self.send_header('Location', f'/?{new_query}')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            extra_headers = {'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'}
            if self.user_id != 'default':
                extra_headers['Set-Cookie'] = f'fashion_user={self.user_id}; Path=/; Max-Age=86400; SameSite=Lax'
            else:
                # 默认用户：清除可能残留的 fashion_user Cookie，防止 API 调用被路由到其他用户
                extra_headers['Set-Cookie'] = 'fashion_user=; Path=/; Max-Age=0'
            self._html_resp(200, _load_chat_html(user_id=uid, gender=gender), extra_headers)
            return

        # ── 管理员面板 ──
        if parsed.path == '/admin':
            self._html_resp(200, _build_admin_html())
            return

        # 兼容旧版 URL 触发
        if parsed.path == '/cmd':
            qs = parse_qs(parsed.query)
            msg = qs.get('t', [''])[0] or qs.get('text', [''])[0]
            if msg:
                action, extra = match_command(msg)
                if action in ('generate', 'recommend', 'today'):
                    _uid = getattr(self, 'user_id', None)
                    _uid = _uid if _uid and _uid != 'default' else None
                    tid = _start_async_pipeline('recommend', extra or '今日穿搭', _uid)
                    self._html_resp(200, REDIRECT_HTML)
                else:
                    result = execute_action(action, extra)
                    self._html_resp(200, f"<html><body style='font-family:sans-serif;padding:20px;background:#f5f0eb'><pre style='white-space:pre-wrap;font-size:15px'>{result}</pre><p><a href='/'>← 返回面板</a></p></body></html>")
            else:
                self._json_resp(400, {"error": "缺少 t 参数"})
            return

        # 🔥 现在就试：风格立即生成
        if parsed.path.startswith('/try/'):
            style_id = parsed.path.split('/try/')[-1].strip()
            if not style_id:
                self._html_resp(400, '<p>缺少风格 ID</p>'); return
            # 读取百科简介
            encyc_path = os.path.join(PROJECT_DIR, 'styles_universal', style_id, 'encyclopedia.md')
            style_desc = ''
            if os.path.exists(encyc_path):
                with open(encyc_path, 'r') as f:
                    for line in f:
                        if '一句话定义' in line:
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: style_desc = m.group(1).strip()[:60]; break
            # 风格名映射（尝试 male/female 路径）
            style_name = style_id
            for sp in [f'styles/male/{style_id}.json', f'styles/female/{style_id}/fingerprint.json']:
                try:
                    with open(os.path.join(PROJECT_DIR, sp)) as f:
                        sj = json.load(f)
                        style_name = sj.get('name_zh', style_id)
                        break
                except:
                    pass
            TRY_HTML = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>现在就试 · {style_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#f5f0eb;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px}}
.card{{background:#fff;border-radius:16px;padding:32px 24px;max-width:360px;width:100%;text-align:center;box-shadow:0 2px 20px rgba(0,0,0,.06)}}
h2{{font-size:22px;color:#3a3028;margin-bottom:8px}}
.desc{{font-size:14px;color:#999;margin-bottom:24px;line-height:1.5}}
.btn{{display:block;width:100%;padding:16px;border:none;border-radius:12px;font-size:18px;font-weight:600;cursor:pointer;margin-bottom:12px;-webkit-tap-highlight-color:transparent}}
.btn-primary{{background:linear-gradient(135deg,#3a3028,#5c4d3c);color:#fff}}
.btn-primary:active{{opacity:.8}}
.btn-info{{background:#e8f0fe;color:#1a73e8}}
.btn-info:active{{opacity:.8}}
.btn-secondary{{background:#f5f0eb;color:#5c4d3c}}
.status{{font-size:13px;color:#999;margin-top:12px;display:none}}
.spinner{{display:inline-block;width:14px;height:14px;border:2px solid #d0c8bc;border-top-color:#3a3028;border-radius:50%;animation:spin .8s linear infinite;margin-right:6px;vertical-align:-2px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
</style>
</head>
<body>
<div class="card">
<h2>🧪 {style_name}</h2>
<div class="desc">{style_desc or '点击下方按钮，AI 将为你生成一套' + style_name + '风格穿搭并推送到微信'}</div>
<button class="btn btn-primary" onclick="tryNow()">🔥 现在就试</button>
<button class="btn btn-info" onclick="location.href='/style/{style_id}'">📖 了解更多</button>
<button class="btn btn-secondary" onclick="history.back()">← 返回</button>
<div class="status" id="status"><span class="spinner"></span>正在生成穿搭...</div>
</div>
<script>
async function tryNow(){{
document.querySelector('.btn-primary').disabled=true;
document.getElementById('status').style.display='block';
try{{
let r=await fetch('/api/try/'+encodeURIComponent('{style_id}'));
let d=await r.json();
if(d.ok){{document.getElementById('status').innerHTML='✅ 已开始生成！稍后查看微信推送';}}
else{{document.getElementById('status').innerHTML='❌ '+d.error;}}
}}catch(e){{document.getElementById('status').innerHTML='❌ 网络错误';}}
}}
</script>
</body>
</html>'''
            self._html_resp(200, TRY_HTML)
            return

        # 📖 风格百科页（直接用已有的精美 HTML）
        if parsed.path.startswith('/style/'):
            style_id = parsed.path.split('/style/')[-1].strip()
            html_path = os.path.join(PROJECT_DIR, 'styles_universal', style_id, 'encyclopedia.html')
            if os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html = f.read()
                back_btn = '<button onclick="location.href=\'/\'" style="position:fixed;top:16px;right:16px;background:#3a3028;color:#fff;border:none;padding:10px 18px;border-radius:20px;font-size:14px;cursor:pointer;z-index:999;box-shadow:0 2px 8px rgba(0,0,0,.3)">← 返回</button>'
                html = html.replace('</body>', back_btn + '</body>')
                self._html_resp(200, html)
                return
            # ── 女性风格：从 styles/female/ 目录查找并渲染 encyclopedia.md ──
            if style_id.startswith('WF-'):
                women_dir = os.path.join(PROJECT_DIR, 'styles/female')
                # 查找匹配的目录
                for d in sorted(os.listdir(women_dir)):
                    if d.startswith(style_id + '_') and os.path.isdir(os.path.join(women_dir, d)):
                        md_path = os.path.join(women_dir, d, 'encyclopedia.md')
                        if os.path.exists(md_path):
                            html = _render_encyclopedia_html(md_path, style_id, d)
                            back_btn = '<button onclick="history.back()" style="position:fixed;top:16px;right:16px;background:#3a3028;color:#fff;border:none;padding:10px 18px;border-radius:20px;font-size:14px;cursor:pointer;z-index:999;box-shadow:0 2px 8px rgba(0,0,0,.3)">← 返回</button>'
                            html = html.replace('</body>', back_btn + '</body>')
                            self._html_resp(200, html)
                            return
                self._html_resp(404, '<p>百科不存在</p>')
                return
            self._html_resp(404, '<p>百科不存在</p>')
            return

        if parsed.path.startswith('/api/try/'):
            style_id = parsed.path.split('/api/try/')[-1].strip()
            if not style_id:
                self._json_resp(400, {"error": "缺少风格 ID"}); return
            try:
                _uid = getattr(self, 'user_id', None)
                _uid = _uid if _uid and _uid != 'default' else None
                tid = _start_async_pipeline('generate', style_id, _uid)
                log(f"🔥 远程试穿: {style_id} → task {tid}")
                self._json_resp(200, {"ok": True, "task_id": tid, "message": f"开始生成 {style_id} 穿搭"})
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
            return

        # 穿搭评分页面
        if parsed.path == '/rate' and self.command != 'POST':
            template_path = os.path.join(PROJECT_DIR, 'templates', 'rating.html')
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    self._html_resp(200, f.read())
            else:
                self._json_resp(404, {"error": "template not found"})
            return

        # 评分 API
        if parsed.path.startswith('/api/outfit/'):
            from urllib.parse import unquote
            import json as _json
            parts = [p for p in parsed.path.split('/') if p]
            oid = unquote(parts[-1]) if len(parts) > 2 else 'unknown'
            if not oid: oid = urlParams.get('id',['unknown'])[0] if 'id' in urlParams else 'unknown'
            # 多用户：从用户目录查找 outfit
            _uid = getattr(self, 'user_id', 'default')
            _outfits_base = resolve_outfits_dir(None if _uid == 'default' else _uid)
            outfit_dir = os.path.join(_outfits_base, oid) if oid != 'unknown' else None
            if outfit_dir and os.path.exists(outfit_dir):
                md = os.path.join(outfit_dir, 'outfit.md')
                if os.path.exists(md):
                    with open(md,'r') as f: txt = f.read()
                    items = []
                    for line in txt.split('\n'):
                        m = re.match(r'^\|\s*[^|]*\|\s*\*?\*?(\w+-\d+)\*?\*?\s*\|\s*(.+?)\s*\|', line)
                        if m: items.append({'id': m.group(1), 'name': m.group(2).strip()})
                    style_m = re.search(r'\*\*风格\*\*[：:]\s*(.+)|风格[：:]\s*(.+)', txt)
                    date_m = re.search(r'(\d{4}-\d{2}-\d{2})', oid)
                    self._json_resp(200, {'outfit': oid.split('_',1)[-1] if '_' in oid else oid, 'style': (style_m.group(1) or style_m.group(2)).strip() if style_m else '', 'date': date_m.group(1) if date_m else '', 'items': items})
                else:
                    self._json_resp(200, {'outfit': oid, 'style': '', 'date': '', 'items': []})
            else:
                self._json_resp(200, {'outfit': oid, 'style': '', 'date': '', 'items': []})
            return

        # 任务轮询
        if parsed.path.startswith('/api/task/'):
            tid = parsed.path.split('/')[-1]
            task = tasks.get(tid)  # 内置磁盘回退（outfits/_tasks/）
            if task is None:
                # 🔧 磁盘回退：分析任务 — 优先查用户目录，再 fallback 主项目
                _uid = self.user_id if self.user_id != 'default' else None
                found = False
                for _candidate_dir in [
                    os.path.join(resolve_user_dir(_uid), 'wardrobe', '_incoming') if _uid else None,
                    os.path.join(PROJECT_DIR, 'wardrobe', '_incoming'),
                ]:
                    if not _candidate_dir:
                        continue
                    analysis_path = os.path.join(_candidate_dir, f'analysis_{tid}.json')
                    if os.path.exists(analysis_path):
                        try:
                            with open(analysis_path, 'r') as f:
                                analysis = json.load(f)
                            self._json_resp(200, {
                                'id': tid,
                                'status': 'done',
                                'message': f'识别完成，共 {len(analysis.get("items", []))} 件单品',
                                'result': json.dumps(analysis, ensure_ascii=False),
                                'image_path': '',
                                'image_url': '',
                                'log': '',
                            })
                            found = True
                            break
                        except Exception:
                            pass
                if not found:
                    self._json_resp(404, {"error": "task not found"})
                return
            tasks.cleanup()
            # 返回安全字段
            safe = {k: task[k] for k in ('id', 'status', 'message', 'result', 'image_path', 'image_url', 'log')}
            self._json_resp(200, safe)
            return

        # 本地图片服务（内存 LRU 缓存 + 浏览器强缓存 + 按需缩图）
        if parsed.path == '/api/image':
            qs = parse_qs(parsed.query)
            file_rel = qs.get('f', [''])[0]
            if not file_rel:
                self._json_resp(400, {"error": "missing f"})
                return
            # 防御：URL 中可能有 ?t= 缓存破坏参数被错误拼接到 f 参数尾部
            if '?' in file_rel:
                file_rel = file_rel.split('?')[0]
            file_abs = os.path.normpath(os.path.join(PROJECT_DIR, file_rel))
            if not file_abs.startswith(PROJECT_DIR):
                self._json_resp(403, {"error": "forbidden"})
                return
            if not os.path.isfile(file_abs):
                self._json_resp(404, {"error": "file not found"})
                return
            # 按需缩图宽度（默认900px，手机3x retina够用，体积减90%+；传 ?w=0 可取原图）
            req_w = int(qs.get('w', ['900'])[0]) if qs.get('w', [''])[0].isdigit() else 900

            # 🆕 预压缩版优先：请求原图但有 _900w.jpg 则直接返回压缩版
            if req_w > 0 and '_900w' not in file_rel and '_600w' not in file_rel and '_300w' not in file_rel:
                base, _ext = os.path.splitext(file_abs)
                sibling = f'{base}_{req_w}w.jpg'
                if os.path.isfile(sibling):
                    file_abs = sibling
                    ct = 'image/jpeg'
                    # 更新 ETag 源文件（压缩版修改时间可能不同）
                    try:
                        fstat_s = os.stat(sibling)
                        etag_pre = f'"{fstat_s.st_mtime}-{fstat_s.st_size}-w{req_w}"'
                    except OSError:
                        etag_pre = None
                    if etag_pre and self.headers.get('If-None-Match') == etag_pre:
                        self._send_body(304, b'', ct, {
                            'Cache-Control': 'public, no-cache, max-age=0',
                            'ETag': etag_pre
                        })
                        return
                    # 从压缩版读取（已是目标尺寸，跳过 resize）
                    data_pre = image_cache_get(file_abs, 0)
                    if data_pre is None:
                        with open(file_abs, 'rb') as f:
                            data_pre = f.read()
                        image_cache_put(file_abs, 0, data_pre)
                    headers_pre = {'Cache-Control': 'public, max-age=60, must-revalidate'}
                    if etag_pre:
                        headers_pre['ETag'] = etag_pre
                    self._send_body(200, data_pre, ct, headers_pre)
                    return

            ct = mimetypes.guess_type(file_abs)[0] or 'application/octet-stream'
            # ETag: mtime + size + width，文件修改后自动变化，浏览器 revalidate
            try:
                fstat = os.stat(file_abs)
                etag = f'"{fstat.st_mtime}-{fstat.st_size}-w{req_w}"'
            except OSError:
                etag = None
            # 检查浏览器缓存是否有效（If-None-Match）
            if etag and self.headers.get('If-None-Match') == etag:
                self._send_body(304, b'', ct, {
                    'Cache-Control': 'public, no-cache, max-age=0',
                    'ETag': etag
                })
                return
            data = image_cache_get(file_abs, req_w)
            if data is None:
                with open(file_abs, 'rb') as f:
                    data = f.read()
                if req_w > 0 and ct.startswith('image/'):
                    data = resize_image_bytes(data, req_w, ct)
                image_cache_put(file_abs, req_w, data)
            headers = {'Cache-Control': 'public, max-age=60, must-revalidate'}
            if etag:
                headers['ETag'] = etag
            self._send_body(200, data, ct, headers)
            return

        # 日志查看（纯文本，可 curl）
        if parsed.path == '/log':
            qs = parse_qs(parsed.query)
            n = int(qs.get('n', ['200'])[0])
            try:
                with open(LOG_FILE, 'r') as f:
                    all_lines = f.readlines()
                self._text_resp(200, ''.join(all_lines[-n:]) if all_lines else '(日志为空)')
            except FileNotFoundError:
                self._text_resp(200, '(日志文件尚未创建)')
            return

        # 日志查看（实时刷新 HTML）
        if parsed.path == '/log/live':
            self._html_resp(200, LOG_LIVE_HTML)
            return

        # 用户列表 API（供性别门页面使用）
        if parsed.path == '/api/users/list':
            from tools.user_manager import list_users_by_gender
            self._json_resp(200, {'users': list_users_by_gender()})
            return

        # 历史记录 API
        if parsed.path == '/api/history':
            qs = parse_qs(parsed.query)
            n = int(qs.get('n', ['50'])[0])
            history = load_history()
            self._json_resp(200, history[:n])
            return

        # 电脑端历史查看页面
        if parsed.path == '/history':
            self._html_resp(200, HISTORY_HTML)
            return

        # 衣橱分析 API
        if parsed.path == '/api/wardrobe':
            # ── 多用户快速路径：直接从用户 tags 目录统计 ──
            if self.user_id != 'default':
                try:
                    tags_dir = os.path.join(self.user_dir, 'wardrobe', 'tags')
                    items = {}
                    if os.path.isdir(tags_dir):
                        for fn in os.listdir(tags_dir):
                            if fn.endswith('.json') and not fn.startswith('SCORE_CACHE'):
                                try:
                                    with open(os.path.join(tags_dir, fn)) as f:
                                        it = json.load(f)
                                    cid = it.get('clothing_id', '')
                                    if cid:
                                        items[cid] = it
                                except:
                                    pass
                    total = len(items)
                    cats = {}
                    for cid, it in items.items():
                        cc = it.get('category_code', '?')
                        cn = it.get('category', cc)
                        if cc not in cats:
                            cats[cc] = {'name': cn, 'count': 0, 'recommended': 0}
                        cats[cc]['count'] += 1
                    category_gaps = {}
                    CAT_RECOMMENDED = {'TS': (5, 12), 'SHIRT': (3, 8), 'LS': (2, 6), 'TANK': (1, 4),
                                       'JK': (2, 6), 'PT': (3, 8), 'SH': (2, 5), 'SHOE': (3, 8),
                                       'BAG': (1, 4), 'HAT': (1, 4), 'SOCK': (3, 8), 'SUN': (1, 3), 'ACC': (1, 5)}
                    for cc, cn_name in CATEGORY_CODE_TO_NAME.items():
                        cinfo = cats.get(cc, {'name': cn_name, 'count': 0})
                        lo, hi = CAT_RECOMMENDED.get(cc, (0, 99))
                        status = 'ok'
                        if cinfo['count'] < lo:
                            status = 'understock'
                        elif cinfo['count'] > hi:
                            status = 'overstock'
                        category_gaps[cc] = {'name': cn_name, 'count': cinfo['count'],
                                             'recommended_min': lo, 'recommended_max': hi, 'status': status}
                    self._json_resp(200, {
                        'metadata': {'total_items': total},
                        'utilization': {'utilization_rate': 0.5},
                        'category_gaps': category_gaps,
                    })
                    return
                except Exception as e:
                    log(f"多用户衣橱API异常: {e}", "ERROR")
                    self._json_resp(500, {"error": str(e)})
                    return

            # ── 单人模式完整分析 ──
            try:
                from wardrobe_advisor import (load_all_clothing, load_state, analyze_category_gaps,
                    analyze_subcategory_gaps, analyze_color_balance, analyze_brand_diversity,
                    analyze_utilization, generate_purchase_suggestions, build_structured_data,
                    mine_cp_combinations, save_monthly_snapshot, compute_monthly_delta)
                wardrobe = load_all_clothing()
                state = load_state()
                gaps = analyze_category_gaps(wardrobe)
                sub_gaps = analyze_subcategory_gaps(wardrobe)
                color_analysis = analyze_color_balance(wardrobe)
                brand_analysis = analyze_brand_diversity(wardrobe)
                utilization = analyze_utilization(wardrobe, state)
                purchase_suggestions = generate_purchase_suggestions(gaps, sub_gaps, color_analysis, brand_analysis)
                cp_data = mine_cp_combinations()
                prev_snap = save_monthly_snapshot(wardrobe)
                monthly_delta = compute_monthly_delta(wardrobe, prev_snap)
                data = build_structured_data(gaps, sub_gaps, color_analysis, brand_analysis,
                                             utilization, purchase_suggestions, cp_data, monthly_delta, wardrobe)
                data['utilization']['zero_wear'] = utilization['zero_wear'][:20]
                data['utilization']['key_unused'] = utilization['key_unused']
                self._json_resp(200, data)
                return
            except Exception as e:
                log(f"衣橱API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # ─── 衣橱子 API ───

        # 单品详情（完整标签）
        if parsed.path.startswith('/api/wardrobe/item/'):
            cid = parsed.path.split('/api/wardrobe/item/')[-1].strip()
            if not cid:
                self._json_resp(400, {"error": "missing clothing_id"})
                return
            # 多用户：使用用户专属标签目录
            _uid = getattr(self, 'user_id', 'default')
            _tags_dir = resolve_tags_dir(None if _uid == 'default' else _uid)
            tag_path = os.path.join(_tags_dir, f'{cid}.json')
            if not os.path.exists(tag_path):
                self._json_resp(404, {"error": f"item {cid} not found"})
                return
            try:
                with open(tag_path, 'r', encoding='utf-8') as f:
                    tag_data = json.load(f)
                # Detail modal: prefer cutout for full-size display
                tag_data['_thumb'] = _find_item_cutout(cid) or _find_item_thumb(cid)
                self._json_resp(200, tag_data)
                return
            except Exception as e:
                log(f"单品详情API异常 {cid}: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 单品列表
        if parsed.path == '/api/wardrobe/items':
            try:
                from wardrobe_advisor import load_all_clothing
                wardrobe = load_all_clothing(include_archived=True)
                items = []
                for cid, item in sorted(wardrobe.items()):
                    meta = item.get('meta', {})
                    brand = item.get('brand', {})
                    color = item.get('color', {})
                    cat_code = item.get('category_code', '?')
                    items.append({
                        'id': cid,
                        'name': meta.get('claude_fit_comment', item.get('category', ''))[:40],
                        'category': CATEGORY_CODE_TO_NAME.get(cat_code, cat_code),
                        'category_code': cat_code,
                        'brand': brand.get('name', ''),
                        'color': color.get('hue_name', ''),
                        'color_family': color.get('hue_family', ''),
                        'usage_count': meta.get('wear_count', 0),
                        'last_used': meta.get('last_worn') or '',
                        'is_key': meta.get('is_key_piece', False),
                        'is_statement': meta.get('is_statement_piece', False),
                        'thumb': _find_item_thumb(cid),
                        '_archived': meta.get('archived', False),
                    })
                self._json_resp(200, {'items': items, 'total': len(items)})
                return
            except Exception as e:
                log(f"单品列表API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 月度统计
        if parsed.path == '/api/wardrobe/stats':
            try:
                from wardrobe_advisor import (load_all_clothing, load_state,
                    analyze_utilization, load_all_outfits, normalize_style)
                wardrobe = load_all_clothing()
                state = load_state()
                utilization = analyze_utilization(wardrobe, state)
                records = load_all_outfits()
                # Monthly stats
                now = time.localtime()
                this_month = f"{now.tm_year}-{now.tm_mon:02d}"
                monthly_records = [r for r in records if r['date'].startswith(this_month)]
                total_all = len(records)
                total_month = len(monthly_records)
                rated = [r for r in records if r['rating']]
                avg_rating = sum(r['rating'] for r in rated) / len(rated) if rated else 0
                # Style distribution
                from collections import Counter
                style_counter = Counter()
                for r in records:
                    style_counter[normalize_style(r['style'])] += 1
                top_styles = [{'name': s, 'count': n} for s, n in style_counter.most_common(5)]
                # Item frequency
                item_freq = Counter()
                for r in records:
                    for iid in r['items']:
                        item_freq[iid] += 1
                top_items = []
                for iid, n in item_freq.most_common(5):
                    name = ''
                    if iid in wardrobe:
                        name = wardrobe[iid].get('meta', {}).get('claude_fit_comment', '')[:25]
                    top_items.append({'id': iid, 'name': name, 'count': n})
                # Active days this month
                from collections import defaultdict
                by_date = defaultdict(list)
                for r in records:
                    by_date[r['date']].append(r)
                active_days = len(by_date)
                active_days_month = len(set(r['date'] for r in monthly_records))
                self._json_resp(200, {
                    'total_outfits': total_all,
                    'monthly_outfits': total_month,
                    'active_days': active_days,
                    'active_days_month': active_days_month,
                    'rated_count': len(rated),
                    'avg_rating': round(avg_rating, 1),
                    'top_styles': top_styles,
                    'top_items': top_items,
                    'utilization_rate': utilization['utilization_rate'],
                    'items_worn': utilization['items_worn_count'],
                    'items_total': len(wardrobe),
                })
                return
            except Exception as e:
                log(f"月度统计API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 🆕 Phase 3: 风格聚类 API
        if parsed.path == '/api/wardrobe/clusters':
            try:
                from wardrobe_cluster import load_tags_dir, compute_style_clusters, compute_wardrobe_health
                _wuid = self.user_id if self.user_id != 'default' else None
                _tags_dir = resolve_tags_dir(_wuid)
                wardrobe = load_tags_dir(_tags_dir)
                clusters = compute_style_clusters(wardrobe)
                health = compute_wardrobe_health(wardrobe)
                self._json_resp(200, {
                    'clusters': clusters,
                    'total_items': len(wardrobe),
                    'total_clusters': len(clusters),
                    'health': {
                        'orphans': health['orphan_count'],
                        'overlap_pairs': health['overlap_count'],
                        'category_count': health['total_categories'],
                    }
                })
                return
            except Exception as e:
                log(f"聚类API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 周报/月报 API
        if parsed.path == '/api/report':
            try:
                from rating_analyzer import (load_all_ratings, analyze, filter_ratings_by_days,
                                             find_neutral_patterns, STYLE_NAMES)
                TAGS_DIR = os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
                params = parse_qs(parsed.query or '')
                period = params.get('period', ['weekly'])[0]

                all_ratings = load_all_ratings()

                if period == 'weekly':
                    ratings = filter_ratings_by_days(all_ratings, 7)
                    if not ratings:
                        ratings = filter_ratings_by_days(all_ratings, 14)
                    prev_ratings = filter_ratings_by_days(all_ratings, 14)
                    prev_ratings = [r for r in prev_ratings if r not in ratings]
                else:
                    ratings = all_ratings
                    prev_ratings = []

                if not ratings:
                    self._json_resp(200, {'period': period, 'empty': True, 'message': '暂无评分数据'})
                    return

                analysis = analyze(ratings)
                prev_analysis = analyze(prev_ratings) if prev_ratings else None

                # 日期范围
                dates = sorted(set(r.get('outfit_id', '')[:10] for r in ratings))
                date_range = f"{dates[0][5:]} → {dates[-1][5:]}" if len(dates) > 1 else (dates[0][5:] if dates else '')

                # 趋势
                trend = 0
                trend_label = ''
                if prev_analysis and prev_analysis['total'] >= 1:
                    trend = round(analysis['avg_rating'] - prev_analysis['avg_rating'], 1)
                    if trend > 0.2:
                        trend_label = f'📈 较上周 ↑ {trend:+.1f}'
                    elif trend < -0.2:
                        trend_label = f'📉 较上周 ↓ {trend:+.1f}'
                    else:
                        trend_label = '📊 较上周持平'

                # 风格排行 + 穿搭图（优先从当前周期评分中找图）
                top_styles = []
                for sid, data in sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])[:3]:
                    image_url = _find_report_style_image_for_period(sid, ratings) or _find_report_style_image(sid)
                    top_styles.append({
                        'id': sid,
                        'name': STYLE_NAMES.get(sid, sid),
                        'count': data['total'],
                        'avg_rating': data['avg'],
                        'image_url': image_url,
                    })

                # 最爱单品 + 缩略图
                top_items = []
                for iid, cnt in list(analysis['items_liked'].items())[:5]:
                    name = iid
                    desc = ''
                    tag_path = os.path.join(TAGS_DIR, f'{iid}.json')
                    if os.path.exists(tag_path):
                        with open(tag_path) as f:
                            tag = json.load(f)
                        name = tag.get('brand', {}).get('name', '') or tag.get('category_display', iid)
                        hue = tag.get('color', {}).get('hue_name', '')
                        series = tag.get('brand', {}).get('series', '') or tag.get('style_culture', {}).get('aesthetic', '')
                        desc_parts = [p for p in [hue, series] if p]
                        desc = ' · '.join(desc_parts) if desc_parts else tag.get('claude_fit_comment', '')[:30]
                    if not name or name == iid:
                        name = iid
                    thumb_url = _find_report_item_thumbnail(iid)
                    top_items.append({
                        'id': iid,
                        'name': name,
                        'description': desc,
                        'count': cnt,
                        'thumbnail_url': thumb_url,
                    })

                result = {
                    'period': period,
                    'date_range': date_range,
                    'total_ratings': analysis['total'],
                    'satisfaction_rate': analysis['satisfaction_rate'],
                    'neutral_rate': analysis['neutral_rate'],
                    'disappoint_rate': analysis['disappoint_rate'],
                    'avg_rating': analysis['avg_rating'],
                    'trend': trend,
                    'trend_label': trend_label,
                    'top_styles': top_styles,
                    'top_items': top_items,
                }

                if period == 'monthly':
                    neutral = find_neutral_patterns(all_ratings)
                    result['neutral_analysis'] = neutral['summary'] if neutral else []
                    # AI 建议
                    suggestions = []
                    if analysis['satisfaction_rate'] >= 60:
                        suggestions.append('✅ 整体满意度良好，继续当前推荐策略')
                    elif analysis['satisfaction_rate'] >= 40:
                        suggestions.append('⚠️ 满意度中等，建议调整推荐权重')
                    else:
                        suggestions.append('❌ 满意度偏低，需要重新评估风格匹配')
                    sorted_styles = sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])
                    if len(sorted_styles) >= 2:
                        best = sorted_styles[0]
                        worst = sorted_styles[-1]
                        if best[0] != worst[0] and worst[1]['avg'] < 2:
                            suggestions.append(f"💡 建议增加 {STYLE_NAMES.get(best[0], best[0])} 推荐，减少 {STYLE_NAMES.get(worst[0], worst[0])}")
                    result['suggestions'] = suggestions

                self._json_resp(200, result)
                return
            except Exception as e:
                log(f"周报API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 冷门单品
        if parsed.path == '/api/wardrobe/cold-items':
            try:
                from wardrobe_advisor import load_all_clothing, load_state, analyze_utilization
                wardrobe = load_all_clothing()
                state = load_state()
                utilization = analyze_utilization(wardrobe, state)
                cold = []
                for item in utilization.get('zero_wear', []):
                    cid = item['id']
                    witem = wardrobe.get(cid, {})
                    cold.append({
                        'id': cid,
                        'name': item.get('name', '')[:40],
                        'brand': item.get('brand', ''),
                        'usage_count': item.get('wear_count', 0),
                        'last_used': witem.get('meta', {}).get('last_worn') or '从未',
                        'thumb': _find_item_thumb(cid),
                        'cutout': _find_item_cutout(cid),
                        'category_code': witem.get('category_code', '?'),
                        'is_key': witem.get('meta', {}).get('is_key_piece', False),
                    })
                self._json_resp(200, {'cold_items': cold, 'total': len(cold)})
                return
            except Exception as e:
                log(f"冷门单品API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # 购买建议/缺口
        if parsed.path == '/api/wardrobe/gaps':
            try:
                from wardrobe_advisor import (load_all_clothing, analyze_category_gaps,
                    analyze_subcategory_gaps, analyze_color_balance, analyze_brand_diversity,
                    generate_purchase_suggestions)
                wardrobe = load_all_clothing()
                gaps = analyze_category_gaps(wardrobe)
                sub_gaps = analyze_subcategory_gaps(wardrobe)
                color_analysis = analyze_color_balance(wardrobe)
                brand_analysis = analyze_brand_diversity(wardrobe)
                suggestions = generate_purchase_suggestions(gaps, sub_gaps, color_analysis, brand_analysis)
                # Also return category gaps for display
                cat_gaps = {}
                for code, g in gaps.items():
                    cat_gaps[code] = {
                        'name': CATEGORY_CODE_TO_NAME.get(code, code),
                        'actual': g['actual'],
                        'ideal_lo': g['ideal'][0],
                        'ideal_hi': g['ideal'][1],
                        'status': g['status'],
                        'diff': g['diff'],
                    }
                self._json_resp(200, {
                    'suggestions': suggestions,
                    'category_gaps': cat_gaps,
                    'color_missing': color_analysis.get('missing_hues', {}),
                })
                return
            except Exception as e:
                log(f"购买建议API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        # ─── 新单品徽标 ───
        if parsed.path == '/api/wardrobe/new-items':
            # 多用户路径
            if self.user_id != 'default':
                new_path = os.path.join(self.user_dir, 'config', 'new_items.json')
            else:
                new_path = os.path.join(PROJECT_DIR, 'config', 'new_items.json')
            if os.path.exists(new_path):
                try:
                    with open(new_path, 'r') as f:
                        new_data = json.load(f)
                    items = new_data.get('items', {})
                    self._json_resp(200, {
                        'new_items': [{'id': k, **v} for k, v in items.items()],
                        'total': len(items),
                    })
                except Exception as e:
                    self._json_resp(500, {"error": str(e)})
            else:
                self._json_resp(200, {'new_items': [], 'total': 0})
            return

        # ─── 探索页 API ───

        if parsed.path == '/api/explore/tweak':
            try:
                # 日常穿搭：动态舒适区（从用户评分数据推导）
                uid = self.user_id if self.user_id != 'default' else None
                tweak_styles = _get_dynamic_mode_styles('tweak', user_id=uid)
                if isinstance(tweak_styles, dict):
                    self._json_resp(200, tweak_styles)
                else:
                    self._json_resp(200, {'styles': tweak_styles})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/transform':
            try:
                # 改变自己：舒适区邻接 + 流行趋势
                uid = self.user_id if self.user_id != 'default' else None
                transform_styles = _get_dynamic_mode_styles('transform', user_id=uid)
                if isinstance(transform_styles, dict):
                    self._json_resp(200, transform_styles)
                else:
                    self._json_resp(200, {'styles': transform_styles})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/cross':
            try:
                # 大胆跨界：未探索 + 冲突风格 + 小众领域
                uid = self.user_id if self.user_id != 'default' else None
                cross_styles = _get_dynamic_mode_styles('cross', user_id=uid)
                if isinstance(cross_styles, dict):
                    self._json_resp(200, cross_styles)
                else:
                    self._json_resp(200, {'styles': cross_styles})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/trends':
            try:
                # 时尚圈子：全部风格（按 trend_category 分组）
                uid = self.user_id if self.user_id != 'default' else None
                styles = _load_style_cards(include_universal=True, with_top_items=True, user_id=uid)
                # ── 加载 trend_category 映射 ──
                tc_map = {}
                for cat_path in [
                    os.path.join(PROJECT_DIR, 'styles_universal', 'categories.json'),
                    os.path.join(PROJECT_DIR, 'styles/female', 'categories.json'),
                ]:
                    if os.path.exists(cat_path):
                        try:
                            with open(cat_path) as f:
                                cat_data = json.load(f)
                            for sid, sinfo in cat_data.get('style_registry', {}).items():
                                if 'trend_category' in sinfo:
                                    tc_map[sid] = sinfo['trend_category']
                        except: pass
                # ── 维度定义 ──
                tc_labels = {
                    'popular_trend': {'label': '🔥 流行趋势', 'color': '#E07B39'},
                    'classic': {'label': '🏛️ 经典风格', 'color': '#2C3E50'},
                    'niche': {'label': '🎭 小众领域', 'color': '#7B4FBF'},
                }
                # ── 分组 ──
                groups = {'popular_trend': [], 'classic': [], 'niche': [], 'uncategorized': []}
                for s in styles:
                    sid = s.get('id', '')
                    tc = tc_map.get(sid, 'uncategorized')
                    if tc not in groups:
                        tc = 'uncategorized'
                    s['trend_category'] = tc
                    s['trend_label'] = tc_labels.get(tc, {}).get('label', '')
                    s['trend_color'] = tc_labels.get(tc, {}).get('color', '')
                    groups[tc].append(s)
                # 空组不返回
                groups = {k: v for k, v in groups.items() if v}
                self._json_resp(200, {
                    'styles': styles,
                    'total': len(styles),
                    'groups': groups,
                    'tc_labels': tc_labels,
                })
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/try-on':
            try:
                params = parse_qs(parsed.query)
                style_id = params.get('style', [''])[0]
                if not style_id:
                    self._json_resp(400, {"error": "缺少风格 ID"})
                    return
                _uid = getattr(self, 'user_id', None)
                _uid = _uid if _uid and _uid != 'default' else None
                tid = _start_async_pipeline('generate', style_id, _uid)
                self._json_resp(200, {"ok": True, "task_id": tid, "message": f"开始生成 {style_id} 穿搭"})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        # ─── 我的页 API ───

        # 中英文值映射（前端 HTML 选项全部用中文，需将 API 返回值也转为中文）
        _GENDER_CN = {'female': '女', '女': '女', 'male': '男', '男': '男'}
        _SKIN_CN = {'tan': '小麦', 'fair': '偏白', 'warm': '偏黄', 'dark': '偏黑',
                    '白皙': '白皙', '偏白': '偏白', '自然': '自然', '小麦': '小麦', '偏黄': '偏黄', '偏黑': '偏黑'}
        _BODY_CN = {'hourglass': '沙漏型', 'pear': '梨型', 'apple': '苹果型', 'rectangle': '矩形',
                    'inverted_triangle': '倒三角', 'petite': '小个子',
                    '沙漏型': '沙漏型', '梨型': '梨型', '苹果型': '苹果型', '矩形': '矩形',
                    '倒三角': '倒三角', '小个子': '小个子',
                    '偏瘦': '偏瘦', '标准': '标准', '偏胖': '偏胖', '肌肉型': '肌肉型'}
        def _cn(val, map_dict):
            return map_dict.get(val, val)

        if parsed.path == '/api/profile':
            try:
                # ── 多用户：优先读取用户 profile.json ──
                if self.user_id != 'default':
                    up_path = os.path.join(self.user_dir, 'profile.json')
                    if os.path.exists(up_path):
                        with open(up_path) as f:
                            up = json.load(f)
                        body = up.get('body', {})
                        lifestyle = up.get('lifestyle', {})
                        # 🛡️ 照片相对路径：确保能通过静态文件服务访问
                        user_photos = up.get('photos', {})
                        profile = {
                            'use_my_image': up.get('use_my_image', False),
                            'gender': _cn(up.get('gender', '女'), _GENDER_CN),
                            'photos': user_photos,
                            'height': str(body.get('height', '')),
                            'weight': str(body.get('weight', '')),
                            'age': str(body.get('age', '')),
                            'body_type': _cn(body.get('shape', ''), _BODY_CN),
                            'skin_tone': _cn(body.get('skin_tone', ''), _SKIN_CN),
                            'shoulder_type': body.get('shoulder_type', ''),
                            'face_shape': body.get('face_shape', ''),
                            'occupation': lifestyle.get('occupation', ''),
                            'style_preference': up.get('style_prefs') and ', '.join(up['style_prefs']) or lifestyle.get('style_preference', ''),
                            'pain_points': body.get('concern', ''),
                            'body_secrets': up.get('body_secrets', ''),
                        }
                        self._json_resp(200, {'profile': profile})
                        return

                # ── 单人模式：优先读取 user_profile.json，fallback analysis.md ──
                up_path = os.path.join(PROJECT_DIR, 'config', 'user_profile.json')
                analysis_path = os.path.join(PROJECT_DIR, 'profile', 'analysis.md')

                if os.path.exists(up_path):
                    with open(up_path) as f:
                        up = json.load(f)
                else:
                    up = {}

                body = up.get('body', {})
                lifestyle = up.get('lifestyle', {})
                profile = {
                    'use_my_image': up.get('use_my_image', True),
                    'gender': up.get('gender', '男'),
                    'photos': up.get('photos', {}),
                    'height': str(body.get('height_cm', '')),
                    'weight': str(body.get('weight_kg', '')),
                    'age': str(body.get('age', '')),
                    'body_type': body.get('body_type', ''),
                    'skin_tone': body.get('skin_tone', ''),
                    'shoulder_type': body.get('shoulder_type', ''),
                    'face_shape': body.get('face_shape', ''),
                    'occupation': lifestyle.get('occupation', ''),
                    'style_preference': lifestyle.get('style_preference', ''),
                    'pain_points': lifestyle.get('pain_points', ''),
                    'body_secrets': up.get('body_secrets', ''),
                }

                # Fallback: 从 analysis.md 填充空字段
                if os.path.exists(analysis_path) and not up:
                    with open(analysis_path) as f:
                        content = f.read()
                    for line in content.split('\n'):
                        line = line.strip()
                        if '身高' in line and not profile['height']:
                            m = re.search(r'(\d{3})\s*cm', line)
                            if m: profile['height'] = m.group(1)
                        elif '体重' in line and not profile['weight']:
                            m = re.search(r'(\d+)\s*kg', line)
                            if m: profile['weight'] = m.group(1)
                        elif ('身形' in line or '体型' in line) and not profile['body_type']:
                            for bt in ['偏瘦','标准','偏胖','H型','倒三角','矩形','肌肉型']:
                                if bt in line: profile['body_type'] = bt; break
                        elif '肤色' in line and not profile['skin_tone']:
                            for st in ['白皙','偏白','自然','小麦','偏黄']:
                                if st in line: profile['skin_tone'] = st; break
                        elif '风格' in line and not profile['style_preference']:
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: profile['style_preference'] = m.group(1).strip()[:60]
                        elif '职业' in line and not profile['occupation']:
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: profile['occupation'] = m.group(1).strip()[:30]

                # Also load stats
                outfits_dir = os.path.join(PROJECT_DIR, 'outfits')
                total_outfits = 0
                rated_list = []
                if os.path.isdir(outfits_dir):
                    for d in os.listdir(outfits_dir):
                        dp = os.path.join(outfits_dir, d)
                        if not os.path.isdir(dp) or d.startswith('.') or d.startswith('_'):
                            continue
                        total_outfits += 1
                        rp = os.path.join(dp, 'rating.json')
                        if os.path.exists(rp):
                            try:
                                with open(rp) as f:
                                    r = json.load(f)
                                rt = r.get('rating', 0)
                                if rt:
                                    rated_list.append(rt)
                            except Exception:
                                pass
                avg_rating = round(sum(rated_list)/len(rated_list), 1) if rated_list else 0
                profile['total_outfits'] = total_outfits
                profile['rated_count'] = len(rated_list)
                profile['avg_rating'] = avg_rating
                self._json_resp(200, {'profile': profile})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        # 今日最新穿搭
        if parsed.path == '/api/today':
            today = time.strftime('%Y-%m-%d')
            latest = None
            _uid = getattr(self, 'user_id', 'default')
            _outfits_base = resolve_outfits_dir(None if _uid == 'default' else _uid)
            for d in sorted(os.listdir(_outfits_base), reverse=True) if os.path.isdir(_outfits_base) else []:
                if d.startswith(today):
                    dp = os.path.join(_outfits_base, d)
                    md = os.path.join(dp, 'outfit.md')
                    if not os.path.exists(md): continue
                    with open(md) as f: content = f.read()
                    items = []
                    for line in content.split('\n'):
                        s = line.strip()
                        if not s.startswith('|') or '---' in s: continue
                        cells = [c.strip().replace('**','') for c in s.split('|')]
                        if len(cells) >= 4 and re.match(r'^[A-Z]+-\d+', cells[2]):
                            # Simplify name like build_prototype
                            iid, iname = cells[2], cells[3]
                            # Basic name shortening
                            for rmv in ['Metal Vent Tech','Metal Vent','Court Lite','入门级','Artengo','Leisure Club','经典','复古','专业','入门','敞穿或卷袖','敞穿','卷袖','叠穿','基本款','常规','标准']:
                                iname = iname.replace(rmv, '').replace('  ', ' ')
                            if iid == 'ACC-003' or 'Apple Watch' in iname:
                                band = ''
                                for b in ['回环尼龙','尼龙回环','米兰尼斯','运动表带','黑色运动','回环']:
                                    if b in iname: band = b; break
                                iname = ('Apple Watch '+band) if band else 'Apple Watch'
                            elif len(iname) > 14: iname = iname[:14]
                            items.append({'id': iid, 'name': iname.strip()})
                    style = ''
                    for line in content.split('\n'):
                        if 'style:' in line.lower():
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: style = m.group(1).strip()[:40]; break
                    img = ''
                    for sub in ['上身效果','豆包生图']:
                        sd = os.path.join(dp, sub)
                        if not os.path.exists(sd): continue
                        for f in sorted(os.listdir(sd)):
                            if f == '上身效果_1.png' or ('人物' in f and f.endswith(('.jpg','.png'))):
                                img = 'outfits/{}/{}/{}'.format(d, sub, f); break
                        if img: break
                    # Extract weather + tags
                    w_str = ''; tags = []
                    for line in content.split('\n'):
                        if 'weather' in line.lower() or '天气' in line:
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: w_str = m.group(1).strip()[:40]; break
                    for line in content.split('\n'):
                        if '风格关键词' in line:
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m:
                                for kw in m.group(1).split(','):
                                    kw = kw.strip()
                                    if kw and len(kw)>=2: tags.append(kw[:8])
                            break
                    if not tags and style:
                        text = style + ' ' + (w_str or '')
                        cats = [
                            ['日系','韩系','美式','欧美','街头','复古','机能','简约','轻熟','运动','City Boy','Clean Fit','户外','军事','工装','网球','跑步','健身'],
                            ['低饱和','浅色','深色','亮色','撞色','单色','印花','条纹','纯色','大地色','黑白灰','蓝色系','清爽'],
                            ['通勤','约会','度假','日常','运动','户外','居家','出行','休闲','雨天','晴天','雨'],
                            ['叠穿','宽松','廓形','层次','修身','高腰','透气','防水']
                        ]
                        for cat in cats:
                            for kw in cat:
                                if kw in text and kw not in tags: tags.append(kw); break
                        all_kw = [kw for cat in cats for kw in cat]
                        for kw in all_kw:
                            if kw in text and kw not in tags and len(tags)<4: tags.append(kw)
                        if not tags: tags = [style[:6]]
                    latest = {'dir': d, 'style': style or d, 'items': items, 'img': img, 'date': d[:10], 'weather': w_str, 'tags': tags}
                    break
            self._json_resp(200, latest or {"empty": True})
            return

        # 健康检查（含今日推荐状态 + Funnel 状态 + 系统资源）
        if parsed.path == '/health':
            _uid = self.user_id if self.user_id != 'default' else None
            outfits_base = resolve_outfits_dir(_uid)
            health = collect_health_data(tasks, outfits_base)
            # 补充管线运行状态
            health['running'] = shared_state.pipeline_running
            self._json_resp(200, health)
            return

        # 女性风格列表（供 onboarding 使用）
        if parsed.path == '/api/onboarding/status':
            up = os.path.join(self.user_dir, 'profile.json')
            complete = False; step = 0
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
                complete = p.get('onboarding_complete', False)
                step = p.get('onboarding_step', 0)
            wardrobe_dir = os.path.join(self.user_dir, 'wardrobe')
            has_wardrobe = False
            if os.path.isdir(wardrobe_dir):
                imgs = [x for x in os.listdir(wardrobe_dir) if x.lower().endswith(('.jpg','.jpeg','.png','.webp'))]
                has_wardrobe = len(imgs) > 0
            self._json_resp(200, {'complete': complete, 'step': step, 'has_wardrobe': has_wardrobe})
            return

        if parsed.path == '/api/styles/women':
            cards = []
            women_dir = os.path.join(PROJECT_DIR, 'styles/female')
            if os.path.isdir(women_dir):
                for d in sorted(os.listdir(women_dir)):
                    fp = os.path.join(women_dir, d, 'fingerprint.json')
                    sd = {}
                    if os.path.exists(fp):
                        with open(fp) as f:
                            sd = json.load(f)
                    img = ''
                    img_dir = os.path.join(women_dir, d, 'images')
                    if os.path.isdir(img_dir):
                        imgs = [x for x in os.listdir(img_dir) if x.lower().endswith(('.jpg','.png','.jpeg','.webp'))]
                        if imgs:
                            img = f'/styles/female/{d}/images/{imgs[0]}'
                    cards.append({
                        'id': sd.get('style_id', d),
                        'name_zh': sd.get('name_zh', d),
                        'desc': (sd.get('description', '') or '')[:50],
                        'img': img,
                    })
            self._json_resp(200, {'styles': cards})
            return

        # 静态文件（图片等）
        from urllib.parse import unquote
        fp = os.path.normpath(os.path.join(PROJECT_DIR, unquote(parsed.path.lstrip('/'))))
        if os.path.isfile(fp) and fp.startswith(PROJECT_DIR):
            ext = os.path.splitext(fp)[1].lower().lstrip('.')
            mime = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif','svg':'image/svg+xml','webp':'image/webp'}.get(ext,'application/octet-stream')
            with open(fp,'rb') as f: data = f.read()
            self._send_body(200, data, mime, {'Cache-Control': 'public, max-age=3600'})
            return

        self._json_resp(404, {"error": "not found"})

    def do_POST(self):
        """API 端点"""
        # 请求体大小上限 50MB，防止 OOM
        _cl_str = self.headers.get('Content-Length', '0')
        try:
            _cl = int(_cl_str)
        except (ValueError, TypeError):
            _cl = 0
        if _cl > 50 * 1024 * 1024:
            self._json_resp(413, {'error': '请求体过大，最大 50MB'})
            return

        # 记录所有 POST 请求（用于故障排查）
        log(f'📨 POST {self.path} (Content-Length={_cl_str}, CT={self.headers.get("Content-Type","?")[:40]})')

        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)

        # ── 多用户路由 v2 ──
        gender, user_id, need_onboarding = _resolve_user_from_request(self)
        self.user_id = user_id
        self.user_gender = gender
        self.user_dir = resolve_user_dir(gender, None if user_id == 'default' else user_id)
        # 设置线程本地用户上下文
        from tools.common import set_thread_user
        set_thread_user(gender, None if user_id == 'default' else user_id)

        # Onboarding 启动
        if parsed.path == '/api/onboarding/start':
            qs = parse_qs(parsed.query)
            uid = qs.get('user', [None])[0]
            onboard_gender = qs.get('gender', [gender])[0] or 'male'
            if uid and not any(uid in users for users in _load_user_registry().values()):
                _create_user(onboard_gender, uid)
            self._json_resp(200, {'ok': True})
            return

        # Onboarding Step 0: 选择性别
        if parsed.path == '/api/onboarding/gender':
            body = self._read_post_body()
            data = json.loads(body)
            gender = data.get('gender', 'female')
            up = os.path.join(self.user_dir, 'profile.json')
            os.makedirs(self.user_dir, exist_ok=True)
            p = {}
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
            p['gender'] = gender
            p['onboarding_step'] = 1
            with open(up, 'w') as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
            log(f"🚻 Onboarding Step0: {user_id} → {gender}")

            # 返回性别对应的风格卡片（精选）和身形选项
            from tools.user_manager import GENDER_DEFAULTS
            gd = GENDER_DEFAULTS.get(gender, GENDER_DEFAULTS.get('female', {}))
            default_styles = gd.get('default_styles', [])

            # 加载 trend_category 映射
            tc_map = {}
            cat_path = os.path.join(PROJECT_DIR, 'styles/female' if gender == 'female' else 'styles_universal', 'categories.json')
            if os.path.exists(cat_path):
                try:
                    with open(cat_path) as f:
                        cat_data = json.load(f)
                    for sid, sinfo in cat_data.get('style_registry', {}).items():
                        if 'trend_category' in sinfo:
                            tc_map[sid] = sinfo['trend_category']
                except: pass

            cards = []
            styles_dir = os.path.join(PROJECT_DIR, 'styles_universal' if gender == 'male' else 'styles/female')
            if os.path.isdir(styles_dir):
                for d in sorted(os.listdir(styles_dir)):
                    if d.startswith('_') or d.startswith('.') or not os.path.isdir(os.path.join(styles_dir, d)):
                        continue
                    fp = os.path.join(styles_dir, d, 'fingerprint.json')
                    sd = {}
                    if os.path.exists(fp):
                        with open(fp) as f:
                            sd = json.load(f)
                    sid = sd.get('style_id', d)
                    # 过滤非风格目录：无 encyclopedia.md 的不展示
                    enc_check = os.path.join(styles_dir, d, 'encyclopedia.md')
                    if d in ('references', 'templates', 'images_meta.json', 'gallery.html') or not os.path.exists(enc_check):
                        continue
                    name_zh, desc = _extract_style_info(styles_dir, d, sd)
                    # 封面图：优先 representative.jpg
                    img = ''
                    rep_path = os.path.join(styles_dir, d, 'representative_thumb.jpg')
                    if not os.path.exists(rep_path):
                        rep_path = os.path.join(styles_dir, d, 'representative.jpg')
                    if os.path.exists(rep_path):
                        img = f'/{os.path.relpath(styles_dir, PROJECT_DIR)}/{d}/{os.path.basename(rep_path)}'
                    if not img:
                        img_dir = os.path.join(styles_dir, d, 'images')
                        if os.path.isdir(img_dir):
                            imgs = [x for x in os.listdir(img_dir) if x.lower().endswith(('.jpg','.png','.jpeg','.webp'))]
                            if imgs:
                                img = f'/{os.path.relpath(styles_dir, PROJECT_DIR)}/{d}/images/{imgs[0]}'
                    cards.append({
                        'id': sid,
                        'name_zh': name_zh,
                        'desc': desc,
                        'img': img,
                        'tc': tc_map.get(sid, ''),
                    })

            # ── 精选：流行趋势优先，经典适量，小众点缀 ──
            popular = [c for c in cards if c['tc'] == 'popular_trend']
            classic = [c for c in cards if c['tc'] == 'classic']
            niche = [c for c in cards if c['tc'] == 'niche']
            other = [c for c in cards if c['tc'] not in ('popular_trend', 'classic', 'niche')]
            curated = popular[:15] + classic[:5] + niche[:2] + other
            body_shapes = gd.get('body_shapes', [])
            self._json_resp(200, {'ok': True, 'next_step': 1, 'style_cards': curated, 'body_shapes': body_shapes})
            return

        # Onboarding Step 1: 保存身形
        if parsed.path == '/api/onboarding/step1':
            body = self._read_post_body()
            data = json.loads(body)
            is_skip = data.get('skip', False)
            up = os.path.join(self.user_dir, 'profile.json')
            p = {}
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
            p['body'] = {
                'height': data.get('height', ''),
                'weight': data.get('weight', ''),
                'shape': data.get('shape', ''),
                'skin_tone': data.get('skin_tone', ''),
                'concern': data.get('concern', ''),
                'skipped': is_skip,
            }
            p['onboarding_step'] = 2
            with open(up, 'w') as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
            log(f"👤 Onboarding Step1: {user_id} — {data.get('shape','?')} {'(跳过)' if is_skip else ''}")
            self._json_resp(200, {'ok': True, 'next_step': 2})
            return

        # Onboarding Step 2: 保存风格偏好
        if parsed.path == '/api/onboarding/step2':
            body = self._read_post_body()
            data = json.loads(body)
            style_ids = data.get('style_ids', [])
            is_skip = data.get('skip', False)
            up = os.path.join(self.user_dir, 'profile.json')
            p = {}
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
            p['style_prefs'] = style_ids
            p['onboarding_step'] = 3
            with open(up, 'w') as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
            log(f"🎨 Onboarding Step2: {user_id} — {len(style_ids)} 风格 {'(跳过)' if is_skip else ''}")
            self._json_resp(200, {'ok': True, 'next_step': 3})
            return

        # Onboarding: 上传衣橱单品
        if parsed.path == '/api/onboarding/wardrobe/add':
            ctype = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in ctype:
                self._json_resp(400, {'error': 'ERR_PARSE', 'message': '需要 multipart/form-data'})
                return
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            # 使用标准库 BytesParser 解析 multipart
            from email.parser import BytesParser
            from email.policy import HTTP
            import uuid as _uuid
            saved_files = []
            try:
                msg = BytesParser(policy=HTTP).parsebytes(
                    b'Content-Type: ' + ctype.encode() + b'\r\n\r\n' + body
                )
                for part in msg.iter_parts():
                    payload = part.get_payload(decode=True)
                    if not payload or len(payload) < 100:
                        continue
                    # 获取文件名
                    disp = part.get_content_disposition() or ''
                    filename = part.get_filename() or f'upload_{_uuid.uuid4().hex[:8]}.jpg'
                    ext = os.path.splitext(filename)[1].lower() or '.jpg'
                    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'):
                        ext = '.jpg'
                    save_name = f"upload_{_uuid.uuid4().hex[:8]}{ext}"
                    wardrobe_dir = os.path.join(self.user_dir, 'wardrobe')
                    os.makedirs(wardrobe_dir, exist_ok=True)
                    save_path = os.path.join(wardrobe_dir, save_name)
                    with open(save_path, 'wb') as f:
                        f.write(payload)
                    saved_files.append(save_name)
                    log(f"📤 Onboarding 上传: {user_id} — {save_name} ({len(payload)} bytes)")
            except Exception as e:
                log(f'⚠️ Onboarding multipart 解析失败: {e}')
                self._json_resp(400, {'error': 'ERR_PARSE', 'message': '图片解析失败，请重试'})
                return

            # 后台快速标签分析
            if saved_files:
                def _bg_quick_tag():
                    for fname in saved_files:
                        try:
                            img_path = os.path.join(wardrobe_dir, fname)
                            log(f"🏷️ quick_tag 启动: {user_id}/{fname}")
                            result = subprocess.run(
                                [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'quick_tag.py'),
                                 img_path, '--user', user_id],
                                capture_output=True, text=True, timeout=60,
                                cwd=PROJECT_DIR
                            )
                            if result.returncode == 0:
                                # 记录 source_file 关联，防止 analyze 阶段重复打标签
                                last_line = result.stdout.strip().split('\n')[-1] if result.stdout else ''
                                try:
                                    tag_info = json.loads(last_line)
                                    cid = tag_info.get('id')
                                    if cid:
                                        tag_path = os.path.join(wardrobe_dir, 'tags', f'{cid}.json')
                                        if os.path.exists(tag_path):
                                            with open(tag_path) as f:
                                                td = json.load(f)
                                            td['meta']['source_file'] = fname
                                            with open(tag_path, 'w') as f:
                                                json.dump(td, f, ensure_ascii=False, indent=2)
                                except:
                                    pass
                                log(f"✅ quick_tag 完成: {user_id}/{fname}")
                            else:
                                log(f"⚠️ quick_tag 失败: {user_id}/{fname} — {result.stderr[:200] if result.stderr else 'unknown'}")
                        except Exception as e:
                            log(f"❌ quick_tag 异常: {user_id}/{fname} — {e}")
                threading.Thread(target=_bg_quick_tag, daemon=True).start()

            self._json_resp(200, {'ok': True, 'files': saved_files, 'count': len(saved_files)})
            return

        # Onboarding 分析（上传完成后触发，运行 quick_tag + 风格匹配）
        if parsed.path == '/api/onboarding/analyze':
            wardrobe_dir = os.path.join(self.user_dir, 'wardrobe')
            tags_dir = os.path.join(wardrobe_dir, 'tags')
            os.makedirs(tags_dir, exist_ok=True)

            # 查找未打标签的图片
            imgs = [x for x in os.listdir(wardrobe_dir)
                    if x.lower().endswith(('.jpg','.jpeg','.png','.webp')) and x.startswith('upload_')]

            missing_tags = []
            for img in imgs:
                # 检查是否已有标签
                img_path = os.path.join(wardrobe_dir, img)
                found = False
                if os.path.isdir(tags_dir):
                    for tf in os.listdir(tags_dir):
                        if tf.endswith('.json'):
                            try:
                                with open(os.path.join(tags_dir, tf)) as f:
                                    td = json.load(f)
                                # 检查 meta 中是否有 source file 记录
                                if td.get('meta', {}).get('source_file') == img:
                                    found = True
                                    break
                            except:
                                pass
                if not found:
                    missing_tags.append(img)

            log(f"🔍 Onboarding analyze: {user_id} — {len(imgs)} imgs, {len(missing_tags)} 未标签")

            if missing_tags:
                # 在后台运行 quick_tag
                def _bg_analyze():
                    for img in missing_tags:
                        try:
                            img_path = os.path.join(wardrobe_dir, img)
                            log(f"🏷️ analyze quick_tag: {user_id}/{img}")
                            result = subprocess.run(
                                [sys.executable, os.path.join(PROJECT_DIR, 'tools', 'quick_tag.py'),
                                 img_path, '--user', user_id],
                                capture_output=True, text=True, timeout=60,
                                cwd=PROJECT_DIR
                            )
                            if result.returncode == 0:
                                # 记录 source_file 关联
                                last_line = result.stdout.strip().split('\n')[-1] if result.stdout else ''
                                try:
                                    tag_info = json.loads(last_line)
                                    cid = tag_info.get('id')
                                    if cid:
                                        tag_path = os.path.join(tags_dir, f'{cid}.json')
                                        if os.path.exists(tag_path):
                                            with open(tag_path) as f:
                                                td = json.load(f)
                                            td['meta']['source_file'] = img
                                            with open(tag_path, 'w') as f:
                                                json.dump(td, f, ensure_ascii=False, indent=2)
                                except:
                                    pass
                                log(f"✅ analyze quick_tag 完成: {user_id}/{img}")
                            else:
                                log(f"⚠️ analyze quick_tag 失败: {user_id}/{img}")
                        except Exception as e:
                            log(f"❌ analyze quick_tag 异常: {user_id}/{img} — {e}")

                    # 分析完成后标记 onboarding 完成
                    _complete_onboarding(user_id, self.user_dir)

                threading.Thread(target=_bg_analyze, daemon=True).start()
                self._json_resp(200, {'ok': True, 'analyzing': True, 'count': len(missing_tags)})
            else:
                # 全部已标签，直接完成
                _complete_onboarding(user_id, self.user_dir)
                self._json_resp(200, {'ok': True, 'analyzing': False, 'complete': True})
            return

        # Onboarding 完成
        if parsed.path == '/api/onboarding/complete':
            up = os.path.join(self.user_dir, 'profile.json')
            p = {}
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
            p['onboarding_step'] = 4
            p['onboarding_complete'] = True
            p['onboarding_done_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            with open(up, 'w') as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
            # 更新注册表状态（不存在则创建）
            reg = _load_user_registry()
            g = gender or 'male'
            if g not in reg:
                reg[g] = {}
            if user_id not in reg[g]:
                reg[g][user_id] = {'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            reg[g][user_id]['last_active'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            reg[g][user_id]['status'] = 'active'
            try:
                from tools.user_manager import save_registry
                save_registry(reg)
            except:
                pass
            log(f"✅ Onboarding 完成: {user_id}")
            self._json_resp(200, {'ok': True, 'redirect': f'/?user={user_id}'})
            return

        # Onboarding 状态查询（供 step4 轮询）
        if parsed.path == '/api/onboarding/status':
            up = os.path.join(self.user_dir, 'profile.json')
            complete = False
            step = 0
            if os.path.exists(up):
                with open(up) as f:
                    p = json.load(f)
                complete = p.get('onboarding_complete', False)
                step = p.get('onboarding_step', 0)
            # 检查 wardrobe 中有没有上传的衣服
            wardrobe_dir = os.path.join(self.user_dir, 'wardrobe')
            has_wardrobe = False
            if os.path.isdir(wardrobe_dir):
                imgs = [x for x in os.listdir(wardrobe_dir) if x.lower().endswith(('.jpg','.jpeg','.png','.webp'))]
                has_wardrobe = len(imgs) > 0
            self._json_resp(200, {'complete': complete, 'step': step, 'has_wardrobe': has_wardrobe})
            return

        if parsed.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"})
                return
            message = data.get('message', '').strip()
            if not message:
                self._json_resp(400, {"error": "empty message"})
                return

            action, extra = match_command(message)
            log(f"💬 聊天: {action} | {extra}")

            if action == 'wardrobe':
                self._json_resp(200, {"result": "👔 衣橱面板已打开，向上滑动查看完整数据", "action": "wardrobe"})
            elif action == 'today':
                _handle_today(self)
            elif action == 'favorites':
                _handle_favorites(self)
            elif action in ('generate', 'recommend'):
                tid = _start_async_pipeline(action, extra, getattr(self, 'user_id', None) if getattr(self, 'user_id', 'default') != 'default' else None)
                self._json_resp(200, {"task_id": tid})
            else:
                result = execute_action(action, extra)
                self._json_resp(200, {"result": result, "action": action})
        elif parsed.path == '/rate':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try: data = json.loads(body)
            except: self._json_resp(400, {"error": "invalid json"}); return
            oid = data.get('outfit_id', 'unknown')
            # 多用户：从用户目录查找 outfit
            _uid = getattr(self, 'user_id', 'default')
            _outfits_base = resolve_outfits_dir(None if _uid == 'default' else _uid)
            d = os.path.join(_outfits_base, oid)
            if not os.path.exists(d):
                # fallback: 尝试从主项目目录查找（兼容旧数据）
                d = os.path.join(PROJECT_DIR, 'outfits', oid)
            if not os.path.exists(d): self._json_resp(404, {"error": "outfit not found"}); return
            with open(os.path.join(d, 'rating.json'), 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log(f"⭐ 评分: {oid} → {data.get('rating','?')}星")
            # 反馈到评分缓存
            try:
                from style_lab import apply_rating_feedback
                apply_rating_feedback(d, data.get('rating', 0), data.get('feedback'))
            except Exception as e:
                log(f"⚠️ 反馈更新失败: {e}", "WARN")
            self._json_resp(200, {"status": "ok"})
        elif parsed.path == '/rate/cancel' and self.command == 'POST':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try: data = json.loads(body)
            except: self._json_resp(400, {"error": "invalid json"}); return
            oid = data.get('outfit_id', '')
            # 多用户：从用户目录查找 outfit
            _uid = getattr(self, 'user_id', 'default')
            _outfits_base = resolve_outfits_dir(None if _uid == 'default' else _uid)
            d = os.path.join(_outfits_base, oid)
            if not os.path.exists(d):
                d = os.path.join(PROJECT_DIR, 'outfits', oid)  # fallback
            if not os.path.exists(d): self._json_resp(404, {"error": "outfit not found"}); return
            rating_file = os.path.join(d, 'rating.json')
            old_rating = 0
            old_feedback = None
            if os.path.exists(rating_file):
                try:
                    with open(rating_file, 'r') as f:
                        old_data = json.load(f)
                    old_rating = old_data.get('rating', 0)
                    old_feedback = old_data.get('feedback')
                except: pass
                os.remove(rating_file)
                log(f"🗑️ 评分取消: {oid} (原评分: {old_rating})")
            # 逆转评分反馈
            if old_rating > 0:
                try:
                    from style_lab import apply_rating_feedback
                    apply_rating_feedback(d, -old_rating, old_feedback)
                except Exception as e:
                    log(f"⚠️ 反馈撤销失败: {e}", "WARN")
            self._json_resp(200, {"status": "ok", "message": "评分已取消"})
        elif parsed.path == '/api/ratings' and self.command == 'POST':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try: data = json.loads(body)
            except: self._json_resp(400, {"error": "invalid json"}); return
            ids = data.get('ids', [])
            ratings = {}
            for oid in ids:
                d = os.path.join(PROJECT_DIR, 'outfits', oid)
                rf = os.path.join(d, 'rating.json')
                if os.path.exists(rf):
                    try:
                        with open(rf) as f:
                            rd = json.load(f)
                        ratings[oid] = rd.get('rating', 0)
                    except: pass
                else:
                    ratings[oid] = 0
            self._json_resp(200, {"ratings": ratings})
        elif parsed.path.startswith('/api/wardrobe/item/') and parsed.path.endswith('/delete'):
            # 彻底删除单品
            cid = parsed.path.split('/api/wardrobe/item/')[-1].replace('/delete', '').strip()
            # 多用户：使用用户专属标签目录
            _uid = getattr(self, 'user_id', 'default')
            _tags_dir = resolve_tags_dir(None if _uid == 'default' else _uid)
            tag_path = os.path.join(_tags_dir, f'{cid}.json')
            if not os.path.exists(tag_path):
                self._json_resp(404, {"error": f"item {cid} not found"})
                return
            try:
                import glob as _glob, shutil as _shutil
                deleted_files = []
                # 删除标签 JSON
                os.remove(tag_path)
                deleted_files.append(tag_path)
                # 删除 enhanced 目录下的图片（多用户感知）
                enhanced_dir = os.path.join(resolve_wardrobe_dir(None if _uid == 'default' else _uid), 'enhanced')
                if os.path.exists(enhanced_dir):
                    for pattern in [f'{cid}_*']:
                        for fpath in _glob.glob(os.path.join(enhanced_dir, pattern)):
                            os.remove(fpath)
                            deleted_files.append(fpath)
                # 清理评分缓存 SCORE_CACHE.json（使用用户标签目录）
                score_cache_path = os.path.join(_tags_dir, 'SCORE_CACHE.json')
                if os.path.exists(score_cache_path):
                    with open(score_cache_path, 'r', encoding='utf-8') as f:
                        score_cache = json.load(f)
                    if cid in score_cache:
                        del score_cache[cid]
                        with open(score_cache_path, 'w', encoding='utf-8') as f:
                            json.dump(score_cache, f, ensure_ascii=False, indent=2)
                        deleted_files.append(f'{score_cache_path} (entry: {cid})')
                # 清理 cutout 映射 .id_to_cutout.json（使用用户标签目录）
                cutout_map_path = os.path.join(_tags_dir, '.id_to_cutout.json')
                if os.path.exists(cutout_map_path):
                    with open(cutout_map_path, 'r', encoding='utf-8') as f:
                        cutout_map = json.load(f)
                    if cid in cutout_map:
                        del cutout_map[cid]
                        with open(cutout_map_path, 'w', encoding='utf-8') as f:
                            json.dump(cutout_map, f, ensure_ascii=False, indent=2)
                        deleted_files.append(f'{cutout_map_path} (entry: {cid})')
                # 删除品类目录下的原始照片（多用户感知）
                categories_dir = resolve_wardrobe_dir(None if _uid == 'default' else _uid)
                for cat_dir in os.listdir(categories_dir):
                    cat_path = os.path.join(categories_dir, cat_dir)
                    if not os.path.isdir(cat_path) or cat_dir.startswith('_') or cat_dir in ('tags', 'enhanced'):
                        continue
                    for fname in os.listdir(cat_path):
                        if fname.startswith(cid):
                            fpath = os.path.join(cat_path, fname)
                            if os.path.isfile(fpath):
                                os.remove(fpath)
                                deleted_files.append(fpath)
                # 穿搭方案中的图片保留不删（已使用的历史记录）
                log(f"单品已删除: {cid} ({len(deleted_files)} files)")
                self._json_resp(200, {"ok": True, "deleted": len(deleted_files), "files": deleted_files})
            except Exception as e:
                log(f"删除单品失败 {cid}: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
        elif parsed.path.startswith('/api/wardrobe/item/') and not parsed.path.endswith('/rotate') and not parsed.path.endswith('/transform'):
            # 更新单品标签
            cid = parsed.path.split('/api/wardrobe/item/')[-1].strip()
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                updates = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"})
                return
            # 多用户：使用用户专属标签目录
            _uid = getattr(self, 'user_id', 'default')
            _tags_dir = resolve_tags_dir(None if _uid == 'default' else _uid)
            tag_path = os.path.join(_tags_dir, f'{cid}.json')
            if not os.path.exists(tag_path):
                self._json_resp(404, {"error": f"item {cid} not found"})
                return
            try:
                with open(tag_path, 'r', encoding='utf-8') as f:
                    current = json.load(f)

                def _deep_merge(base, patch):
                    for k, v in patch.items():
                        if isinstance(v, dict) and isinstance(base.get(k), dict):
                            _deep_merge(base[k], v)
                        else:
                            base[k] = v

                _deep_merge(current, updates)

                # 🆕 品类修改：验证并同步 category_code ↔ category
                _cat_code = current.get('category_code', '')
                _cat_name = current.get('category', '')
                if _cat_code in CATEGORY_CODE_TO_NAME:
                    # category_code 有效 → 同步 category 中文名
                    current['category'] = CATEGORY_CODE_TO_NAME[_cat_code]
                elif _cat_name:
                    # 只有中文名 → 反向查 category_code
                    _rev = {v: k for k, v in CATEGORY_CODE_TO_NAME.items()}
                    if _cat_name in _rev:
                        current['category_code'] = _rev[_cat_name]
                    # 否则保留原样（可能是自由文本品类名）

                # 🆕 自动重新生成服装介绍 — 从结构化字段动态构建
                _brand = (current.get('brand') or {}).get('name', '')
                _color = (current.get('color') or {}).get('hue_name', '')
                _cat = current.get('category', '')
                _styles = current.get('style_modifiers', [])
                # 过滤掉颜色/身形类描述性标签（不应出现在名称中）
                _color_kw = {'颜色显白', '显白', '显瘦', '纯色', '深色', '浅色', '亮色', '暗色'}
                _name_styles = [s for s in _styles if s not in _color_kw]
                _parts = [p for p in [
                    _brand if _brand not in ('未知', '') else '',
                    _color,
                    _name_styles[0] if _name_styles else '',
                    _cat
                ] if p]
                # 去重：风格词已含品类时去掉品类词（如"跑鞋鞋子"→"跑鞋"）
                _cat_redundant = {
                    '鞋子': ['鞋'], '帽子': ['帽'], '袜子': ['袜'],
                    '短袖上衣': ['短袖', 'T恤'], '长裤': ['裤'], '短裤': ['裤'],
                }
                for _cat_k, _cat_v in _cat_redundant.items():
                    if _cat == _cat_k and _parts and any(v in _parts[-1] for v in _cat_v):
                        _parts = _parts[:-1]
                        break
                _short_name = ''.join(_parts) if _parts else _cat
                # 提取旧 comment 最后一个逗号后的身形适配描述
                _old = (current.get('meta') or {}).get('claude_fit_comment', '')
                _body_hint = ''
                if '，' in _old:
                    _body_hint = _old.rsplit('，', 1)[-1].strip()
                elif ',' in _old:
                    _body_hint = _old.rsplit(',', 1)[-1].strip()
                # 只有身形相关才保留
                _body_kw = ['显白', '修饰', '平衡', '拉长', '显瘦', '遮盖', '优化', '腿型', '比例']
                if not any(kw in _body_hint for kw in _body_kw):
                    _body_hint = ''
                _new_comment = _short_name
                if _body_hint: _new_comment += '，' + _body_hint
                current.setdefault('meta', {})['claude_fit_comment'] = _new_comment

                with open(tag_path, 'w', encoding='utf-8') as f:
                    json.dump(current, f, ensure_ascii=False, indent=2)

                log(f"标签更新: {cid}")
                self._json_resp(200, {"ok": True, "item_id": cid})
            except Exception as e:
                log(f"标签更新失败 {cid}: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
        elif parsed.path.startswith('/api/wardrobe/item/') and parsed.path.endswith('/transform'):
            # 复合变换单品图片（旋转+缩放+平移）
            cid = parsed.path.split('/api/wardrobe/item/')[-1].replace('/transform', '').strip()
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                params = json.loads(body)
                degrees = int(params.get('rotate', 0))
                scale = float(params.get('scale', 1.0))
                tx = int(params.get('translate_x', 0))
                ty = int(params.get('translate_y', 0))
            except (json.JSONDecodeError, ValueError):
                self._json_resp(400, {"error": "invalid json"})
                return
            import glob as _glob
            from PIL import Image as _PILImage
            transformed = 0
            def _transform_img(fpath, orig_w, orig_h):
                nonlocal transformed
                try:
                    img = _PILImage.open(fpath)
                    if degrees % 360 != 0:
                        img = img.rotate(-degrees, expand=True)
                    if abs(scale - 1.0) > 0.01:
                        new_w = int(img.width * scale)
                        new_h = int(img.height * scale)
                        img = img.resize((new_w, new_h), _PILImage.LANCZOS)
                        # Crop back to original dimensions based on pan
                        left = (img.width - orig_w) // 2 + tx
                        top = (img.height - orig_h) // 2 + ty
                        left = max(0, min(left, img.width - orig_w))
                        top = max(0, min(top, img.height - orig_h))
                        if img.width > orig_w or img.height > orig_h:
                            img = img.crop((left, top, left + orig_w, top + orig_h))
                    img.save(fpath, 'PNG')
                    transformed += 1
                    return True
                except Exception as e:
                    log(f"图片变换失败 {fpath}: {e}", "WARN")
                    return False
            # 多用户：使用用户专属路径
            _uid = getattr(self, 'user_id', 'default')
            enhanced_dir = os.path.join(resolve_wardrobe_dir(None if _uid == 'default' else _uid), 'enhanced')
            if os.path.exists(enhanced_dir):
                for pattern in [f'{cid}_cutout.*', f'{cid}_cutout_thumb.*', f'{cid}_thumb.*']:
                    for fpath in _glob.glob(os.path.join(enhanced_dir, pattern)):
                        img = _PILImage.open(fpath)
                        w, h = img.size
                        img.close()
                        _transform_img(fpath, w, h)
            outfits_dir = resolve_outfits_dir(None if _uid == 'default' else _uid)
            if os.path.exists(outfits_dir):
                for d in sorted(os.listdir(outfits_dir)):
                    dp = os.path.join(outfits_dir, d)
                    if not os.path.isdir(dp): continue
                    items_dir = os.path.join(dp, 'items')
                    if not os.path.exists(items_dir): continue
                    for fpath in _glob.glob(os.path.join(items_dir, f'{cid}_*cutout*')):
                        img = _PILImage.open(fpath)
                        w, h = img.size
                        img.close()
                        _transform_img(fpath, w, h)
            # 从变换后的 _cutout.png 重新生成 _cutout_thumb.png（白底合成）
            cutout_path = os.path.join(enhanced_dir, f'{cid}_cutout.png')
            if os.path.exists(cutout_path):
                try:
                    img = _PILImage.open(cutout_path)
                    w, h = img.size
                    if img.mode == 'RGBA':
                        white_bg = _PILImage.new('RGB', img.size, (255, 255, 255))
                        white_bg.paste(img, mask=img.split()[3])
                        img = white_bg
                    if w > 200:
                        ratio = 200 / w
                        img = img.resize((200, int(h * ratio)), _PILImage.LANCZOS)
                    thumb_path = os.path.join(enhanced_dir, f'{cid}_cutout_thumb.png')
                    img.save(thumb_path, 'PNG', optimize=True)
                except Exception as e:
                    log(f"缩略图更新失败 {cid}: {e}", "WARN")
            log(f"图片变换: {cid} rotate={degrees} scale={scale} pan=({tx},{ty}) -> {transformed} files")
            self._json_resp(200, {"ok": True, "transformed": transformed})

        # ─── 衣橱添加入库 ───
        elif parsed.path == '/api/wardrobe/add':
            # 生成请求 ID 贯穿全链路
            req_id = str(int(time.time() * 1000) % 100000)
            length = int(self.headers.get('Content-Length', 0))
            # 设置 socket 超时（手机通过 Funnel 上传可能很慢）
            try:
                self.connection.settimeout(15)
            except Exception as e:
                log(f'[{req_id}] ⚠️ 设置超时失败: {e}')
            # 分块读取
            body = b''
            deadline = time.time() + 90
            try:
                while len(body) < length:
                    remain = length - len(body)
                    chunk = self.rfile.read(min(remain, 8192))
                    if not chunk:
                        break
                    body += chunk
                    if time.time() > deadline:
                        log(f'[{req_id}] ⚠️ 上传总超时: {len(body)}B/{length}B')
                        break
            except Exception as e:
                log(f'[{req_id}] ⚠️ 上传读取中断: {e} ({len(body)}B/{length}B)')
            if len(body) < length:
                self._json_resp(400, {"error": "ERR_TIMEOUT", "message": f"数据接收不完整 ({len(body)}/{length}B)，请重试"})
                return
            content_type = self.headers.get('Content-Type', '')
            log(f'[{req_id}] 衣橱上传: {len(body)}B')

            # 使用标准库 BytesParser 解析 multipart（20年生产环境验证，覆盖所有边界情况）
            if 'multipart/form-data' in content_type:
                from email.parser import BytesParser
                from email.policy import HTTP
                import base64 as _b64
                image_b64_list = []
                try:
                    msg = BytesParser(policy=HTTP).parsebytes(
                        b'Content-Type: ' + content_type.encode() + b'\r\n\r\n' + body
                    )
                    for part in msg.iter_parts():
                        payload = part.get_payload(decode=True)
                        if payload and len(payload) >= 100:
                            image_b64_list.append(_b64.b64encode(payload).decode('utf-8'))
                except Exception as e:
                    log(f'[{req_id}] ⚠️ multipart 解析失败: {e}')
                    self._json_resp(400, {"error": "ERR_PARSE", "message": "图片数据解析失败，请重试"})
                    return

                if not image_b64_list:
                    self._json_resp(400, {"error": "ERR_PARSE", "message": "未检测到有效图片，请重新选择"})
                    return
                if len(image_b64_list) > 10:
                    self._json_resp(400, {"error": "ERR_SIZE", "message": "最多10张图片"})
                    return
                tid = tasks.create()
                _uid = self.user_id if self.user_id != 'default' else None
                # 🛡️ 持久化 _user_id，确保崩溃恢复时重试队列保留用户上下文
                if _uid:
                    tasks.update(tid, _user_id=_uid)
                threading.Thread(target=_run_add_analysis, args=(tid, image_b64_list, _uid, req_id), daemon=True).start()
                log(f'[{req_id}] 📸 衣橱添加(binary): {tid} ({len(image_b64_list)} 张图片, {len(body)/1024:.0f}KB)')
                self._json_resp(200, {"task_id": tid, "message": f"正在分析 {len(image_b64_list)} 张图片..."})
            else:
                # 兼容旧版 JSON + base64 方式
                try:
                    data = json.loads(body.decode('utf-8'))
                except json.JSONDecodeError:
                    self._json_resp(400, {"error": "ERR_PARSE", "message": "数据格式错误，请刷新页面后重试"})
                    return
                images = data.get('images', [])
                if not images or not isinstance(images, list):
                    self._json_resp(400, {"error": "ERR_PARSE", "message": "请至少提供一张图片"})
                    return
                if len(images) > 10:
                    self._json_resp(400, {"error": "ERR_SIZE", "message": "最多10张图片"})
                    return
                tid = tasks.create()
                _uid = self.user_id if self.user_id != 'default' else None
                # 🛡️ 持久化 _user_id，确保崩溃恢复时重试队列保留用户上下文
                if _uid:
                    tasks.update(tid, _user_id=_uid)
                threading.Thread(target=_run_add_analysis, args=(tid, images, _uid, req_id), daemon=True).start()
                log(f'[{req_id}] 📸 衣橱添加(JSON): {tid} ({len(images)} 张图片)')
                self._json_resp(200, {"task_id": tid, "message": f"正在分析 {len(images)} 张图片..."})

        elif parsed.path == '/api/wardrobe/add/confirm':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"}); return
            task_id = data.get('task_id', '')
            items = data.get('items', [])
            if not items:
                self._json_resp(400, {"error": "请至少确认一件单品"}); return
            # 加载临时分析结果 — 优先用户目录，fallback 主项目（兼容旧分析）
            _uid = self.user_id if self.user_id != 'default' else None
            user_incoming = os.path.join(resolve_user_dir(_uid), 'wardrobe', '_incoming')
            main_incoming = os.path.join(PROJECT_DIR, 'wardrobe', '_incoming')
            analysis_path = os.path.join(user_incoming, f'analysis_{task_id}.json')
            if not os.path.exists(analysis_path):
                analysis_path = os.path.join(main_incoming, f'analysis_{task_id}.json')
            # 确保 _incoming_dir 在使用前已定义（修复 UnboundLocalError）
            _incoming_dir = os.path.dirname(analysis_path) if os.path.exists(os.path.dirname(analysis_path)) else main_incoming
            if os.path.exists(analysis_path):
                with open(analysis_path, 'r') as f:
                    saved = json.load(f)
                saved_items = {str(i): it for i, it in enumerate(saved.get('items', []))}
                # 从分析 JSON 读取 user_id（优先），fallback 到当前请求上下文
                analysis_uid = saved.get('_user_id') or _uid
                for i, item in enumerate(items):
                    if not item.get('_temp_image_path'):
                        item['_temp_image_path'] = saved_items.get(str(i), {}).get('_temp_image_path', '')
                    # 注入 user_id 供 _finalize_add_item 路由
                    if not item.get('_user_id'):
                        item['_user_id'] = analysis_uid
            else:
                # 没有分析 JSON，使用当前请求上下文
                for item in items:
                    if not item.get('_user_id'):
                        item['_user_id'] = _uid
            added = []
            errors = []
            _source_images = set()  # 🆕 收集所有源图路径，统一清理
            # 串行入库（避免并行线程 + 锁竞争 + rembg 内存爆炸导致超时）
            for i, item in enumerate(items):
                try:
                    result = _finalize_add_item(item)
                    added.append((i, result))
                    # 记录源图路径，等所有单品入库后统一清理
                    if result.get('_source_image'):
                        _source_images.add(result['_source_image'])
                except Exception as e:
                    log(f"入库失败: {e}", "ERROR")
                    import traceback
                    traceback.print_exc()
                    errors.append(str(e))
            # 恢复原始顺序
            added.sort(key=lambda x: x[0])
            added = [{k: v for k, v in r.items() if not k.startswith('_')} for _, r in added]
            # 统一清理：所有单品入库后再删临时文件（避免同源图互相踩踏）
            for _src in _source_images:
                try:
                    if os.path.exists(_src):
                        os.remove(_src)
                except Exception:
                    pass
            # 🆕 清理原始上传图片（可能和裁剪图不同路径）
            for _i in range(10):  # 最多 10 张原图
                _orig = os.path.join(_incoming_dir, f'img_{task_id}_{_i}.jpg')
                try:
                    if os.path.exists(_orig):
                        os.remove(_orig)
                except Exception:
                    pass
            # 🆕 清理旧 _incoming 文件（>24h 的残留）
            _now_ts = time.time()
            try:
                for _fn in os.listdir(_incoming_dir):
                    _fp = os.path.join(_incoming_dir, _fn)
                    if os.path.isfile(_fp) and _now_ts - os.path.getmtime(_fp) > 86400:
                        os.remove(_fp)
            except Exception:
                pass
            # 清理分析JSON
            try:
                os.remove(analysis_path)
            except: pass
            # 🆕 清理 cloth parsing 裁剪图
            if _incoming_dir and task_id:
                try:
                    for _fn in os.listdir(_incoming_dir):
                        if _fn.startswith(f'crop_{task_id}_'):
                            os.remove(os.path.join(_incoming_dir, _fn))
                except Exception:
                    pass
            self._json_resp(200, {"ok": True, "added": added, "errors": errors,
                                  "message": f'已添加 {len(added)} 件单品' + (f'，{len(errors)} 件失败' if errors else '')})

        # ─── 🆕 衣橱匹配：新衣与现有单品配对 ───
        elif parsed.path == '/api/wardrobe/add/match':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"}); return
            new_items = data.get('items', [])
            task_id = data.get('task_id', '')
            if not new_items:
                self._json_resp(400, {"error": "请提供新衣分析结果"}); return

            # 加载临时分析结果（补充 _temp_image_path）— 优先用户目录
            if task_id:
                _uid = self.user_id if self.user_id != 'default' else None
                user_incoming = os.path.join(resolve_user_dir(_uid), 'wardrobe', '_incoming')
                main_incoming = os.path.join(PROJECT_DIR, 'wardrobe', '_incoming')
                analysis_path = os.path.join(user_incoming, f'analysis_{task_id}.json')
                if not os.path.exists(analysis_path):
                    analysis_path = os.path.join(main_incoming, f'analysis_{task_id}.json')
                if os.path.exists(analysis_path):
                    with open(analysis_path, 'r') as f:
                        saved = json.load(f)
                    saved_items = {str(i): it for i, it in enumerate(saved.get('items', []))}
                    for i, item in enumerate(new_items):
                        if not item.get('_temp_image_path'):
                            item['_temp_image_path'] = saved_items.get(str(i), {}).get('_temp_image_path', '')

            # 为每件新衣匹配
            all_matches = []
            for i, new_item in enumerate(new_items):
                matches = match_for_new_item(new_item)
                all_matches.append({
                    'item_index': i,
                    'suggested_id': new_item.get('suggested_id', ''),
                    'category': new_item.get('category', ''),
                    'category_code': new_item.get('category_code', ''),
                    'color': new_item.get('color', {}),
                    'matches': matches,
                })
            self._json_resp(200, {"ok": True, "match_results": all_matches})

        # ─── 🆕 以新衣为核心 AI 生成穿搭 ───
        elif parsed.path == '/api/wardrobe/add/generate-outfit':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"}); return
            new_item = data.get('new_item', {})
            selected_ids = data.get('selected_ids', [])
            if not new_item:
                self._json_resp(400, {"error": "请提供新衣信息"}); return

            tid = tasks.create()
            _uid = self.user_id if self.user_id != 'default' else None
            threading.Thread(target=_run_preview_outfit, args=(tid, new_item, selected_ids, _uid), daemon=True).start()
            log(f"🪄 预览穿搭: {tid} (新衣={new_item.get('suggested_id','?')}, 匹配={selected_ids})")
            self._json_resp(200, {"task_id": tid, "message": "正在生成穿搭预览..."})

        elif parsed.path == '/api/wardrobe/new-items/dismiss':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"}); return
            cid = data.get('clothing_id', '')
            if not cid:
                self._json_resp(400, {"error": "missing clothing_id"}); return
            new_path = os.path.join(PROJECT_DIR, 'config', 'new_items.json')
            if os.path.exists(new_path):
                with open(new_path, 'r') as f:
                    new_data = json.load(f)
                if cid in new_data.get('items', {}):
                    del new_data['items'][cid]
                    with open(new_path, 'w') as f:
                        json.dump(new_data, f, ensure_ascii=False, indent=2)
                    log(f"🔔 新单品徽标已消除: {cid}")
            self._json_resp(200, {"ok": True})

        # ─── 我的形象 API (POST) ───

        elif parsed.path == '/api/profile/save':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"})
                return
            try:
                # ── 多用户：保存到用户目录，合并 onboarding 数据 ──
                if self.user_id != 'default':
                    profile_path = os.path.join(self.user_dir, 'profile.json')
                    existing = {}
                    if os.path.exists(profile_path):
                        with open(profile_path) as f:
                            existing = json.load(f)
                    photos = data.get('photos', {})
                    if not photos:
                        # 从现有数据保留 photos
                        photos = existing.get('photos', {})
                    # 合并：保留 onboarding 字段，追加形象字段
                    existing['photos'] = photos
                    existing['use_my_image'] = data.get('use_my_image', existing.get('use_my_image', True))
                    existing['gender'] = data.get('gender', existing.get('gender', 'female'))
                    existing['body'] = {
                        'height': str(data.get('height_cm', existing.get('body', {}).get('height', ''))),
                        'weight': str(data.get('weight_kg', existing.get('body', {}).get('weight', ''))),
                        'age': str(data.get('age', existing.get('body', {}).get('age', ''))),
                        'shape': data.get('body_type', existing.get('body', {}).get('shape', '')),
                        'skin_tone': data.get('skin_tone', existing.get('body', {}).get('skin_tone', '')),
                        'shoulder_type': data.get('shoulder_type', existing.get('body', {}).get('shoulder_type', '')),
                        'face_shape': data.get('face_shape', existing.get('body', {}).get('face_shape', '')),
                        'concern': data.get('pain_points', existing.get('body', {}).get('concern', '')),
                    }
                    existing['lifestyle'] = {
                        'occupation': data.get('occupation', existing.get('lifestyle', {}).get('occupation', '')),
                        'style_preference': data.get('style_preference', existing.get('lifestyle', {}).get('style_preference', '')),
                    }
                    # 同时更新 style_prefs 数组（兼容旧格式）
                    sp = data.get('style_preference', '')
                    existing['style_prefs'] = [s.strip() for s in sp.split(',') if s.strip()] if sp else []
                    existing['body_secrets'] = data.get('body_secrets', existing.get('body_secrets', ''))
                    existing['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                    with open(profile_path, 'w', encoding='utf-8') as f:
                        json.dump(existing, f, ensure_ascii=False, indent=2)
                    log(f"👤 形象档案已保存 ({self.user_id})")
                    self._json_resp(200, {"ok": True, "profile": existing})
                    return

                # ── 单人模式：保存到 config/user_profile.json ──
                profile_path = os.path.join(PROJECT_DIR, 'config', 'user_profile.json')
                existing = {}
                if os.path.exists(profile_path):
                    with open(profile_path) as f:
                        existing = json.load(f)
                photos = data.get('photos', {})
                if not photos:
                    photos = existing.get('photos', {})
                profile = {
                    'use_my_image': data.get('use_my_image', True),
                    'gender': data.get('gender', '男'),
                    'photos': photos,
                    'body': {
                        'height_cm': data.get('height_cm', ''),
                        'weight_kg': data.get('weight_kg', ''),
                        'age': data.get('age', ''),
                        'body_type': data.get('body_type', ''),
                        'skin_tone': data.get('skin_tone', ''),
                        'shoulder_type': data.get('shoulder_type', ''),
                        'face_shape': data.get('face_shape', ''),
                    },
                    'lifestyle': {
                        'occupation': data.get('occupation', ''),
                        'style_preference': data.get('style_preference', ''),
                        'pain_points': data.get('pain_points', ''),
                    },
                    'body_secrets': data.get('body_secrets', ''),
                    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                }
                os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, ensure_ascii=False, indent=2)
                log(f"👤 形象档案已保存")
                self._json_resp(200, {"ok": True, "profile": profile})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        elif parsed.path == '/api/profile/photos/upload':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"})
                return
            try:
                import base64 as _b64
                slot = data.get('slot', 'full_body_front')
                image_b64 = data.get('image', '')
                if not image_b64:
                    self._json_resp(400, {"error": "no image data"})
                    return
                if ',' in image_b64 and ';base64' in image_b64:
                    image_b64 = image_b64.split(',', 1)[1]

                # ── 多用户：保存到用户目录 ──
                if self.user_id != 'default':
                    photo_dir = os.path.join(self.user_dir, 'profile', 'photos')
                    profile_path = os.path.join(self.user_dir, 'profile.json')
                else:
                    photo_dir = os.path.join(PROJECT_DIR, 'profile', 'photos')
                    profile_path = os.path.join(PROJECT_DIR, 'config', 'user_profile.json')
                os.makedirs(photo_dir, exist_ok=True)
                slot_names = {
                    'full_body_front': 'user_full_front.jpg',
                    'face_closeup': 'user_face.jpg',
                    'full_body_side': 'user_side.jpg',
                }
                filename = slot_names.get(slot, f'user_{slot}.jpg')
                filepath = os.path.join(photo_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(_b64.b64decode(image_b64))

                # update profile
                profile = {}
                if os.path.exists(profile_path):
                    with open(profile_path) as f:
                        profile = json.load(f)
                if 'photos' not in profile:
                    profile['photos'] = {}
                # 🛡️ 多用户：存储用户相对路径；单人：存储项目相对路径
                if self.user_id != 'default':
                    photo_rel_path = f'users/{self.user_gender}/{self.user_id}/profile/photos/{filename}'
                else:
                    photo_rel_path = f'profile/photos/{filename}'
                profile['photos'][slot] = photo_rel_path
                profile['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, ensure_ascii=False, indent=2)
                log(f"📷 照片已上传 ({self.user_id}): {slot} → {filename}")
                # 异步去背景（不阻塞上传响应）
                def _bg_remove():
                    try:
                        remove_person_background(filepath)
                    except Exception as e2:
                        log(f"⚠️ 上传后抠图失败: {e2}")
                threading.Thread(target=_bg_remove, daemon=True).start()
                self._json_resp(200, {"ok": True, "slot": slot, "path": photo_rel_path})
                return
            except Exception as e:
                log(f"照片上传失败: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        elif parsed.path == '/api/profile/analyze':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"})
                return
            try:
                import base64 as _b64
                image_b64s = data.get('images', [])
                if not image_b64s:
                    self._json_resp(400, {"error": "请先上传至少一张照片"})
                    return
                user_content = []
                for img in image_b64s:
                    b64_data = img.get('b64', '')
                    if ',' in b64_data and ';base64' in b64_data:
                        b64_data = b64_data.split(',', 1)[1]
                    slot_labels = {
                        'full_body_front': '正面全身照',
                        'face_closeup': '半身面部照',
                        'full_body_side': '侧面全身照',
                    }
                    label = slot_labels.get(img.get('slot', ''), '照片')
                    user_content.append({
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b64_data}'}
                    })
                    user_content.append({'type': 'text', 'text': f'[上图: {label}]'})
                user_content.append({
                    'type': 'text',
                    'text': (
                        '请分析以上照片中人物的身体特征。只返回JSON，不要其他文字。\n'
                        '{\n'
                        '  "gender": "男 或 女",\n'
                        '  "body_type": "偏瘦 / 标准 / 偏胖 / 肌肉型",\n'
                        '  "skin_tone": "白皙 / 偏白 / 自然 / 小麦 / 偏黄 / 偏黑",\n'
                        '  "shoulder_type": "窄肩 / 标准 / 宽肩 / 溜肩（不确定就填标准）",\n'
                        '  "face_shape": "圆脸 / 方脸 / 长脸 / 瓜子脸 / 椭圆脸（不确定就填空字符串）",\n'
                        '  "estimated_height_cm": "估算身高cm数（不确定填0）",\n'
                        '  "analysis_notes": "简短分析说明（1-2句中文）"\n'
                        '}'
                    )
                })
                messages = [{'role': 'user', 'content': user_content}]
                response_text = call_doubao_chat(messages, max_tokens=1024, timeout=60)
                analysis = extract_json(response_text)
                if not analysis:
                    self._json_resp(200, {"ok": False, "error": "AI 分析失败，请手动填写"})
                    return
                log(f"🔍 AI 身形分析完成: {analysis.get('body_type', '?')} {analysis.get('skin_tone', '?')}")
                self._json_resp(200, {"ok": True, "analysis": analysis})
                return
            except Exception as e:
                log(f"AI 分析失败: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return

        elif parsed.path == '/api/profile/reset':
            try:
                profile_path = os.path.join(PROJECT_DIR, 'config', 'user_profile.json')
                if os.path.exists(profile_path):
                    os.remove(profile_path)
                log(f"👤 形象档案已重置")
                self._json_resp(200, {"ok": True})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        else:
            self._json_resp(404, {"error": "not found"})

    def _maybe_gzip(self, body):
        """如果客户端支持 gzip 则压缩，返回 (compressed_body, is_gzip)"""
        accept = self.headers.get('Accept-Encoding', '')
        if 'gzip' in accept and len(body) > 1024:
            import gzip
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as f:
                f.write(body)
            return buf.getvalue(), True
        return body, False

    def _read_post_body(self):
        """读取 POST 请求体"""
        length = int(self.headers.get('Content-Length', 0))
        if length > 0:
            return self.rfile.read(length).decode('utf-8')
        return ''

    def _send_body(self, code, body, content_type, extra_headers=None):
        """发送响应（自动 gzip 压缩）。客户端断开时静默忽略。"""
        compressed, is_gzip = self._maybe_gzip(body)
        try:
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(compressed)))
            if is_gzip:
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Vary', 'Accept-Encoding')
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(compressed)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # 客户端已断开（Funnel 超时/网络切换），静默忽略

    def _json_resp(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self._send_body(code, body, 'application/json; charset=utf-8',
                        {'Cache-Control': 'no-store, max-age=0'})

    def _html_resp(self, code, html, extra_headers=None):
        body = html.encode('utf-8')
        headers = {'Cache-Control': 'public, max-age=60, must-revalidate'}
        if extra_headers:
            headers.update(extra_headers)
        self._send_body(code, body, 'text/html; charset=utf-8', headers)

    def _text_resp(self, code, text):
        body = text.encode('utf-8')
        self._send_body(code, body, 'text/plain; charset=utf-8')

    def log_message(self, format, *args):
        pass  # 禁用默认HTTP日志，改用自定义log函数

REDIRECT_HTML = """<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url=/">
<title>穿搭助手</title></head><body></body></html>"""

LOG_LIVE_HTML = """<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>📋 操作日志</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1815;color:#c8c0b4;font-family:'SF Mono',Menlo,monospace;font-size:12px;padding:12px}
#log{white-space:pre-wrap;line-height:1.5}
#status{color:#8b7a64;margin-bottom:8px;font-size:11px}
</style>
</head>
<body>
<div id="status">🟢 实时监控中... <span id="count"></span></div>
<pre id="log">加载中...</pre>
<script>
var lastLen=0;
function refresh(){
fetch('/log?n=100').then(r=>r.text()).then(function(t){
document.getElementById('log').textContent=t;
var lines=t.split('\n').filter(function(l){return l});
document.getElementById('count').textContent=lines.length+' 行';
if(lines.length!==lastLen){lastLen=lines.length;window.scrollTo(0,document.body.scrollHeight)}
})
}
refresh();
setInterval(refresh,3000);
</script>
</body>
</html>"""

HISTORY_HTML = """<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>📋 操作历史</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f5f0eb;color:#3a3028;font-family:-apple-system,'PingFang SC',sans-serif;padding:16px;max-width:700px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px;letter-spacing:1px}
.sub{font-size:12px;color:#9b8c7c;margin-bottom:20px}
.card{background:#fff;border:1px solid #e0d8d0;border-radius:8px;padding:14px 16px;margin-bottom:12px;display:flex;gap:12px;align-items:flex-start}
.card .thumb{width:72px;height:72px;border-radius:4px;object-fit:cover;flex-shrink:0;background:#f0ebe0;border:1px solid #e0d8d0}
.card .info{flex:1;min-width:0}
.card .style{font-size:16px;font-weight:600;margin-bottom:4px}
.card .meta{font-size:12px;color:#9b8c7c;margin-bottom:4px}
.card .items{font-size:13px;color:#5c4d3c;line-height:1.5}
.card .status{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:6px}
.status-done{background:#e8f0e0;color:#5a7d3a}
.status-error{background:#fce8e8;color:#c04040}
.empty{text-align:center;padding:40px;color:#9b8c7c;font-size:14px}
#refresh{font-size:11px;color:#9b8c7c;text-align:right;margin-bottom:8px}
</style>
</head>
<body>
<h1>📋 手机端操作历史</h1>
<div class="sub">每次远程操控的穿搭推荐记录</div>
<div id="refresh">⏱ 自动刷新</div>
<div id="list">加载中...</div>
<script>
function load(){
fetch('/api/history?n=50').then(r=>r.json()).then(function(data){
var el=document.getElementById('list');
if(!data.length){el.innerHTML='<div class="empty">暂无操作记录<br><small>用手机发送第一条指令吧</small></div>';return}
var h='';
data.forEach(function(e){
var statusCls=e.status==='done'?'status-done':'status-error';
var statusText=e.status==='done'?'✅ 成功':'❌ 失败';
var thumb=e.image_url?'<img class="thumb" src="'+esc(e.image_url)+'" loading="lazy">':'<div class="thumb"></div>';
var items=e.result||'';
// 提取单品行
var itemLines=items.match(/\\*\\*\\w+-\\d+\\*\\*[^\\n]*/g)||[];
var itemHtml=itemLines.length?itemLines.join('<br>') : items.substring(0,100);
h+='<div class="card">'+thumb+'<div class="info"><div class="style">'+esc(e.style)+'<span class="status '+statusCls+'">'+statusText+'</span></div><div class="meta">'+esc(e.time)+'</div><div class="items">'+itemHtml+'</div></div></div>';
});
el.innerHTML=h;
document.getElementById('refresh').textContent='⏱ 更新于 '+new Date().toLocaleTimeString();
})
}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
load();
setInterval(load,15000);
</script>
</body>
</html>"""

# ── 启动 ──────────────────────────────────────────────
def main():
    port = 8765
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg in ('--port', '-p') and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg.startswith('--port='):
            port = int(arg.split('=', 1)[1])
        elif arg.isdigit():
            port = int(arg)

    server = ThreadingHTTPServer(('0.0.0.0', port), WebhookHandler)
    server.daemon_threads = True  # 收到 SIGTERM 后主线程退出时自动清理请求线程

    # ── Tailscale Funnel 自动启动 ──
    _funnel_ok = False
    try:
        _funnel_check = subprocess.run(
            ['tailscale', 'funnel', 'status'],
            capture_output=True, text=True, timeout=5
        )
        if 'Funnel on' not in (_funnel_check.stdout or ''):
            log("🌐 自动启用 Tailscale Funnel...")
            subprocess.run(
                ['tailscale', 'funnel', '--bg', '--https', '443', f'http://localhost:{port}'],
                capture_output=True, timeout=10
            )
            _funnel_ok = True
        elif f'http://localhost:{port}' in (_funnel_check.stdout or '') or f'http://127.0.0.1:{port}' in (_funnel_check.stdout or ''):
            _funnel_ok = True
        else:
            log(f"⚠️ Funnel 端口不一致，重置...")
            subprocess.run(['tailscale', 'funnel', '--https=443', 'off'], capture_output=True, timeout=5)
            subprocess.run(['tailscale', 'funnel', '--bg', '--https', '443', f'http://localhost:{port}'], capture_output=True, timeout=10)
            _funnel_ok = True
    except Exception as e:
        log(f"⚠️ Funnel 启动失败: {e}")

    log("=" * 55)
    log("👔 Fashion 穿搭助手 — 交互式聊天")
    log(f"📡 服务: http://0.0.0.0:{port}")
    log(f"💬 面板: http://localhost:{port}/")
    if _funnel_ok:
        log("🌐 Funnel: 已就绪")

    # ── 启动恢复：扫描磁盘上的中断任务，分析类自动重试 ──
    interrupted, retried, retry_queue = tasks.recover_on_startup()
    if interrupted or retried:
        log(f"♻️ 启动恢复: {interrupted} 个中断, {retried} 个自动重试")

    # ── 处理重试队列：读图片 → base64 → 重新提交分析 ──
    if retry_queue:
        _process_retry_queue(retry_queue)

    # ── Watchdog：自动检测超时任务（running > 5min → error）──
    tasks.start_watchdog(interval=30)

    # ── 信号处理：优雅关闭（等待活跃任务完成）──
    _shutdown_flag = threading.Event()
    setup_signal_handlers(server, tasks, _shutdown_flag, graceful_timeout=15)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass  # SIGINT handler 已处理
    finally:
        tasks.stop_watchdog()
        log("👋 服务已关闭")
        server.server_close()

if __name__ == '__main__':
    main()
