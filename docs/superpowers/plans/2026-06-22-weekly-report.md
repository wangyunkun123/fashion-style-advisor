# 穿搭周报系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在手机端「月度报告」位置新增周报视图（默认显示），单品缩略图 + 风格穿搭图视觉化

**Architecture:** rating_analyzer.py（数据）→ wechat_control.py `/api/report`（API）→ build_prototype.py（HTML 生成）→ prototype/mobile-v2.html（手机展示）

**Tech Stack:** Python 3, vanilla HTML/CSS/JS, cron

## Global Constraints

- 复用现有「月度报告」segmented 按钮，改名为「📊 穿搭报告」
- 默认显示周报（`/api/report?period=weekly`），底部「查看完整月度报告」切换
- 单品用 `wardrobe/enhanced/{ID}_cutout_thumb.png` 缩略图，风格用评分最高 outfit 的 `上身效果_1.png`
- 周报 cron 每周一 8:57，月报 cron 每月 1 号 8:57
- 不破坏现有 `/api/wardrobe/stats` 月度统计 API（保留但不再作为唯一入口）
- `rating_analyzer.py` 数据层已完成（Task 0 验证即可）

---

### Task 0: 验证数据层就绪

**Files:**
- Verify: `tools/rating_analyzer.py:110-175`

**Interfaces:**
- Produces: `filter_ratings_by_days(ratings, days=7)` → list, `generate_weekly_report()` → str
- These are already implemented, just need to verify they work

- [ ] **Step 1: Run weekly report and verify output**

```bash
cd /Users/rabbit/Claude\ code/Fashion && python3 tools/rating_analyzer.py --weekly
```

Expected: 输出周报文本，包含「📊 穿搭周报」「📈 本周满意度」「🎯 本周风格」「👔 本周最爱」

- [ ] **Step 2: Verify monthly report still works**

```bash
cd /Users/rabbit/Claude\ code/Fashion && python3 tools/rating_analyzer.py --report
```

Expected: 输出完整月报，包含「📊 穿搭偏好月度报告」「📈 满意度分布」「🎯 风格偏好」「🔍 中立模式分析」

- [ ] **Commit checkpoint** (if any fixes needed)

---

### Task 1: 新增 /api/report API 端点

**Files:**
- Modify: `tools/wechat_control.py` (在 `/api/wardrobe/stats` 区块之后插入新端点)

**Interfaces:**
- Consumes: `rating_analyzer.load_all_ratings()`, `rating_analyzer.analyze()`, `rating_analyzer.filter_ratings_by_days()`
- Produces: `GET /api/report?period=weekly|monthly` → JSON `{period, date_range, total_ratings, satisfaction_rate, avg_rating, trend, top_styles: [{id, name, count, avg_rating, image_url}], top_items: [{id, name, description, count, thumbnail_url}]}`

- [ ] **Step 1: Add /api/report route in wechat_control.py**

在 `/api/wardrobe/stats` 的 `return` 之后、`# 冷门单品` 注释之前插入以下路由：

