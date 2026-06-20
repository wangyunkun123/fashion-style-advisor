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
TS_CMD=""              # 最终使用的 tailscale 命令
TS_SOCKET="/Users/rabbit/.tailscale/tailscaled.sock"

cleanup() {
    echo ""
    echo "🛑 正在关闭服务..."
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    if [ -n "$FUNNEL_OFF" ]; then
        echo "🔄 关闭 funnel..."
        $TS_CMD funnel --https=443 off 2>/dev/null || true
    fi
    echo "👋 已关闭"
    exit 0
}
trap cleanup INT TERM

echo "========================================="
echo "👔 Fashion 穿搭助手 — 手机远程控制"
echo "========================================="

# 检查 tailscale 命令行工具
if ! command -v tailscale &>/dev/null; then
    echo "❌ 未安装 tailscale，请 brew install tailscale"
    exit 1
fi

# ── 探测可用的 tailscaled ──
# 优先使用系统级 tailscaled（重启后自动运行，无需额外启动）
if tailscale status &>/dev/null 2>&1; then
    TS_CMD="tailscale"
    echo "✅ 检测到系统 Tailscale 已运行"
elif tailscale --socket="$TS_SOCKET" status &>/dev/null 2>&1; then
    TS_CMD="tailscale --socket=$TS_SOCKET"
    echo "✅ 检测到用户态 Tailscale"
else
    echo "🔄 启动用户态 tailscaled..."
    mkdir -p /Users/rabbit/.tailscale
    nohup /opt/homebrew/opt/tailscale/bin/tailscaled \
        --tun=userspace-networking \
        --socket="$TS_SOCKET" \
        --state=/Users/rabbit/.tailscale/tailscaled.state \
        --statedir=/Users/rabbit/.tailscale/ \
        > /tmp/tailscaled.log 2>&1 &
    sleep 3
    if tailscale --socket="$TS_SOCKET" status &>/dev/null 2>&1; then
        TS_CMD="tailscale --socket=$TS_SOCKET"
        echo "✅ 用户态 Tailscale 已启动"
    else
        echo "❌ Tailscale 启动失败，请检查日志: /tmp/tailscaled.log"
        exit 1
    fi
fi

# ── 确保 funnel 已启用 ──
if ! $TS_CMD funnel status 2>/dev/null | grep -q "Funnel on"; then
    echo "🌐 启用 Tailscale Funnel (http://localhost:$PORT → HTTPS)..."
    $TS_CMD funnel --bg --https 443 http://localhost:$PORT 2>&1
    FUNNEL_OFF="1"
else
    # Funnel 已启用，但检查代理目标是否正确
    CURRENT_TARGET=$($TS_CMD funnel status 2>/dev/null | grep -o "http://localhost:[0-9]*" || true)
    if [ -n "$CURRENT_TARGET" ] && [ "$CURRENT_TARGET" != "http://localhost:$PORT" ]; then
        echo "🔄 Funnel 目标端口不一致，重新设置..."
        $TS_CMD funnel --https=443 off 2>/dev/null || true
        sleep 1
        $TS_CMD funnel --bg --https 443 http://localhost:$PORT 2>&1
        FUNNEL_OFF="1"
    else
        echo "✅ Funnel 已就绪"
    fi
fi

# 检查端口是否被占用
if lsof -i :$PORT -sTCP:LISTEN &>/dev/null; then
    echo "⚠️  端口 $PORT 已被占用，跳过启动"
    SERVER_PID=$(lsof -i :$PORT -sTCP:LISTEN -t | head -1)
else
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
