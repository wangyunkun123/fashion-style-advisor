#!/bin/bash
# ── 穿搭助手 手机远程控制 — 一键启动 ──
# 用法: bash tools/start_wechat_control.sh
# 退出: Ctrl+C (同时关闭 tailscale funnel 和 webhook 服务)
# 手机端: https://macbook-pro-1.taildbfbc0.ts.net/ (永久不变)

set -e
PORT=8765
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FUNNEL_OFF=""
SERVER_PID=""
TS_SOCKET="/Users/rabbit/.tailscale/tailscaled.sock"

cleanup() {
    echo ""
    echo "🛑 正在关闭服务..."
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$FUNNEL_OFF" ] && tailscale --socket="$TS_SOCKET" funnel --https=443 off 2>/dev/null
    echo "👋 已关闭"
    exit 0
}
trap cleanup INT TERM

echo "========================================="
echo "👔 Fashion 穿搭助手 — 手机远程控制"
echo "========================================="

# 检查 tailscale
if ! command -v tailscale &>/dev/null; then
    echo "❌ 未安装 tailscale，请 brew install tailscale"
    exit 1
fi

# 确保 tailscaled 在运行
if ! tailscale --socket="$TS_SOCKET" status &>/dev/null; then
    echo "🔄 启动 tailscaled..."
    mkdir -p /Users/rabbit/.tailscale
    nohup /opt/homebrew/opt/tailscale/bin/tailscaled \
        --tun=userspace-networking \
        --socket="$TS_SOCKET" \
        --state=/Users/rabbit/.tailscale/tailscaled.state \
        --statedir=/Users/rabbit/.tailscale/ \
        > /tmp/tailscaled.log 2>&1 &
    sleep 3
fi

# 确保 funnel 已启用
if ! tailscale --socket="$TS_SOCKET" funnel status 2>/dev/null | grep -q "Funnel on"; then
    echo "🌐 启用 Tailscale Funnel..."
    tailscale --socket="$TS_SOCKET" funnel --bg --https 443 http://localhost:$PORT 2>&1
    FUNNEL_OFF="1"
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

echo ""
echo "────────────────────────────────────────"
echo "  ✅ 服务已就绪！"
echo ""
echo "  📱 手机访问 (永久不变):"
echo "     https://macbook-pro-1.taildbfbc0.ts.net/"
echo ""
echo "  按 Ctrl+C 关闭所有服务"
echo "────────────────────────────────────────"
echo ""

wait