```python
        # 周报/月报 API
        if parsed.path == '/api/report':
            try:
                from rating_analyzer import load_all_ratings, analyze, filter_ratings_by_days
                from urllib.parse import parse_qs
                params = parse_qs(parsed.query or '')
                period = params.get('period', ['weekly'])[0]
                
                all_ratings = load_all_ratings()
                
                if period == 'weekly':
                    ratings = filter_ratings_by_days(all_ratings, 7)
                    if not ratings:
                        ratings = filter_ratings_by_days(all_ratings, 14)
                    prev_ratings = filter_ratings_by_days(all_ratings, 14)
                    prev_ratings = [r for r in prev_ratings if r not in ratings]
                else:
                    ratings = all_ratings
                    prev_ratings = []
                
                if not ratings:
                    self._json_resp(200, {'period': period, 'empty': True, 'message': '暂无评分数据'})
                    return
                
                analysis = analyze(ratings)
                prev_analysis = analyze(prev_ratings) if prev_ratings else None
                
                # 日期范围
                dates = sorted(set(r.get('outfit_id', '')[:10] for r in ratings))
                date_range = f"{dates[0][5:]} → {dates[-1][5:]}" if len(dates) > 1 else (dates[0][5:] if dates else '')
                
                # 趋势
                trend = 0
                trend_label = ''
                if prev_analysis and prev_analysis['total'] >= 1:
                    trend = round(analysis['avg_rating'] - prev_analysis['avg_rating'], 1)
                    if trend > 0.2:
                        trend_label = f'📈 较上周 ↑ {trend:+.1f}'
                    elif trend < -0.2:
                        trend_label = f'📉 较上周 ↓ {trend:+.1f}'
                    else:
                        trend_label = f'📊 较上周持平'
                
                # 风格排行 + 穿搭图
                top_styles = []
                for sid, data in sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])[:3]:
                    image_url = _find_style_image(sid)
                    top_styles.append({
                        'id': sid,
                        'name': STYLE_NAMES.get(sid, sid),
                        'count': data['total'],
                        'avg_rating': data['avg'],
                        'image_url': image_url,
                    })
                
                # 最爱单品 + 缩略图
                top_items = []
                for iid, cnt in list(analysis['items_liked'].items())[:5]:
                    name = iid
                    desc = ''
                    tag_path = os.path.join(TAGS_DIR, f'{iid}.json')
                    if os.path.exists(tag_path):
                        with open(tag_path) as f:
                            tag = json.load(f)
                        name = tag.get('brand', {}).get('name', '') or tag.get('category_display', iid)
                        hue = tag.get('color', {}).get('hue_name', '')
                        series = tag.get('brand', {}).get('series', '') or tag.get('style_culture', {}).get('aesthetic', '')
                        desc_parts = [p for p in [hue, series] if p]
                        desc = ' · '.join(desc_parts) if desc_parts else tag.get('claude_fit_comment', '')[:30]
                    thumb_url = _find_item_thumbnail(iid)
                    top_items.append({
                        'id': iid,
                        'name': name,
                        'description': desc,
                        'count': cnt,
                        'thumbnail_url': thumb_url,
                    })
                
                # 月报额外数据
                result = {
                    'period': period,
                    'date_range': date_range,
                    'total_ratings': analysis['total'],
                    'satisfaction_rate': analysis['satisfaction_rate'],
                    'neutral_rate': analysis['neutral_rate'],
                    'disappoint_rate': analysis['disappoint_rate'],
                    'avg_rating': analysis['avg_rating'],
                    'trend': trend,
                    'trend_label': trend_label,
                    'top_styles': top_styles,
                    'top_items': top_items,
                }
                
                if period == 'monthly':
                    from rating_analyzer import find_neutral_patterns
                    neutral = find_neutral_patterns(all_ratings)
                    result['neutral_analysis'] = neutral['summary'] if neutral else []
                    result['feedback_reasons'] = analysis.get('feedback_reasons', {})
                    # AI 建议
                    suggestions = []
                    if analysis['satisfaction_rate'] >= 60:
                        suggestions.append('✅ 整体满意度良好，继续当前推荐策略')
                    elif analysis['satisfaction_rate'] >= 40:
                        suggestions.append('⚠️ 满意度中等，建议调整推荐权重')
                    else:
                        suggestions.append('❌ 满意度偏低，需要重新评估风格匹配')
                    sorted_styles = sorted(analysis['by_style'].items(), key=lambda x: -x[1]['avg'])
                    if len(sorted_styles) >= 2:
                        best = sorted_styles[0]
                        worst = sorted_styles[-1]
                        if best[0] != worst[0] and worst[1]['avg'] < 2:
                            suggestions.append(f"💡 建议增加 {STYLE_NAMES.get(best[0], best[0])} 推荐，减少 {STYLE_NAMES.get(worst[0], worst[0])}")
                    result['suggestions'] = suggestions
                
                self._json_resp(200, result)
                return
            except Exception as e:
                log(f"周报API异常: {e}", "ERROR")
                self._json_resp(500, {"error": str(e)})
                return
```

