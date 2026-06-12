#!/usr/bin/env python3
"""
穿搭助手 — 手机远程控制服务

架构:
  手机浏览器 → HTML面板(ngrok) → HTTP服务 → Claude CLI + 脚本管线 → Server酱推送效果图 → 微信

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
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'seedream.local.json')

# ── 加载配置 ──────────────────────────────────────────
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

SENDKEY = config.get('wechat_sendkey', '')
if not SENDKEY:
    print("❌ 未配置 wechat_sendkey，请在 config/seedream.local.json 中设置")
    sys.exit(1)

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
                print(f"  ✅ 推送成功: {title}")
                return result
            else:
                print(f"  ⚠️  推送返回: {result.get('message', 'unknown')}")
                return result
    except Exception as e:
        print(f"  ❌ 推送失败: {e}")
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

    # 中文短文本默认当作风格名
    if len(msg) <= 20 and re.search(r'[一-鿿]', msg):
        return ('generate', msg)

    return ('unknown', msg)

HELP_TEXT = """📱 **穿搭助手 - 远程指令菜单**

| 指令 | 说明 |
|------|------|
| **推荐穿搭** | AI 分析天气+衣柜，推荐今日搭配 |
| **生成 风格名** | 完整生图流程 |
| **同步** | 推送到 GitHub |
| **状态** | 查看文件状态 |
| **帮助** | 显示本菜单 |

💡 示例:
  • "推荐穿搭"
  • "生成 日系清凉休闲"
  • "同步\""""

# ── 管线核心 ──────────────────────────────────────────
def get_github_raw_url(file_path):
    """本地路径 → GitHub Raw URL"""
    rel = os.path.relpath(file_path, PROJECT_DIR)
    return f"https://raw.githubusercontent.com/wangyunkun123/fashion-style-advisor/main/{rel}"

def find_latest_composite():
    """找到最新生成的排版合成图"""
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    for d in sorted(os.listdir(outfit_base), reverse=True):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp) or d.startswith('.'):
            continue
        for f in sorted(os.listdir(dp), reverse=True):
            if '_方案' in f and f.endswith('.jpg'):
                return os.path.join(dp, f)
        for sub in ['上身效果', 'generated']:
            sp = os.path.join(dp, sub)
            if os.path.isdir(sp):
                for f in sorted(os.listdir(sp), reverse=True):
                    if '_方案' in f and f.endswith('.jpg'):
                        return os.path.join(sp, f)
    return None

def run_pipeline(style_hint):
    """完整生图管线: 推荐 → Seedream生图 → 排版 → 推送效果图"""
    print(f"🚀 启动管线: {style_hint}")

    # Step 1: Claude 推荐搭配 + 创建所有文件 + 调用生图和排版
    prompt = f"""根据 wardrobe/服装档案.md 和当前天气（北京6月中旬），为「{style_hint}」推荐一套完整穿搭并完成以下操作：

1. 创建 outfits/2026-06-12_{style_hint}/ 目录
2. 写入 outfit.md（含单品ID、搭配理由、配色逻辑、风格关键词）
3. 在 outfits/.../豆包生图/ 目录下放入：人物照片(profile/photos/IMG_8493.jpg)、上衣、下装、鞋子、配饰的参考图（从 wardrobe/ 对应单品目录复制）
4. 在 outfits/.../豆包生图/ 目录下写入 豆包提示词.txt（Seedream生图英文提示词）
5. 创建 outfits/.../items/ 目录，从 wardrobe/enhanced/ 复制对应单品 _cutout.png 抠图

⚡ 豆包提示词.txt 必须放在 豆包生图/ 目录内！

完成后依次执行:
  python3 tools/generate.py {style_hint}
  python3 tools/composite_v2.py
  git add -A && git commit -m "🎨 {style_hint}" && git push"""

    run_cli(['claude', '-p', prompt], timeout=600)

    # Step 2: 推送最终效果图到微信
    composite = find_latest_composite()
    if composite and os.path.exists(composite):
        run_cli(['git', 'add', '-A'], timeout=30)
        run_cli(['git', 'commit', '-m', f'🎨 {style_hint} — 远程操控'], timeout=30)
        run_cli(['git', 'push'], timeout=60)

        github_url = get_github_raw_url(composite)
        push_wechat(
            f"👔 {style_hint}",
            f"![效果图]({github_url})\n\n🔗 [GitHub](https://github.com/wangyunkun123/fashion-style-advisor)"
        )
        return f"✅ 完成\n{github_url}"
    else:
        push_wechat(f"⚠️ {style_hint} 未找到效果图", "请检查 Mac 上的生成日志")
        return "⚠️ 未找到排版图"

