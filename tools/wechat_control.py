#!/usr/bin/env python3
"""
穿搭助手 — 手机远程控制服务（交互式聊天版）

架构:
  手机浏览器 → HTML聊天面板(ngrok) → HTTP API → Claude管线 → 面板实时显示结果
  同时推送到微信作为备份通知

依赖: 纯 Python 标准库
启动: bash tools/start_wechat_control.sh
"""

import json
import os
import re
import sys
import shutil
import subprocess
import threading
import time
import mimetypes
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'seedream.local.json')
LOG_FILE = os.path.join(PROJECT_DIR, 'tools', 'wechat_control.log')
HISTORY_FILE = os.path.join(PROJECT_DIR, 'tools', 'wechat_history.json')

# ── 日志 ────────────────────────────────────────────
def log(msg, level='INFO'):
    """写日志到文件 + stdout"""
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except:
        pass

# ── 加载配置 ──────────────────────────────────────────
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

SENDKEY = config.get('wechat_sendkey', '')
if not SENDKEY:
    print("❌ 未配置 wechat_sendkey")
    log("未配置 wechat_sendkey", "FATAL")
    sys.exit(1)

API_KEY = config.get('api_key', '')
API_CHAT_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions'
CHAT_MODEL = 'doubao-seed-2.0-code'

# ── 品类到目录/前缀映射 ──────────────────────────────────
# wardrobe.md 品类 → 目录名 → 豆包生图前缀
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
}

# ── 品类代码 → 中文名 ──────────────────────────────────
CATEGORY_NAMES = {
    'TS': 'T恤/短袖', 'LS': '长袖上衣', 'SHIRT': '衬衫', 'TANK': '背心',
    'JK': '外套/夹克', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
    'BAG': '包', 'HAT': '帽子', 'SOCK': '袜子', 'SUN': '太阳镜', 'ACC': '配饰',
}

# ── 品类代码 → CATEGORY_MAP 中文名（用于入库）──
CATEGORY_CODE_TO_NAME = {
    'TS': '短袖上衣', 'LS': '长袖上衣', 'SHIRT': '衬衣', 'TANK': '背心',
    'JK': '外套', 'PT': '长裤', 'SH': '短裤', 'SHOE': '鞋子',
    'BAG': '包', 'HAT': '帽子', 'SOCK': '袜子', 'SUN': '墨镜', 'ACC': '手部配饰',
}

def _find_item_thumb(clothing_id):
    """查找单品抠图缩略图路径（优先 items/ 目录，其次 wardrobe/enhanced/）"""
    import glob as _glob, os as _os
    # Search in all outfit items/ dirs first (newest first)
    outfits_dir = _os.path.join(PROJECT_DIR, 'outfits')
    if _os.path.exists(outfits_dir):
        for d in sorted(_os.listdir(outfits_dir), reverse=True):
            dp = _os.path.join(outfits_dir, d)
            if not _os.path.isdir(dp): continue
            items_dir = _os.path.join(dp, 'items')
            if not _os.path.exists(items_dir): continue
            pattern = _os.path.join(items_dir, f'{clothing_id}_*cutout*')
            matches = _glob.glob(pattern)
            if matches:
                p = _os.path.relpath(matches[0], PROJECT_DIR)
                mtime = int(_os.path.getmtime(matches[0]))
                return f'{p}?v={mtime}'
    # Fallback to wardrobe/enhanced/ — try cutout first, then thumb
    enhanced_dir = _os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
    if _os.path.exists(enhanced_dir):
        # Priority 1: cutout files
        pattern = _os.path.join(enhanced_dir, f'{clothing_id}_*cutout*')
        matches = _glob.glob(pattern)
        if matches:
            p = _os.path.relpath(matches[0], PROJECT_DIR)
            mtime = int(_os.path.getmtime(matches[0]))
            return f'{p}?v={mtime}'
        # Priority 2: generated thumbnails
        pattern = _os.path.join(enhanced_dir, f'{clothing_id}_thumb.*')
        matches = _glob.glob(pattern)
        if matches:
            p = _os.path.relpath(matches[0], PROJECT_DIR)
            mtime = int(_os.path.getmtime(matches[0]))
            return f'{p}?v={mtime}'
    return ''

# ── 任务管理器 ────────────────────────────────────────
class TaskManager:
    """线程安全的内存任务状态追踪"""
    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()
        self._ttl = 3600  # 1小时后过期

    def create(self):
        tid = str(int(time.time() * 1000))
        with self._lock:
            self._tasks[tid] = {
                'id': tid,
                'status': 'queued',
                'message': '排队中...',
                'result': '',
                'image_path': '',
                'image_url': '',
                'log': '',
                'created_at': time.time()
            }
        return tid

    def update(self, tid, **kwargs):
        with self._lock:
            if tid in self._tasks:
                self._tasks[tid].update(kwargs)

    def get(self, tid):
        with self._lock:
            task = self._tasks.get(tid)
            return dict(task) if task else None

    def cleanup(self):
        now = time.time()
        with self._lock:
            expired = [tid for tid, t in self._tasks.items()
                       if now - t['created_at'] > self._ttl]
            for tid in expired:
                del self._tasks[tid]

tasks = TaskManager()

# ── Server酱推送 ──────────────────────────────────────
def push_wechat(title, content=""):
    """推送到微信。自动将 GitHub Raw URL 转换为 jsDelivr CDN（国内访问更快）"""
    # 自动转换 GitHub Raw → jsDelivr CDN
    content = re.sub(
        r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)',
        r'https://cdn.jsdelivr.net/gh/\1/\2@\3/\4',
        content
    )
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    payload = {"title": title, "desp": content}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json;charset=utf-8'
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('code') == 0:
                log(f"推送成功: {title}")
                return result
            else:
                log(f"推送返回异常: {result.get('message', 'unknown')}", "WARN")
                return result
    except Exception as e:
        log(f"推送失败: {e}", "ERROR")
        return None

# ── 历史记录 ──────────────────────────────────────────
def load_history():
    """加载操作历史"""
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_history(entry):
    """追加一条历史记录（保留最近200条）"""
    history = load_history()
    history.insert(0, entry)
    if len(history) > 200:
        history = history[:200]
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

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
        return out if out else "✅ 执行完成（无文本输出）"
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

    if re.search(r'推荐|穿搭|穿什么|怎么穿|搭配|今天穿', msg):
        return ('recommend', msg)

    if len(msg) <= 20 and re.search(r'[一-鿿]', msg):
        return ('generate', msg)

    return ('unknown', msg)