- [ ] **Step 2: Add helper functions before the route**

在 `/api/report` 路由之前的类中（或文件顶部工具函数区）添加两个辅助函数：

```python
def _find_item_thumbnail(item_id):
    """查找单品缩略图 URL，优先 CDN 后本地"""
    thumb_path = os.path.join(PROJECT_DIR, 'wardrobe', 'enhanced', f'{item_id}_cutout_thumb.png')
    if os.path.exists(thumb_path):
        # 尝试 CDN URL
        try:
            h = _sp.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=PROJECT_DIR).stdout.strip()
            cdn = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/wardrobe/enhanced/{item_id}_cutout_thumb.png'
            return cdn
        except:
            return f'/wardrobe/enhanced/{item_id}_cutout_thumb.png'
    return ''


def _find_style_image(style_id):
    """查找某风格评分最高的 outfit 效果图 URL"""
    best_img = ''
    best_rating = -1
    outfits_base = os.path.join(PROJECT_DIR, 'outfits')
    if not os.path.isdir(outfits_base):
        return ''
    for d in sorted(os.listdir(outfits_base), reverse=True):
        rpath = os.path.join(outfits_base, d, 'rating.json')
        img_path = os.path.join(outfits_base, d, '上身效果', '上身效果_1.png')
        if not os.path.exists(rpath) or not os.path.exists(img_path):
            continue
        try:
            with open(rpath) as f:
                r = json.load(f)
            if r.get('style_id', '') == style_id and r.get('rating', 0) > best_rating:
                best_rating = r['rating']
                # 构建 CDN URL
                try:
                    h = _sp.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=PROJECT_DIR).stdout.strip()
                    best_img = f'https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{h}/outfits/{d}/上身效果/上身效果_1.png'
                except:
                    best_img = f'/outfits/{d}/上身效果/上身效果_1.png'
        except:
            pass
    return best_img
```

注意：`STYLE_NAMES` 和 `TAGS_DIR` 常量需在路由代码前引用，从 rating_analyzer import：
```python
from rating_analyzer import STYLE_NAMES
# TAGS_DIR 在文件顶部已有定义或需添加：
# TAGS_DIR = os.path.join(PROJECT_DIR, 'wardrobe', 'tags')
```

- [ ] **Step 3: Test API endpoints**

```bash
# 启动服务器后测试
curl -s http://localhost:8765/api/report?period=weekly | python3 -m json.tool | head -30
curl -s http://localhost:8765/api/report?period=monthly | python3 -m json.tool | head -30
```

Expected: 返回完整 JSON，包含 `top_items[0].thumbnail_url` 和 `top_styles[0].image_url`

- [ ] **Step 4: Commit**

```bash
git add tools/wechat_control.py
git commit -m "feat: 新增 /api/report 周报/月报 API 端点"
```

---

### Task 2: 更新手机端显示（build_prototype.py）

**Files:**
- Modify: `tools/build_prototype.py:769-780` (CSS), `tools/build_prototype.py:1014` (按钮文案), `tools/build_prototype.py:1028-1031` (HTML), `tools/build_prototype.py:1413` (JS)

**Interfaces:**
- Consumes: `GET /api/report?period=weekly|monthly` (from Task 1)
- Produces: Updated `prototype/mobile-v2.html` with visual weekly/monthly report

- [ ] **Step 1: Modify segmented button text**

In `build_prototype.py`, change line 1014:
```python
# OLD:
<div class="segmented" id="wrd-seg"><div class="seg-btn active" data-sub="my">我的衣橱</div><div class="seg-btn" data-sub="monthly">月度报告</div>...
# NEW:
<div class="segmented" id="wrd-seg"><div class="seg-btn active" data-sub="my">我的衣橱</div><div class="seg-btn" data-sub="monthly">📊 穿搭报告</div>...
```

