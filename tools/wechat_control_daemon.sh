#!/bin/bash
# ── Fashion 穿搭助手 daemon wrapper ──
# 由 LaunchAgent 调用，防止重复启动
# 日志: tools/wechat_control_launchd.log

PORT=8765
PROJECT_DIR="/Users/rabbit/Claude code/Fashion"
THROTTLE_FILE="/tmp/fashion_daemon_throttle"

# 端口已占用 → 节流日志（每5分钟最多写一次），sleep后退出
if /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    NOW=$(date +%s)
    LAST_LOG=0
    [ -f "$THROTTLE_FILE" ] && read -r LAST_LOG < "$THROTTLE_FILE" 2>/dev/null
    if [ $((NOW - LAST_LOG)) -gt 300 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 服务运行中 (端口 $PORT 已占用)" >> "$PROJECT_DIR/tools/wechat_control_launchd.log"
        echo "$NOW" > "$THROTTLE_FILE"
    fi
    # 休眠30秒再退出，防止 launchd 密集重启循环
    sleep 30
    exit 0
fi

cd "$PROJECT_DIR"
exec /usr/bin/python3 tools/wechat_control.py --port "$PORT"
