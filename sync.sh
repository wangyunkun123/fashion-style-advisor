#!/bin/bash
# 一键同步 Fashion 项目到 GitHub
cd "/Users/rabbit/Claude code/Fashion"

MESSAGE="${1:-更新 $(date '+%Y-%m-%d %H:%M')}"
git add -A
git commit -m "$MESSAGE" 2>&1 || echo "⚠️  没有新变更"
git push 2>&1
echo ""
echo "✅ 同步完成: https://github.com/wangyunkun123/fashion-style-advisor"