- [ ] **Step 2: Add new CSS rules**

在 `build_prototype.py` 的 CSS 区块末尾（`</style>` 之前）添加：

```python
# 报告页新样式（追加到现有 .wrd-monthly 样式之后）
css_addon = """
.report-item-card{display:flex;align-items:center;gap:12px;background:var(--white);border-radius:10px;padding:12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.report-item-thumb{width:56px;height:56px;border-radius:8px;object-fit:contain;background:#f5f0eb;flex-shrink:0}
.report-item-info{flex:1;min-width:0}
.report-item-name{font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px}
.report-item-desc{font-size:11px;color:var(--muted)}
.report-item-count{font-size:11px;color:var(--navy);font-weight:600;margin-top:2px}
.report-style-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}
.report-style-card{background:var(--white);border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.report-style-img{width:100%;aspect-ratio:4/3;object-fit:cover;background:#eef2f7}
.report-style-placeholder{width:100%;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;background:var(--navy);color:#fff;font-size:13px;font-weight:600;text-align:center;padding:8px}
.report-style-info{padding:8px 10px}
.report-style-name{font-size:12px;font-weight:600;color:var(--text)}
.report-style-meta{font-size:10px;color:var(--muted)}
.report-toggle-btn{display:block;width:100%;padding:14px;margin-top:12px;background:var(--white);border:1.5px dashed var(--navy);border-radius:12px;color:var(--navy);font-size:14px;font-weight:600;text-align:center;cursor:pointer}
.report-toggle-btn:active{background:#f0edf5}
.report-section-title{font-size:13px;font-weight:700;color:var(--text);margin:16px 0 8px}
.report-section-title:first-child{margin-top:0}
.report-empty{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}
"""
```

将 `css_addon` 插入到 CSS 字符串中 `.wrd-monthly` 样式块之后。

- [ ] **Step 3: Update HTML container**

在 `build_prototype.py` 中，将第 1029-1030 行改为：
```python
# OLD:
<div class="wrd-sub" id="sub-monthly" style="display:none">
<div id="wrd-monthly-content"><div class="wrd-loading">加载中...</div></div>
</div>
# NEW:
<div class="wrd-sub" id="sub-monthly" style="display:none">
<div id="wrd-report-content"><div class="wrd-loading">加载中...</div></div>
</div>
```

- [ ] **Step 4: Replace JS function loadMonthlyReport() with loadReport()**

将现有的 `loadMonthlyReport()` 函数（约在 line 1413）替换为：

