#!/bin/bash
# 一键同步 Fashion 项目到 GitHub
cd "$(dirname "$0")"

MESSAGE="${1:-更新 $(date '+%Y-%m-%d %H:%M')}"
git add -A
git commit -m "$MESSAGE" 2>&1 || echo "⚠️  没有新变更"
if ! git push 2>&1; then
    echo "❌ 推送失败，请检查网络连接"
    exit 1
fi
echo "✅ 同步完成: https://github.com/wangyunkun123/fashion-style-advisor"
