#!/usr/bin/env python3
"""
微信远程控制服务 — 通过 Server酱 Turbo Webhook 接收微信指令，操控穿搭生成

架构:
  微信(手机) → Server酱 → Webhook回调(POST) → 本服务(HTTP) → Claude CLI/脚本 → Server酱推送 → 微信

依赖: 纯 Python 标准库，无需 pip install
启动: python3 tools/wechat_control.py [--port 8765]
穿透: ngrok http 8765  (另开终端)

Server酱控制台配置 Webhook URL: https://xxx.ngrok-free.app/webhook
"""

import json
import os
import sys
import re
import subprocess
import threading
import time
import hashlib
import hmac
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'seedream.local.json')

# ── 加载配置 ──────────────────────────────────────────
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

SENDKEY = config.get('wechat_sendkey', '')
WEBHOOK_SECRET = config.get('webhook_secret', SENDKEY)  # 默认用 sendkey 做签名

if not SENDKEY:
    print("❌ 未配置 wechat_sendkey，请在 config/seedream.local.json 中设置")
    sys.exit(1)

# ── Server酱推送 ──────────────────────────────────────
def push_wechat(title, content="", openid=""):
    """推送到微信，可选指定 openid 实现双向回复"""
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    payload = {"title": title, "desp": content}
    if openid:
        payload["openid"] = openid

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
        return "⏰ 命令超时（超过 5 分钟），请稍后重试"
    except FileNotFoundError as e:
        return f"❌ 命令未找到: {e}"

def match_command(message):
    """
    从用户消息中识别指令，返回 (action, extra)
    action: 'recommend' | 'generate' | 'sync' | 'status' | 'help' | 'unknown'
    extra: 附加参数（如风格名称）
    """
    msg = message.strip()
    if not msg:
        return ('help', '')

    # 帮助
    if re.search(r'^(帮助|help|功能|命令|菜单|\\?)$', msg, re.I):
        return ('help', '')

    # 同步/推送
    if re.search(r'^(同步|推送|push|上传|上传到)', msg, re.I):
        return ('sync', '')

    # 状态
    if re.search(r'^(状态|status|情况|检查)$', msg, re.I):
        return ('status', '')

    # 生成效果图
    m = re.search(r'(?:生成|效果图|生图|来一张|画一张)(?:[：:\s]*(.+))?', msg)
    if m:
        style = (m.group(1) or '').strip()
        return ('generate', style)

    # 推荐穿搭
    if re.search(r'推荐|穿搭|穿什么|怎么穿|搭配|今天穿', msg):
        return ('recommend', msg)

    # 默认：尝试作为风格名称来生成
    if len(msg) <= 20 and re.search(r'[一-鿿]', msg):
        return ('generate', msg)

    return ('unknown', msg)

HELP_TEXT = """📱 **穿搭助手 - 远程指令菜单**

| 指令 | 说明 |
|------|------|
| **推荐穿搭** | AI 分析天气+衣柜，推荐今日搭配 |
| **生成 风格名** | 生图完整流程（效果图→排版→推送）|
| **效果图** | 同上，使用默认风格 |
| **同步** | 推送到 GitHub |
| **状态** | 查看项目文件状态 |
| **帮助** | 显示本菜单 |

💡 示例:
  • "推荐穿搭"
  • "生成 日系清凉休闲"
  • "效果图"
  • "同步"
"""

def execute_action(action, extra, openid):
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
        # 调用 Claude 进行穿搭推荐
        prompt = f"根据 wardrobe/服装档案.md 和当前天气（北京6月中旬），推荐一套适合今天的穿搭。给出单品ID和搭配理由，简洁回复，200字以内。用户消息: {extra}"
        push_wechat("🤔 AI 正在思考穿搭...", "请稍等 15-30 秒", openid)
        return run_cli(['claude', '-p', prompt], timeout=120)

    elif action == 'generate':
        # 完整生成流程
        style = extra if extra else "日系 city boy"
        prompt = f"生成效果图 {style}"
        push_wechat(f"🎨 开始生成「{style}」效果图", "正在调用 Seedream 生图 + 排版，约需 1-2 分钟...", openid)
        return run_cli(['claude', '-p', prompt], timeout=300)

    elif action == 'unknown':
        return f"🤔 未识别的指令: 「{extra}」\n\n{HELP_TEXT}"

    return "❌ 未知错误"

