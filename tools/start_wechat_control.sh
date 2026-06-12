#!/bin/bash
# ── 穿搭助手微信远程控制 — 一键启动 ──
# 用法: bash tools/start_wechat_control.sh
# 退出: Ctrl+C (同时关闭 ngrok 和 webhook 服务)

set -e
PORT=8765
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NGROK_PID=""
SERVER_PID=""

cleanup() {
    echo ""
    echo "🛑 正在关闭服务..."
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$NGROK_PID" ] && kill "$NGROK_PID" 2>/dev/null
    echo "👋 已关闭所有服务"
    exit 0
}
trap cleanup INT TERM

echo "========================================="
echo "👔 Fashion 穿搭助手 — 微信远程控制"
echo "========================================="

# ── 0. 检查环境 ──────────────────────────
echo ""
echo "📋 环境检查..."

# 检查 claude CLI
if ! command -v claude &>/dev/null; then
    # 尝试常见路径
    if [ -f "$HOME/.local/bin/claude" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    elif [ -f "/usr/local/bin/claude" ]; then
        export PATH="/usr/local/bin:$PATH"
    else
        echo "⚠️  未找到 claude 命令，推荐/生成功能可能不可用"
    fi
fi

# 检查 ngrok
if ! command -v ngrok &>/dev/null; then
    echo ""
    echo "❌ 未安装 ngrok"
    echo "   安装方法: brew install ngrok"
    echo "   然后注册免费账号: https://dashboard.ngrok.com/signup"
    echo "   添加 token: ngrok config add-authtoken <你的token>"
    exit 1
fi

echo "✅ 环境就绪"

# ── 1. 启动 Webhook 服务 ─────────────────
echo ""
echo "🚀 启动 Webhook 服务 (端口 $PORT)..."
cd "$PROJECT_DIR"
python3 tools/wechat_control.py --port "$PORT" &
SERVER_PID=$!
sleep 1.5

# 验证服务是否启动成功
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "❌ Webhook 服务启动失败，请检查错误信息"
    exit 1
fi

# ── 2. 启动 ngrok ────────────────────────
echo ""
echo "🌐 启动 ngrok 隧道..."
ngrok http "$PORT" --log=stdout &
NGROK_PID=$!
sleep 2

echo ""
echo "────────────────────────────────────────"
echo "  ✅ 服务已就绪！"
echo ""
echo "  📋 后续步骤:"
echo "     1. 打开 https://dashboard.ngrok.com"
echo "        找到 ngrok 提供的 https URL"
echo "     2. 打开 https://sct.ftqq.com/ 控制台"
echo "        消息通道 → 选择通道 → Webhook 配置"
echo "        填写 Webhook URL: https://xxx.ngrok-free.app/webhook"
echo ""
echo "  🧪 本地测试: curl http://localhost:$PORT/health"
echo ""
echo "  按 Ctrl+C 关闭所有服务"
echo "────────────────────────────────────────"
echo ""

# 保持服务运行
wait
