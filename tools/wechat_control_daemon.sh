#!/bin/bash
# ── Fashion 穿搭助手 daemon wrapper ──
# 由 LaunchAgent 调用，防止重复启动
# 日志: tools/wechat_control_launchd.log
#
# 可靠性增强 (2026-06-23):
#   - curl /health 验证（非仅 lsof 端口检查）→ 僵尸进程检测
#   - 端口占用 + /health 失败 → 强制 kill 旧进程重启
#   - Tailscale Funnel 自动启动（Mac 重启后无需手动）
#   - 节流日志（每5分钟最多写一次）

PORT=8765
PROJECT_DIR="/Users/rabbit/Claude code/Fashion"
THROTTLE_FILE="/tmp/fashion_daemon_throttle"
HEALTH_URL="http://localhost:${PORT}/health"
LOG_FILE="${PROJECT_DIR}/tools/wechat_control_launchd.log"

log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ── 端口已占用 → 执行健康检查 ──
if /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    # 健康检查：curl /health，最多等5秒
    HEALTH_RESP=$(curl -s --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "")

    if echo "$HEALTH_RESP" | grep -q '"status":"ok"'; then
        # 服务健康 → 节流日志
        NOW=$(date +%s)
        LAST_LOG=0
        [ -f "$THROTTLE_FILE" ] && read -r LAST_LOG < "$THROTTLE_FILE" 2>/dev/null
        if [ $((NOW - LAST_LOG)) -gt 300 ]; then
            log_msg "✅ 服务健康 (端口 $PORT 已占用, /health 返回 ok)"
            echo "$NOW" > "$THROTTLE_FILE"
        fi
        sleep 30
        exit 0
    else
        # 端口被占用但 /health 失败 → 僵尸进程，强制 kill 重启
        PID=$(/usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t 2>/dev/null | head -1)
        log_msg "⚠️ 检测到僵尸进程 (端口 $PORT 占用但 /health 失败, PID=$PID)，强制重启"
        kill -9 "$PID" 2>/dev/null || true
        sleep 2
    fi
fi

# ── 端口空闲 → 启动 Tailscale Funnel（先于服务启动）──
if command -v tailscale &>/dev/null && tailscale status &>/dev/null 2>&1; then
    if ! tailscale funnel status 2>/dev/null | grep -q "Funnel on"; then
        log_msg "🌐 自动启用 Tailscale Funnel (http://localhost:${PORT} → HTTPS)..."
        tailscale funnel --bg --https 443 "http://localhost:${PORT}" 2>&1 | tail -1 >> "$LOG_FILE"
    else
        CURRENT_TARGET=$(tailscale funnel status 2>/dev/null | grep -o "http://localhost:[0-9]*" || true)
        if [ -n "$CURRENT_TARGET" ] && [ "$CURRENT_TARGET" != "http://localhost:${PORT}" ]; then
            log_msg "🔄 Funnel 目标端口不一致 ($CURRENT_TARGET → $PORT)，重置..."
            tailscale funnel --https=443 off 2>/dev/null || true
            sleep 1
            tailscale funnel --bg --https 443 "http://localhost:${PORT}" 2>&1 | tail -1 >> "$LOG_FILE"
        fi
    fi
fi

# ── 启动服务（exec 替换当前进程，由 launchd 直接监控）──
cd "$PROJECT_DIR"
log_msg "🚀 启动 Fashion 穿搭助手服务..."
exec /usr/bin/python3 tools/wechat_control.py --port "$PORT"
