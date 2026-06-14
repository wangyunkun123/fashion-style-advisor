# Fashion Style Advisor

AI 时尚顾问，专攻亚洲男性穿搭。用户画像和身形分析在 memory 中。

## 核心文件
- `wardrobe/服装档案.md` — 76件服装索引（TS-001 等 ID 体系），按品类分子目录存图
- `profile/analysis.md` — 用户身形分析
- `outfits/` — 按 `日期_场景` 组织每日穿搭
- `config/seedream.local.json` — API 密钥 + Server酱 SendKey（不提交 Git）

## 风格库
- `styles_universal/` — 49风格百科（知识层）：文化/历史/品牌/名人/秀场/图片
- `styles/` — 8风格指纹（匹配层）：五层评分引擎
- `wardrobe/tags/` — 76件服装结构化标签 + 608组评分缓存
- `config/style_defaults.json` — 天气-场合-风格映射

### 风格库操作
| 操作 | 命令 |
|------|------|
| 研究风格 | `python3 tools/style_research.py <style_id>` |
| 发现新趋势 | `python3 tools/style_research.py --discover` |
| 查看覆盖 | `python3 tools/style_research.py --list` |
| 搜集图片 | `python3 tools/style_image_scout.py <style_id>` |
| 浏览图库 | `open styles_universal/references/gallery.html` |
| 风格排名 | `python3 tools/style_matcher.py <style_id>` |
| 自动推荐 | `python3 tools/style_matcher.py --auto <温度> <天气> <场合>` |

> 📖 完整操作手册: `styles_universal/README.md`

## 操作指令
- **"推荐穿搭"** → 读取 wardrobe + 天气 → 风格匹配筛选 → 给出搭配方案
- **"推送穿搭"** → `python3 tools/build_push.py <outfit_dir>` — 百科增强推送（冷知识+单品解释+配色+备选风格）
- **"风格排名"** → `python3 tools/style_matcher.py <style_id>`
- **"风格矩阵"** → `python3 tools/style_scorer.py --matrix`
- **"分析偏好"** → `python3 tools/rating_analyzer.py --report`
- **"生成效果图"** → Seedream生图 → sync_items同步 → composite_v2排版 → git push → build_push推送

## 微信推送
首次双版+引导语，用户点击选择。简介版去评分，百科版带评分。月度自动回访。

| 版本 | 引导语 | 评分 | 月度回访 |
|------|--------|------|---------|
| 🅰️ 简介版 | 不想费心，每天一套穿好就走 👌 | ❌ | 30天→"想继续躺平？" |
| 🅱️ 百科版 | 想跟AI一起探索风格，越穿越懂自己 🧠✨ | ✅ | 30天→"AI学会你了，换简约？" |
| 31天 | 后悔提醒：想改回上一版？ |
| 60天 | 再确认：还是喜欢现在的方式？ |

```bash
python3 tools/build_push.py <outfit_dir>              # 按偏好推送
python3 tools/build_push.py --set simple|rich|both     # 设置偏好
python3 tools/monthly_checkin.py                       # 月度回访（auto_learn.sh自动调用）
```
> 完整生图流程：`outfit.md` → `generate.py` → `sync_items.py` → `composite_v2.py` → `git push` → `build_push.py`

## 用户打分
推送底部自动带评分链接。三级评分 + 偏好学习。

| 评分 | 含义 | 系统动作 |
|------|------|---------|
| ⭐⭐⭐ | 满意 | 增加该风格权重 + 单品优先级提升 |
| ⭐⭐ | 一般 | 累积≥3次后分析重合点，降低频率 |
| ⭐ | 失望 | 弹出二级反馈(风格/场景/搭配/单品) → 标记为不推荐 |

```bash
python3 tools/rating_analyzer.py --report    # 月度偏好报告
python3 tools/rating_analyzer.py --summary   # 简要统计
```
数据存储在 `outfits/<id>/rating.json`（已加入 .gitignore），不提交到 Git。
- **"排版"/"合成"** → `python3 tools/composite_v2.py <outfit_dir>`
- **"同步"/"推送"** → `bash sync.sh`
- **"添加新衣服"** → 放入 wardrobe → 更新服装档案.md → auto_orient → enhance_clothing
- **"新想法"** → 记录到 `系统升级建议.md`

## 生图完整流程
1. Seedream API 生图 → `outfits/<日期>_<风格>/豆包生图/`
2. **同步抠图**：`python3 tools/sync_items.py <dir>` → 自动复制 `_cutout.png` 并命名为 `{ID}_{名称}_cutout.png`
3. `python3 tools/composite_v2.py <dir>` → 生成 `_直角画册.jpg`
4. `git add -A && git commit && git push`
5. `wechat_control.py` 内 `push_wechat()` 推送效果图

> ⚠️ items/ 文件名必须为 `{ID}_{名称}_cutout.png` 格式（如 `SHIRT-004_黑白格纹长袖衬衫_cutout.png`），否则 composite_v2 找不到衣服。用 `sync_items.py` 自动处理。
> ⚠️ 微信推送图片必须用 jsDelivr CDN URL（`cdn.jsdelivr.net/gh/...`），不能用 GitHub Raw（`raw.githubusercontent.com` 国内慢/被阻断）。`push_wechat()` 已内置自动转换。

## 手机远程控制
- 启动：`bash tools/start_wechat_control.sh`
- 手机通过 ngrok HTTPS URL 访问 HTML 面板
- 端口 8765，详情见 `memory/wechat-remote-control.md`

## Git
- Remote: `git@github.com:wangyunkun123/fashion-style-advisor.git` (SSH)
- Web: https://github.com/wangyunkun123/fashion-style-advisor (public)
