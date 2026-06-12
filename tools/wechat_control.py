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
import sys
import re
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
    """推送到微信"""
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
    return f"https://raw.githubusercontent.com/wangyunkun123/fashion-style-advisor/main/{rel}"

def find_latest_composite():
    """找到最新生成的排版合成图（优先当日，按文件修改时间）"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    today = time.strftime('%Y-%m-%d')
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

def find_outfit_dir(style_hint):
    """根据风格名找到对应的 outfit 目录（按创建时间，最新优先）"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    candidates = []
    for d in os.listdir(outfit_base):
        dp = os.path.join(outfit_base, d)
        if os.path.isdir(dp) and style_hint in d:
            candidates.append((dp, os.path.getctime(dp)))
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    return None

def run_pipeline(style_hint, task_id=None):
    """完整生图管线: 推荐 → Seedream生图 → 排版 → 推送"""
    log(f"🚀 管线启动: {style_hint}")
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

    prompt = f"""今天是{today}，北京6月中旬天气（晴/多云，22-34°C）。

根据 wardrobe/服装档案.md，为「{style_hint}」推荐一套全新穿搭。

❌ 今日已使用以下单品，严禁再次使用: {used_str}
必须从未使用的单品中选择，确保上衣、下装、鞋子不与今日任何一套重复。

操作步骤:
1. 创建 outfits/{today}_{style_hint}/ 目录
2. 写入 outfit.md（含单品ID、搭配理由、配色逻辑、风格关键词）
3. 在 outfits/.../豆包生图/ 目录下放入：人物照片(profile/photos/IMG_8493.jpg)、上衣、下装、鞋子、配饰的参考图（从 wardrobe/ 对应单品目录复制）
4. 在 outfits/.../豆包生图/ 目录下写入 豆包提示词.txt（Seedream生图英文提示词）
5. 创建 outfits/.../items/ 目录，从 wardrobe/enhanced/ 复制对应单品 _cutout.png 抠图

⚡ 豆包提示词.txt 必须放在 豆包生图/ 目录内！

❌ 不要运行 generate.py、composite_v2.py、notify.py 或做任何推送。"""

    try:
        out1 = run_cli(['claude', '-p', prompt], timeout=600)
        # 提取关键信息
        if out1:
            key = out1[:300]
            progress(f'✅ 穿搭方案已创建\n{key}')

        progress('🎨 Step 2/4: Seedream AI 生图中...')
        out2 = run_cli(['python3', 'tools/generate.py', style_hint], timeout=120)
        if out2:
            progress(f'✅ Seedream 生图完成\n{out2[:300]}')

        progress('🖼️ Step 3/4: 排版合成中...')
        outfit_dir = find_outfit_dir(style_hint)
        if outfit_dir:
            out3 = run_cli(['python3', 'tools/composite_v2.py', outfit_dir], timeout=120)
        else:
            out3 = run_cli(['python3', 'tools/composite_v2.py'], timeout=120)
        if out3:
            progress(f'✅ 排版完成\n{out3[:300]}')

        progress('📤 Step 4/4: 推送 GitHub...')
        composite = find_latest_composite()
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

            # 微信备份推送
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
        style = extra if extra else "今日穿搭"
        threading.Thread(target=run_pipeline, args=(style, task_id), daemon=True).start()
        return None  # 异步，结果通过 task 轮询
    elif action == 'generate':
        style = extra if extra else "日系 city boy"
        threading.Thread(target=run_pipeline, args=(style, task_id), daemon=True).start()
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
</style>
</head>
<body>
<div id="app">
<div class="header"><h1>👔 穿搭助手</h1><div class="sub">AI STYLE ADVISOR</div></div>
<div id="messages"></div>
<div class="input-bar">
<div class="chips" id="chips">
<span class="chip" data-cmd="推荐穿搭">🧠 推荐</span>
<span class="chip" data-cmd="生成效果图">🎨 生成</span>
<span class="chip" data-cmd="同步">📤 同步</span>
<span class="chip" data-cmd="状态">📊 状态</span>
<span class="chip" data-cmd="帮助">❓ 帮助</span>
</div>
<div class="input-row">
<input type="text" id="input" placeholder="输入指令…如：生成 日系休闲" autocomplete="off" enterkeyhint="send">
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
                    tid = tasks.create()
                    style = extra if extra else "今日穿搭"
                    threading.Thread(target=run_pipeline, args=(style, tid), daemon=True).start()
                    self._html_resp(200, REDIRECT_HTML)
                else:
                    result = execute_action(action, extra)
                    self._html_resp(200, f"<html><body style='font-family:sans-serif;padding:20px;background:#f5f0eb'><pre style='white-space:pre-wrap;font-size:15px'>{result}</pre><p><a href='/'>← 返回面板</a></p></body></html>")
            else:
                self._json_resp(400, {"error": "缺少 t 参数"})
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
                tid = tasks.create()
                style = extra if extra else "今日穿搭"
                threading.Thread(target=run_pipeline, args=(style, tid), daemon=True).start()
                self._json_resp(200, {"task_id": tid})
            else:
                result = execute_action(action, extra)
                self._json_resp(200, {"result": result, "action": action})
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
