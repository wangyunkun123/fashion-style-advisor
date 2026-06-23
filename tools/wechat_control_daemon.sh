#!/bin/bash
# ── Fashion 穿搭助手 daemon wrapper ──
# 由 LaunchAgent 调用，防止重复启动
# 日志: tools/wechat_control_launchd.log

PORT=8765
PROJECT_DIR="/Users/rabbit/Claude code/Fashion"

# 端口已占用 → 退出（告诉 launchd 一切正常，不重启）
if /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 端口 $PORT 已被占用，跳过启动"
    exit 0
fi

cd "$PROJECT_DIR"
exec /usr/bin/python3 tools/wechat_control.py --port "$PORT"
