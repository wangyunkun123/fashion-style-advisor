# Fashion Style Advisor

AI 时尚顾问，专攻亚洲男性穿搭。用户画像和身形分析在 memory 中。

## 核心文件
- `wardrobe/服装档案.md` — 76件服装索引（TS-001 等 ID 体系），按品类分子目录存图
- `profile/analysis.md` — 用户身形分析
- `outfits/` — 按 `日期_场景` 组织每日穿搭
- `config/seedream.local.json` — API 密钥 + Server酱 SendKey（不提交 Git）
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

## 操作指令
- **"推荐穿搭"** → 读取 wardrobe + 天气 → 风格匹配筛选 → 给出搭配方案
- **"推送穿搭"** → `python3 tools/build_push.py <outfit_dir>` — 百科增强推送（冷知识+单品解释+配色+备选风格）
- **"风格排名"** → `python3 tools/style_matcher.py <style_id>`
- **"风格矩阵"** → `python3 tools/style_scorer.py --matrix`
- **"分析偏好"** → `python3 tools/rating_analyzer.py --report`
- **"生成效果图"** → Seedream生图 → sync_items同步 → composite_v2排版 → git push → build_push推送

## 微信推送
首次双版+引导语，用户点击选择。简洁版去评分，百科版带评分。月度自动回访。

| 版本 | 引导语 | 评分 | 月度回访 |
|------|--------|------|---------|
| 🅰️ 简洁版 | 不想费心，每天一套穿好就走 👌 | ❌ | 30天→"想继续躺平？" |
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
- **"重建原型"** → `python3 tools/build_prototype.py`
- **"添加新衣服"** → 放入 wardrobe → 更新服装档案.md → auto_orient → enhance_clothing
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
- 端口 8765，静态文件从项目根目录提供（中文路径需 URL decode）
- 原型页面从 `prototype/mobile-v2.html` 加载（由 `build_prototype.py` 构建）
- 详情见 `memory/wechat-remote-control.md`

## ⚠️ 质量守则（Critical — 不可违反）

### 1. 数据同步：控制台与微信内容必须一致

手机控制台生成的穿搭，微信推送和控制台显示必须使用**完全相同的内容**。

**实现机制（三层防御）**：
1. **主通道**：`build_push.py --stdout` → stdout 输出 `__PUSH_RESULT__{json}` → `wechat_control.py` 解析
2. **备用通道**：`.push_cache.json` 缓存文件
3. **兜底通道**：`format_outfit_summary()` 简单摘要

**调用规范**：手机控制台调用 build_push 必须加 `--no-bline --stdout`：
```bash
python3 tools/build_push.py <outfit_dir> --rich --no-bline --stdout
```

**禁止行为**：
- ❌ 控制台用简单摘要、微信用百科内容（两条代码路径）
- ❌ build_push 内部独立触发 B线替换 pipeline 已生成的 outfit
- ❌ 直接调用 `build_push.py --rich` 不加 `--no-bline --stdout`

### 2. 场景适配：运动/功能场景必须选对单品

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

### 3. 服装入库：两步标注流程

新衣服入库必须执行两步（不可只做视觉）：
1. **视觉识别**：品类/颜色/面料/廓形/品牌Logo
2. **网络搜索**：品牌 + 系列名称 → 官方定位/产品线/文化背景/场景用途

标签覆盖四个维度：身形修饰 + 风格文化 + 场景用途 + 设计特征。

### 4. 手机端推送：首次必须双版

`build_push.py` 首次推送默认 `mode='both'`（双版）：
- 🅰️ 简洁版：单品清单 + 效果图
- 🅱️ 百科版：风格故事 + 单品解释 + 配色 + 备选风格 + 评分

底部带模式选择链接，用户点击后写入 `config/push_preference.json`。

### 5. 单品禁用：只有一星差评才禁用

- ~~一天内已用单品避开~~ ← 已废除
- 只有用户对某套穿搭点 ⭐ 一星评价时，该套的所有单品才加入禁用清单
- `get_banned_items()` 扫描 `outfits/*/rating.json`，`rating==1` 的 outfit 中所有单品禁用

### 6. 配色色块：先 git push 再发微信

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