HELP_TEXT = """📱 **穿搭助手 - 指令菜单**
> **推荐穿搭** — AI分析衣柜+天气推荐
> **生成 风格名** — 完整生图流程
> **同步** — 推送到GitHub
> **状态** — 查看文件状态
> **帮助** — 显示本菜单"""

# ── 管线核心 ──────────────────────────────────────────
def get_github_raw_url(file_path):
    rel = os.path.relpath(file_path, PROJECT_DIR)
    # 加时间戳避免浏览器/GitHub CDN 缓存旧图
    cache_buster = int(time.time())
    return f"https://raw.githubusercontent.com/wangyunkun123/fashion-style-advisor/main/{rel}?t={cache_buster}"

def find_latest_composite(date_str=None):
    """找到最新生成的排版合成图（严格限定当日，不跨 outfit 兜底）"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    today = date_str or time.strftime('%Y-%m-%d')
    candidates = []
    for d in os.listdir(outfit_base):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        if not d.startswith(today):
            continue
        for root, _, files in os.walk(dp):
            for f in files:
                if '_方案' in f and f.endswith('.jpg'):
                    fp = os.path.join(root, f)
                    candidates.append(fp)
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]

def get_banned_items():
    """获取因一星评价被禁用的单品清单 — 只有用户明确打一星才禁用"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    banned = []
    for d in os.listdir(outfit_base):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp):
            continue
        rating_file = os.path.join(dp, 'rating.json')
        if not os.path.exists(rating_file):
            continue
        try:
            with open(rating_file, 'r') as f:
                rating_data = json.load(f)
            if rating_data.get('rating') == 1:
                md = os.path.join(dp, 'outfit.md')
                if os.path.exists(md):
                    with open(md, 'r') as f:
                        content = f.read()
                    ids = re.findall(
                        r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                        content
                    )
                    banned.extend(ids)
        except:
            pass
    return list(set(banned))


def get_recent_outfit_items(limit=3):
    """获取最近 N 套穿搭中已使用的核心单品 ID（去重），用于避免重复推荐"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    today = time.strftime('%Y-%m-%d')
    recent = []  # [(date_label, [core_ids]), ...]
    for d in sorted(os.listdir(outfit_base), reverse=True):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        if d.startswith(today):
            continue  # 跳过今天的
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
            # 只关注核心品类（上衣/下装/鞋子）
            core = [i for i in ids if i.startswith(('TS-', 'LS-', 'TANK-', 'SHIRT-', 'JK-', 'SH-', 'PT-', 'SHOE-'))]
            if core:
                recent.append((d, core))
        except:
            pass
        if len(recent) >= limit:
            break
    return recent


CAT_EMOJI = {
    '上衣': '👕', '内搭': '👕', 'T恤': '👕', '短袖': '👕', '长袖': '👕',
    '衬衫': '👔', '外套': '🧥', '外层': '🧥', '外搭': '🧥', '夹克': '🧥',
    '下装': '👖', '裤子': '👖', '短裤': '🩳', '鞋子': '👟', '鞋': '👟',
    '包': '🎒', '帽子': '🧢', '墨镜': '🕶️', '配饰': '⌚', '手表': '⌚',
    '袜子': '🧦', '手串': '📿',
}

def format_outfit_summary(outfit_md_path):
    """从 outfit.md 提取穿搭摘要"""
    try:
        with open(outfit_md_path, 'r') as f:
            content = f.read()
        items = re.findall(
            r'^\|\s*([^|]+?)\s*\|\s*(?:\*\*)?(\w+-\d+)(?:\*\*)?\s*\|\s*([^|]+?)\s*(?:\||$)',
            content, re.MULTILINE
        )
        lines = []
        for cat, item_id, name in [(c.strip(), i, n.strip()) for c, i, n in items]:
            emoji = ''
            for key, val in CAT_EMOJI.items():
                if key in cat:
                    emoji = val
                    break
            lines.append(f"- {emoji} **{item_id}** {name}" if emoji else f"- **{item_id}** {name}")
        return '\n'.join(lines) if lines else ''
    except:
        return ''

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
        comment = (d.get('meta') or {}).get('claude_fit_comment', '') or ''
        filename = filename_map.get(cid, '')
        if cat not in cats:
            cats[cat] = []
        cats[cat].append({
            'id': cid, 'brand': brand, 'collection': collection,
            'color': color, 'styles': styles, 'comment': comment,
            'filename': filename,
        })

    # 按固定品类顺序输出
    cat_order = ['短袖上衣', '长袖上衣', '衬衣', '背心', '外套', '长裤', '短裤',
                 '鞋子', '帽子', '包', '墨镜', '手部配饰', '袜子']
    lines = []
    for cat in cat_order:
        if cat not in cats:
            continue
        lines.append(f'## {cat}')
        lines.append('| ID | 品牌·系列 | 颜色 | 场景标签 | 穿搭提示 |')
        lines.append('|-----|----------|------|---------|---------|')
        for it in cats[cat]:
            brand_str = it['brand']
            if it['collection']:
                brand_str += ' ' + it['collection']
            if not brand_str:
                brand_str = '—'
            # 截断品牌名避免表格过宽
            brand_str = brand_str[:28]
            # 场景标签：取风格修饰符中非身形相关的
            scene_tags = [s for s in it['styles']
                          if not any(kw in s for kw in ['增加', '显白', '显瘦', '拉长', '遮盖', '修饰', '无明显'])]
            styles_str = ' · '.join(scene_tags) if scene_tags else '—'
            comment_short = it['comment'][:55] if it['comment'] else '—'
            lines.append(f'| {it["id"]} | {brand_str} | {it["color"]} | {styles_str} | {comment_short} |')
        lines.append('')

    return '\n'.join(lines)

def call_doubao_chat(messages, max_tokens=4096, timeout=120):
    """调用 doubao-seed-2.0-code 聊天 API"""
    payload = json.dumps({
        'model': CHAT_MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.7,
    }).encode('utf-8')
    req = urllib.request.Request(API_CHAT_URL, data=payload, headers={
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': f'Bearer {API_KEY}',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        choice = result['choices'][0]
        msg = choice.get('message', {})
        content = msg.get('content', '')
        # doubao 部分模型可能把内容放在 reasoning_content 里
        if not content:
            reasoning = msg.get('reasoning_content', '')
            if reasoning:
                log(f"⚠️ content 为空, reasoning_content 前200字: {reasoning[:200]}", "WARN")
            # 记录完整响应用于排查
            finish = choice.get('finish_reason', 'unknown')
            log(f"⚠️ API 返回空 content, finish_reason={finish}, keys={list(msg.keys())}", "WARN")
        return content
    except Exception as e:
        log(f"豆包 API 调用失败: {e}", "ERROR")
        raise

def extract_json(text):
    """从 AI 回复中提取 JSON 对象"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass
    # 提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    # 提取 { ... } 块
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return None

