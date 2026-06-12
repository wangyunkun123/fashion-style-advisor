#!/bin/bash
# ── 穿搭助手 手机远程控制 — 一键启动 ──
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
    echo "👋 已关闭"
    exit 0
}
trap cleanup INT TERM

echo "========================================="
echo "👔 Fashion 穿搭助手 — 手机远程控制"
echo "========================================="

# 检查 ngrok
if ! command -v ngrok &>/dev/null; then
    echo "❌ 未安装 ngrok，请 brew install ngrok"
    exit 1
fi

# 启动 Webhook 服务
echo ""
echo "🚀 启动 Webhook 服务 (端口 $PORT)..."
cd "$PROJECT_DIR"
python3 tools/wechat_control.py --port "$PORT" &
SERVER_PID=$!
sleep 1.5

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "❌ 服务启动失败"
    exit 1
fi

# 启动 ngrok
echo ""
echo "🌐 启动 ngrok 隧道..."
ngrok http "$PORT" --log=stdout &
NGROK_PID=$!
sleep 2

echo ""
echo "────────────────────────────────────────"
echo "  ✅ 服务已就绪！"
echo ""
echo "  📱 手机访问 ngrok 提供的 https URL"
echo "     添加到主屏幕即可像 App 一样使用"
echo ""
echo "  按 Ctrl+C 关闭所有服务"
echo "────────────────────────────────────────"
echo ""

wait