```javascript
function loadReport(period){{
period = period || 'weekly';
var el = document.getElementById('wrd-report-content');
el.innerHTML = '<div class="wrd-loading">加载中...</div>';
fetch('/api/report?period=' + period).then(function(r){{return r.json()}}).then(function(d){{
if(d.empty){{el.innerHTML='<div class="report-empty">📊 暂无评分数据<br><span style="font-size:12px;color:var(--muted)">评分后会在这里生成报告</span></div>';return}}
var html = '<div class="wrd-monthly">';

// 标题行
var periodLabel = d.period === 'weekly' ? '📊 穿搭周报' : '📊 穿搭月报';
html += '<div class="wm-card"><div class="wm-title">' + periodLabel + '</div>';
html += '<div style="font-size:11px;color:var(--muted);margin-bottom:8px">📅 ' + escHtml(d.date_range) + ' | ' + d.total_ratings + ' 次评分</div>';

// 满意度
html += '<div class="wm-stat-row"><div class="wm-stat-item"><div class="wm-stat-val" style="color:#e74c3c">' + d.satisfaction_rate + '%</div><div class="wm-stat-lbl">❤️ 满意</div></div>';
html += '<div class="wm-stat-item"><div class="wm-stat-val">' + d.neutral_rate + '%</div><div class="wm-stat-lbl">🤔 一般</div></div>';
html += '<div class="wm-stat-item"><div class="wm-stat-val">' + d.avg_rating + '</div><div class="wm-stat-lbl">⭐ 均分</div></div></div>';
if(d.trend_label) html += '<div style="font-size:11px;color:var(--muted);margin-top:4px">' + escHtml(d.trend_label) + '</div>';
html += '</div>'; // wm-card

// 风格排行（带图）
if(d.top_styles && d.top_styles.length){{
html += '<div class="report-section-title">🎯 ' + (d.period === 'weekly' ? '本周风格' : '风格偏好') + '</div>';
html += '<div class="report-style-grid">';
d.top_styles.forEach(function(s){{
html += '<div class="report-style-card">';
if(s.image_url){{
html += '<img class="report-style-img" src="' + s.image_url + '" alt="' + escHtml(s.name) + '" loading="lazy">';
}} else {{
html += '<div class="report-style-placeholder">' + escHtml(s.name) + '</div>';
}}
html += '<div class="report-style-info"><div class="report-style-name">' + escHtml(s.name) + '</div>';
html += '<div class="report-style-meta">' + s.count + '次 · ' + s.avg_rating + '分</div></div>';
html += '</div>';
}});
html += '</div>';
}}

// 最爱单品（带缩略图）
if(d.top_items && d.top_items.length){{
html += '<div class="report-section-title">👔 ' + (d.period === 'weekly' ? '本周最爱' : '最爱单品') + '</div>';
d.top_items.forEach(function(item){{
html += '<div class="report-item-card">';
if(item.thumbnail_url){{
html += '<img class="report-item-thumb" src="' + item.thumbnail_url + '" alt="' + escHtml(item.id) + '" loading="lazy">';
}} else {{
html += '<div class="report-item-thumb" style="display:flex;align-items:center;justify-content:center;font-size:20px">👔</div>';
}}
html += '<div class="report-item-info">';
html += '<div class="report-item-name">' + escHtml(item.name) + '</div>';
if(item.description) html += '<div class="report-item-desc">' + escHtml(item.description) + '</div>';
html += '<div class="report-item-count">穿过 ' + item.count + ' 次</div>';
html += '</div></div>';
}});
}}

// 月报专属：中立分析 + AI 建议
if(d.period === 'monthly'){{
if(d.neutral_analysis && d.neutral_analysis.length){{
html += '<div class="wm-card"><div class="wm-title">🔍 中立模式分析</div>';
d.neutral_analysis.forEach(function(s){{html += '<div style="font-size:11px;color:var(--sub);margin-bottom:4px">' + escHtml(s) + '</div>'}});
html += '</div>';
}}
if(d.suggestions && d.suggestions.length){{
html += '<div class="wm-card"><div class="wm-title">💡 AI 建议</div>';
d.suggestions.forEach(function(s){{html += '<div style="font-size:11px;color:var(--sub);margin-bottom:4px">' + escHtml(s) + '</div>'}});
html += '</div>';
}}
}}

// 底部切换按钮
html += '</div>'; // wrd-monthly
if(d.period === 'weekly'){{
html += '<button class="report-toggle-btn" onclick="loadReport(\'monthly\')">📅 查看完整月度报告 →</button>';
}} else {{
html += '<button class="report-toggle-btn" onclick="loadReport(\'weekly\')">↩ 返回周报</button>';
}}
el.innerHTML = html;
}}).catch(function(e){{el.innerHTML='<div class="report-empty">⚠️ 加载失败<br><span style="font-size:12px">' + e.message + '</span></div>'}});
}}

function loadMonthlyReport(){{loadReport('weekly')}}
```

注意：`loadMonthlyReport()` 保留为兼容函数，内部直接调用 `loadReport('weekly')`。原来 `loadMonthlyReport` 在 segmented 点击事件中被调用，现在它默认加载周报。

- [ ] **Step 5: Rebuild prototype and verify**

```bash
cd /Users/rabbit/Claude\ code/Fashion && python3 tools/build_prototype.py
```

Expected: 无错误输出，`prototype/mobile-v2.html` 重新生成

