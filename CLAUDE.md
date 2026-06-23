# Fashion Style Advisor

AI 时尚顾问，专攻亚洲男性穿搭。用户画像和身形分析在 memory 中。

## 核心文件
- `wardrobe/服装档案.md` — 76件服装索引（TS-001 等 ID 体系），按品类分子目录存图
- `profile/analysis.md` — 用户身形分析
- `outfits/` — 按 `日期_场景` 组织每日穿搭
- `config/seedream.local.json` — API 密钥（不提交 Git）
- `prototype/mobile-v2.html` — 手机控制台原型（由 `build_prototype.py` 自动生成，勿手动编辑）
- `prototype/icons-set.html` — 83个自定义图标库预览（Clothing-Icons + Lucide）
- `prototype/icons-tab.json` — Tab Bar 图标配置映射

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

### 女性风格库（styles_women/）
| 操作 | 命令 |
|------|------|
| 研究风格 | `python3 tools/style_research_agent.py WF-01` |
| 查看集群 | `python3 tools/style_research_agent.py --list-clusters` |
| 批量生成 | `python3 tools/style_research_agent.py --batch-female` |
| 旧版研究 | `python3 tools/style_research.py <style_id>` (仅男性风格) |

> 📖 完整操作手册: `styles_women/README.md`
> 📚 共享知识层: `styles_women/_shared/` (3 集群品牌矩阵+文化背景)

### 趋势分类（trend_category）— 六维分类体系
每个风格自动标注三级趋势分类：🔥 流行趋势 / 🏛️ 经典风格 / 🎭 小众领域。

| 操作 | 命令 |
|------|------|
| 查看趋势分布 | `python3 tools/style_research.py --list` (男性) / `python3 tools/style_research_agent.py --list-clusters` (女性) |
| 自动归类 | 研究工具内置 `auto_classify_trend_category()` |
| 手动归类 | 编辑 `styles_universal/categories.json` 或 `styles_women/categories.json` 的 `trend_category` 字段 |
| 重新生成 HTML | `python3 tools/generate_encyclopedia_html.py` (含彩色趋势标签) |

分类决策树：`aesthetic==avant_garde → niche` > `era==classic → classic` > `复古+street→niche` > `2020s+TikTok原生集群→trend`

边界原则：
- TikTok 标签 + 古老美学 → 看品牌生态（老钱风→经典，Royalcore→趋势）
- 被收编的亚文化 40+ 年 → 经典（Mod）；反建制核心 → 小众（Punk）
- 从趋势转入小众 → 按当前状态（暗黑学院→小众）

## 操作指令
- **"推荐穿搭"** → 读取 wardrobe + 天气 → 风格匹配筛选 → 给出搭配方案
- **"风格排名"** → `python3 tools/style_matcher.py <style_id>`
- **"风格矩阵"** → `python3 tools/style_scorer.py --matrix`
- **"分析偏好"** → `python3 tools/rating_analyzer.py --report`
- **"生成效果图"** → 两轮接力Seedream生图（抠图参考）→ composite_v2排版 → git push

## 用户打分
手机端内嵌评分。三级评分 + 偏好学习。

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
- **"重建原型"** → `python3 tools/build_prototype.py`
- **"添加新衣服"** → 放入 wardrobe → 更新服装档案.md → auto_orient → enhance_clothing → 生成缩略图 `python3 tools/generate_thumbnails.py <ID>`
- **"搜索图片"/"找图"** → `python3 tools/fashion_image_search.py --query "<关键词>"` — 免费服装图片搜索
- **"采集小红书"** → 两步走：① Playwright 浏览器搜索 `python3 tools/xiaohongshu_scraper.py --search "<关键词>"`（过一次验证码） → ② `xhs read <id> --json` 提取详情（无验证码） → 写入 `encyclopedia.md`（详见 `tools/小红书采集流程.md`）
- **"XHS读笔记"** → `xhs read <note_id或url> --json`（免验证码，直接API读取）
- **"采集Instagram"/"搜INS"** → `python3 tools/instagram_search.py --query "<关键词>"`（无需登录，详见 `tools/Instagram采集流程.md`）
- **"双平台采集"** → 小红书 Top 5 + Instagram Top 5 → 下载封面 → 写入百科 + 更新 `images_meta.json`
- **"新想法"** → 记录到 `系统升级建议.md`
- **"衣橱分析"** → `python3 tools/wardrobe_advisor.py --report`

## 手机控制台（2026-06-15 改版）

### 页面结构
```
┌─ Hero 区（最新穿搭效果图 + 风格标签 + 配色条）──┐
├─ 单品清单（3列网格 + Clothing-Icons 图标）─────┤
├─ 其他推荐（横向卡片 + 换一批按钮）─────────────┤
├─ 历史推荐（可展开穿搭卡片 + 风格标签）─────────┤
├─ 输入框 ─── [输入需求… ▶] ───────────────────┤
├─ Tab Bar ────────────────────────────────────┤
│  🧠推荐  🧪探索  👔衣橱  ➕添加  ⚙️设置          │
└──────────────────────────────────────────────┘
```

| Tab | 功能 |
|-----|------|
| 🧠 推荐 | 一键推荐今日穿搭（首次返回已有，后续生成新品） |
| 🧪 探索 | 弹出子菜单：微调探索 / 大胆混搭 |
| 👔 衣橱 | 展开衣橱分析面板（品类/利用率/购买建议） |
| ➕ 添加 | 新衣服入库引导 |
| ⚙️ 设置 | 弹出子菜单：同步/状态/帮助 |

