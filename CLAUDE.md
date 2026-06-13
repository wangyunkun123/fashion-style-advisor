# Fashion Style Advisor

AI 时尚顾问，专攻亚洲男性穿搭。用户画像和身形分析在 memory 中。

## 核心文件
- `wardrobe/服装档案.md` — 76件服装索引（TS-001 等 ID 体系），按品类分子目录存图
- `profile/analysis.md` — 用户身形分析
- `outfits/` — 按 `日期_场景` 组织每日穿搭
- `config/seedream.local.json` — API 密钥 + Server酱 SendKey（不提交 Git）

## 风格库
- `styles/` — 8个风格指纹定义（JSON）
- `wardrobe/tags/` — 76件服装结构化标签（JSON）
- `wardrobe/tags/SCORE_CACHE.json` — 608组风格兼容度缓存
- `tools/style_matcher.py` — 风格匹配引擎
- `config/style_defaults.json` — 天气-场合-风格默认映射

### 风格匹配流程
```
风格指定 → python3 tools/style_matcher.py <style_id> → 候选单品排名
       → python3 tools/style_matcher.py <style_id> <品类> → 某品类筛选
未指定   → python3 tools/style_matcher.py --auto <温度> <天气> <场合> → 自动推荐
```

## 通用风格百科
- `styles_universal/` — 41+风格百科全书（文化/历史/品牌/名人/秀场）
- `styles_universal/categories.json` — 五维风格分类体系
- `tools/style_research.py` — 风格研究代理（自学习系统）

### 风格研究操作
- **"研究风格"** → `python3 tools/style_research.py <style_id>` 生成研究提示词
- **"发现新风格"** → `python3 tools/style_research.py --discover`
- **"风格列表"** → `python3 tools/style_research.py --list`
- **"充实风格"** → `python3 tools/style_research.py --enrich <style_id>`

## 操作指令
- **"推荐穿搭"** → 读取 wardrobe + 天气 → 风格匹配筛选 → 给出搭配方案
- **"风格排名"** → `python3 tools/style_matcher.py <style_id>`
- **"风格矩阵"** → `python3 tools/style_scorer.py --matrix`
- **"生成效果图"** → 完整流程：Seedream生图 → 同步抠图 → composite_v2排版 → git push → 微信推送
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
