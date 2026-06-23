#!/bin/bash
# 风格库月度自动学习
# Cron: 每月1日 9:07
# 流程: 发现新趋势 → 充实旧风格 → 刷新图片URL → 记录报告

cd "$(dirname "$0")/.." || exit 1
LOG="styles_universal/references/_auto_learn.log"
REPORT="styles_universal/references/_monthly_report_$(date '+%Y-%m').md"

echo "============================================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 🔍 月度自动学习开始" >> "$LOG"

# ── 1. 发现新趋势 ──
echo "[$(date '+%Y-%m-%d %H:%M')] 📡 发现新趋势..." >> "$LOG"
python3 tools/style_research.py --discover >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M')] ✅ 发现完成" >> "$LOG"

# ── 2. 充实最旧的5个风格 ──
echo "[$(date '+%Y-%m-%d %H:%M')] 📝 充实旧风格..." >> "$LOG"
ENRICH_LIST=$(python3 -c "
import json, os, glob
from datetime import datetime
registry = json.load(open('styles_universal/categories.json'))['style_registry']
# 按百科最后修改时间排序，取最旧的5个
oldest = []
for sid in registry:
    path = f'styles_universal/{sid}/encyclopedia.md'
    if os.path.exists(path):
        mtime = os.path.getmtime(path)
        oldest.append((mtime, sid))
oldest.sort()
for mtime, sid in oldest[:5]:
    print(sid)
")
for sid in $ENRICH_LIST; do
    echo "[$(date '+%Y-%m-%d %H:%M')]   充实: $sid" >> "$LOG"
    python3 tools/style_research.py --enrich "$sid" >> "$LOG" 2>&1
done
echo "[$(date '+%Y-%m-%d %H:%M')] ✅ 充实完成" >> "$LOG"

# ── 3. 刷新图片URL ──
echo "[$(date '+%Y-%m-%d %H:%M')] 🖼️ 检查图片URL..." >> "$LOG"
python3 -c "
import json, os, glob, urllib.request

styles_dir = 'styles_universal'
broken = 0
fixed = 0
for fpath in sorted(glob.glob(f'{styles_dir}/*/references/images.json')):
    with open(fpath) as f:
        data = json.load(f)

    sid = data.get('style_id', '')
    modified = False
    for cat_key, cat_data in data.get('categories', {}).items():
        for img in cat_data.get('images', []):
            url = img.get('url', '')
            if not url or url == '#': continue
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'FashionStyleAdvisor/1.0')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status >= 400:
                        raise Exception(f'HTTP {resp.status}')
            except Exception as e:
                broken += 1
                img['_broken'] = True
                img['_broken_reason'] = str(e)[:80]
                img['_checked'] = '$(date +%Y-%m-%d)'
                modified = True

    if modified:
        data['_last_checked'] = '$(date +%Y-%m-%d)'
        with open(fpath, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        fixed += 1

print(f'检查完成: {broken}个失效URL, {fixed}个文件已标记')
" >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M')] ✅ 图片URL检查完成" >> "$LOG"

# ── 4. 生成月度报告 ──
echo "[$(date '+%Y-%m-%d %H:%M')] 📊 生成月度报告..." >> "$LOG"
python3 tools/style_research.py --list > /tmp/style_coverage.txt 2>&1
python3 tools/style_image_scout.py --list > /tmp/image_coverage.txt 2>&1

cat > "$REPORT" << EOF
# 风格库月度报告 — $(date '+%Y年%m月')

## 覆盖率
$(head -3 /tmp/style_coverage.txt)
$(grep '覆盖率' /tmp/style_coverage.txt)
$(grep '覆盖率' /tmp/image_coverage.txt)

## 本月操作
- 发现新趋势: 查看 styles_universal/discover_prompt.txt
- 充实旧风格: $ENRICH_LIST
- 图片URL检查: 标记失效链接

## 待处理
- 查看 discover_prompt.txt 中的新趋势，确认是否入库
- 运行 python3 tools/style_research.py --list 查看完整状态
EOF

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ 月度报告: $REPORT" >> "$LOG"

echo "[$(date '+%Y-%m-%d %H:%M')] 🎉 月度自动学习完成" >> "$LOG"