### 原型构建流程
```bash
python3 tools/build_prototype.py          # 手动重建原型
# 或通过管线自动触发（生成穿搭后自动重建）
```
- `build_prototype.py` 扫描 `outfits/` 目录，动态注入 Hero、单品、历史卡片数据
- `wechat_control.py` 通过 `_load_chat_html()` 从文件读取原型 HTML
- **⚠️ 布局铁律**：确认版排版只改数据源，绝不动 CSS/HTML 结构（详见 memory）
- **⚠️ Hero 图规则**：优先 AI 原始生图 `上身效果_1.png`，不用排版图
- **⚠️ 管线重建**：每次生成新穿搭后必须运行 `build_prototype.py` 重建原型

## 生图完整流程（两轮接力抠图参考）

### 管线
1. `execute_outfit_plan()` 复制抠图（`wardrobe/enhanced/{ID}_cutout.png`）到豆包生图/
2. **Pass 1**: `generate.py` → 人物+上衣+下装+鞋子抠图 → Seedream生成基础穿搭
3. **Pass 2**: Pass1最佳图 + 帽子/包/墨镜/袜子抠图 → Seedream精确配饰
4. `composite_v2.py` 排版合成
5. `git push` → CDN
6. `build_prototype.py` 重建原型

> ⚠️ 参考图使用抠图（去背景），非原始照片。抠图透明部分自动补中性灰底(#D9D9D9)
> ⚠️ Seedream API 参数名为 `image`（非 `reference_images`）
> ⚠️ Pass 1 生成 4 张，Pass 2 用第 1 张做底图生成 2 张，最终保留 Pass1 备份 + Pass2 最佳

## 手机远程控制
- 启动：`bash tools/start_wechat_control.sh`
- 手机通过 ngrok HTTPS URL 访问 HTML 面板
- 端口 8765，静态文件从项目根目录提供（中文路径需 URL decode）
- 原型页面从 `prototype/mobile-v2.html` 加载（由 `build_prototype.py` 构建）
- 详情见 `memory/wechat-remote-control.md`

## ⚠️ 质量守则（Critical — 不可违反）

### 1. 场景适配：运动/功能场景必须选对单品

**规则**：
- 运动场景（网球/跑步/健身/足球等）必须选功能运动鞋，**不可选工装靴、帆布鞋、拖鞋**
- 运动下装必须选运动短裤/紧身裤，不可选亚麻裤、沙滩裤
- 上衣优先选速干/Polo/背心等运动面料

**实现**：
- AI prompt 包含 `⚠️ 场景匹配` 规则
- `get_wardrobe_summary()` 从 `wardrobe/tags/*.json` 动态生成表格，自动包含场景标签
- 每件单品在「场景标签」列标注用途（如 `入门网球`、`工装风`、`足球文化`）

**防止回退**：
- JSON 标签是唯一数据源，改了标签 AI 即时看到
- 禁止手改 `服装档案.md` 后就以为完事——JSON 才是真相源

### 2. 服装入库：两步标注流程

新衣服入库必须执行两步（不可只做视觉）：
1. **视觉识别**：品类/颜色/面料/廓形/品牌Logo
2. **网络搜索**：品牌 + 系列名称 → 官方定位/产品线/文化背景/场景用途

标签覆盖四个维度：身形修饰 + 风格文化 + 场景用途 + 设计特征。

### 3. 单品禁用：只有一星差评才禁用

- ~~一天内已用单品避开~~ ← 已废除
- 只有用户对某套穿搭点 ⭐ 一星评价时，该套的所有单品才加入禁用清单
- `get_banned_items()` 扫描 `outfits/*/rating.json`，`rating==1` 的 outfit 中所有单品禁用

### 4. 配色色块：先 git push 再用 CDN

生成 `_swatches.png` 后必须**先 `git push` 再构建 CDN URL**，否则 jsDelivr 拿不到图片。

```python
_sp.run(['git', 'commit', '-m', '🎨 配色色块'], ...)
_sp.run(['git', 'push'], ...)  # ← 必须！不能省略
h = _sp.run(['git', 'rev-parse', '--short', 'HEAD'], ...)
swatch_img_url = f'https://cdn.jsdelivr.net/gh/...@{h}/...'
```

## Git
- Remote: `git@github.com:wangyunkun123/fashion-style-advisor.git` (SSH)
- Web: https://github.com/wangyunkun123/fashion-style-advisor (public)

## 免费服装图片搜索
无需任何付费 API，三个免费源：

| 源 | 免费额度 | API Key | 命令 |
|----|---------|---------|------|
| DuckDuckGo | 无限次，免 Key | ❌ | `python3 tools/fashion_image_search.py --query "linen shirt"` |
| Pexels | 200次/小时 | ✅ 免费注册 | `python3 tools/fashion_image_search.py --query "..." --source pexels` |
| Unsplash | 50次/小时 | ✅ 免费注册 | `python3 tools/fashion_image_search.py --query "..." --source unsplash` |

```bash
python3 tools/fashion_image_search.py --query "关键词"                  # 默认 DuckDuckGo
python3 tools/fashion_image_search.py --query "关键词" --all-sources     # 三源同时搜
python3 tools/fashion_image_search.py --query "关键词" --save ./图片     # 下载到本地
python3 tools/fashion_image_search.py --list-sources                     # 查看可用源
```
> API Key 配置在 `config/seedream.local.json`（`pexels_api_key` / `unsplash_api_key`）
