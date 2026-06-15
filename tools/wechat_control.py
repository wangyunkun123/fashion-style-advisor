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
CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="穿搭助手">
<title>👔 穿搭助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;background:#f5f0eb;height:100vh;display:flex;justify-content:center}
#app{max-width:500px;width:100%;height:100vh;display:flex;flex-direction:column;background:#f5f0eb}
.header{background:linear-gradient(135deg,#3a3028,#5c4d3c);color:#fff;padding:14px 18px;text-align:center;flex-shrink:0}
.header h1{font-size:19px;font-weight:600;letter-spacing:1px}
.header .sub{font-size:11px;opacity:.6;letter-spacing:1px}
#messages{flex:1;overflow-y:auto;padding:12px;-webkit-overflow-scrolling:touch;display:flex;flex-direction:column;gap:10px}
.msg{max-width:82%;padding:11px 14px;border-radius:16px;font-size:15px;line-height:1.5;word-break:break-word;animation:fadeIn .2s}
.msg.assistant{align-self:flex-start;background:#fff;border:1px solid #e0d8d0;border-bottom-left-radius:4px;color:#3a3028}
.msg.user{align-self:flex-end;background:#3a3028;color:#fff;border-bottom-right-radius:4px}
.msg img{max-width:100%;border-radius:8px;margin:8px 0;border:1px solid #e0d8d0}
.msg .spinner{display:inline-block;width:14px;height:14px;border:2px solid #d0c8bc;border-top-color:#3a3028;border-radius:50%;animation:spin .8s linear infinite;margin-right:6px;vertical-align:-2px}
.msg .bar{height:3px;background:#e0d8d0;border-radius:2px;margin-top:8px;overflow:hidden}
.msg .bar div{height:100%;background:linear-gradient(90deg,#3a3028,#8b7a64);border-radius:2px;animation:progress 2s ease-in-out infinite;width:40%}
.msg.error{border-color:#e8c0c0;background:#fff5f5}
.input-bar{flex-shrink:0;background:#fff;border-top:1px solid #e0d8d0;padding:0;padding-bottom:env(safe-area-inset-bottom)}
.input-row{display:flex;gap:8px;padding:8px 12px}
.input-row input{flex:1;padding:11px 14px;border:1px solid #d0c8bc;border-radius:20px;font-size:15px;background:#f8f6f3;outline:none;-webkit-appearance:none}
.input-row input:focus{border-color:#8b7a64}
.input-row button{width:44px;height:44px;background:#3a3028;color:#fff;border:none;border-radius:50%;font-size:18px;cursor:pointer;flex-shrink:0;-webkit-tap-highlight-color:transparent}
/* ── Tab Bar ── */
.tab-bar{display:flex;justify-content:space-around;background:#fff;border-top:1px solid #e8e2da;padding:8px 0 10px;padding-bottom:calc(10px + env(safe-area-inset-bottom))}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;cursor:pointer;padding:4px 0;-webkit-tap-highlight-color:transparent;position:relative;transition:opacity .15s}
.tab:active{opacity:.6}
.tab .t-icon{font-size:22px;line-height:1.2}
.tab .t-label{font-size:10px;color:#8b7a64;font-weight:500;letter-spacing:.5px}
.tab.active .t-label{color:#3a3028;font-weight:700}
/* ── 子菜单 ── */
.submenu{position:fixed;background:#fff;border:1px solid #d0c8bc;border-radius:14px;box-shadow:0 4px 20px rgba(0,0,0,.16);padding:4px 0;z-index:99;min-width:130px;animation:fadeIn .15s}
.submenu-item{padding:12px 20px;font-size:15px;white-space:nowrap;cursor:pointer;color:#3a3028;-webkit-tap-highlight-color:transparent}
.submenu-item:active{background:#f5f0eb}
.submenu-item+.submenu-item{border-top:1px solid #f0ece6}
.submenu-mask{position:fixed;top:0;left:0;right:0;bottom:0;z-index:98;background:rgba(0,0,0,.05)}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes progress{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
/* ── 衣橱面板 ── */
#wardrobe-panel{flex-shrink:0;background:#f8f6f3;border-top:1px solid #e0d8d0;max-height:55vh;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0}
.wardrobe-header{position:sticky;top:0;background:#3a3028;color:#fff;padding:10px 18px;font-size:15px;font-weight:600;display:flex;justify-content:space-between;align-items:center;z-index:1}
.wardrobe-header span{cursor:pointer;font-size:18px;opacity:.7}
.w-section{padding:12px 14px}
.w-section+.w-section{border-top:1px solid #e8e2da}
.w-section-title{font-size:12px;color:#9b8c7c;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-weight:600}
.w-stats{display:flex;gap:8px;margin-bottom:8px}
.w-stat{flex:1;background:#fff;border-radius:10px;padding:10px;text-align:center;border:1px solid #e8e2da}
.w-stat .num{font-size:22px;font-weight:700;color:#3a3028}
.w-stat .label{font-size:10px;color:#9b8c7c;margin-top:2px}
.w-row{display:flex;align-items:center;justify-content:space-between;padding:5px 0;font-size:13px;border-bottom:1px solid #f0ece6}
.w-row:last-child{border-bottom:none}
.w-row .name{color:#3a3028;flex:1}
.w-row .bar-wrap{flex:1;height:6px;background:#e8e2da;border-radius:3px;margin:0 8px;overflow:hidden}
.w-row .bar-fill{height:100%;border-radius:3px}
.w-row .val{font-size:11px;color:#9b8c7c;min-width:40px;text-align:right}
.w-tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}
.w-tag.warn{background:#fff3e0;color:#e65100}
.w-tag.danger{background:#ffebee;color:#c62828}
.w-tag.ok{background:#e8f5e9;color:#2e7d32}
.w-suggest{background:#fff;border:1px solid #e8e2da;border-radius:10px;padding:10px 12px;margin-bottom:6px}
.w-suggest .pri{font-size:10px;font-weight:600;margin-bottom:3px}
.w-suggest .item{font-size:14px;font-weight:600;color:#3a3028}
.w-suggest .reason{font-size:11px;color:#9b8c7c;margin-top:3px}
.w-subcat{margin-bottom:4px;font-size:12px}
.w-loading{text-align:center;padding:30px;color:#9b8c7c;font-size:13px}
</style>
</head>
<body>
<div id="app">
<div class="header"><h1>👔 穿搭助手</h1><div class="sub">AI STYLE ADVISOR</div></div>
<div id="messages"></div>
<div id="wardrobe-panel" style="display:none;flex-shrink:0;background:#f8f6f3;border-top:1px solid #e0d8d0;max-height:55vh;overflow-y:auto;-webkit-overflow-scrolling:touch">
<div class="wardrobe-header">👔 我的衣橱 <span onclick="toggleWardrobe()">✕</span></div>
<div id="wardrobe-content"><div class="w-loading">加载中...</div></div>
</div>
<div class="input-bar">
<div class="input-row">
<input type="text" id="input" placeholder="输入穿搭需求…" autocomplete="off" enterkeyhint="send">
<button id="sendBtn">▶</button>
</div>
<div class="tab-bar">
<div class="tab" id="tab-recommend" onclick="showRecommendMenu(event)"><span class="t-icon">👕</span><span class="t-label">推荐</span></div>
<div class="tab" id="tab-explore" onclick="showExploreMenu(event)"><span class="t-icon">💡</span><span class="t-label">探索</span></div>
<div class="tab" id="tab-wardrobe" onclick="toggleWardrobe()"><span class="t-icon">🏠</span><span class="t-label">衣橱</span></div>
<div class="tab" onclick="addClothes()"><span class="t-icon">📸</span><span class="t-label">添加</span></div>
<div class="tab" id="tab-settings" onclick="showSettingsMenu(event)"><span class="t-icon">👤</span><span class="t-label">我的</span></div>
</div>
</div>
</div>
<script>
const msgs=document.getElementById('messages');
const input=document.getElementById('input');
const POLL_INTERVAL=2000,MAX_POLLS=90;

function addMsg(role,html){const d=document.createElement('div');d.className='msg '+role;d.innerHTML=html;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d}

function addLoading(){return addMsg('assistant','<span class="spinner"></span>处理中...<div class="bar"><div></div></div>')}

function send(){
var t=input.value.trim();if(!t)return;
addMsg('user',esc(t));input.value='';
fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t})})
.then(r=>r.json()).then(d=>{
if(d.action==='wardrobe'){toggleWardrobe();addMsg('assistant',esc(d.result).replace(/\n/g,'<br>'))}
else if(d.task_id){var el=addLoading();pollTask(d.task_id,el,0)}
else if(d.result){addMsg('assistant',esc(d.result).replace(/\n/g,'<br>'))}
else{addMsg('assistant error',esc(JSON.stringify(d)))}
}).catch(e=>{addMsg('assistant error','网络错误: '+e.message)})
}

function pollTask(tid,el,n){
fetch('/api/task/'+tid).then(r=>r.json()).then(d=>{
if(!d){el.innerHTML='⚠️ 任务已过期';return}
if(d.status==='done'){
var h=esc(d.result||'完成').replace(/\n/g,'<br>');
if(d.log)h+='<details style="margin-top:8px;font-size:12px;color:#9b8c7c"><summary>📋 操作日志</summary><pre style="white-space:pre-wrap;margin-top:4px">'+esc(d.log)+'</pre></details>';
if(d.image_url)h+='<br><img src="'+esc(d.image_url)+'" style="max-width:100%;border-radius:8px;margin-top:8px">';
el.innerHTML=h;el.querySelector('.bar')?.remove();
}else if(d.status==='error'){
var eh=esc(d.message);if(d.log)eh+='<details style="margin-top:8px;font-size:12px;color:#9b8c7c"><summary>📋 操作日志</summary><pre style="white-space:pre-wrap;margin-top:4px">'+esc(d.log)+'</pre></details>';
el.innerHTML='❌ '+eh;el.classList.add('error');el.querySelector('.bar')?.remove();
}else{
var mh='<span class="spinner"></span>'+esc(d.message||'处理中...');
if(d.log)mh+='<div style="font-size:12px;color:#9b8c7c;margin-top:6px;line-height:1.4">'+esc(d.log).replace(/\n/g,'<br>')+'</div>';
el.innerHTML=mh+'<div class="bar"><div></div></div>';
if(n<MAX_POLLS)setTimeout(function(){pollTask(tid,el,n+1)},POLL_INTERVAL);
else el.innerHTML='⏰ 任务超时，请查看微信通知';
}
}).catch(function(){if(n<MAX_POLLS)setTimeout(function(){pollTask(tid,el,n+1)},POLL_INTERVAL)})
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

document.getElementById('sendBtn').onclick=send;
input.addEventListener('keydown',function(e){if(e.key==='Enter')send()});

// ── Tab Bar 点击 ──
document.querySelector('.tab-bar').addEventListener('click',function(e){
var c=e.target.closest('.tab');if(!c)return;
var cmd=c.dataset.cmd;
if(cmd){input.value=cmd;send();c.blur()}
});

// ── 通用子菜单 ──
function _popMenu(btn,items){
var old=document.querySelector('.submenu');if(old)old.remove();
var mask=document.querySelector('.submenu-mask');if(mask)mask.remove();
var m=document.createElement('div');m.className='submenu';
var h='';items.forEach(function(it){h+='<div class="submenu-item" data-cmd="'+esc(it.cmd)+'">'+it.label+'</div>'});
m.innerHTML=h;
document.body.appendChild(m);
var maskEl=document.createElement('div');maskEl.className='submenu-mask';
maskEl.onclick=function(){m.remove();maskEl.remove()};
document.body.appendChild(maskEl);
// 定位：在按钮上方居中
var rect=btn.getBoundingClientRect();
m.style.left='50%';
m.style.transform='translateX(-50%)';
m.style.bottom=(window.innerHeight-rect.top+6)+'px';
// 绑定点击
m.querySelectorAll('.submenu-item').forEach(function(it){
it.onclick=function(ev){ev.stopPropagation();input.value=this.dataset.cmd;send();m.remove();maskEl.remove()}
});
}

// ── 推荐子菜单 ──
function showRecommendMenu(e){e.stopPropagation();_popMenu(e.currentTarget,[{cmd:'今日穿搭',label:'🎯 今日穿搭'},{cmd:'历史推荐',label:'⭐ 历史推荐'}]);}

// ── 探索子菜单 ──
function showExploreMenu(e){e.stopPropagation();_popMenu(e.currentTarget,[{cmd:'探索 日系',label:'🧪 微调探索'},{cmd:'大胆 混搭',label:'🚀 大胆混搭'}]);}

// ── 设置子菜单 ──
function showSettingsMenu(e){e.stopPropagation();_popMenu(e.currentTarget,[{cmd:'同步',label:'📤 同步GitHub'},{cmd:'状态',label:'📊 项目状态'},{cmd:'帮助',label:'❓ 使用帮助'}]);}

// ── 添加新衣服 ──
function addClothes(){
addMsg('assistant','➕ <b>添加新衣服</b><br><br>流程：<br>1. 把衣服图片放入 <code>wardrobe/</code> 目录<br>2. 在此输入 <b>添加新衣服</b> 触发入库<br>3. AI 自动：视觉识别 → 网络搜索品牌 → 生成标签<br><br>⚠️ 请先在电脑端操作');
}

// 欢迎消息
addMsg('assistant','👋 你好！我是穿搭助手<br><br>点击底部 <b>推荐</b> 获取今日穿搭<br>点击 <b>衣橱</b> 查看衣柜分析<br>或直接在输入框描述需求…');

// ── 衣橱面板 ──
var wardrobePanel=document.getElementById('wardrobe-panel');
var wardrobeContent=document.getElementById('wardrobe-content');
var wardrobeOpen=false;

function toggleWardrobe(){
wardrobeOpen=!wardrobeOpen;
wardrobePanel.style.display=wardrobeOpen?'block':'none';
if(wardrobeOpen&&wardrobeContent.querySelector('.w-loading')){
loadWardrobe();
}
}

function loadWardrobe(){
fetch('/api/wardrobe').then(function(r){return r.json()}).then(function(d){
var h='';

// 概览
var meta=d.metadata||{};
var util=d.utilization||{};
var gaps=d.category_gaps||{};
var brands=d.brand_diversity||{};
var ps=d.purchase_suggestions||[];
var shoes=d.subcategory_gaps||{};
var keyUnused=util.key_unused||[];

// 卡片：概览统计
var overstock=0,gap=0,healthy=0;
for(var k in gaps){var s=gaps[k];if(s.status==='overstock')overstock++;else if(s.status==='gap')gap++;else healthy++;}
h+='<div class="w-section"><div class="w-section-title">📊 概览</div>';
h+='<div class="w-stats">';
h+='<div class="w-stat"><div class="num">'+meta.total_items+'</div><div class="label">总件数</div></div>';
h+='<div class="w-stat"><div class="num" style="color:'+(util.utilization_rate<.3?'#c62828':'#2e7d32')+'">'+(util.utilization_rate*100).toFixed(0)+'%</div><div class="label">利用率</div></div>';
h+='<div class="w-stat"><div class="num" style="color:#c62828">'+overstock+'</div><div class="label">超标品类</div></div>';
h+='<div class="w-stat"><div class="num" style="color:#e65100">'+gap+'</div><div class="label">缺口品类</div></div>';
h+='</div></div>';

// 品类健康（超标+缺口）
h+='<div class="w-section"><div class="w-section-title">📦 品类健康</div>';
var order=['TS','LS','SHIRT','TANK','JK','PT','SH','SHOE','BAG','HAT','SOCK','SUN','ACC'];
var names={'TS':'短袖','LS':'长袖','SHIRT':'衬衫','TANK':'背心','JK':'外套','PT':'长裤','SH':'短裤','SHOE':'鞋子','BAG':'包','HAT':'帽子','SOCK':'袜子','SUN':'墨镜','ACC':'配饰'};
for(var i=0;i<order.length;i++){
var code=order[i],g=gaps[code];
if(!g)continue;
var tag='';
if(g.status==='overstock')tag='<span class="w-tag danger">超标+'+g.diff+'</span>';
else if(g.status==='gap')tag='<span class="w-tag warn">缺-'+g.diff+'</span>';
else tag='<span class="w-tag ok">✓</span>';
var maxW=15,pct=g.actual/maxW*100;
var barColor=g.status==='overstock'?'#c62828':(g.status==='gap'?'#e65100':'#7cb342');
h+='<div class="w-row"><span class="name">'+(names[code]||code)+'</span>';
h+='<div class="bar-wrap"><div class="bar-fill" style="width:'+Math.min(pct,100)+'%;background:'+barColor+'"></div></div>';
h+='<span class="val">'+g.actual+'件 '+tag+'</span></div>';
}
h+='</div>';

// 购买建议（高+中各1条）
h+='<div class="w-section"><div class="w-section-title">🛒 购买建议</div>';
var shown=0;
for(var i=0;i<ps.length&&shown<3;i++){
var p=ps[i];
var priEmoji=p.priority==='high'?'🔴':(p.priority==='medium'?'🟡':'🟢');
var priLabel=p.priority==='high'?'优先':(p.priority==='medium'?'可选':'建议');
h+='<div class="w-suggest"><div class="pri">'+priEmoji+' '+priLabel+'</div>';
h+='<div class="item">'+esc(p.item)+'</div>';
h+='<div class="reason">💡 '+esc(p.reason)+'</div></div>';
shown++;
}
h+='</div>';

// 鞋柜速览
var shoeSubs=shoes.SHOE||{};
h+='<div class="w-section"><div class="w-section-title">👟 鞋柜速览</div>';
for(var sub in shoeSubs){
var ids=shoeSubs[sub]||[];
var icon=ids.length?'✅':'⚠️';
var color=ids.length?'#2e7d32':'#c62828';
h+='<div class="w-subcat" style="color:'+color+'">'+icon+' '+sub+'：'+(ids.length?ids.join('、'):'缺失')+'</div>';
}
h+='</div>';

// 闲置关键单品
if(keyUnused&&keyUnused.length){
h+='<div class="w-section"><div class="w-section-title">💤 沉睡好货</div>';
for(var i=0;i<Math.min(keyUnused.length,4);i++){
var ku=keyUnused[i];
h+='<div class="w-row"><span class="name"><b>'+ku.id+'</b></span><span style="font-size:11px;color:#9b8c7c">'+(ku.name||'').substring(0,30)+'</span></div>';
}
h+='<div style="font-size:11px;color:#9b8c7c;margin-top:4px">以上是好品质但从未穿过的单品，给它们一次机会吧 ✨</div>';
h+='</div>';
}

wardrobeContent.innerHTML=h;
}).catch(function(e){
wardrobeContent.innerHTML='<div class="w-loading" style="color:#c62828">⚠️ 加载失败: '+e.message+'</div>';
});
}

</script>
</body>
</html>"""

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
