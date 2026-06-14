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
    """找到最新生成的排版合成图（优先当日，按文件修改时间）"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    today = date_str or time.strftime('%Y-%m-%d')
    candidates = []
    for d in os.listdir(outfit_base):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        for root, _, files in os.walk(dp):
            for f in files:
                if '_方案' in f and f.endswith('.jpg'):
                    fp = os.path.join(root, f)
                    candidates.append(fp)
    if not candidates:
        return None
    # 优先当日合成图
    today_candidates = [c for c in candidates if today in c]
    if today_candidates:
        today_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return today_candidates[0]
    # 兜底：全局最新（但打印警告）
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    log(f"⚠️ 未找到当日排版图，使用最近期: {os.path.basename(candidates[0])}", "WARN")
    return candidates[0]

def get_todays_used_items():
    """获取今日已用单品清单"""
    today = time.strftime('%Y-%m-%d')
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    used = []
    for d in sorted(os.listdir(outfit_base)):
        if not d.startswith(today):
            continue
        md = os.path.join(outfit_base, d, 'outfit.md')
        if os.path.exists(md):
            with open(md, 'r') as f:
                content = f.read()
            ids = re.findall(r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+)', content)
            used.extend(ids)
    return list(set(used))

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
    """获取衣柜摘要文本（给 AI 的上下文）"""
    wardrobe_md = os.path.join(PROJECT_DIR, 'wardrobe', '服装档案.md')
    with open(wardrobe_md, 'r') as f:
        content = f.read()
    # 去掉 frontmatter 和说明段落，保留表格
    lines = content.split('\n')
    summary = []
    in_table_section = False
    for line in lines:
        if line.startswith('## ') or line.startswith('|'):
            in_table_section = True
        if line.startswith('## 服装档案总结'):
            break
        if in_table_section:
            summary.append(line)
    return '\n'.join(summary)

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
        content = result['choices'][0]['message']['content']
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
2. 避开用户已使用的单品
3. 考虑颜色搭配、风格统一、体型修饰
4. 输出严格的 JSON 格式，不要包含任何其他文字

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
- 必须包含上衣和下装
- 鞋子、帽子、包、袜子、墨镜等配饰根据场景酌情添加
- seedream_prompt 必须是英文，详细描述服装细节和场景氛围"""


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
    used_items = get_todays_used_items()
    used_str = '、'.join(used_items) if used_items else '无'

    progress('🤖 Step 1/4: AI 分析穿搭方案...')

    # ── 构建衣柜上下文 ──
    wardrobe_summary = get_wardrobe_summary()

    system_prompt = OUTFIT_SYSTEM_PROMPT

    user_prompt = f"""今天是{today}，北京6月中旬天气（晴/多云，22-34°C）。

为「{style_hint}」推荐一套全新穿搭。

❌ 今日已使用以下单品，严禁再次使用: {used_str}
必须从未使用的单品中选择，确保上衣、下装、鞋子不与今日任何一套重复。

以下是完整衣柜档案：
---
{wardrobe_summary}
---

请输出 JSON 格式的穿搭方案。"""

    try:
        # 调用 API 获取穿搭方案
        content = call_doubao_chat([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ], max_tokens=4096, timeout=180)

        plan = extract_json(content)
        if not plan:
            log(f"API 返回无法解析为 JSON:\n{content[:500]}", "ERROR")
            raise ValueError("AI 穿搭分析返回格式异常，请重试")

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
            result_text = f"👔 **{style_hint}**\n\n{summary}" if summary else f"👔 **{style_hint}**"

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

            # 微信推送：统一走 build_push 时尚版（B线由状态计数器自动触发）
            try:
                run_cli(['python3', 'tools/build_push.py', outfit_dir, '--rich'], timeout=120)
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
.input-bar{flex-shrink:0;background:#fff;border-top:1px solid #e0d8d0;padding:8px 12px;padding-bottom:max(8px,env(safe-area-inset-bottom))}
.chips{display:flex;gap:8px;overflow-x:auto;padding-bottom:8px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex-shrink:0;padding:7px 14px;border:1px solid #d0c8bc;border-radius:16px;background:#fdfbf8;color:#5c4d3c;font-size:13px;cursor:pointer;white-space:nowrap;-webkit-tap-highlight-color:transparent}
.chip:active{background:#f0ebe0;border-color:#b8a88c}
.input-row{display:flex;gap:8px}
.input-row input{flex:1;padding:11px 14px;border:1px solid #d0c8bc;border-radius:20px;font-size:15px;background:#f8f6f3;outline:none;-webkit-appearance:none}
.input-row input:focus{border-color:#8b7a64}
.input-row button{width:44px;height:44px;background:#3a3028;color:#fff;border:none;border-radius:50%;font-size:18px;cursor:pointer;flex-shrink:0;-webkit-tap-highlight-color:transparent}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes progress{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
#history-bar:active{background:#f0ebe0}
.history-card{background:#fff;border:1px solid #e0d8d0;border-radius:8px;padding:10px 12px;margin-bottom:8px;cursor:pointer}
.history-card:active{background:#faf8f5}
.history-card .detail{display:none;margin-top:6px;font-size:13px;line-height:1.5}
.history-card .detail img{max-width:100%;border-radius:6px;margin-top:6px}
</style>
</head>
<body>
<div id="app">
<div class="header"><h1>👔 穿搭助手</h1><div class="sub">AI STYLE ADVISOR</div></div>
<div id="messages"></div>
<div id="history-bar" style="flex-shrink:0;background:#f8f6f3;border-top:1px solid #e0d8d0;cursor:pointer;padding:8px 18px;font-size:13px;color:#5c4d3c;display:flex;align-items:center;gap:6px;user-select:none;-webkit-tap-highlight-color:transparent" onclick="toggleHistoryBar()">
<span id="history-icon">▶</span> <span>📋 历史记录</span> <span id="history-count" style="font-size:11px;color:#9b8c7c"></span>
</div>
<div id="history-panel" style="display:none;flex-shrink:0;background:#f8f6f3;border-top:1px solid #e0d8d0;max-height:40vh;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:8px 14px"></div>
<div class="input-bar">
<div class="chips" id="chips">
<span class="chip" data-cmd="推荐穿搭">🧠 推荐</span>
<span class="chip" data-cmd="生成效果图">🎨 生成</span>
<span class="chip" data-cmd="同步">📤 同步</span>
<span class="chip" data-cmd="状态">📊 状态</span>
<span class="chip" data-cmd="帮助">❓ 帮助</span>
<span class="chip" data-cmd="探索 日系" style="background:#e8f5e9;color:#2e7d32;">🧪 探索</span>
<span class="chip" data-cmd="大胆 混搭" style="background:#fff3e0;color:#e65100;">🚀 大胆</span>
</div>
<div class="input-row">
<input type="text" id="input" placeholder="输入指令…如：生成 日系休闲 | 探索 街头 | 大胆 混搭" autocomplete="off" enterkeyhint="send">
<button id="sendBtn">▶</button>
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
if(d.task_id){var el=addLoading();pollTask(d.task_id,el,0)}
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
document.getElementById('chips').addEventListener('click',function(e){
var c=e.target.closest('.chip');if(c){input.value=c.dataset.cmd;send()}
});

// 欢迎消息
addMsg('assistant','👋 你好！我是穿搭助手<br><br>试试输入:<br>• <b>推荐穿搭</b> — AI推荐+生图<br>• <b>生成 日系休闲</b> — 完整流程<br>• <b>状态</b> — 查看项目状态<br>• <b>同步</b> — 推送GitHub');

// ── 历史栏 ──
var historyPanel=document.getElementById('history-panel');
var historyIcon=document.getElementById('history-icon');
var historyCount=document.getElementById('history-count');
var historyOpen=false;

function loadHistoryBar(){
fetch('/api/history?n=20').then(function(r){return r.json()}).then(function(data){
if(!data||!data.length){historyCount.textContent='(暂无)';return}
historyCount.textContent='('+data.length+'条)';
var h='';
data.forEach(function(e){
var emoji=e.status==='done'?'✅':'❌';
h+='<div class="history-card" onclick="toggleCard(this)" data-img="'+esc(e.image_url||'')+'" data-result="'+esc(e.result||'')+'">';
h+='<div style="font-size:14px;font-weight:600">'+emoji+' '+esc(e.style)+'</div>';
h+='<div style="font-size:11px;color:#9b8c7c;margin-top:2px">'+esc(e.time)+'</div>';
h+='<div class="detail"></div></div>';
});
historyPanel.innerHTML=h;
})}

function toggleHistoryBar(){
historyOpen=!historyOpen;
historyPanel.style.display=historyOpen?'block':'none';
historyIcon.textContent=historyOpen?'▼':'▶';
if(historyOpen)loadHistoryBar();
}

function toggleCard(el){
var detail=el.querySelector('.detail');
if(detail.style.display==='block'){detail.style.display='none';return}
var img=el.dataset.img,result=el.dataset.result;
var h=result.replace(/\\n/g,'<br>');
if(img)h+='<br><img src="'+img+'" loading="lazy">';
detail.innerHTML=h;detail.style.display='block';
}

</script>
</body>
</html>"""

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
                names = {'simple': '🅰️ 简约版', 'rich': '🅱️ 时尚版', 'both': '🅰️+🅱️ 双版'}
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

            if action in ('generate', 'recommend'):
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
