#!/bin/bash
# ── 穿搭助手 手机远程控制 — 一键启动 ──
# 用法: bash tools/start_wechat_control.sh
# 退出: Ctrl+C (同时关闭 cloudflare 和 webhook 服务)

set -e
PORT=8765
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CF_PID=""
SERVER_PID=""

cleanup() {
    echo ""
    echo "🛑 正在关闭服务..."
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$CF_PID" ] && kill "$CF_PID" 2>/dev/null
    echo "👋 已关闭"
    exit 0
}
trap cleanup INT TERM

echo "========================================="
echo "👔 Fashion 穿搭助手 — 手机远程控制"
echo "========================================="

# 检查 cloudflared
if ! command -v cloudflared &>/dev/null; then
    echo "❌ 未安装 cloudflared，请 brew install cloudflare/cloudflare/cloudflared"
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

# 启动 Cloudflare Tunnel
echo ""
echo "🌐 启动 Cloudflare 隧道..."
cloudflared tunnel --url http://localhost:$PORT > /tmp/cloudflared.log 2>&1 &
CF_PID=$!
sleep 6

# 提取 URL
URL=$(grep -o 'https://.*trycloudflare\.com' /tmp/cloudflared.log | tail -1)

echo ""
echo "────────────────────────────────────────"
echo "  ✅ 服务已就绪！"
echo ""
if [ -n "$URL" ]; then
    echo "  📱 手机访问:"
    echo "     $URL"
else
    echo "  📱 查看日志: tail -f /tmp/cloudflared.log"
fi
echo ""
echo "  按 Ctrl+C 关闭所有服务"
echo "────────────────────────────────────────"
echo ""

wait