# ── HTTP Webhook 处理器 ──────────────────────────────
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
<a class="btn" href="/cmd?t=推荐穿搭"><span class="icon">🧠</span>推荐穿搭<span class="tag">AI 分析</span></a>
<a class="btn" href="/cmd?t=生成效果图"><span class="icon">🎨</span>生成效果图<span class="tag">完整流程</span></a>
<a class="btn" href="/cmd?t=生成 日系清凉休闲"><span class="icon">🏖️</span>生成 日系清凉休闲<span class="tag">一键</span></a>
<a class="btn" href="/cmd?t=同步"><span class="icon">📤</span>同步到 GitHub<span class="tag">推送</span></a>
<a class="btn" href="/cmd?t=状态"><span class="icon">📊</span>查看状态<span class="tag">检查</span></a>
</div>
<div class="custom">
<input type="text" id="cmd" placeholder="输入指令…如：生成 韩系简约" autocomplete="off">
<button onclick="send()">发送</button>
</div>
<div class="footer"><span>🔗 ngrok 远程</span><span>📱 收藏到主屏幕</span></div>
</div>
<script>
function send(){var t=document.getElementById('cmd').value.trim();if(t)location.href='/cmd?t='+encodeURIComponent(t)}
document.getElementById('cmd').addEventListener('keydown',function(e){if(e.key==='Enter')send()})
</script>
</body>
</html>"""

class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        """健康检查 + 手机控制面板 + URL触发"""
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(self.path)

        # URL 触发命令：/cmd?t=推荐穿搭
        if parsed.path == '/cmd':
            qs = parse_qs(parsed.query)
            msg = qs.get('t', [''])[0] or qs.get('text', [''])[0]
            if msg:
                thread = threading.Thread(target=self._process_and_reply, args=(msg, ''), daemon=True)
                thread.start()
                self._html_resp(200, f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>穿搭助手</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#f5f0eb;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#fff;border:1px solid #e0d8d0;padding:30px 24px;text-align:center;max-width:360px;width:90%}}
h2{{font-size:20px;margin-bottom:6px}} .st{{color:#9b8c7c;font-size:14px;margin-bottom:20px}}
.cmd{{background:#f9f6f3;border:1px solid #e0d8d0;padding:12px;border-radius:4px;font-size:16px;margin:16px 0;color:#3a3028}}
.note{{color:#9b8c7c;font-size:13px;margin-top:16px}}
a{{color:#6b5e4f}}
</style></head><body>
<div class="card"><h2>👔 穿搭助手</h2><div class="st">指令已提交，后台处理中</div>
<div class="cmd">📨 {msg}</div><div class="note">结果将推送到微信<br>也可稍后访问 <a href="/">控制面板</a></div>
</div></body></html>""")
            else:
                self._json_resp(400, {"error": "缺少 t 参数，如 /cmd?t=推荐穿搭"})
            return

        # 手机控制面板 HTML
        if parsed.path == '/' or parsed.path == '':
            self._html_resp(200, MOBILE_PANEL_HTML)
            return

        # 健康检查 JSON
        if parsed.path == '/health':
            self._json_resp(200, {"status": "ok", "service": "Fashion 穿搭助手 Webhook", "time": time.strftime("%H:%M:%S")})
            return

        self._json_resp(404, {"error": "not found"})

    def do_POST(self):
        """接收 Server酱 Webhook 回调"""
        if self.path != '/webhook':
            self._json_resp(404, {"error": "webhook endpoint is /webhook"})
            return

        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body.decode('utf-8'))

            print(f"\n📩 [{time.strftime('%H:%M:%S')}] 收到微信消息: {body.get('message', '(空)')[:100]}")

            # 验证签名（可选）
            sign = self.headers.get('X-Sct-Signature', '')
            if sign and WEBHOOK_SECRET:
                expected = hmac.new(
                    WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(sign, expected):
                    print("  ⚠️  签名验证失败")
                    self._json_resp(403, {"error": "invalid signature"})
                    return

            # 提取消息和 openid
            message = body.get('message', '').strip()
            openid = body.get('openid', '')

            if not message:
                self._json_resp(200, {"code": 0, "msg": "empty message ignored"})
                return

            # 后台处理（立即返回 200，避免 Server酱 超时）
            thread = threading.Thread(
                target=self._process_and_reply,
                args=(message, openid),
                daemon=True
            )
            thread.start()

            self._json_resp(200, {"code": 0, "msg": "processing"})

        except json.JSONDecodeError:
            print("  ⚠️  请求体不是有效 JSON")
            self._json_resp(400, {"error": "invalid json"})
        except Exception as e:
            print(f"  ❌ 处理出错: {e}")
            self._json_resp(500, {"error": str(e)})

    def _process_and_reply(self, message, openid):
        """后台线程：解析指令 → 执行 → 推送结果"""
        action, extra = match_command(message)
        print(f"  🎯 识别意图: {action} | 参数: {extra}")

        result = execute_action(action, extra, openid)

        # 截断过长内容（微信推送有长度限制）
        if len(result) > 1500:
            result = result[:1500] + "\n\n... (内容过长已截断，完整结果请查看 GitHub)"

        # 推送结果回微信
        title_map = {
            'recommend': '👔 穿搭推荐',
            'generate': '🎨 效果图生成',
            'sync': '📤 同步结果',
            'status': '📊 项目状态',
            'help': '📋 指令菜单',
            'unknown': '🤔 指令识别',
        }
        title = title_map.get(action, '📢 执行结果')

        push_wechat(title, result, openid)

    def _json_resp(self, code, data):
        """发送 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_resp(self, code, html):
        """发送 HTML 响应"""
        body = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"  🌐 {args[0]}" if args else "")

# ── 启动服务器 ────────────────────────────────────────
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

    print("=" * 60)
    print("👔 Fashion 穿搭助手 — 微信远程控制服务")
    print("=" * 60)
    print(f"  📡 HTTP Webhook 服务: http://0.0.0.0:{port}/webhook")
    print(f"  ❤️  健康检查: http://localhost:{port}/health")
    print("-" * 60)
    print("  📱 下一步操作:")
    print(f"     1. 另开终端运行: ngrok http {port}")
    print(f"     2. 复制 ngrok 提供的 https URL")
    print(f"     3. 去 Server酱控制台配置 Webhook URL:")
    print(f"        https://sct.ftqq.com/  →  消息通道  →  Webhook")
    print(f"     4. Webhook URL 填: https://xxx.ngrok-free.app/webhook")
    print("-" * 60)

    # 启动时发送上线通知（带 openid 支持，让用户可以回复）
    push_wechat(
        "🟢 穿搭助手已上线",
        "回复以下指令开始操控:\n"
        "• **推荐穿搭** — 获取今日搭配方案\n"
        "• **生成 风格名** — 生成效果图\n"
        "• **同步** — 推送到 GitHub\n"
        "• **帮助** — 查看完整菜单",
    )
    print("  📤 已推送上线通知到微信\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已关闭")
        server.server_close()

if __name__ == '__main__':
    main()
