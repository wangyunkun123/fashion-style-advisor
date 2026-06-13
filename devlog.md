# 开发日志

## 2026-06-13: 微信效果图不显示问题 — 根因与解决方案

### 问题
微信推送效果图后，手机上图片加载不出来（或加载缓慢导致空白），连续多次重试无效。

### 根因
`raw.githubusercontent.com` 在国内网络环境下访问缓慢或被间歇性阻断。Server酱服务器在国内，通过 `raw.githubusercontent.com` 抓取图片嵌入微信消息时容易超时失败，导致微信端看不到图片。

### 解决方案
使用 **jsDelivr CDN** (`cdn.jsdelivr.net`) 替代 GitHub Raw URL。jsDelivr 在国内有 CDN 节点，加载速度快且稳定。

**URL 转换规则：**
```
❌ https://raw.githubusercontent.com/<user>/<repo>/<branch>/<path>
✅ https://cdn.jsdelivr.net/gh/<user>/<repo>@<branch>/<path>
```

### 永久防护措施
1. 微信推送图片统一使用 jsDelivr CDN URL
2. 生图后输出文件名加版本号（`_v2.jpg`）避免缓存混淆
3. `tools/sync_items.py` 自动格式化 items/ 文件名，杜绝卡片空白

### 相关 commit
- `70c599c` 修复 items/ 文件名格式
- `bcb1fbd` 添加 sync_items.py 自动同步脚本
- `2f79534` 切换为 jsDelivr CDN

---

## 2026-06-13: Phase 2 风格库 + 服装标签系统上线

### 产出
- **服装标签库**: 76件 Claude 视觉识别 + 结构化 JSON 标签（22个品牌识别）
- **风格库**: 8个风格指纹定义 + 五层匹配引擎
- **匹配引擎**: 608组预计算评分缓存
- **天气-场合自动推荐**: 基于温度/天气/场合自动选风格

### 核心文件
- `wardrobe/tags/*.json` — 76件标签
- `styles/*.json` — 8个风格指纹
- `tools/style_matcher.py` — 匹配引擎
- `tools/style_scorer.py` — 全量打分
- `config/style_defaults.json` — 天气-场合映射

### 风格匹配流程
```
用户指定风格 → style_matcher 排名 → 候选单品 → 搭配推荐
未指定风格 → auto_suggest(天气,场合) → 自动匹配 → 搭配推荐
```