# ── 衣橱入库辅助函数 ──────────────────────────────────

def _get_next_id(category_code):
    """扫描 wardrobe/tags/ 获取某品类下一个可用 ID"""
    existing = []
    tags_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
    if os.path.isdir(tags_dir):
        for fn in os.listdir(tags_dir):
            if fn.startswith(f'{category_code}-') and fn.endswith('.json'):
                m = re.search(rf'{category_code}-(\d+)', fn)
                if m:
                    existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    return f'{category_code}-{next_num:03d}'


def _append_to_wardrobe_md(cid, category_name, filename, tag_data):
    """向 wardrobe/服装档案.md 对应品类表格追加一行"""
    md_path = os.path.join(PROJECT_DIR, 'wardrobe', '服装档案.md')
    if not os.path.exists(md_path):
        log(f"服装档案.md 不存在", "WARN")
        return

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
        log(f"未找到品类 {category_name} 的表格位置", "WARN")
        return

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


def _register_new_item(cid, category_name):
    """注册新单品到 config/new_items.json"""
    new_path = os.path.join(PROJECT_DIR, 'config', 'new_items.json')
    items = {}
    if os.path.exists(new_path):
        try:
            with open(new_path, 'r') as f:
                items = json.load(f).get('items', {})
        except:
            pass
    items[cid] = {
        'added_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'category': category_name,
    }
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    with open(new_path, 'w') as f:
        json.dump({'items': items}, f, ensure_ascii=False, indent=2)


def _resize_image_for_api(image_path, max_size=1024):
    """将图片缩放到 max_size px，返回 JPEG bytes"""
    from PIL import Image as PILImage
    img = PILImage.open(image_path)
    if img.mode in ('RGBA', 'P', 'LA'):
        rgb = PILImage.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        rgb.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = rgb
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    # 缩放
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
    import io
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return buf.getvalue()


def _finalize_add_item(item_data):
    """执行完整的衣橱入库流程：复制图片 → 增强 → 写标签 → 更新档案 → 注册新单品"""
    cid = item_data.get('override_id') or item_data.get('suggested_id')
    if not cid:
        raise ValueError("缺少 clothing ID")

    category_name = item_data.get('category', '')
    category_code = item_data.get('category_code', '')

    # 获取品类目录名
    cat_info = CATEGORY_MAP.get(category_name, {})
    cat_dir = cat_info.get('dir', category_name)

    # 1. 复制原图到品类目录
    src_img = item_data.get('_temp_image_path', '')
    if not src_img or not os.path.exists(src_img):
        raise ValueError(f"临时图片不存在: {src_img}")

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    dest_dir = os.path.join(PROJECT_DIR, 'wardrobe', cat_dir)
    os.makedirs(dest_dir, exist_ok=True)
    dest_filename = f'Image_{timestamp}_{cid}.jpg'
    dest_path = os.path.join(dest_dir, dest_filename)
    shutil.copy2(src_img, dest_path)
    log(f"图片已复制: {dest_path}")

    # 2. 运行 enhance_clothing 增强管线
    try:
        from enhance_clothing import enhance_image
        cutout_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
        os.makedirs(cutout_dir, exist_ok=True)
        cutout_path = os.path.join(cutout_dir, f'{cid}_cutout.png')
        enhanced_jpg = os.path.join(cutout_dir, dest_filename)
        enhance_image(dest_path, cutout_path, enhanced_jpg)
        log(f"图片增强完成: {cid}")
    except Exception as e:
        log(f"图片增强失败（非致命）: {e}", "WARN")

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

    # 4. 写入标签 JSON
    tags_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
    os.makedirs(tags_dir, exist_ok=True)
    tag_path = os.path.join(tags_dir, f'{cid}.json')
    with open(tag_path, 'w', encoding='utf-8') as f:
        json.dump(tag_data, f, ensure_ascii=False, indent=2)
    log(f"标签已写入: {tag_path}")

    # 5. 追加到服装档案
    _append_to_wardrobe_md(cid, category_name, dest_filename, tag_data)

    # 6. 注册新单品
    _register_new_item(cid, category_name)

    # 7. 清理临时图片
    try:
        os.remove(src_img)
    except:
        pass

    return {
        'clothing_id': cid,
        'category': category_name,
        'name': f'{tag_data["brand"].get("name", "")} {tag_data["color"].get("hue_name", "")}{category_name}'.strip(),
    }


