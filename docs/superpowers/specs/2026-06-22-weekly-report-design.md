# 穿搭周报系统设计

> 在现有「月度报告」基础上新增周报视图，默认显示周报，底部可切换月报。

**目标**：用户每周一看上周穿搭总结，同时保留月度综合报告。

**架构**：`rating_analyzer.py`（数据层）→ `build_prototype.py` / `wechat_control.py`（API 层）→ `prototype/mobile-v2.html`（展示层）

**涉及文件**：`tools/rating_analyzer.py`、`tools/wechat_control.py`、`tools/build_prototype.py`

---

## 一、展示层（手机端）

### 入口

复用现有「衣橱」Tab → segmented 控件中的「月度报告」按钮（`data-sub="monthly"`）。

按钮文案改为「📊 穿搭报告」，兼容周报和月报。

### 页面结构

```
┌──────────────────────────────────┐
│  📊 穿搭周报                      │
│  6/16 → 6/22 | 本周 5 次评分      │
│                                  │
│  ━━━ 📈 满意度 ━━━               │
│  ❤️ 满意 80%   🤔 一般 20%        │
│  📊 平均 2.8/3  📈 较上周 +0.2    │
│                                  │
│  ━━━ 🎯 本周风格 ━━━             │
│  ┌──────────┐ ┌──────────┐      │
│  │[穿搭缩略] │ │[穿搭缩略] │      │
│  │日系CityBoy│ │Clean Fit │      │
│  │ 3次 2.8分 │ │ 2次 2.5分 │      │
│  └──────────┘ └──────────┘      │
│                                  │
│  ━━━ 👔 最爱单品 ━━━             │
│  ┌──────────────────────────┐   │
│  │ [🧥缩略图] 宽松直筒牛仔裤  │   │
│  │            浅色水洗 · 4次  │   │
│  └──────────────────────────┘   │
│  ┌──────────────────────────┐   │
│  │ [👟缩略图] Nike空军一号    │   │
│  │            全白 · 3次     │   │
│  └──────────────────────────┘   │
│                                  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  📅 查看完整月度报告 →           │
└──────────────────────────────────┘
```

### 月度报告视图（点切换后）

```
┌──────────────────────────────────┐
│  📊 穿搭月报                      │
│  2026年6月 | 共 18 次评分         │
│                                  │
│  ━━━ 📈 满意度分布 ━━━           │
│  ❤️ 满意 69%  🤔 一般 19%        │
│  💔 失望 12%                     │
│  📊 平均 2.6/3                   │
│                                  │
│  ━━━ 🎯 风格偏好 ━━━             │
│  Clean Fit  ████████░░ 2.8分     │
│  韩系简约    ██████░░░░ 3.0分     │
│  ... (带缩略图的风格卡片)         │
│                                  │
│  ━━━ 👔 最爱单品 Top 5 ━━━      │
│  (同上缩略图格式)                │
│                                  │
│  ━━━ 🔍 中立模式分析 ━━━         │
│  ━━━ 💔 1星反馈原因 ━━━         │
│  ━━━ 💡 AI 建议 ━━━             │
│                                  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  ↩ 返回周报                       │
└──────────────────────────────────┘
```

### CSS 新增规则

- `.report-item-card` — 单品卡片（缩略图 + 文字横向布局）
- `.report-item-thumb` — 60×60 缩略图
- `.report-style-grid` — 风格卡片网格（2 列）
- `.report-style-card` — 单个风格卡（穿搭图 + 名称 + 次数 + 评分）
- `.report-style-img` — 风格穿搭缩略图（aspect-ratio: 4/3, object-fit: cover）
- `.report-toggle` — 底部切换按钮样式

---

## 二、数据层（rating_analyzer.py）

### 新增函数

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `filter_ratings_by_days(ratings, days)` | 评分列表 + 天数 | 过滤后列表 | 按 outfit 目录名前缀（YYYY-MM-DD）过滤 |
| `generate_weekly_report()` | 无 | 字符串 | 周报文本（原始，备命令行使用） |

### 数据结构扩展

`analyze()` 返回增加字段：
- `outfit_images` — `{style_id: image_url}` 映射，每个风格取评分最高的 outfit 缩略图

### API 端点（wechat_control.py 新增）

**`GET /api/report?period=weekly|monthly`**

返回 JSON：

```json
{
  "period": "weekly",
  "date_range": "6/16 → 6/22",
  "total_ratings": 5,
  "satisfaction_rate": 80,
  "neutral_rate": 20,
  "disappoint_rate": 0,
  "avg_rating": 2.8,
  "trend": 0.2,
  "trend_label": "较上周 ↑",
  "top_styles": [
    {
      "id": "clean_fit",
      "name": "Clean Fit",
      "count": 2,
      "avg_rating": 2.8,
      "image_url": "https://cdn.jsdelivr.net/gh/.../outfits/.../上身效果_1.png"
    }
  ],
  "top_items": [
    {
      "id": "SHOE-005",
      "name": "Nike Court Lite",
      "description": "入门级网球鞋 · 全白配色",
      "count": 3,
      "thumbnail_url": "https://cdn.jsdelivr.net/gh/.../wardrobe/enhanced/SHOE-005_cutout_thumb.png"
    }
  ]
}
```

### 缩略图 URL 生成

- 单品缩略图：`wardrobe/enhanced/{ID}_cutout_thumb.png` → CDN URL
- 风格穿搭图：遍历该风格 outfits，取评分最高的 `上身效果_1.png` → CDN URL
- CDN base：`https://cdn.jsdelivr.net/gh/wangyunkun123/fashion-style-advisor@{commit_hash}/`

---

## 三、定时调度

| 任务 | Cron | 命令 |
|------|------|------|
| 周报数据预生成 | 每周一 8:57 | `curl -s http://localhost:8765/cmd --data-urlencode "t=生成周报"` |
| 月报 | 每月1号 8:57 | `curl -s http://localhost:8765/cmd --data-urlencode "t=偏好报告"` |
| 每日穿搭 | 每天 5:57 | (现有，不变) |

周报/月报都是手机端打开时实时调 `/api/report` 返回最新数据，Cron 只是预热缓存。

**7 天过期提醒**：Claude Cron 7 天自动过期，需到期前重建。月报 cron 同理。

---

## 四、兜底规则

| 场景 | 处理 |
|------|------|
| 本周 0 评分 | 自动扩到 14 天；仍为 0 显示「暂无评分」 |
| 上周无数据 | 趋势行不显示（不强行对比 0） |
| 风格数据无图 | 用纯色背景 + 风格名文字占位 |
| 某风格无 `上身效果_1.png` | 取该风格任意 outfit 图，都无则用纯色占位 |
| CDN 未更新 | 用本地 `/wardrobe/enhanced/` 路径兜底 |

---

## 五、改动范围

| 文件 | 改动内容 |
|------|---------|
| `tools/rating_analyzer.py` | +`filter_ratings_by_days()`, +`generate_weekly_report()`, `--weekly` 标志 |
| `tools/wechat_control.py` | +`/api/report` 端点，返回周报/月报 JSON（含缩略图 URL） |
| `tools/build_prototype.py` | 修改 `sub-monthly` 子页 HTML + JS：默认周报，底部月报切换；单品缩略图卡片；风格穿搭图卡片 |

---

## 六、不改动

- 现有「月度报告」API `/api/wardrobe/stats` 保持不变
- `monthly_checkin.py` 月度回访逻辑不变
- 手机端 Tab Bar / 页面结构不变
- 微信推送流程不变
