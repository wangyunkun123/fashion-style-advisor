# 开发日志

## 2026-06-13: 风格库 v2.0 完工 — 49风格百科 + 图片参考 + 自学习系统

### 产出
- **通用风格百科**: 49篇完整百科（文化史/美学/品牌/名人/秀场/趋势），9地域全覆盖
- **图片参考**: 416张杂志/秀场/街拍/名人图，HTML浏览页一键查看
- **自学习系统**: `--discover` 发现14趋势入库8个 + 月度自动学习
- **操作手册**: `styles_universal/README.md` 完整操作流程
- **女士风格库**: 列入 P1 升级计划，工具链完全可复用

### 架构
```
双层体系: 通用百科(知识层/49风格) + 个人指纹(匹配层/8风格)
自学习: 发现→研究→入库→图片搜集→月度报告→微信推送
```

### 定时任务
- 每月1日 9:07 自动: 发现趋势 + 充实5旧风格 + 图片URL校验 + 微信推送报告

---

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


## 2026-06-13: 用户打分系统上线

### 设计
三级评分：⭐⭐⭐满意 → ⭐⭐一般 → ⭐失望(二级反馈)
系统：templates/rating.html + wechat_control.py /rate端点 + rating_analyzer.py

### 测试结果
10套穿搭评分验证：正确识别日系City Boy为偏好风格(3.0/3)，Clean Fit为中性(1.8/3)，度假/街头为不匹配(1.0/3)

### 核心文件
- templates/rating.html — 移动端评分页面
- tools/rating_analyzer.py — 偏好分析引擎
- outfits/*/rating.json — 评分数据(.gitignore)

---

## 2026-06-13: Phase 2 全面完工 — 审美系统上线

### 核心交付

**服装标签库**
- 76件 Claude 视觉识别 + 结构化 JSON
- 22品牌识别：Adidas(5) Uniqlo(4) Nike(3) HLA(3) 等
- 每件含颜色向量/廓形/面料/图案/品牌/身形修饰

**通用风格百科 (双层架构)**
- 49风格百科（文化史/美学/品牌/名人/秀场/趋势），9地域全覆盖
- 416张参考图（杂志/秀场/街拍/名人/社交），HTML浏览页
- 8风格个人指纹（五层匹配引擎）+ 608组预计算评分缓存

**推送系统**
- 双版智能推送：🅰️简约版(无评分) 🅱️百科版(带评分+风格故事+单品解释+配色+参考图+备选)
- 首次推送双版+引导语，用户点击选择偏好
- 月度自动回访：30天(模式切换推荐) → 31天(后悔提醒) → 60天(再确认)
- 精准天气系统：实时API + 中文翻译 + 风险预警(暴雨/大风/高温/闷热)
- jsDelivr CDN解决GitHub Raw国内慢问题

**用户打分系统**
- 三级评分：⭐⭐⭐满意→增加推荐 ⭐⭐一般→累积分析 ⭐失望→二级反馈
- 移动端评分页面 + /rate HTTP端点
- 偏好分析引擎：月度报告(满意度分布/风格偏好/单品Top5/中立模式分析/1星原因)

**自学习系统**
- 月度自动：发现新趋势 + 充实5旧风格 + 图片URL校验 + 月度报告 + 微信推送
- 定时：每月1日 9:07 (Cron durable)

**项目优化**
- 清理冗余文件：composite.py tag_remap.py tag_compare.py 8个_discover.md 等
- 项目文件从~200精简到核心工具链
- CLAUDE.md + 系统升级建议.md 完整文档化

### 工具清单
| 工具 | 用途 |
|------|------|
| style_matcher.py | 五层风格匹配引擎 |
| style_scorer.py | 全量打分+缓存 |
| style_research.py | 风格研究代理(自学习) |
| style_image_scout.py | 图片搜集代理 |
| generate_encyclopedia_html.py | 百科HTML生成 |
| build_push.py | 智能推送(双版+偏好+评分) |
| weather_advisor.py | 精准天气顾问 |
| rating_analyzer.py | 偏好分析引擎 |
| monthly_checkin.py | 月度回访 |
| auto_learn.sh | 月度自动学习 |
| sync_items.py | 抠图同步 |
| composite_v2.py | 排版合成 |
| generate.py | Seedream生图 |
| wechat_control.py | HTTP服务+手机远程 |

### 数据文件
| 文件 | 说明 |
|------|------|
| wardrobe/tags/*.json | 76件服装标签 |
| wardrobe/tags/SCORE_CACHE.json | 608组评分缓存 |
| styles_universal/ | 49风格百科+图片 |
| config/push_preference.json | 推送偏好 |
| config/style_defaults.json | 天气-场合映射 |