def _run_add_analysis(task_id, image_b64_list):
    """后台线程：调用豆包视觉 API 分析衣物图片"""
    try:
        tasks.update(task_id, status='running', message='正在保存图片...')

        # 1. 保存临时图片
        incoming_dir = os.path.join(PROJECT_DIR, 'wardrobe', '_incoming')
        os.makedirs(incoming_dir, exist_ok=True)
        temp_paths = []
        import base64 as _b64
        for i, b64_str in enumerate(image_b64_list):
            # 去掉可能的 data:image/...;base64, 前缀
            if ',' in b64_str and b64_str.startswith('data:'):
                b64_str = b64_str.split(',', 1)[1]
            img_bytes = _b64.b64decode(b64_str)
            temp_path = os.path.join(incoming_dir, f'img_{task_id}_{i}.jpg')
            with open(temp_path, 'wb') as f:
                f.write(img_bytes)
            temp_paths.append(temp_path)

        tasks.update(task_id, status='running', message=f'正在AI智能识别 {len(temp_paths)} 张图片...')

        # 2. 构建多模态 prompt
        content_blocks = []
        for i, tp in enumerate(temp_paths):
            # 缩放并编码图片
            jpg_bytes = _resize_image_for_api(tp)
            img_b64 = _b64.b64encode(jpg_bytes).decode('utf-8')
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
            content_blocks.append({
                "type": "text",
                "text": f"【图片 {i+1}】"
            })

        # 构建分析指令
        analysis_prompt = """你是一位专业的服装鉴定师。请仔细分析以上每张图片中的服装单品，输出严格的JSON格式结果。

对每件单品，按以下结构输出：
{
  "items": [
    {
      "category_code": "品类代码，必须是以下之一: TS(短袖T恤), LS(长袖上衣), SHIRT(衬衣), TANK(背心), JK(外套/夹克), PT(长裤), SH(短裤), SHOE(鞋子), BAG(包), HAT(帽子), SOCK(袜子), SUN(墨镜), ACC(配饰)",
      "category": "中文品类名，如 短袖上衣、衬衣、长裤",
      "color": {
        "hue_family": "暖色/冷色/中性色",
        "hue_name": "具体颜色名，如 藏青色、米白色、焦糖色、浅灰色",
        "saturation": "高饱和/中饱和/低饱和/无彩色",
        "lightness": "高明度/中明度/低明度",
        "is_neutral": false,
        "friendly_for_pale_skin": false
      },
      "brand": {
        "name": "品牌名，如识别到logo或标志性款式则填写，否则填'未知'",
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
        "fit": "合身/宽松/修身/oversize/直筒/锥形/阔腿",
        "shoulder_effect": "无特殊效果/增加肩宽/落肩/插肩",
        "torso_effect": "无特殊效果/显瘦/遮盖腹部/拉长比例",
        "length_ratio": "标准/短款/长款/及膝/过膝"
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
        "claude_fit_comment": "一句话总结版型与适配度"
      }
    }
  ]
}

注意：
- 严格只输出JSON，不要包含markdown代码块标记或解释文字
- 如果图片中没有服装单品，返回 {"items": []}
- 仔细区分品类：有领子扣子的是衬衣(SHIRT)，无领T恤根据袖长分短袖(TS)或长袖(LS)
- 品牌识别：看到明显logo或认识标志性款式的填品牌名，否则填"未知"，confidence相应降低
- 颜色描述要具体（如"浅灰蓝"而非"蓝色"）
- formality 1=极休闲(运动/居家) 2=休闲(日常) 3=中间(通勤) 4=正式(商务) 5=极正式(礼服)"""

        content_blocks.append({"type": "text", "text": analysis_prompt})

        messages = [{"role": "user", "content": content_blocks}]

        tasks.update(task_id, status='running', message='AI正在识别品类/颜色/品牌/面料...')

        # 3. 调用豆包视觉 API
        response_text = call_doubao_chat(messages, max_tokens=4096, timeout=180)

        if not response_text:
            tasks.update(task_id, status='error', message='AI 未返回结果，请重试')
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

        # 5. 为每件单品分配建议 ID 和补充信息
        for i, item in enumerate(items):
            cc = item.get('category_code', 'TS')
            # 验证品类代码
            if cc not in CATEGORY_CODE_TO_NAME:
                cc = 'TS'  # fallback
            item['category_code'] = cc
            item['category'] = CATEGORY_CODE_TO_NAME.get(cc, item.get('category', '短袖上衣'))
            item['suggested_id'] = _get_next_id(cc)
            item['_temp_image_path'] = temp_paths[i] if i < len(temp_paths) else ''
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

        # 保存临时分析结果
        analysis_path = os.path.join(incoming_dir, f'analysis_{task_id}.json')
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump({'items': items, '_task_id': task_id}, f, ensure_ascii=False, indent=2)

        tasks.update(task_id, status='done', message=f'识别完成，共 {len(items)} 件单品',
                     result=json.dumps({'items': items, '_task_id': task_id}, ensure_ascii=False))
        log(f"衣物分析完成: {task_id} → {len(items)} 件")

    except Exception as e:
        log(f"衣物分析失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        tasks.update(task_id, status='error', message=f'分析失败: {str(e)[:80]}')


def execute_outfit_plan(plan, today, style_hint):
    """根据 AI 方案创建目录、写入文件、复制图片"""
    wardrobe = parse_wardrobe()
    outfit_dir = os.path.join(PROJECT_DIR, 'outfits', f'{today}_{style_hint}')
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

## 风格关键词

{plan.get('keywords', style_hint)}
"""
    with open(os.path.join(outfit_dir, 'outfit.md'), 'w') as f:
        f.write(outfit_md)

    # ── 2. 写入豆包提示词.txt ──
    seedream_prompt = plan.get('seedream_prompt', '')
    with open(os.path.join(shengtu_dir, '豆包提示词.txt'), 'w') as f:
        f.write(seedream_prompt)

    # ── 3. 复制人物照片 ──
    person_photo = os.path.join(PROJECT_DIR, 'profile', 'photos', 'IMG_8493.jpg')
    if os.path.exists(person_photo):
        shutil.copy2(person_photo, os.path.join(shengtu_dir, '人物_IMG_8493.jpg'))

    # ── 4. 复制抠图到豆包生图/（用抠图做 Seedream 参考图，非原始照片）──
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
        cutout_src = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced', f'{item_id}_cutout.png')
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
        base = os.path.splitext(w['filename'])[0]
        cutout_name = f"{base}_cutout.png"
        cutout_src = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced', cutout_name)
        # 必须以 ID_ 前缀命名，composite_v2 的 find_img() 才能匹配
        dst_name = f"{item_id}_{cutout_name}"
        if os.path.exists(cutout_src):
            shutil.copy2(cutout_src, os.path.join(items_dir, dst_name))
        else:
            log(f"⚠️ 抠图不存在: {cutout_name}", "WARN")

    log(f"✅ 穿搭方案已创建: {outfit_dir}")
    return outfit_dir

OUTFIT_SYSTEM_PROMPT = """你是一位专攻亚洲男性穿搭的 AI 时尚顾问。用户会提供完整衣柜档案和场景需求，你需要推荐一套全新穿搭方案。

要求：
1. 仔细分析场景需求（运动/休闲/通勤/约会等）
2. **避开最近已穿单品**：prompt 中会列出 📌 最近已穿的核心单品，必须至少换掉上衣/下装/鞋子中的两件，给出有新鲜感的搭配
3. 所有单品 ID 必须从上方衣柜清单中选取，严禁编造不存在的 ID
4. 考虑颜色搭配、风格统一、体型修饰
5. 输出严格的 JSON 格式，不要包含任何其他文字

输出 JSON 格式：
{
  "weather_note": "天气描述",
  "style": "风格标签",
  "items": [
    {"category": "上衣", "id": "TS-xxx", "name": "单品描述", "color": "颜色"}
  ],
  "reasoning": "搭配理由（100-200字）",
  "color_logic": "配色逻辑",
  "keywords": "风格关键词",
  "seedream_prompt": "英文 Seedream 生图提示词，描述一个30岁亚洲男性179cm偏瘦白皙，穿着上述服装的全身照，高质量写真风格"
}

注意：
- 每套穿搭必须包含：上衣、下装、鞋子（三者缺一不可，这是硬性要求）
- 帽子、包、袜子、墨镜、配饰等根据场景酌情添加
- ACC-003 是 Apple Watch 表带套组（含米兰尼斯/回环/运动三款表带），推荐时需指定使用哪款表带
- seedream_prompt 必须是英文，详细描述服装细节和场景氛围
- 除用户明确标记为「一星差评禁用」的单品外，所有单品均可自由选用，同一单品可以出现在不同风格的穿搭中
- ⚠️ 场景匹配：运动场景（网球/跑步/健身）必须选功能运动鞋/跑鞋/网球鞋，不可选工装靴、帆布鞋、拖鞋、亚麻裤等非运动单品"""


def _detect_bline_from_hint(style_hint):
    """从 style_hint 检测 B线触发词"""
    try:
        from style_lab import detect_bline_trigger
        return detect_bline_trigger(style_hint)
    except ImportError:
        return False, False


def run_pipeline(style_hint, task_id=None):
    """完整生图管线: API穿搭分析 → Seedream生图 → 排版 → 推送"""
    is_bline, is_bold = _detect_bline_from_hint(style_hint)
    bline_tag = '🚀' if is_bold else ('🧪' if is_bline else '')
    log(f"🚀 管线启动: {style_hint} {'| B线'+('大胆' if is_bold else '微调') if is_bline else ''}")
    log_lines = []

    def progress(msg):
        log(f"📍 {msg}")
        if task_id:
            log_lines.append(msg)
            tasks.update(task_id, status='running', message=msg, log='\n'.join(log_lines))

    today = time.strftime('%Y-%m-%d')
    banned_items = get_banned_items()

    progress('🤖 Step 1/4: AI 分析穿搭方案...')

    # ── 构建衣柜上下文 ──
    wardrobe_summary = get_wardrobe_summary()

    system_prompt = OUTFIT_SYSTEM_PROMPT

    # 构建 prompt：无禁用单品时不提"禁用"概念，避免触发 AI 的"避免复用"本能
    ban_section = ''
    if banned_items:
        banned_str = '、'.join(banned_items)
        ban_section = f'\n🚫 一星差评禁用单品（严禁使用以下ID）: {banned_str}\n'

    # 获取最近已穿单品，避免重复推荐
    recent_outfits = get_recent_outfit_items(limit=3)
    recent_section = ''
    if recent_outfits:
        recent_lines = []
        for dir_name, ids in recent_outfits:
            label = dir_name.split('_', 1)[-1] if '_' in dir_name else dir_name[:10]
            recent_lines.append(f"  {label}: {'、'.join(ids)}")
        if recent_lines:
            recent_section = '\n📌 最近已穿（请避开这些核心单品，至少换掉上衣/下装/鞋子中的两件）:\n' + '\n'.join(recent_lines) + '\n'

    user_prompt = f"""今天是{today}，北京6月中旬天气（晴/多云，22-34°C）。

为「{style_hint}」推荐一套穿搭。{ban_section}{recent_section}
⚠️ 上衣、下装、鞋子三者缺一不可，每项必须从下方衣柜表格中选取真实的单品ID。
⚠️ 永远不要输出 UNAVAILABLE 作为ID。表格里每个ID都可用。

以下是完整衣柜档案：
---
{wardrobe_summary}
---

请输出 JSON 格式的穿搭方案。"""

    try:
        # 调用 API 获取穿搭方案（最多重试一次）
        plan = None
        for attempt in range(2):
            content = call_doubao_chat([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ], max_tokens=4096, timeout=180)

            plan = extract_json(content)
            if plan:
                break

            log(f"API 返回无法解析为 JSON (attempt {attempt+1}/2):\n{content[:500]}", "ERROR")
            if attempt == 0:
                # 重试：追加强制 JSON 指令
                user_prompt += "\n\n⚠️ 你的回复必须是纯 JSON，不要包含任何解释、markdown代码块标记或额外文字。以 { 开头，以 } 结尾。"
                progress('🔄 JSON解析失败，重试中...')
                time.sleep(2)  # 短暂冷却

        if not plan:
            raise ValueError("AI 穿搭分析返回格式异常，已重试1次仍失败，请稍后再试")

        # ⚠️ 硬拦截：检测 UNAVAILABLE
        items = plan.get('items', [])
        unavailable = [it for it in items if it.get('id', '') == 'UNAVAILABLE']
        if unavailable:
            log(f"⚠️ AI 返回了 UNAVAILABLE 单品，强制重试: {[it.get('category','') for it in unavailable]}", "WARN")
            progress('🔄 检测到 UNAVAILABLE，强制重试...')
            # 重试：追加极强指令
            user_prompt += "\n\n❌ 你上一次输出了 UNAVAILABLE。这是严重错误。衣柜中所有鞋子和裤子都可用。必须为上衣、下装、鞋子各选一个真实ID（如 SHOE-005、SH-003）。"
            content = call_doubao_chat([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ], max_tokens=4096, timeout=180)
            plan = extract_json(content)
            if not plan:
                raise ValueError("AI 穿搭分析返回格式异常（UNAVAILABLE重试后JSON解析失败）")
            items2 = plan.get('items', [])
            unavailable2 = [it for it in items2 if it.get('id', '') == 'UNAVAILABLE']
            if unavailable2:
                log(f"⚠️ 重试后仍返回 UNAVAILABLE: {[it.get('category','') for it in unavailable2]}", "ERROR")
                raise ValueError("AI 两次返回 UNAVAILABLE，请稍后重试")

        # 执行文件操作
        outfit_dir = execute_outfit_plan(plan, today, style_hint)
        progress(f'✅ 穿搭方案已创建')

        progress('🎨 Step 2/4: Seedream AI 生图中...')
        out2 = run_cli(['python3', 'tools/generate.py', style_hint], timeout=120)
        if out2:
            progress(f'✅ Seedream 生图完成\n{out2[:300]}')

        progress('🖼️ Step 3/4: 排版合成中...')
        out3 = run_cli(['python3', 'tools/composite_v2.py', outfit_dir], timeout=120)
        if out3:
            progress(f'✅ 排版完成\n{out3[:300]}')

        progress('📤 Step 4/4: 推送 GitHub...')
        composite = find_latest_composite(today)
        if composite and os.path.exists(composite):
            run_cli(['git', 'add', '-A'], timeout=30)
            run_cli(['git', 'commit', '-m', f'🎨 {style_hint} — 远程操控'], timeout=30)
            out4 = run_cli(['git', 'push'], timeout=60)
            if out4:
                progress(f'✅ 推送完成\n{out4[:300]}')

            github_url = get_github_raw_url(composite)
            comp_dir = os.path.dirname(composite)
            if '_方案' in os.path.basename(composite):
                comp_dir = os.path.dirname(comp_dir)
            outfit_md = os.path.join(comp_dir, 'outfit.md')
            summary = format_outfit_summary(outfit_md)
            # 控制台用简介版（清爽易读），微信按用户偏好推送
            result_text = f"👔 **{style_hint}**\n\n{summary}" if summary else f"👔 **{style_hint}**"

            # 微信推送：build_push 按用户偏好推送完整内容
            try:
                # --no-bline 防止 build_push 独立触发 B线替换 outfit 内容
                run_cli(['python3', 'tools/build_push.py', outfit_dir, '--rich', '--no-bline'], timeout=120)
                # build_push 可能生成了 _swatches.png 等新文件，提交并推送
                run_cli(['git', 'add', '-A'], timeout=10)
                run_cli(['git', 'commit', '-m', '📱 手机端穿搭推送'], timeout=10)
                run_cli(['git', 'push'], timeout=30)
            except Exception:
                content = f"![效果图]({github_url})\n\n"
                if summary:
                    content += f"**单品清单**\n{summary}\n\n"
                content += f"🔗 [GitHub](https://github.com/wangyunkun123/fashion-style-advisor)"
                push_wechat(f"👔 {style_hint}", content)

            # 重建原型HTML(使用最新数据)
            run_cli(['python3', 'tools/build_prototype.py'], timeout=30)

            # 更新控制台结果（与微信推送内容一致）
            if task_id:
                tasks.update(task_id, status='done', message='✅ 全部完成',
                             result=result_text, image_path=composite, image_url=github_url,
                             log='\n'.join(log_lines))

            # 保存历史记录
            save_history({
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'style': style_hint,
                'status': 'done',
                'image_url': github_url,
                'result': result_text,
            })
        else:
            if task_id:
                tasks.update(task_id, status='error', message='未找到排版图', log='\n'.join(log_lines))
            push_wechat(f"⚠️ {style_hint} 未找到效果图", "请检查 Mac 上的生成日志")
    except Exception as e:
        if task_id:
            tasks.update(task_id, status='error', message=str(e)[:200], log='\n'.join(log_lines))
        push_wechat(f"❌ {style_hint} 生成失败", str(e)[:500])

def _start_async_pipeline(action, extra):
    """启动异步穿搭管线，返回 task_id"""
    tid = tasks.create()
    style = extra if extra else "今日穿搭"
    threading.Thread(target=run_pipeline, args=(style, tid), daemon=True).start()
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

def _style_has_image(style_id):
    """检查风格是否有代表性图片"""
    img_path = os.path.join(PROJECT_DIR, 'styles_universal', style_id, 'representative.jpg')
    if os.path.exists(img_path):
        return f'/api/image?f=styles_universal/{style_id}/representative.jpg'
    return None

def _load_style_cards(include_universal=False):
    """加载风格卡片数据，返回 [{id, name_zh, name_en, description, category, has_encyclopedia, image}]"""
    styles = []
    # B-line styles
    styles_dir = os.path.join(PROJECT_DIR, 'styles')
    if os.path.isdir(styles_dir):
        for fn in sorted(os.listdir(styles_dir)):
            if not fn.endswith('.json'): continue
            fp = os.path.join(styles_dir, fn)
            try:
                with open(fp) as f:
                    d = json.load(f)
                sid = d.get('style_id', fn.replace('.json', ''))
                name_zh = d.get('name_zh', sid)
                styles.append({
                    'id': sid,
                    'name_zh': name_zh,
                    'name_en': d.get('name_en', ''),
                    'description': (d.get('description') or '')[:120],
                    'category': d.get('category', ''),
                    'has_encyclopedia': os.path.exists(os.path.join(
                        PROJECT_DIR, 'styles_universal', sid, 'encyclopedia.md')),
                    'image': _style_has_image(sid),
                })
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
                    # Extract Chinese name from markdown title: "# 日系 City Boy (Japanese City Boy)"
                    name_zh = first_line.lstrip('# ').split('(')[0].strip() if first_line.startswith('#') else d
                    styles.append({
                        'id': d,
                        'name_zh': name_zh,
                        'name_en': d.replace('_', ' ').title(),
                        'description': '',
                        'category': '',
                        'has_encyclopedia': True,
                        'image': _style_has_image(d),
                    })
                except: pass
    return styles


# ── 聊天界面 HTML（从 prototype/mobile-v2.html 加载）───
def _load_chat_html():
    """Load prototype HTML from file, with caching"""
    proto_path = os.path.join(PROJECT_DIR, "prototype", "mobile-v2.html")
    if os.path.exists(proto_path):
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

    # 检查今日是否已有 outfit
    existing = []
    for d in sorted(os.listdir(os.path.join(PROJECT_DIR, 'outfits')), reverse=True):
        if d.startswith(today):
            dp = os.path.join(PROJECT_DIR, 'outfits', d)
            md = os.path.join(dp, 'outfit.md')
            if os.path.exists(md):
                existing.append(d)
    existing.sort(reverse=True)

    if click_count == 1 and existing:
        # 首次点击且有今日穿搭 → 返回已生成的
        latest = existing[0]
        dp = os.path.join(PROJECT_DIR, 'outfits', latest)
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
        tid = _start_async_pipeline('recommend', extra)
        handler._json_resp(200, {"task_id": tid, "result": f'🔍 正在为你生成第 {click_count} 套今日穿搭…'})


def _handle_favorites(handler):
    """返回近10次三星好评穿搭"""
    favs = []
    outfits_dir = os.path.join(PROJECT_DIR, 'outfits')
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
    try:
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True,
                     text=True, cwd=PROJECT_DIR).stdout.strip()
        if h:
            import urllib.parse
            return f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/{urllib.parse.quote(rel_path, safe="/")}'
    except:
        pass
    return ''


# ── HTTP 处理器 ───────────────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)

        # 聊天面板
        if parsed.path in ('/', ''):
            self._html_resp(200, _load_chat_html())
            return

        # 兼容旧版 URL 触发
        if parsed.path == '/cmd':
            qs = parse_qs(parsed.query)
            msg = qs.get('t', [''])[0] or qs.get('text', [''])[0]
            if msg:
                action, extra = match_command(msg)
                if action in ('generate', 'recommend'):
                    tid = _start_async_pipeline(action, extra)
                    self._html_resp(200, REDIRECT_HTML)
                else:
                    result = execute_action(action, extra)
                    self._html_resp(200, f"<html><body style='font-family:sans-serif;padding:20px;background:#f5f0eb'><pre style='white-space:pre-wrap;font-size:15px'>{result}</pre><p><a href='/'>← 返回面板</a></p></body></html>")
            else:
                self._json_resp(400, {"error": "缺少 t 参数"})
            return

        # 推送偏好设置（从微信链接点击触发）
        if parsed.path == '/setpref':
            qs = parse_qs(parsed.query)
            mode = qs.get('mode', ['both'])[0]
            if mode in ('simple', 'rich', 'both'):
                pref_file = os.path.join(PROJECT_DIR, 'config', 'push_preference.json')
                os.makedirs(os.path.dirname(pref_file), exist_ok=True)
                import json as _json
                with open(pref_file, 'w') as f:
                    _json.dump({'mode': mode, 'updated': time.strftime('%Y-%m-%d %H:%M')}, f, ensure_ascii=False, indent=2)
                names = {'simple': '🅰️ 简洁版', 'rich': '🅱️ 时尚版', 'both': '🅰️+🅱️ 双版'}
                self._html_resp(200, f"<html><body style='font-family:sans-serif;padding:40px;text-align:center;background:#f5f0eb'><h2>✅ 推送偏好已设置</h2><p style='font-size:24px;margin:20px'>{names.get(mode, mode)}</p><p style='color:#999'>下次推送将按此偏好发送</p><p><a href='/'>返回控制面板</a></p></body></html>")
                log(f"推送偏好已设置为: {mode}")
            else:
                self._json_resp(400, {"error": "mode 必须是 simple/rich/both"})
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
            # 风格名映射
            try:
                with open(os.path.join(PROJECT_DIR, 'styles', f'{style_id}.json')) as f:
                    sj = json.load(f)
                    style_name = sj.get('name_zh', style_id)
            except:
                style_name = style_id
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
                # 注入返回按钮
                back_btn = '<button onclick="history.back()" style="position:fixed;top:16px;right:16px;background:#3a3028;color:#fff;border:none;padding:10px 18px;border-radius:20px;font-size:14px;cursor:pointer;z-index:999">← 返回</button>'
                html = html.replace('</body>', back_btn + '</body>')
                self._html_resp(200, html)
            else:
                self._html_resp(404, '<p>百科不存在</p>')
            return

        if parsed.path.startswith('/api/try/'):
            style_id = parsed.path.split('/api/try/')[-1].strip()
            if not style_id:
                self._json_resp(400, {"error": "缺少风格 ID"}); return
            try:
                tid = _start_async_pipeline('generate', style_id)
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
            outfit_dir = os.path.join(PROJECT_DIR, 'outfits', oid) if oid != 'unknown' else None
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
            task = tasks.get(tid)
            if task is None:
                self._json_resp(404, {"error": "task not found"})
                return
            tasks.cleanup()
            # 返回安全字段
            safe = {k: task[k] for k in ('id', 'status', 'message', 'result', 'image_path', 'image_url', 'log')}
            self._json_resp(200, safe)
            return

        # 本地图片服务
        if parsed.path == '/api/image':
            qs = parse_qs(parsed.query)
            file_rel = qs.get('f', [''])[0]
            if not file_rel:
                self._json_resp(400, {"error": "missing f"})
                return
            file_abs = os.path.normpath(os.path.join(PROJECT_DIR, file_rel))
            if not file_abs.startswith(PROJECT_DIR):
                self._json_resp(403, {"error": "forbidden"})
                return
            if not os.path.isfile(file_abs):
                self._json_resp(404, {"error": "file not found"})
                return
            ct = mimetypes.guess_type(file_abs)[0] or 'application/octet-stream'
            with open(file_abs, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=300')
            self.end_headers()
            self.wfile.write(data)
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
            tag_path = os.path.join(PROJECT_DIR, 'wardrobe', 'tags', f'{cid}.json')
            if not os.path.exists(tag_path):
                self._json_resp(404, {"error": f"item {cid} not found"})
                return
            try:
                with open(tag_path, 'r', encoding='utf-8') as f:
                    tag_data = json.load(f)
                tag_data['_thumb'] = _find_item_thumb(cid)
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
                wardrobe = load_all_clothing()
                items = []
                for cid, item in sorted(wardrobe.items()):
                    meta = item.get('meta', {})
                    brand = item.get('brand', {})
                    color = item.get('color', {})
                    cat_code = item.get('category_code', '?')
                    items.append({
                        'id': cid,
                        'name': meta.get('claude_fit_comment', item.get('category', ''))[:40],
                        'category': CATEGORY_NAMES.get(cat_code, cat_code),
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
                        'name': CATEGORY_NAMES.get(code, code),
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
                # 日常穿搭：用户风格指纹匹配的B线风格
                styles = _load_style_cards()
                self._json_resp(200, {'styles': styles[:8]})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/transform':
            try:
                # 改变自己：B线风格中随机选取
                styles = _load_style_cards()
                import random; random.shuffle(styles)
                self._json_resp(200, {'styles': styles[:6]})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/cross':
            try:
                # 大胆跨界：随机选两个B线风格
                styles = _load_style_cards()
                import random
                if len(styles) >= 2:
                    a, b = random.sample(styles, 2)
                    self._json_resp(200, {'styles': [a, b], 'fusion': f'{a["name_zh"]} × {b["name_zh"]}'})
                else:
                    self._json_resp(200, {'styles': styles[:2], 'fusion': ''})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/explore/trends':
            try:
                # 时尚圈子：全部风格
                styles = _load_style_cards(include_universal=True)
                self._json_resp(200, {'styles': styles, 'total': len(styles)})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        # ─── 我的页 API ───

        if parsed.path == '/api/pref':
            try:
                pref_path = os.path.join(PROJECT_DIR, 'config', 'push_preference.json')
                mode = 'both'
                if os.path.exists(pref_path):
                    with open(pref_path) as f:
                        pref = json.load(f)
                    mode = pref.get('mode', 'both')
                self._json_resp(200, {'mode': mode})
                return
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return

        if parsed.path == '/api/profile':
            try:
                analysis_path = os.path.join(PROJECT_DIR, 'profile', 'analysis.md')
                profile = {'height': '', 'weight': '', 'body_type': '', 'skin_tone': '', 'style_preference': '', 'occupation': ''}
                if os.path.exists(analysis_path):
                    with open(analysis_path) as f:
                        content = f.read()
                    for line in content.split('\n'):
                        line = line.strip()
                        if '身高' in line or 'height' in line.lower():
                            m = re.search(r'(\d{3})\s*cm', line)
                            if m: profile['height'] = m.group(1) + 'cm'
                        elif '体重' in line or 'weight' in line.lower():
                            m = re.search(r'(\d+)\s*kg', line)
                            if m: profile['weight'] = m.group(1) + 'kg'
                        elif '身形' in line or 'body' in line.lower():
                            for bt in ['偏瘦','标准','偏胖','H型','倒三角','矩形']:
                                if bt in line: profile['body_type'] = bt; break
                        elif '肤色' in line or 'skin' in line.lower():
                            for st in ['白皙','偏白','自然','小麦','偏黄']:
                                if st in line: profile['skin_tone'] = st; break
                        elif '风格' in line or 'style' in line.lower():
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: profile['style_preference'] = m.group(1).strip()[:60]
                        elif '职业' in line or 'occupation' in line.lower():
                            m = re.search(r'[：:]\s*(.+)', line)
                            if m: profile['occupation'] = m.group(1).strip()[:30]
                # Also load stats
                records = _load_recent_outfits(100)
                total_outfits = len(records)
                rated = [r for r in records if r.get('rating')]
                avg_rating = round(sum(r['rating'] for r in rated)/len(rated), 1) if rated else 0
                profile['total_outfits'] = total_outfits
                profile['rated_count'] = len(rated)
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
            for d in sorted(os.listdir(os.path.join(PROJECT_DIR, 'outfits')), reverse=True):
                if d.startswith(today):
                    dp = os.path.join(PROJECT_DIR, 'outfits', d)
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

        # 健康检查
        if parsed.path == '/health':
            self._json_resp(200, {"status": "ok", "service": "Fashion 穿搭助手", "time": time.strftime("%H:%M:%S")})
            return

        # 静态文件（图片等）
        from urllib.parse import unquote
        fp = os.path.normpath(os.path.join(PROJECT_DIR, unquote(parsed.path.lstrip('/'))))
        if os.path.isfile(fp) and fp.startswith(PROJECT_DIR):
            ext = os.path.splitext(fp)[1].lower()
            mime = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif','svg':'image/svg+xml'}.get(ext,'application/octet-stream')
            with open(fp,'rb') as f: data = f.read()
            self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',len(data)); self.end_headers()
            self.wfile.write(data)
            return

        self._json_resp(404, {"error": "not found"})

    def do_POST(self):
        """API 端点"""
        from urllib.parse import urlparse
        parsed = urlparse(self.path)

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
                tid = _start_async_pipeline(action, extra)
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
        elif parsed.path.startswith('/api/wardrobe/item/') and parsed.path.endswith('/delete'):
            # 彻底删除单品
            cid = parsed.path.split('/api/wardrobe/item/')[-1].replace('/delete', '').strip()
            tag_path = os.path.join(PROJECT_DIR, 'wardrobe', 'tags', f'{cid}.json')
            if not os.path.exists(tag_path):
                self._json_resp(404, {"error": f"item {cid} not found"})
                return
            try:
                import glob as _glob, shutil as _shutil
                deleted_files = []
                # 删除标签 JSON
                os.remove(tag_path)
                deleted_files.append(tag_path)
                # 删除 enhanced 目录下的图片
                enhanced_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
                if os.path.exists(enhanced_dir):
                    for pattern in [f'{cid}_cutout.*', f'{cid}_thumb.*']:
                        for fpath in _glob.glob(os.path.join(enhanced_dir, pattern)):
                            os.remove(fpath)
                            deleted_files.append(fpath)
                # 穿搭方案中的图片保留不删（已使用的历史记录）
                log(f"单品已删除: {cid} ({len(deleted_files)} files)")
                self._json_resp(200, {"ok": True, "deleted": len(deleted_files)})
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
            tag_path = os.path.join(PROJECT_DIR, 'wardrobe', 'tags', f'{cid}.json')
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
            enhanced_dir = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced')
            if os.path.exists(enhanced_dir):
                for pattern in [f'{cid}_cutout.*', f'{cid}_thumb.*']:
                    for fpath in _glob.glob(os.path.join(enhanced_dir, pattern)):
                        img = _PILImage.open(fpath)
                        w, h = img.size
                        img.close()
                        _transform_img(fpath, w, h)
            outfits_dir = os.path.join(PROJECT_DIR, 'outfits')
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
            log(f"图片变换: {cid} rotate={degrees} scale={scale} pan=({tx},{ty}) -> {transformed} files")
            self._json_resp(200, {"ok": True, "transformed": transformed})

        # ─── 衣橱添加入库 ───
        elif parsed.path == '/api/wardrobe/add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_resp(400, {"error": "invalid json"}); return
            images = data.get('images', [])
            if not images or not isinstance(images, list):
                self._json_resp(400, {"error": "请至少提供一张图片"}); return
            if len(images) > 10:
                self._json_resp(400, {"error": "最多10张图片"}); return
            tid = tasks.create()
            threading.Thread(target=_run_add_analysis, args=(tid, images), daemon=True).start()
            log(f"📸 衣橱添加: {tid} ({len(images)} 张图片)")
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
            # 加载临时分析结果以获取 _temp_image_path
            incoming_dir = os.path.join(PROJECT_DIR, 'wardrobe', '_incoming')
            analysis_path = os.path.join(incoming_dir, f'analysis_{task_id}.json')
            if os.path.exists(analysis_path):
                with open(analysis_path, 'r') as f:
                    saved = json.load(f)
                saved_items = {str(i): it for i, it in enumerate(saved.get('items', []))}
                for i, item in enumerate(items):
                    if not item.get('_temp_image_path'):
                        item['_temp_image_path'] = saved_items.get(str(i), {}).get('_temp_image_path', '')
            added = []
            errors = []
            for item in items:
                try:
                    result = _finalize_add_item(item)
                    added.append(result)
                except Exception as e:
                    log(f"入库失败: {e}", "ERROR")
                    errors.append(str(e))
            # 清理临时文件
            try:
                os.remove(analysis_path)
            except: pass
            self._json_resp(200, {"ok": True, "added": added, "errors": errors,
                                  "message": f'已添加 {len(added)} 件单品' + (f'，{len(errors)} 件失败' if errors else '')})

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

        else:
            self._json_resp(404, {"error": "not found"})

    def _json_resp(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_resp(self, code, html):
        body = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.end_headers()
        self.wfile.write(body)

    def _text_resp(self, code, text):
        body = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

    server = HTTPServer(('0.0.0.0', port), WebhookHandler)

    log("=" * 55)
    log("👔 Fashion 穿搭助手 — 交互式聊天")
    log(f"📡 服务: http://0.0.0.0:{port}")
    log(f"💬 面板: http://localhost:{port}/")

    push_wechat(
        "🟢 穿搭助手已上线",
        "手机打开控制面板即可对话操控\n\n"
        "• 输入指令即可交互\n"
        "• 1-2分钟后收到效果图"
    )
    log("📤 已推送上线通知")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("👋 服务已关闭")
        server.server_close()

if __name__ == '__main__':
    main()