def execute_action(action, extra):
    """执行指令并返回结果文本"""
    print(f"  📋 执行指令: {action} | 参数: {extra}")

    if action == 'help':
        return HELP_TEXT

    elif action == 'sync':
        return run_cli(['bash', 'sync.sh'], timeout=60)

    elif action == 'status':
        status_output = run_cli(['git', 'status', '--short'], timeout=30)
        branch_output = run_cli(['git', 'branch', '--show-current'], timeout=10)
        return f"📂 分支: {branch_output}\n📋 文件状态:\n{status_output if status_output else '(干净)'}"

    elif action == 'recommend':
        threading.Thread(target=run_pipeline, args=(extra if extra else "今日穿搭",), daemon=True).start()
        return "🤔 正在生成搭配方案，完成后推送效果图到微信..."

    elif action == 'generate':
        style = extra if extra else "日系 city boy"
        threading.Thread(target=run_pipeline, args=(style,), daemon=True).start()
        return f"🎨 正在生成「{style}」效果图，完成后推送..."

    elif action == 'unknown':
        return f"🤔 未识别的指令: 「{extra}」\n\n{HELP_TEXT}"

    return "❌ 未知错误"

# ── 手机控制面板 HTML ──────────────────────────────────
MOBILE_PANEL_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="穿搭助手">
<title>👔 穿搭助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;background:#f5f0eb;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:12px}
.panel{background:#fff;border:1px solid #e0d8d0;max-width:400px;width:100%;overflow:hidden}
.header{background:linear-gradient(135deg,#3a3028,#5c4d3c);color:#fff;padding:20px 20px 16px;text-align:center}
.header h1{font-size:22px;font-weight:600;letter-spacing:2px;margin-bottom:4px}
.header .sub{font-size:12px;opacity:.7;letter-spacing:1px}
.btns{padding:16px 14px;display:flex;flex-direction:column;gap:10px}
.btn{display:block;width:100%;padding:14px 16px;border:1px solid #d0c8bc;background:#fdfbf8;color:#3a3028;font-size:16px;text-align:left;border-radius:4px;cursor:pointer;text-decoration:none;transition:all .15s;-webkit-tap-highlight-color:transparent}
.btn:active{background:#f0ebe0;border-color:#b8a88c}
.btn .icon{font-size:22px;margin-right:10px;vertical-align:-2px}
.btn .tag{float:right;font-size:11px;color:#9b8c7c;margin-top:3px}
.custom{border-top:1px solid #e8e0d6;padding:14px;display:flex;gap:8px}
.custom input{flex:1;padding:12px;border:1px solid #d0c8bc;border-radius:4px;font-size:15px;background:#fdfbf8;outline:none;-webkit-appearance:none}
.custom input:focus{border-color:#8b7a64}
.custom button{padding:12px 18px;background:#3a3028;color:#fff;border:none;border-radius:4px;font-size:15px;cursor:pointer;white-space:nowrap}
.footer{padding:12px 14px;text-align:center;font-size:11px;color:#b0a090;border-top:1px solid #e8e0d6}
.footer span{margin:0 8px}
</style>
</head>
<body>
<div class="panel">
<div class="header"><h1>👔 穿搭助手</h1><div class="sub">FASHION STYLE ADVISOR · REMOTE</div></div>
<div class="btns">
<a class="btn" href="/cmd?t=推荐穿搭"><span class="icon">🧠</span>推荐+生图<span class="tag">搭配→出图 全流程</span></a>
<a class="btn" href="/cmd?t=生成效果图"><span class="icon">🎨</span>生成效果图<span class="tag">完整流程</span></a>
<a class="btn" href="/cmd?t=生成 日系清凉休闲"><span class="icon">🏖️</span>生成 日系清凉休闲<span class="tag">一键</span></a>
<a class="btn" href="/cmd?t=同步"><span class="icon">📤</span>同步到 GitHub<span class="tag">推送</span></a>
<a class="btn" href="/cmd?t=状态"><span class="icon">📊</span>查看状态<span class="tag">检查</span></a>
</div>
<div class="custom">
<input type="text" id="cmd" placeholder="输入风格名…如：韩系简约" autocomplete="off">
<button onclick="send()">发送</button>
</div>
<div class="footer"><span>📱 添加到主屏幕</span><span>🔗 ngrok 远程</span></div>
</div>
<script>
function send(){var t=document.getElementById('cmd').value.trim();if(t)location.href='/cmd?t='+encodeURIComponent(t)}
document.getElementById('cmd').addEventListener('keydown',function(e){if(e.key==='Enter')send()})
</script>
</body>
</html>"""

# ── HTTP 处理器 ───────────────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        """控制面板 / 健康检查 / URL触发"""
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(self.path)

        # 手机控制面板
        if parsed.path in ('/', ''):
            self._html_resp(200, MOBILE_PANEL_HTML)
            return

        # URL 命令触发: /cmd?t=推荐穿搭
        if parsed.path == '/cmd':
            qs = parse_qs(parsed.query)
            msg = qs.get('t', [''])[0] or qs.get('text', [''])[0]
            if msg:
                thread = threading.Thread(target=self._process, args=(msg,), daemon=True)
                thread.start()
                self._html_resp(200, f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>穿搭助手</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#f5f0eb;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#fff;border:1px solid #e0d8d0;padding:30px 24px;text-align:center;max-width:360px;width:90%}}
h2{{font-size:20px;margin-bottom:6px}} .st{{color:#9b8c7c;font-size:14px;margin-bottom:20px}}
.cmd{{background:#f9f6f3;border:1px solid #e0d8d0;padding:12px;border-radius:4px;font-size:16px;margin:16px 0;color:#3a3028}}
.note{{color:#9b8c7c;font-size:13px;margin-top:16px}} a{{color:#6b5e4f}}
</style></head><body>
<div class="card"><h2>👔 穿搭助手</h2><div class="st">指令已提交，后台处理中</div>
<div class="cmd">📨 {msg}</div><div class="note">效果图将推送到微信<br><a href="/">← 返回控制面板</a></div>
</div></body></html>""")
            else:
                self._json_resp(400, {"error": "缺少 t 参数，如 /cmd?t=推荐穿搭"})
            return

        # 健康检查
        if parsed.path == '/health':
            self._json_resp(200, {"status": "ok", "service": "Fashion 穿搭助手", "time": time.strftime("%H:%M:%S")})
            return

        self._json_resp(404, {"error": "not found"})

    def _process(self, message):
        """后台线程：解析指令 → 执行 → 推送结果"""
        action, extra = match_command(message)
        print(f"  🎯 意图: {action} | 参数: {extra}")

        result = execute_action(action, extra)

        if len(result) > 1500:
            result = result[:1500] + "\n\n... (内容过长已截断)"

        title_map = {
            'recommend': '👔 穿搭推荐', 'generate': '🎨 效果图生成',
            'sync': '📤 同步结果', 'status': '📊 项目状态',
            'help': '📋 指令菜单', 'unknown': '🤔 指令识别',
        }
        push_wechat(title_map.get(action, '📢 执行结果'), result)

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

    def log_message(self, format, *args):
        print(f"  🌐 {args[0]}" if args else "")

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

    print("=" * 55)
    print("👔 Fashion 穿搭助手 — 手机远程控制")
    print("=" * 55)
    print(f"  📡 服务: http://0.0.0.0:{port}")
    print(f"  ❤️  健康: http://localhost:{port}/health")
    print(f"  📱 面板: http://localhost:{port}/")
    print("-" * 55)
    print(f"  启动 ngrok: ngrok http {port}")
    print(f"  手机访问 ngrok 提供的 https URL 即可")
    print("-" * 55)

    push_wechat("🟢 穿搭助手已上线", "手机打开控制面板即可远程操控")
    print("  📤 已推送上线通知\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已关闭")
        server.server_close()

if __name__ == '__main__':
    main()