```bash
# 检查新 HTML 包含关键元素
grep -c "report-style-grid" prototype/mobile-v2.html  # > 0
grep -c "report-item-card" prototype/mobile-v2.html   # > 0
grep -c "loadReport" prototype/mobile-v2.html          # > 0
grep -c "📊 穿搭报告" prototype/mobile-v2.html         # > 0
```

- [ ] **Step 6: Commit**

```bash
git add tools/build_prototype.py prototype/mobile-v2.html
git commit -m "feat: 手机端周报视图 — 单品缩略图 + 风格穿搭图 + 月报切换"
```

---

### Task 3: 设置周报 Cron 任务

**Files:**
- Modify: `.claude/scheduled_tasks.json` (via CronCreate tool)

- [ ] **Step 1: Create weekly cron job (Monday 8:57 AM)**

```
Cron: 57 8 * * 1
Prompt: curl -s -G http://localhost:8765/cmd --data-urlencode "t=偏好报告"
Durable: true
Recurring: true
```

This fires every Monday at 8:57 AM, hitting the server to pre-warm the weekly report data.

- [ ] **Step 2: Create monthly cron job (1st of month 8:57 AM)**

```
Cron: 57 8 1 * *
Prompt: curl -s -G http://localhost:8765/cmd --data-urlencode "t=偏好报告"
Durable: true
Recurring: true
```

This fires on the 1st of every month to ensure monthly report data is fresh.

- [ ] **Step 3: Verify cron jobs are registered**

```bash
# Check scheduled tasks
cat .claude/scheduled_tasks.json
```

Expected: Two durable recurring entries for weekly and monthly.

---

### Task 4: 端到端验证 + 日志

**Files:**
- Modify: `devlog.md`, `devlog/2026-06-22.md`

- [ ] **Step 1: Full flow test**

```bash
# 1. 确认服务器运行
curl -s http://localhost:8765/health | python3 -m json.tool

# 2. 测试周报 API
curl -s "http://localhost:8765/api/report?period=weekly" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'周报: {d[\"total_ratings\"]}次评分, {d[\"satisfaction_rate\"]}%满意, {len(d[\"top_items\"])}件单品')"

# 3. 测试月报 API
curl -s "http://localhost:8765/api/report?period=monthly" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'月报: {d[\"total_ratings\"]}次评分, 风格数{len(d[\"top_styles\"])}')"

# 4. 重建原型
python3 tools/build_prototype.py

# 5. 验证原型包含新元素
grep -c "report-style-grid" prototype/mobile-v2.html
grep -c "report-item-thumb" prototype/mobile-v2.html
```

- [ ] **Step 2: Git push**

```bash
cd /Users/rabbit/Claude\ code/Fashion && git push
```

- [ ] **Step 3: Update devlog**

在 `devlog.md` 顶部添加摘要行，在 `devlog/2026-06-22.md` 追加周报功能记录：

```markdown
## 穿搭周报系统

### 背景
用户希望每周看到穿搭评分总结，同时保留月度综合报告。服装少，月报间隔太长。

### 实现
- rating_analyzer.py: +filter_ratings_by_days(), +generate_weekly_report(), --weekly 标志
- wechat_control.py: +/api/report?period=weekly|monthly API，返回含缩略图URL的JSON
- build_prototype.py: 月度报告→穿搭报告，默认周报+月报切换，单品缩略图+风格穿搭图
- Cron: 每周一8:57预热周报，每月1号8:57预热月报

### 改动文件
| 文件 | 改动 |
|------|------|
| tools/rating_analyzer.py | +70行（filter + weekly_report） |
| tools/wechat_control.py | +100行（/api/report + 辅助函数） |
| tools/build_prototype.py | +80行（CSS + HTML + JS重写）|
| .claude/scheduled_tasks.json | +2 cron 任务 |
```

- [ ] **Step 4: Commit devlog**

```bash
git add devlog.md devlog/2026-06-22.md
git commit -m "📝 周报系统开发日志"
```
