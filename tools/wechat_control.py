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

    # ── 4. 复制参考图到豆包生图/ ──
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
        src_dir = os.path.join(PROJECT_DIR, 'wardrobe', cat_info['dir'])
        src_file = os.path.join(src_dir, w['filename'])
        if not os.path.exists(src_file):
            # 尝试在其他目录找
            log(f"⚠️ 找不到源文件: {src_file}", "WARN")
            continue
        prefix = cat_info['prefix']
        dst_name = f"{prefix}_{w['filename']}"
        shutil.copy2(src_file, os.path.join(shengtu_dir, dst_name))

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

# ── 聊天界面 HTML ─────────────────────────────────────
CHAT_HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no,viewport-fit=cover">
<title>穿搭助手</title>
<style>
:root{--navy:#1e3a5f;--navy-light:#2a5080;--text:#1a2838;--sub:#6b7d94;
  --muted:#94a3b5;--border:#e6ecf3;--bg:#f8fafc;--white:#fff;
  --shadow:0 2px 8px rgba(30,58,95,.04);--radius:14px;--radius-sm:10px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#e2e6ec;display:flex;justify-content:center;min-height:100vh;-webkit-font-smoothing:antialiased}
#app{max-width:500px;width:100%;background:var(--bg);min-height:100vh;display:flex;flex-direction:column;position:relative;overflow:hidden;padding-bottom:80px}
.header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:var(--white);border-bottom:1px solid var(--border)}
.header h1{font-size:17px;font-weight:700;color:var(--text);letter-spacing:-.4px}
.header .avatar{width:34px;height:34px;background:var(--navy);border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600}
.segmented{display:flex;background:#eef2f7;border-radius:12px;padding:3px;margin:14px 20px;gap:2px}
.seg-btn{flex:1;text-align:center;padding:9px 0;font-size:13px;font-weight:600;color:var(--sub);border-radius:10px;cursor:pointer;transition:all .25s;-webkit-tap-highlight-color:transparent}
.seg-btn.active{background:var(--navy);color:#fff;box-shadow:0 2px 8px rgba(30,58,95,.25)}
.page{display:none;flex:1;flex-direction:column;overflow:hidden}
.page.active{display:flex}
.scroll-area{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 20px 16px}
.page-bottom{flex-shrink:0;padding:10px 20px;background:var(--bg);border-top:1px solid var(--border);z-index:5;display:flex;gap:0}
.page-bottom input{width:100%;padding:14px 18px;border:none;border-radius:var(--radius-sm);background:var(--white);font-size:14px;color:var(--text);box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);outline:none;-webkit-appearance:none}
.page-bottom input:focus{border-color:var(--navy);box-shadow:0 0 0 3px rgba(30,58,95,.08)}
.page-bottom input::placeholder{color:var(--muted)}

/* Hero card */
.hero-card{background:var(--white);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);margin:16px 0 14px;border:1px solid rgba(30,58,95,.05)}
.hero-img{width:100%;background:#f8fafc;overflow:hidden}
.hero-img img{width:100%;display:block}
.hero-body{padding:18px}
.hero-style{font-size:22px;font-weight:800;color:var(--text);letter-spacing:-.5px;margin-bottom:6px}
.hero-meta{font-size:12px;color:var(--sub);margin-bottom:14px}
/* Style tags */
.style-tags{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.style-tags span{font-size:11px;color:#fff;background:var(--navy);padding:4px 10px;border-radius:10px;font-weight:500}
/* Item grid — 3 cols */
.item-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.item-grid .item-row{flex-direction:column;align-items:flex-start;gap:4px;padding:8px;background:#f8fafc;border-radius:8px;border:none}
.item-grid .item-emoji{width:16px;height:16px}
.item-grid .item-cat{font-size:9px;width:auto}
.item-grid .item-id{font-size:8px}
.item-grid .item-name{font-size:9px;white-space:normal}
.item-thumb{width:28px;height:28px;object-fit:cover;border-radius:4px;cursor:pointer;flex-shrink:0;margin-left:auto}
/* Lightbox */
.lightbox{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.9);z-index:200;align-items:center;justify-content:center}
.lightbox.show{display:flex}
.lightbox img{max-width:90%;max-height:80%;object-fit:contain;border-radius:8px}
.lightbox .close{position:absolute;top:20px;right:24px;color:#fff;font-size:32px;cursor:pointer;z-index:201}
/* Palette strip */
.palette-strip{display:flex;align-items:center;gap:4px;padding-top:10px;border-top:1px solid var(--border)}
.pal-label{font-size:9px;color:var(--muted);font-weight:600;letter-spacing:.5px;margin-right:6px}
.pal-dot{width:16px;height:16px;border-radius:4px;border:1px solid var(--border);display:inline-block}

/* Item rows */
.item-list{display:flex;flex-direction:column}
.item-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f2f5f9}
.item-row:last-child{border-bottom:none}
.item-emoji{width:20px;height:20px;flex-shrink:0;color:var(--navy)}
.item-emoji svg{width:100%;height:100%;display:block}
.item-cat{font-size:11px;color:var(--muted);width:36px;flex-shrink:0;font-weight:500}
.item-id{font-size:10px;color:var(--sub);font-family:monospace;background:#f0f4f8;padding:3px 8px;border-radius:5px;flex-shrink:0}
.item-name{font-size:14px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}

/* Section */
.section-header{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:1.5px;margin:0 0 12px}

/* Mini rec cards — horizontal, square-ish */
.rec-cards{display:flex;gap:10px;margin-bottom:16px}
.rec-card{flex:1;min-width:0;background:var(--white);border-radius:var(--radius-sm);padding:14px 12px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;text-align:center}
.rec-card:active{transform:scale(.97)}
.rec-card{display:flex;flex-direction:column}
.rec-card .rc-style-name{font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px}
.rec-card .rc-items{font-size:11px;color:var(--sub);line-height:1.8}
.rec-card .rc-items div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rec-card .rc-detail{display:none;margin-top:6px;padding-top:6px;border-top:1px solid #f0f4f8}
.rec-card.open .rc-detail{display:block}
.rec-card .rc-detail .rci{font-size:11px;color:var(--sub);line-height:1.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rec-card .rc-arrow{text-align:center;font-size:9px;color:var(--muted);margin-top:6px;transition:transform .25s;cursor:pointer}
.rec-card.open .rc-arrow{transform:rotate(180deg)}
.rec-card.dashed{background:transparent;border:2px dashed #dce3ed;display:flex;align-items:center;justify-content:center}
.rec-card.dashed .dash-text{color:var(--muted);font-size:12px}

/* Tab Bar */
.tab-bar{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(30,58,95,.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:18px;padding:6px 8px;display:flex;gap:2px;z-index:100;box-shadow:0 8px 32px rgba(30,58,95,.25);max-width:440px;width:calc(100% - 32px)}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;cursor:pointer;padding:8px 0;border-radius:14px;transition:all .25s;-webkit-tap-highlight-color:transparent;min-width:56px}
.tab .t-icon{width:22px;height:22px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5);transition:color .25s}
.tab .t-icon svg{width:100%;height:100%}
.tab .t-label{font-size:10px;color:rgba(255,255,255,.55);font-weight:500;transition:color .25s}
.tab.active{background:rgba(255,255,255,.15)}
.tab.active .t-icon{color:#fff}
.tab.active .t-label{color:#fff;font-weight:600}

/* Favorites */
.fav-list{display:flex;flex-direction:column;gap:8px}
.fav-card{display:flex;align-items:center;gap:12px;background:var(--white);border-radius:var(--radius-sm);padding:14px 16px;box-shadow:var(--shadow);border:1px solid rgba(30,58,95,.04);cursor:pointer;flex-wrap:wrap}
.fav-card.expanded{flex-direction:column;align-items:stretch}
.fav-num{width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.fav-info{flex:1;min-width:0}
.fav-style{font-size:14px;font-weight:700;color:var(--text);margin-bottom:3px}
.fav-meta{font-size:11px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fav-expand{display:none}
.fav-card.expanded .fav-expand{display:block;width:100%;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
.fav-expand .item-grid{margin-bottom:0}
.fav-card .fav-arrow{font-size:9px;color:var(--muted);transition:transform .25s;flex-shrink:0}
.fav-card.expanded .fav-arrow{transform:rotate(180deg)}
.fav-card.expanded .h-thumb-sm{display:none}
.fav-card.filtered{display:none}
.h-char-img{width:80px;height:80px;border-radius:8px;object-fit:cover;flex-shrink:0;cursor:pointer}
.h-thumb-sm{width:42px;height:42px;border-radius:6px;object-fit:cover;flex-shrink:0;margin-left:8px}
.h-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.h-tags span{font-size:9px;background:var(--navy);color:#fff;padding:2px 7px;border-radius:8px;font-weight:500}
.h-expand-row{display:flex;gap:14px;align-items:flex-start}
.h-char-img-lg{width:170px;height:226px;border-radius:10px;object-fit:cover;flex-shrink:0;cursor:pointer}
/* 2x4 square grid */
.h-square-grid{flex:1;display:grid;grid-template-columns:repeat(2,1fr);gap:5px;align-content:start;grid-auto-rows:52px}
.h-square-grid .item-row{display:flex;flex-direction:column;gap:2px;padding:6px 5px;background:#f8fafc;border-radius:6px;cursor:pointer;position:relative;overflow:hidden;min-height:52px}
.h-square-grid .item-row .ir-top{display:flex;align-items:center;gap:3px}
.h-square-grid .item-row.clickable:active{background:#eef2f7}
.h-square-grid .item-emoji{width:16px;height:16px;flex-shrink:0}
.h-square-grid .item-id{font-size:7px;flex-shrink:0}
.h-square-grid .item-name{font-size:8px;line-height:1.3;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.h-square-grid .item-row.expanded{grid-row:span 2;padding:3px;z-index:2}
.h-square-grid .item-row.expanded .ir-top,.h-square-grid .item-row.expanded .item-name{display:none}
.h-square-grid .item-row.expanded .item-img{display:block}
.h-square-grid .item-img{display:none;width:100%;height:100%;object-fit:contain;position:absolute;top:0;left:0;padding:4px}
.h-square-grid .item-row.showing-img .item-img{display:block}
.placeholder{text-align:center;padding:60px 20px}
.placeholder .ph-icon{font-size:40px;margin-bottom:12px;opacity:.2}
.placeholder .ph-text{font-size:14px;line-height:1.7;color:var(--sub)}
</style></head><body><div id="app">

<!-- ═══ 推荐页 ═══ -->
<div class="page active" id="page-recommend">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented" id="seg-recommend">
<div class="seg-btn active" data-sub="today">今日推荐</div>
<div class="seg-btn" data-sub="history">历史推荐</div>
</div>

<!-- 今日推荐 -->
<div class="subpage active" id="sub-today" style="display:flex;flex-direction:column;flex:1;overflow:hidden">
<div class="scroll-area">
<div class="hero-card">
<div class="hero-img"><img src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/%E4%B8%8A%E8%BA%AB%E6%95%88%E6%9E%9C/%E4%B8%8A%E8%BA%AB%E6%95%88%E6%9E%9C_1.png" alt=""></div>
<div class="hero-body">
<div class="style-tags"><span>网球运动</span><span>清爽低饱和</span><span>专业功能</span><span>City Boy</span></div>
<div class="hero-style">清爽专业网球运动风</div>
<div class="hero-meta">2026/06/14 · 晴 · 22~34&deg;C · 紫外线 强</div>
<div class="item-list">
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m33.973 41.092-19.817.005c-.487 0-1.081.033-1.08-.653.001-.48.093-.979.13-1.458l.06-.924c.015-.159.044-.313.052-.474l.026-3.327c.009-.22.054-.435.059-.658l.013-.837c.008-.46.069-.945.108-1.407l.78-5.914-.572.396c-.463.28-1.051.457-1.588.51-.692.069-.88-.155-1.228-.673-.735-1.095-1.764-2.062-2.865-2.779l-1.535-.963c-.217-.141-.48-.313-.601-.55l-.06-.135c-.241-.746.476-1.249.926-1.697l.861-.925 1.92-2.543c.875-1.168 1.887-2.215 3.259-2.77 2.069-.84 2.069-1.09 3.513-2.794.116-.137.31-.265.398-.412.211-.358.511-1.048.655-1.427.299-.787.207-1.52 1.124-1.813.625-.038.757.207 1.27.513 2.489 1.483 5.558 1.542 7.985-.056.194-.127.392-.302.61-.384l.03-.01c1.556-.583 1.465 2.756 2.429 3.187.538.24.835.793 1.193 1.236a7.4 7.4 0 0 0 2.481 1.995c.36.174.741.312 1.084.52 1.036.625 1.803 1.592 2.568 2.506.537.642 3.26 3.975 4.036 4.165.353.086 1.166.989 1.211 1.308.107.766-.325 1.444-.752 2.032l-2.927 3.958c-.6.794-2.547-.404-3.081-.829-.818-.65-.351-.413-1.35-.694a5.1 5.1 0 0 1-1.624-.819l.964 8.17c.056.398.028.823.028 1.226v2.187c.002.344-.017.731.048 1.068l.226 2.118c.039.74-.316.82-.967.825M18.846 8.332c-.307.65-.335 1.301-.789 2.031l2.629 1.297c3.335 1.504 5.003.678 7.941-.754.129-.066.777-.34.824-.414-.293-.46-.484-.944-.658-1.46-.075-.223-.121-.518-.249-.714l-.017.014c-1.059.863-2.334 1.2-3.642 1.466-.328.067-.723.03-1.06.03-1.505 0-2.67-.303-4.045-.983zm-1.59 3.066-1.007 1.24a6.5 6.5 0 0 1-2.263 1.635c-.388.164-.812.265-1.188.446-1.132.546-1.982 1.83-2.703 2.833l-1.028 1.372c-.408.52-.859 1.018-1.312 1.498l-.456.463 1.694 1.107c1.47 1.029 2.059 1.704 3.074 3.097 1.051-.215 1.638-.838 2.494-1.365.15-.927.067-2.514-.166-3.391l-.21-.713c-.434-1.4.678-1.473.994-.928l.121.254c.191.432.26.915.393 1.365l.066.294c.25 1.412.19 2.27-.008 3.629l-.834 5.871-.31 3.479-.003 2.978c0 .091-.034.247-.01.33.42-.038.842-.03 1.262-.045l2.11-.095c.78-.037 1.902-.431 2.3.384l.02.035c.135.292-.164.655-.426.748-.233.083-.588.047-.838.053l-2.008.082c-.37.01-.718.078-1.09.087-.464.01-.955-.011-1.414.043l-.1 1.634 19.18.01-.115-1.338-.033-.33-3.866-.22c-.235-.013-.465-.06-.702-.07l-.991-.026c-.245-.013-.486-.055-.732-.061-.533-.013-1.498.18-1.368-.74.113-.795 1.403-.488 1.924-.471l1.5.014 3.52.255c.225.014.45.014.672.048l-.01-2.983-.486-5.031-.751-5.111c-.2-1.644-.134-2.928.404-4.543.072-.217.135-.49.299-.659.459-.471 1.133.033 1.052.61l-.414 1.458c-.129.44-.377 2.808 0 3.15.664.602 1.555 1.154 2.422 1.36l.01-.025c.631-1.511 3.284-3.452 4.637-4.189-1.3-1.067-2.302-2.4-3.362-3.69-.712-.868-1.455-1.848-2.478-2.368-1.403-.714-2.242-1.03-3.357-2.328-.308-.359-.581-.751-.899-1.101-5.077 2.572-6.37 3.31-11.818.687-.466-.225-.966-.434-1.392-.728M41.73 21.763c-1.81.911-3.583 2.181-4.675 3.923.26.242.556.446.852.642.333.199.663.359 1.043.445l2.861-3.898c.375-.573.485-.703-.08-1.113"/><path d="M24.123 37.854h-1.17c-.234 0-.609.05-.809-.064-.621-.356-.339-1.056.265-1.202.286-.015 1.669-.056 1.846.034l.027.014a.7.7 0 0 1 .29.262l.02.034a.618.618 0 0 1-.447.919z"/></svg></span><span class="item-cat">上衣</span><span class="item-id">TS-009</span><span class="item-name">Lululemon 运动短袖</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/TS-009_Image_20260610_0821_27_191_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m25.802 31.152-1.821-6.51-3.163 11.733-1.396 6.469c-.08.438-.126.895-.249 1.324-.756 2.627-3.486 2.998-5.875 2.812-1.27-.099-2.607-.356-3.589-1.238-1.234-1.108-1.15-2.156-1.013-3.624l1.04-12.071.75-9.92.322-4.596c.028-.221.076-.42.085-.648l.011-7.248c.004-.224.043-.442.045-.665l-.001-4.239c0-1.107.036-1.099 1.2-1.333 1.542-.309 3.15-.516 4.724-.54.934 0 1.936-.064 2.855.11.34.064.63.198.958.288 2.154.59 4.6.688 6.775.22l.968-.252C29.54.884 30.133.861 31.313.86l1.806.068c.652.054 1.31.108 1.957.219l.905.17c.769.135 1 .29 1.001 1.052l-.008 3.546c.006.423.047.736.066 1.13l.089 3.236c.002.395.075.77.077 1.164l.013 4.533 1.047 14.444.874 9.842c.025.245.033.496.071.74l.237 2.377c.28 1.56-1.3 2.938-2.67 3.348-2.448.734-6.535.541-7.787-2.115-.25-.53-.287-1.172-.404-1.741l-.939-4.588zM30.688 2.29c-.41.01-.851-.004-1.255.06-.657.102-1.31.33-2.01.441l-1.146.127c-1.557.158-3.512.084-5.065-.224-.543-.107-1.084-.273-1.629-.355-1.272-.191-3.72-.003-4.976.13.922.373 2.58.828 3.568 1.03 4.52 1.24 8.304.971 12.843-.208 1.028-.267 2.074-.439 3.061-.848zm-18.304.98-.02 2.633c.003.22-.002.46.043.676.354.065.72.067 1.076.107l1.842.284 4.637.938c1.866.318 3.771.495 5.663.335l4.422-.676 4.887-.98c.192-.027.387-.02.578-.048l.006-.709.001-1.54c0-.284.026-.604-.027-.882-.553.348-1.2.54-1.827.708l-4.22 1.05c-1.837.407-3.236.65-5.099.65l-1.37-.015c-1.234-.071-2.44-.277-3.643-.55l-5.084-1.326-1.716-.6c-.041-.018-.106-.056-.149-.056M35.55 7.977l-4.438.803c.087 1.497.632 3.061 1.713 4.131 1.018 1.011 1.654 1.17 2.944 1.44l-.073-6.372c-.054-.015-.092-.009-.146-.002m-23.167.058.016 6.273c1.309-.284 1.976-.509 2.95-1.568 1.085-1.319 1.32-2.354 1.55-3.944l-3.144-.584c-.455-.066-.912-.147-1.372-.177m5.863 1.024c-.039.21-.043.41-.066.62-.328 3.076-2.777 5.99-5.986 6.083L10.186 41.36c.26.108.567.15.842.2l2.323.29c.154.014.3.053.457.06l1.48.007c.384-.002.73-.02 1.108-.06l.901-.115c.329-.058.657-.11.973-.22.017-.225.07-.437.11-.658l.847-3.866 2.07-7.967 1.628-6.013c.197-.837.382-1.114.36-1.982l-.004-10.875c0-.13.024-.282-.002-.41-1.33-.082-2.642-.266-3.954-.49-.353-.06-.74-.096-1.08-.202m11.393.04-3.708.576c-.133.015-.264.044-.397.053l-.797.017c-.04.55-.011 1.121-.012 1.674l.004 10.365c.008.302.148.726.25 1.017l1 3.794c.008.035.02.063.031.097l.532 1.916a1 1 0 0 0 .031.109l2.062 7.688 1.093 5.117c1.192.209 1.957.333 3.165.358 1.976.065 3.144-.067 4.874-.97l-1.927-25.076c-3.587-.394-5.835-3.247-6.102-6.738a.3.3 0 0 0-.1.002m8.22 33.357c-1.511.835-2.912.86-4.562.858-.5-.001-1.01.017-1.509-.022l-1.757-.215c.089.72.318 1.23.881 1.696.847.675 1.888.883 2.949.884 1.397 0 3.807-.197 4.154-1.818l.009-.04c.05-.243.002-.47-.029-.71zm-27.844.375c-.056.273-.048.681.036.95l.045.131c.726 2.073 6.037 2.233 7.173.81.31-.322.668-1.14.67-1.593l-1.777.217c-.954.071-2.302.024-3.285-.075z"/></svg></span><span class="item-cat">下装</span><span class="item-id">SH-005</span><span class="item-name">Artengo 网球短裤</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SH-005_Image_20260610_0838_22_364_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m15 10.42 4.8-5.07" />
  <path d="M19 18h3" />
  <path d="M9.5 22 21.414 9.415A2 2 0 0 0 21.2 6.4l-5.61-4.208A1 1 0 0 0 14 3v2a2 2 0 0 1-1.394 1.906L8.677 8.053A1 1 0 0 0 8 9c-.155 6.393-2.082 9-4 9a2 2 0 0 0 0 4h14" /></svg></span><span class="item-cat">鞋子</span><span class="item-id">SHOE-005</span><span class="item-name">Nike 网球鞋</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SHOE-005_Image_20260610_0848_30_512_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16.236 35.938c-2.107-.513-3.827-1.38-5.435-2.873-.703-.652-1.36-1.366-2.242-1.78-1.763-.829-2.826.082-3.813-.377-1.461-.679-1.263-2.1-.255-3.096 1.993-1.967 6.174-2.487 8.79-2.473.236-3.702 3.61-7.03 6.631-8.802 2.384-1.398 4.74-1.915 7.523-1.86.976.02 1.56.036 2.521-.089-.193-1.668-1.1-1.697-1.235-2.26-.116-.479.157-.76.6-.863.773-.054 1.582 1.156 1.804 1.766l.104.352c.125.331.059.73.11 1.078l1.25.172c4.655.84 8.898 4.695 9.77 9.397l.156.767c.078.444.114.898.154 1.347l.05.442c.044.709.007 1.442.006 2.154l-.002.648c-.008 1.903-1.847 3.185-3.571 3.479l-1.266.151c-.488.064-1.198.103-1.717.133h-2.372c-.868-.072-.617-.053-1.494.242l-4.39 1.33c-4.1 1.235-7.305 2.036-11.677 1.015m14.175-19.853c-.488.108-1.004.18-1.478.339-1.594.535-3.05 1.878-3.936 3.265l-.21.362c.614.35 1.956.51 2.263 1.16l.014.027c.063.133.041.393-.013.529l-1.393 2.96 1.63.572 3.327 1.112c.617.208 1.24.49 1.873.634.05-.803.038-1.633-.009-2.435l-.125-1.799-.154-1.096c-.218-1.5-.58-3.023-1.166-4.425l-.344-.763c-.073-.148-.147-.335-.279-.442m-4.407.12c-3.386.124-6.388 1.718-8.691 4.188l-.956 1.092 1.496.535c.417.135.836.347 1.258.45l1.484-2.46c.667-1.1.56-1.186 1.73-.798.36.12.718.236 1.065.39l.617-.99a10.1 10.1 0 0 1 2.331-2.405c-.093-.002-.245-.022-.334-.001m6.121.028.453 1.111.645 2.159.356 1.743c.03.128.035.26.054.39l.274 3.151.008 7.104 1.875-.01c.18-.007.357-.04.535-.055l1.192-.095c1.083-.088 2.014-.135 2.946-.743 1.086-.822.841-1.84.834-3.053-.003-.446.011-.901-.019-1.347-.353-5.161-3.68-9.11-8.736-10.265-.136-.03-.287-.043-.417-.09M21.92 20.619l-1.428 2.333c.1.073.234.105.35.143l2.164.736c.347.115.712.224 1.047.37l.206.074 1.155-2.41zm-6.39 2.155a7.3 7.3 0 0 0-.865 2.72c.144.08.292.124.446.182l9.409 3.249 7.397 2.448.57.176c.02-.333.038-2.908-.01-2.952-.095-.084-.286-.093-.408-.131l-15.391-5.303c-.377-.133-.78-.234-1.148-.389m-3.037 4.045c-1.765.068-5.718.651-7.02 2.053-1.041 1.12.6.55 1.137.521 1.176-.064 2.458.334 3.399 1.044l1.694 1.468c2.783 2.421 5.71 3.157 9.298 2.964l1.965-.202c.485-.105.974-.168 1.456-.29l6.245-1.816L14.931 27.2c-.59-.219-.791-.373-1.443-.38z"/><path d="M37.059 30.254c-1.198-.108-1.247-1.172-.483-1.448.27-.098 1.297-.007 1.839-.138.218-.053.417-.152.634-.21.34-.05.729.104.883.421l.048.102c.462 1.146-2.359 1.264-2.921 1.273"/></svg></span><span class="item-cat">帽子</span><span class="item-id">HAT-004</span><span class="item-name">基础棒球帽</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/HAT-004_Image_20260610_0810_53_039_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 10a4 4 0 0 1-8 0" />
  <path d="M3.103 6.034h17.794" />
  <path d="M3.4 5.467a2 2 0 0 0-.4 1.2V20a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6.667a2 2 0 0 0-.4-1.2l-2-2.667A2 2 0 0 0 17 2H7a2 2 0 0 0-1.6.8z" /></svg></span><span class="item-cat">包</span><span class="item-id">BAG-007</span><span class="item-name">Wilson 网球桶包</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/BAG-007_Image_20260610_1043_55_563%20%E6%8B%B7%E8%B4%9D_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M25.13 41.235c-2.064.793-2.632 1.437-4.966 1.435-.334 0-.68.008-1.011-.026-5.854-.596-9.674-7.518-5.875-12.485 1.476-1.929 4.052-3.026 6.472-2.828l.047.005c.294-.434.629-.831.965-1.231l.247-.278c.116-.127.114-.13.139-.301l.455-3.586c.046-.314.128-.63.158-.946l.913-10.315.343-4.362c.052-.462.204-.743.679-.876l13.349-.002c.086.003.164.01.243.047l.025.012c.2.097.398.278.486.486l.012.035c.136.367-.024 1.03-.053 1.416l-1.891 19.167c-.076.912-.182.524.133 1.395l.228.786c.32 1.46.384 3.15-.167 4.564-.914 2.347-2.005 3.584-4.171 4.714zm-.52-34.236-.095.014c-.064.155-.047.415-.053.585l-.138 1.86c-.035.376-.106.768-.073 1.148l11.567-.001.1.012.332-3.61zm-.513 5.1c-.069.402-.072.81-.113 1.209l-.118 1.224c-.02.222-.057.44-.056.664l11.701-.008.283-3.07c-.716-.074-1.473-.029-2.194-.03l-8.85.002c-.216 0-.438-.012-.653.01m10.674 4.602-11.103.01c-.057.29-.034.602-.067.897l-.359 3.574c.168.147.37.235.567.334l1.115.497c1.462.542 2.96.905 4.515 1.043l.92.037c1.523.09 2.814.072 4.347-.086l.617-6.31zm-11.749 6.1-.412 3.047 2.617 1.64c.319.203.683.38.97.626.63.54-.007 1.547-.812 1.222-.698-.282-3.375-2.164-3.53-2.15-.007.001-.112.125-.126.142l-.662.867a17.8 17.8 0 0 1 2.967 4.88c.075.186.109.397-.006.57l-.02.033c-.23.35-.753.469-1.092.196-.253-.204-.364-.549-.496-.836l-.361-.723a19.7 19.7 0 0 0-2.046-3.024c-.202-.247-.175-.44-.521-.435l-.675.02c-.707.055-1.5.265-2.141.565.14.166.31.29.468.435l.664.647c1.105 1.134 2.188 2.43 2.957 3.825l.825 1.557c.159.363.328.717.458 1.091l.489 1.584c.218.752.134 1.371.285 2.014l5.318-2.438c.113-.05.261-.092.36-.166-.216-.52-.318-1.06-.396-1.615-.511-3.642.773-7.31 4.348-8.797a5.7 5.7 0 0 1 1.834-.44l.24-2.522a31.5 31.5 0 0 1-4.014.04l-2.293-.213c-1.848-.28-3.502-.88-5.197-1.642m11.394 5.826c-3.143.445-4.999 3.229-5 6.266 0 .251-.011.515.023.764l.28 1.48a.8.8 0 0 0 .096.254l.17-.073c.525-.262 1.056-.514 1.555-.82 1.86-1.138 3.419-3.154 3.476-5.408.019-.752-.16-1.739-.406-2.465a1.3 1.3 0 0 0-.194.002m-19.155 1.665c-1.508 1.437-2.408 3.83-1.72 5.881l.102.343c.933 2.548 3.124 4.424 5.91 4.573.602.049 1.19.034 1.789-.045.037-3.836-2.643-7.757-5.471-10.212-.196-.17-.446-.343-.61-.54"/></svg></span><span class="item-cat">袜子</span><span class="item-id">SOCK-006</span><span class="item-name">防滑底短袜</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/SOCK-006_Image_20260610_0807_48_614_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
<div class="item-row"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 10v2.2l1.6 1" />
  <path d="m16.13 7.66-.81-4.05a2 2 0 0 0-2-1.61h-2.68a2 2 0 0 0-2 1.61l-.78 4.05" />
  <path d="m7.88 16.36.8 4a2 2 0 0 0 2 1.61h2.72a2 2 0 0 0 2-1.61l.81-4.05" />
  <circle cx="12" cy="12" r="6" /></svg></span><span class="item-cat">配饰</span><span class="item-id">ACC-003</span><span class="item-name">Apple Watch 黑色运动</span><img class="item-thumb" src="../outfits/2026-06-14_%E6%89%93%E7%BD%91%E7%90%83%E7%A9%BF%E6%90%AD/items/ACC-003_Image_20260610_0840_55_238_cutout.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"></div>
</div>
<div class="palette-strip"><span class="pal-label">COLOR PALETTE</span><span class="pal-dot" style="background:#dcd7cd"></span><span class="pal-dot" style="background:#b4b4a0"></span><span class="pal-dot" style="background:#fff"></span><span class="pal-dot" style="background:#3c5032"></span><span class="pal-dot" style="background:#282826"></span></div>
</div></div>

<div class="section-header">其他推荐</div>
<div class="rec-cards">
<div class="rec-card" onclick="this.classList.toggle('open')"><div class="rc-style-name">夏日度假休闲</div><div class="rc-items"><div>TS-008 椰树印花短袖</div><div>SH-008 亚麻短裤</div><div>SHOE-002 复古训练鞋</div></div><div class="rc-detail"><div class="rci">HAT-004 棒球帽</div><div class="rci">SOCK-005 船袜</div></div><div class="rc-arrow">▾</div></div>
<div class="rec-card" onclick="this.classList.toggle('open')"><div class="rc-style-name">衬衫叠穿层次</div><div class="rc-items"><div>SHIRT-002 基础衬衫</div><div>TS-011 落肩T恤</div><div>SHOE-005 网球鞋</div></div><div class="rc-detail"><div class="rci">SH-004 休闲短裤</div><div class="rci">SOCK-005 船袜</div></div><div class="rc-arrow">▾</div></div>
<div class="rec-card dashed"><div class="dash-text">+ 换一批</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" id="today-input" placeholder="描述穿搭需求，如「今天要去约会」..." onkeydown="if(event.key==='Enter')sendOutfit()"><button style="width:44px;height:44px;background:var(--navy);color:#fff;border:none;border-radius:50%;font-size:16px;cursor:pointer;flex-shrink:0;margin-left:8px" onclick="sendOutfit()">▶</button></div>
</div>

<!-- 历史推荐 -->
<div class="subpage" id="sub-history" style="display:none;flex-direction:column;flex:1;overflow:hidden">
<div class="scroll-area" id="history-scroll">
<div class="section-header" style="margin-top:4px">今日穿搭</div>
<div class="fav-list" id="today-list" style="margin-bottom:16px"><div style="padding:16px;color:var(--muted);font-size:13px">今日暂无推荐</div></div>
<div class="section-header">历史最爱</div>
<div class="fav-list" id="fav-list" style="margin-bottom:16px"><div class="fav-card" onclick="this.classList.toggle('expanded')"><div class="fav-num">1</div><div class="fav-info"><div class="fav-style">清爽专业网球运动风 ⭐ ⭐ ⭐</div><div class="h-tags"><span>网球运动</span><span>速干透气</span><span>清爽显白</span><span>低饱和配色</span></div></div><img class="h-thumb-sm" src="../outfits/2026-06-14_打网球穿搭/上身效果/上身效果_1.png" loading="lazy"><div class="fav-arrow">▾</div><div class="fav-expand"><div class="h-expand-row"><img class="h-char-img-lg" src="../outfits/2026-06-14_打网球穿搭/上身效果/上身效果_1.png" onclick="event.stopPropagation();showImg(this.src)" loading="lazy"><div class="h-square-grid"><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m33.973 41.092-19.817.005c-.487 0-1.081.033-1.08-.653.001-.48.093-.979.13-1.458l.06-.924c.015-.159.044-.313.052-.474l.026-3.327c.009-.22.054-.435.059-.658l.013-.837c.008-.46.069-.945.108-1.407l.78-5.914-.572.396c-.463.28-1.051.457-1.588.51-.692.069-.88-.155-1.228-.673-.735-1.095-1.764-2.062-2.865-2.779l-1.535-.963c-.217-.141-.48-.313-.601-.55l-.06-.135c-.241-.746.476-1.249.926-1.697l.861-.925 1.92-2.543c.875-1.168 1.887-2.215 3.259-2.77 2.069-.84 2.069-1.09 3.513-2.794.116-.137.31-.265.398-.412.211-.358.511-1.048.655-1.427.299-.787.207-1.52 1.124-1.813.625-.038.757.207 1.27.513 2.489 1.483 5.558 1.542 7.985-.056.194-.127.392-.302.61-.384l.03-.01c1.556-.583 1.465 2.756 2.429 3.187.538.24.835.793 1.193 1.236a7.4 7.4 0 0 0 2.481 1.995c.36.174.741.312 1.084.52 1.036.625 1.803 1.592 2.568 2.506.537.642 3.26 3.975 4.036 4.165.353.086 1.166.989 1.211 1.308.107.766-.325 1.444-.752 2.032l-2.927 3.958c-.6.794-2.547-.404-3.081-.829-.818-.65-.351-.413-1.35-.694a5.1 5.1 0 0 1-1.624-.819l.964 8.17c.056.398.028.823.028 1.226v2.187c.002.344-.017.731.048 1.068l.226 2.118c.039.74-.316.82-.967.825M18.846 8.332c-.307.65-.335 1.301-.789 2.031l2.629 1.297c3.335 1.504 5.003.678 7.941-.754.129-.066.777-.34.824-.414-.293-.46-.484-.944-.658-1.46-.075-.223-.121-.518-.249-.714l-.017.014c-1.059.863-2.334 1.2-3.642 1.466-.328.067-.723.03-1.06.03-1.505 0-2.67-.303-4.045-.983zm-1.59 3.066-1.007 1.24a6.5 6.5 0 0 1-2.263 1.635c-.388.164-.812.265-1.188.446-1.132.546-1.982 1.83-2.703 2.833l-1.028 1.372c-.408.52-.859 1.018-1.312 1.498l-.456.463 1.694 1.107c1.47 1.029 2.059 1.704 3.074 3.097 1.051-.215 1.638-.838 2.494-1.365.15-.927.067-2.514-.166-3.391l-.21-.713c-.434-1.4.678-1.473.994-.928l.121.254c.191.432.26.915.393 1.365l.066.294c.25 1.412.19 2.27-.008 3.629l-.834 5.871-.31 3.479-.003 2.978c0 .091-.034.247-.01.33.42-.038.842-.03 1.262-.045l2.11-.095c.78-.037 1.902-.431 2.3.384l.02.035c.135.292-.164.655-.426.748-.233.083-.588.047-.838.053l-2.008.082c-.37.01-.718.078-1.09.087-.464.01-.955-.011-1.414.043l-.1 1.634 19.18.01-.115-1.338-.033-.33-3.866-.22c-.235-.013-.465-.06-.702-.07l-.991-.026c-.245-.013-.486-.055-.732-.061-.533-.013-1.498.18-1.368-.74.113-.795 1.403-.488 1.924-.471l1.5.014 3.52.255c.225.014.45.014.672.048l-.01-2.983-.486-5.031-.751-5.111c-.2-1.644-.134-2.928.404-4.543.072-.217.135-.49.299-.659.459-.471 1.133.033 1.052.61l-.414 1.458c-.129.44-.377 2.808 0 3.15.664.602 1.555 1.154 2.422 1.36l.01-.025c.631-1.511 3.284-3.452 4.637-4.189-1.3-1.067-2.302-2.4-3.362-3.69-.712-.868-1.455-1.848-2.478-2.368-1.403-.714-2.242-1.03-3.357-2.328-.308-.359-.581-.751-.899-1.101-5.077 2.572-6.37 3.31-11.818.687-.466-.225-.966-.434-1.392-.728M41.73 21.763c-1.81.911-3.583 2.181-4.675 3.923.26.242.556.446.852.642.333.199.663.359 1.043.445l2.861-3.898c.375-.573.485-.703-.08-1.113"/><path d="M24.123 37.854h-1.17c-.234 0-.609.05-.809-.064-.621-.356-.339-1.056.265-1.202.286-.015 1.669-.056 1.846.034l.027.014a.7.7 0 0 1 .29.262l.02.034a.618.618 0 0 1-.447.919z"/></svg></span><span class="item-id">TS-009</span></div><span class="item-name">Lululemon 科技运动短袖</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/TS-009_Image_20260610_0821_27_191_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"></span><span class="item-id">SH-005</span></div><span class="item-name">Decathlon 网球线运动短</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/SH-005_Image_20260610_0838_22_364_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m15 10.42 4.8-5.07" />
  <path d="M19 18h3" />
  <path d="M9.5 22 21.414 9.415A2 2 0 0 0 21.2 6.4l-5.61-4.208A1 1 0 0 0 14 3v2a2 2 0 0 1-1.394 1.906L8.677 8.053A1 1 0 0 0 8 9c-.155 6.393-2.082 9-4 9a2 2 0 0 0 0 4h14" /></svg></span><span class="item-id">SHOE-005</span></div><span class="item-name">Nike 网球鞋</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/SHOE-005_Image_20260610_0848_30_512_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16.236 35.938c-2.107-.513-3.827-1.38-5.435-2.873-.703-.652-1.36-1.366-2.242-1.78-1.763-.829-2.826.082-3.813-.377-1.461-.679-1.263-2.1-.255-3.096 1.993-1.967 6.174-2.487 8.79-2.473.236-3.702 3.61-7.03 6.631-8.802 2.384-1.398 4.74-1.915 7.523-1.86.976.02 1.56.036 2.521-.089-.193-1.668-1.1-1.697-1.235-2.26-.116-.479.157-.76.6-.863.773-.054 1.582 1.156 1.804 1.766l.104.352c.125.331.059.73.11 1.078l1.25.172c4.655.84 8.898 4.695 9.77 9.397l.156.767c.078.444.114.898.154 1.347l.05.442c.044.709.007 1.442.006 2.154l-.002.648c-.008 1.903-1.847 3.185-3.571 3.479l-1.266.151c-.488.064-1.198.103-1.717.133h-2.372c-.868-.072-.617-.053-1.494.242l-4.39 1.33c-4.1 1.235-7.305 2.036-11.677 1.015m14.175-19.853c-.488.108-1.004.18-1.478.339-1.594.535-3.05 1.878-3.936 3.265l-.21.362c.614.35 1.956.51 2.263 1.16l.014.027c.063.133.041.393-.013.529l-1.393 2.96 1.63.572 3.327 1.112c.617.208 1.24.49 1.873.634.05-.803.038-1.633-.009-2.435l-.125-1.799-.154-1.096c-.218-1.5-.58-3.023-1.166-4.425l-.344-.763c-.073-.148-.147-.335-.279-.442m-4.407.12c-3.386.124-6.388 1.718-8.691 4.188l-.956 1.092 1.496.535c.417.135.836.347 1.258.45l1.484-2.46c.667-1.1.56-1.186 1.73-.798.36.12.718.236 1.065.39l.617-.99a10.1 10.1 0 0 1 2.331-2.405c-.093-.002-.245-.022-.334-.001m6.121.028.453 1.111.645 2.159.356 1.743c.03.128.035.26.054.39l.274 3.151.008 7.104 1.875-.01c.18-.007.357-.04.535-.055l1.192-.095c1.083-.088 2.014-.135 2.946-.743 1.086-.822.841-1.84.834-3.053-.003-.446.011-.901-.019-1.347-.353-5.161-3.68-9.11-8.736-10.265-.136-.03-.287-.043-.417-.09M21.92 20.619l-1.428 2.333c.1.073.234.105.35.143l2.164.736c.347.115.712.224 1.047.37l.206.074 1.155-2.41zm-6.39 2.155a7.3 7.3 0 0 0-.865 2.72c.144.08.292.124.446.182l9.409 3.249 7.397 2.448.57.176c.02-.333.038-2.908-.01-2.952-.095-.084-.286-.093-.408-.131l-15.391-5.303c-.377-.133-.78-.234-1.148-.389m-3.037 4.045c-1.765.068-5.718.651-7.02 2.053-1.041 1.12.6.55 1.137.521 1.176-.064 2.458.334 3.399 1.044l1.694 1.468c2.783 2.421 5.71 3.157 9.298 2.964l1.965-.202c.485-.105.974-.168 1.456-.29l6.245-1.816L14.931 27.2c-.59-.219-.791-.373-1.443-.38z"/><path d="M37.059 30.254c-1.198-.108-1.247-1.172-.483-1.448.27-.098 1.297-.007 1.839-.138.218-.053.417-.152.634-.21.34-.05.729.104.883.421l.048.102c.462 1.146-2.359 1.264-2.921 1.273"/></svg></span><span class="item-id">HAT-004</span></div><span class="item-name">棒球帽</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/HAT-004_Image_20260610_0810_53_039_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 10a4 4 0 0 1-8 0" />
  <path d="M3.103 6.034h17.794" />
  <path d="M3.4 5.467a2 2 0 0 0-.4 1.2V20a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6.667a2 2 0 0 0-.4-1.2l-2-2.667A2 2 0 0 0 17 2H7a2 2 0 0 0-1.6.8z" /></svg></span><span class="item-id">BAG-007</span></div><span class="item-name">Wilson 网球桶包</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/BAG-007_Image_20260610_1043_55_563 拷贝_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M25.13 41.235c-2.064.793-2.632 1.437-4.966 1.435-.334 0-.68.008-1.011-.026-5.854-.596-9.674-7.518-5.875-12.485 1.476-1.929 4.052-3.026 6.472-2.828l.047.005c.294-.434.629-.831.965-1.231l.247-.278c.116-.127.114-.13.139-.301l.455-3.586c.046-.314.128-.63.158-.946l.913-10.315.343-4.362c.052-.462.204-.743.679-.876l13.349-.002c.086.003.164.01.243.047l.025.012c.2.097.398.278.486.486l.012.035c.136.367-.024 1.03-.053 1.416l-1.891 19.167c-.076.912-.182.524.133 1.395l.228.786c.32 1.46.384 3.15-.167 4.564-.914 2.347-2.005 3.584-4.171 4.714zm-.52-34.236-.095.014c-.064.155-.047.415-.053.585l-.138 1.86c-.035.376-.106.768-.073 1.148l11.567-.001.1.012.332-3.61zm-.513 5.1c-.069.402-.072.81-.113 1.209l-.118 1.224c-.02.222-.057.44-.056.664l11.701-.008.283-3.07c-.716-.074-1.473-.029-2.194-.03l-8.85.002c-.216 0-.438-.012-.653.01m10.674 4.602-11.103.01c-.057.29-.034.602-.067.897l-.359 3.574c.168.147.37.235.567.334l1.115.497c1.462.542 2.96.905 4.515 1.043l.92.037c1.523.09 2.814.072 4.347-.086l.617-6.31zm-11.749 6.1-.412 3.047 2.617 1.64c.319.203.683.38.97.626.63.54-.007 1.547-.812 1.222-.698-.282-3.375-2.164-3.53-2.15-.007.001-.112.125-.126.142l-.662.867a17.8 17.8 0 0 1 2.967 4.88c.075.186.109.397-.006.57l-.02.033c-.23.35-.753.469-1.092.196-.253-.204-.364-.549-.496-.836l-.361-.723a19.7 19.7 0 0 0-2.046-3.024c-.202-.247-.175-.44-.521-.435l-.675.02c-.707.055-1.5.265-2.141.565.14.166.31.29.468.435l.664.647c1.105 1.134 2.188 2.43 2.957 3.825l.825 1.557c.159.363.328.717.458 1.091l.489 1.584c.218.752.134 1.371.285 2.014l5.318-2.438c.113-.05.261-.092.36-.166-.216-.52-.318-1.06-.396-1.615-.511-3.642.773-7.31 4.348-8.797a5.7 5.7 0 0 1 1.834-.44l.24-2.522a31.5 31.5 0 0 1-4.014.04l-2.293-.213c-1.848-.28-3.502-.88-5.197-1.642m11.394 5.826c-3.143.445-4.999 3.229-5 6.266 0 .251-.011.515.023.764l.28 1.48a.8.8 0 0 0 .096.254l.17-.073c.525-.262 1.056-.514 1.555-.82 1.86-1.138 3.419-3.154 3.476-5.408.019-.752-.16-1.739-.406-2.465a1.3 1.3 0 0 0-.194.002m-19.155 1.665c-1.508 1.437-2.408 3.83-1.72 5.881l.102.343c.933 2.548 3.124 4.424 5.91 4.573.602.049 1.19.034 1.789-.045.037-3.836-2.643-7.757-5.471-10.212-.196-.17-.446-.343-.61-.54"/></svg></span><span class="item-id">SOCK-006</span></div><span class="item-name">防滑底短袜</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/SOCK-006_Image_20260610_0807_48_614_cutout.png" loading="lazy"></div><div class="item-row clickable" onclick="event.stopPropagation();this.classList.toggle('expanded')"><div class="ir-top"><span class="item-emoji"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 10v2.2l1.6 1" />
  <path d="m16.13 7.66-.81-4.05a2 2 0 0 0-2-1.61h-2.68a2 2 0 0 0-2 1.61l-.78 4.05" />
  <path d="m7.88 16.36.8 4a2 2 0 0 0 2 1.61h2.72a2 2 0 0 0 2-1.61l.81-4.05" />
  <circle cx="12" cy="12" r="6" /></svg></span><span class="item-id">ACC-003</span></div><span class="item-name">Apple Watch 运动表带</span><img class="item-img" src="../outfits/2026-06-14_打网球穿搭/items/ACC-003_Image_20260610_0840_55_238_cutout.png" loading="lazy"></div></div></div></div></div></div>
</div>
<div class="page-bottom"><input type="text" id="history-search" placeholder="搜索历史推荐..." oninput="filterHistory()"></div>
</div>
</div>

<!-- ═══ 探索页 ═══ -->
<div class="page" id="page-explore">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented"><div class="seg-btn active">日常穿搭</div><div class="seg-btn">改变自己</div><div class="seg-btn">大胆跨界</div><div class="seg-btn">时尚圈子</div></div>
<div class="scroll-area"><div class="placeholder"><div class="ph-icon">&#x1f9ea;</div><div class="ph-text">日常微调探索<br>以你最近的风格为基点<br>小幅延伸出新搭配</div></div></div>
<div class="page-bottom"><input type="text" placeholder="描述你想尝试的风格..."></div>
</div>

<!-- ═══ 衣橱页 ═══ -->
<div class="page" id="page-wardrobe">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented"><div class="seg-btn active">我的衣橱</div><div class="seg-btn">月度报告</div><div class="seg-btn">冷门单品</div><div class="seg-btn">购买建议</div></div>
<div class="scroll-area">
<div style="display:flex;gap:10px;margin:16px 0 12px">
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:var(--navy)">76</div><div style="font-size:10px;color:var(--muted)">总件数</div></div>
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:#c4523c">26%</div><div style="font-size:10px;color:var(--muted)">利用率</div></div>
<div style="flex:1;background:var(--white);border-radius:10px;padding:14px 10px;text-align:center;box-shadow:var(--shadow)"><div style="font-size:26px;font-weight:800;color:#c4523c">8</div><div style="font-size:10px;color:var(--muted)">超标</div></div>
</div>
</div>
<div class="page-bottom"><input type="text" placeholder="搜索衣服..."></div>
</div>

<!-- ═══ 添加页 ═══ -->
<div class="page" id="page-add">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="segmented"><div class="seg-btn active">拍照</div><div class="seg-btn">上传图片</div></div>
<div class="scroll-area"><div class="placeholder"><div class="ph-icon">&#x1f4f8;</div><div class="ph-text">拍照识别衣服<br>对准衣服拍照<br>AI 自动识别品牌品类颜色</div></div></div>
<div class="page-bottom" style="display:flex;gap:10px">
<button style="flex:1;padding:14px;background:var(--navy);color:#fff;border:none;border-radius:24px;font-size:15px;font-weight:600">确认分析</button>
<button style="flex:1;padding:14px;background:#eef2f7;color:var(--sub);border:none;border-radius:24px;font-size:15px">取消重选</button>
</div>
</div>

<!-- ═══ 我的页 ═══ -->
<div class="page" id="page-profile">
<div class="header"><h1>穿搭助手</h1><div class="avatar">K</div></div>
<div class="scroll-area"><div class="placeholder" style="padding:80px 20px"><div class="ph-icon">&#x1f464;</div><div class="ph-text">个人中心<br>即将上线<br>推送偏好 · 穿搭统计 · 身形档案</div></div></div>
</div>

</div>

<!-- Tab Bar -->
<div class="lightbox" id="lightbox" onclick="this.classList.remove('show')"><span class="close">&times;</span><img id="lightbox-img" src=""></div>

<div class="tab-bar" id="tab-bar">
<div class="tab active" data-page="rec"><div class="t-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z" /></svg></div><span class="t-label">推荐</span></div>
<div class="tab" data-page="exp"><div class="t-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" />
  <line x1="22" x2="18" y1="12" y2="12" />
  <line x1="6" x2="2" y1="12" y2="12" />
  <line x1="12" x2="12" y1="6" y2="2" />
  <line x1="12" x2="12" y1="22" y2="18" /></svg></div><span class="t-label">探索</span></div>
<div class="tab" data-page="wrd"><div class="t-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1" />
  <rect width="7" height="7" x="14" y="3" rx="1" />
  <rect width="7" height="7" x="14" y="14" rx="1" />
  <rect width="7" height="7" x="3" y="14" rx="1" /></svg></div><span class="t-label">衣橱</span></div>
<div class="tab" data-page="add"><div class="t-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z" />
  <circle cx="12" cy="13" r="3" /></svg></div><span class="t-label">添加</span></div>
<div class="tab" data-page="me"><div class="t-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
  <circle cx="12" cy="7" r="4" /></svg></div><span class="t-label">我的</span></div>
</div>

<script>
function showImg(src){document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').classList.add('show')}
function showItemImg(el){var t=el.dataset.thumb;if(t)showImg(t)}
var currentPage='recommend';
document.querySelectorAll('#tab-bar .tab').forEach(function(tab){tab.addEventListener('click',function(){var p=this.dataset.page;if(p===currentPage)return;currentPage=p;document.querySelectorAll('#tab-bar .tab').forEach(function(t){t.classList.remove('active')});this.classList.add('active');document.querySelectorAll('.page').forEach(function(pg){pg.classList.remove('active')});document.getElementById('page-'+p).classList.add('active')})});
document.querySelectorAll('.segmented').forEach(function(seg){seg.addEventListener('click',function(e){var b=e.target.closest('.seg-btn');if(!b)return;seg.querySelectorAll('.seg-btn').forEach(function(s){s.classList.remove('active')});b.classList.add('active');var sub=b.dataset.sub;if(!sub)return;var parent=seg.parentElement;parent.querySelectorAll('.subpage').forEach(function(sp){sp.style.display='none'});var t=document.getElementById('sub-'+sub);if(t)t.style.display='flex'})});
function filterHistory(){var q=document.getElementById('history-search').value.toLowerCase();document.querySelectorAll('#today-list .fav-card, #fav-list .fav-card').forEach(function(c){var t=c.textContent.toLowerCase();c.classList.toggle('filtered',q&&!t.includes(q))})}
function sendOutfit(){var inp=document.getElementById('today-input');var msg=inp.value.trim()||'推荐穿搭';inp.value='';inp.placeholder='生成中...';fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})}).then(r=>r.json()).then(d=>{if(d.task_id){inp.placeholder='任务进行中...';pollTask(d.task_id)}else{inp.placeholder=d.result||'已发送';setTimeout(function(){location.reload()},2000)}}).catch(function(e){inp.placeholder='网络错误: '+e.message})}
function pollTask(tid){fetch('/api/task/'+tid).then(r=>r.json()).then(function(d){if(d.status==='done'){location.reload()}else if(d.status==='error'){document.getElementById('today-input').placeholder='生成失败:'+(d.message||'')}else{document.getElementById('today-input').placeholder='生成中...';setTimeout(function(){pollTask(tid)},3000)}})}
</script>
</body></html>
"""

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
        import subprocess as _sp
        h = _sp.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True,
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
            self._html_resp(200, CHAT_HTML)
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

        # 健康检查
        if parsed.path == '/health':
            self._json_resp(200, {"status": "ok", "service": "Fashion 穿搭助手", "time": time.strftime("%H:%M:%S")})
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
