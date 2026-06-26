# 开发日志

## 2026-06-25: 多用户管线全链路修复 — Alice 女性测试用户完整打通

### 问题背景
Alice (女性测试用户) 穿搭生成使用主用户形象、推送显示主用户内容、Profile 数据交叉污染。经诊断发现 9 个 Bug 分布在 5 个文件中。

### Bug 1-2: 用户上下文丢失（致命）
- **generate.py 缺少 --user**: 子进程搜索主用户 outfits/ 目录，用男性人物照生图
- **set_thread_user 时序错误**: 在 `_load_all_clothing()` 之后才调用，AI 看到的还是主用户 83 件衣橱

### Bug 3-5: 多用户路由盲区（高危）
- 3 个端点 (`/cmd`, `/api/try/`, `/api/explore/try-on`) 未传 `user_id`，后台线程丢失上下文
- `common.py` 三个函数 (`get_banned_items/get_recent_outfits/get_wear_counts`) 硬编码主用户目录
- `unified_pipeline.py` 评分历史/星级统计读主用户目录

### Bug 6-7: 静默崩溃与性别硬编码（致命）
- `generate.py --user alice` 触发 `from tools.common import` 但项目根目录不在 `sys.path` → 子进程静默崩溃
- `build_creation_prompt` 硬编码 "亚洲男性穿搭" → Seedream prompt 写死 "Asian man"

### Bug 8: 品类盲区 → AI 无上衣可选
- Alice 衣橱 8 个品类（连衣裙/针织衫/套装等）中有 3 个不在 `cat_order` 列表
- 33°C 又跳过长袖上衣 → AI 表格里零上衣 → 返回空 items
- 修复：补全 5 个女性品类 + 连衣裙/套装验证 + 温度过滤改为标注

### Bug 9: 原型 CDN 路径全部指向主用户
- `build_prototype.py` 8 处硬编码 `../outfits/` → Alice 手机 Hero 图和单品缩略图都是主用户的
- 修复：引入 `OUTFITS_REL` / `WARDROBE_REL` 动态路径

### 追加修复: Profile 数据交叉污染
- **中英文不匹配**: Alice profile 存 English 值 (`female/tan/hourglass`)，前端 HTML 选项全用中文 → 默认选第一个 → 看起来像没保存
- **Cookie 跨用户污染**: `fashion_user=alice` cookie 导致主用户页面 API 路由到 Alice → 互相覆盖数据
- 修复：API 返回值翻译 + `__USER__='default'` 显式路由 + `user=default` 服务端识别

### 代码变化
- `wechat_control.py`: set_thread_user 提前 + 3 端点 user_id + generate.py --user + build_creation_prompt user_id + 中英文翻译 + user=default 路由
- `unified_pipeline.py`: 品类列表补全 + 温度过滤标注 + 连衣裙/套装验证 + OUTFITS_DIR 动态化 + 性别感知
- `build_prototype.py`: OUTFITS_REL/WARDROBE_REL 动态路径 + __USER__='default' + get_display_name 多用户
- `common.py`: _get_active_outfits_dir() 辅助函数 + 三个函数动态路由
- `generate.py`: sys.path.insert 项目根目录

### 验证结果
- Alice 穿搭生成完整跑通：选品(连衣裙+鞋) → R2创作(Asian woman) → Seedream 生图 → CDN 推送
- 两个 Profile 完全隔离：主用户(男/179/68/标准) vs Alice(女/173/55/沙漏型)
- 保存→刷新→数据不丢失，不互相覆盖

### 备份标签
```bash
git tag female-user-pipeline-fixed  # 女性用户管线全链路修复
```

### 凌晨：上传稳定性攻坚战（17 项修复）

手机端凌晨上传频繁失败，从客户端→网络→服务端逐层排查：

**客户端**
- 压缩质量阶梯：优先 JPEG 0.7→0.5→0.3 降级，禁止发送原始文件
- 上传前大小检查：>400KB 自动压缩
- Canvas blob 压缩 → FormData 发送（避免 Funnel POST 限制）

**网络层**
- 修复 socket 超时：`self.rfile._sock` → `self.connection`（正确的 socket 对象）
- `rfile.read()` 加 30s 超时 + boundary 引号处理
- 上传超时 30s→60s（凌晨手机网络更慢）
- 上传分块读取 + 进度追踪：定位传输数据量

**服务端**
- 修复上传响应 BrokenPipe 导致前端报失败
- 修复上传阻塞：multipart 解析完整度检查
- 预览图缓存碰撞修复
- API 400 智能处理
- launchd 稳定性加固：直接管理 Python 进程 + Funnel 自动启动

**进程管理**
- 修复信号处理器死锁：`shutdown()` 在独立线程中调用
- 修复 SIGTERM 后进程僵死：`daemon_threads=True` + plist 加固

### 上午：入库管线三阶段升级

**Phase 1: 品类系统解耦 + 女性品类扩展**
- 品类代码与性别解耦（原硬编码男性品类 → 动态按性别加载）
- 女性品类扩展：DRESS(连衣裙) / SKIRT(半身裙) / JMP(连体裤) / BLOUSE(女士衬衫) / KNIT(针织衫)
- `CATEGORY_CONFIG` 统一品类配置，替代多处不一致映射
- 预览任务目录隔离：`users/{uid}/wardrobe/_incoming/` 按用户分离

**Phase 2: 多件检测 + Cloth Parsing 分割预处理**
- 集成 SegFormer-B2 (`mattmdjaga/segformer_b2_clothes`) 18 类服装语义分割
- `local_files_only=True` 修复国内 HuggingFace SSL 连接问题
- 最小面积阈值 3.0%（过滤误检噪点）
- 连通区域分析：同一品类多件独立检测

**Phase 3: 自动衣橱分类 + 风格聚类 + 入库自动推荐**
- 入库自动风格推荐（基于品类/颜色/品牌/面料匹配风格指纹）
- 自动 `claude_fit_comment` 生成：品牌 + 颜色 + 风格 + 品类 → 短名
- 品类冗余去重："跑鞋鞋子"→"跑鞋"、"短袖上衣T恤"→"短袖上衣"

### 白底提取管线（替代旧灰底补全方案）

**新增 `tools/extract_clothing.py`**
- `extract_to_white_bg()`：SegFormer 裁剪 → Seedream 整件重构到纯白背景(#FFFFFF)
- `remove_white_background()`：阈值去白底(>240) → 透明 PNG + 中性灰底 JPG
- 优于旧方案：整件重构（非局部 inpainting）+ 白底阈值去底（非复杂背景抠图）

**四类图片处理路径**
| 图片类型 | SegFormer | Seedream白底 | VLM行为 |
|:---|:---:|:---:|:---|
| 真人模特照 | ✅ 检测+裁剪 | ✅ 白底重构 | 逐件分析 |
| 干净单品图 | — 跳过 | — | 原图直送 |
| 电商商品图 | ✅ 检测 | ✅ | 忽略水印/促销 |
| 多图拼贴 | ✅ | ✅ | 只分析主体 |

### 入库确认增强
- 多件识别 checkbox 勾选：用户选择需入库的单品
- 全选/取消全选 toggle bar
- 只发送勾选项确认入库

### 缓存与显示修复
- `Cache-Control: no-cache, max-age=0` + ETag（修复 24h 缓存导致卡片显示旧图）
- 透明 PNG 保存到 `enhanced/{id}_cutout.png` + 透明缩略图重新生成
- 标签编辑自动更新 `claude_fit_comment`（品牌/颜色/风格/品类变更即时反映）

### 入库残留清理
- 原图清理：入库后删除 `_incoming/` 临时文件
- `_incoming` 泄漏修复：超过 24h 的分析 JSON + 残留图片自动清理
- ID 冲突旧图替换：同名 ID 重新入库时先删除旧文件

### 改动文件
| 文件 | 改动 |
|------|------|
| `tools/wechat_control.py` | 上传重构 + Phase 1/2/3 + 白底管线 + checkbox确认 + 缓存修复 + 残留清理 |
| `tools/extract_clothing.py` | **新增** — 白底提取 + 去白底模块（296 行） |
| `tools/cloth_parser.py` | SegFormer B2 集成 + `local_files_only=True` |
| `prototype/mobile-v2.html` | checkbox UI + 选择逻辑 + 上传压缩 |
| `config/new_items.json` | NEW 徽标注册 |
| `users/_registry.json` | 多用户注册 |

### 已知问题
- `wechat_control.py` 仍为巨石文件（~6200 行），业务逻辑层待抽出
- 调试日志（临时 POST/GET 追踪）待清理

### 下午～晚间：男女分线架构 — 项目最大规模重构

#### 背景
多用户测试引入女用户 (nan) 后，男女性数据频繁交叉污染（衣橱/风格/Profile/生图），且推荐系统对女性几乎不可用。决定将项目从「单用户男性为主」重构为「男女双线独立运行 + 共享公共逻辑」。

#### 性别分离架构 (`c785a0a`)
```
项目根目录
├── users/
│   ├── male/
│   │   ├── kun/     # 主用户（原 wardrobe/outfits/ 迁移至此）
│   │   └── becca/   # 男性测试用户
│   └── female/
│       └── nan/     # 女性测试用户（原 users/alice/ 迁移）
├── styles/
│   ├── male/        # 18 个男性风格指纹 (*.json)
│   └── female/      # 50 个女性风格指纹 (WF-* 子目录)
├── config/
│   ├── style_defaults_male.json
│   ├── style_defaults_female.json
│   └── beauty_direction_female.json  # 新增：女性美妆指引
└── tools/           # 公共逻辑（男女共享）
```

核心原则：
- 男女内容独立运行，数据互不污染
- `tools/` 公共逻辑适用于男女，可按 gender 参数做针对性优化
- 修改公共逻辑时同步影响男女，改 gender-specific 部分互不干扰

#### 目录迁移 (`2ca7334`)
- `wardrobe/` → `users/male/kun/wardrobe/` (76件服装)
- `outfits/` → `users/male/kun/outfits/` (历史穿搭)
- `users/alice/` → `users/female/nan/`
- `users/becca/` → `users/male/becca/`
- `styles/` 平面 JSON → `styles/male/` (旧格式删除)
- `styles_women/` → `styles/female/` (目录结构保留)
- `config/user_profile.json` → 各用户 `profile.json`
- 清理统计：1655 文件，~520MB

#### 关键 Bug：`resolve_user_dir()` 根因修复
这是导致 4 轮 "还是男性形象" 反馈的底层根因。

**Bug**：`resolve_user_dir(user_id='nan')` — 关键字参数调用时 `gender=None, user_id='nan'`，但原代码只有两个分支：
1. `gender is not None and user_id is None` → 位置参数兼容（把 gender 当 uid 用）
2. `gender and user_id` → 两参数都有的情况

关键字参数 `gender=None` 两条都不命中，返回 `PROJ_DIR`。**所有** 基于 `resolve_user_dir` 的性别检测静默 fallback 到男性默认值。

**修复**：新增第三分支——仅 user_id 传参时自动查 gender：
```python
if (gender is None or gender == '') and user_id and user_id != 'default':
    g = get_user_gender(user_id)
    if g:
        return os.path.join(PROJ_DIR, 'users', g, user_id)
```

#### 风格推荐性别感知 (`032e971`, `c684525`)
- `style_matcher.py`：`DEFAULTS_CONFIG` 拆为 `DEFAULTS_CONFIG_MALE` / `DEFAULTS_CONFIG_FEMALE`，`auto_suggest_style()` 和 `load_defaults()` 接受 `gender` 参数
- `style_lab.py`：`STYLES_DIR` 更新为扫描 `styles/male/` + `styles/female/` 两个目录（`load_all_styles()` 68风格 = 18男 + 50女）
- `_load_style_cards()`：按性别路由到正确风格目录
- `/api/try/`：兼容两种风格文件结构（男性平面 JSON / 女性子目录 fingerprint.json）

#### Explore 个性化匹配重写 (`7b7a53e`)
新增 3 个辅助函数，替代失效的 `style_lab.load_all_styles()`：
- `_load_user_style_context(user_id)`：统一加载 style_prefs/gender/has_clothing/has_ratings
- `_load_all_style_fingerprints(gender)`：按性别加载全部风格指纹
- `_compute_wardrobe_style_affinity(user_id, gender, style_ids)`：衣橱-风格匹配评分

`_get_dynamic_mode_styles` 信号优先级：**引导偏好 > 评分舒适区 > 衣橱匹配 > 趋势 fallback**。无数据用户返回空状态 + hint 提示。

#### 女性美妆系统 (`config/beauty_direction_female.json`)
- 11 个美学集群（东亚/欧式经典/现代都市/浪漫女性/极简奢华/自然逃离/前卫另类/都市街头/戏剧表达/文化优雅/先锋艺术）
- 每集群含 `hair.en/hair.cn`（发型）、`makeup.en/makeup.cn`（妆容）、`vibe` 字段
- `build_creation_prompt()` 注入 `beauty_direction`：按风格匹配集群 → 发型+妆容描述融入 seedream prompt
- nan profile 新增 `hair` 字段（length/color/texture），`user_manager.py` GENDER_DEFAULTS['female'] 同步

#### 人物身份保持修复 (`generate.py`)
Pass 1 生图未告知 Seedream 用参考人物照片作为身份基准，导致 AI 生成泛型 "Asian woman" 而非 nan 本人。修复：检测到 `人物_` 参考图时自动注入 identity clause：
```
Image 1 is a reference photo of the person to portray.
Preserve their facial identity, skin tone, and body shape —
they are the model wearing this outfit.
```

#### 设置页重构 (`260e3ed`)
- 移除性别选择器（已在性别门入口确定）
- 形象管理折叠卡整合全部形象内容
- 风格偏好改为风格库弹窗选择器（最多5个）+ 芯片预览 + 清空联动
- 体型选择兼容 `seg-body-male` / `seg-body-female` 双容器

#### 路径/CDN 修复（多次迭代）
- Hero 区服装缩略图：相对路径 → CDN URL (`eaef12c`, `eaf2879`)
- 衣橱缩略图 + `renderItemCardH` / `loadColdItems` / `renderMatchSection` 路径修复 (`2ce3f54`)
- JS 字符串拼接结构破坏修复：`"../'+` → `'+__CDN__+` (`6f26afb`)
- `generate.py` 子进程 `sys.path` 项目根目录修复
- `onerror` 回退路径适配新目录结构 (`2a60a9f`)

#### 紧急恢复：styles/ 误删 (`58a793b`)
`git rm -r styles/` 误匹配了 `styles/male/` 和 `styles/female/` 子目录。旧平面 JSON (`styles/*.json`) 正确删除，新子目录从 `c785a0a` 恢复。

#### 代码变化
| 文件 | 改动 |
|------|------|
| `tools/common.py` | `resolve_user_dir()` 第三分支：关键字参数自动查 gender |
| `tools/style_matcher.py` | 性别感知：双配置文件 + 双 fallback + auto_suggest_style(gender) |
| `tools/style_lab.py` | `load_all_styles()` / `load_style()` 扫描 male+female 双目录 |
| `tools/unified_pipeline.py` | `_is_female_early` 早检测 + gender-aware 风格路由 + beauty 注入 |
| `tools/wechat_control.py` | 3 个 Explore 辅助函数 + `_get_dynamic_mode_styles` 重写 + 设置页 API + 风格选择器 API + 多用户路由完善 |
| `tools/generate.py` | Pass 1 人物身份保持 clause + `--user` 参数 |
| `tools/build_prototype.py` | Explore hint 支持 + CDN 路径 + gender 感知 |
| `tools/user_manager.py` | GENDER_DEFAULTS['female'] 加 hair 字段 |
| `config/beauty_direction_female.json` | **新增** — 11 集群女性美妆指引 |
| `users/female/nan/profile.json` | 加 hair 字段 |
| `prototype/mobile-v2.html` | 设置页重构 + 风格选择器弹窗 |

#### 验证结果
- nan 今日穿搭完整跑通：DRESS-004 + SHOE-004 → Seedream prompt 明确 "Asian woman" + 长发妆容描述
- kun 今日穿搭正常：TS-003 + PT-002 + SHOE-002 → 男性形象无 beauty 注入
- Explore 三种模式正确个性化：nan 返回 5 个引导风格，kun 返回 10 个舒适区风格
- 两用户 Profile/衣橱/风格/生图 完全隔离，互不污染

#### 备份标签
```bash
git tag gender-split-architecture  # 男女分线架构
```

#### 待完成
- `STYLE_PHOTO_MAP` 无女性条目（50 个女性风格 fallback 到 DEFAULT_PHOTO_DIRECTION）
- `validate_outfit()` 硬编码男性单品 ID 未泛化
- `scene_profiles.json` 无女性场景（闺蜜聚会/下午茶/逛街等）
- `_get_persona_description()` `shape_cn` 缺少 `petite` 体型映射
- CLI 工具（`style_lab.py`/`sync_items.py`/`fix_orientation.py`/`generate_thumbnails.py`）仍硬编码旧路径
- `wardrobe/enhanced/` 146 个 `Image_` 命名抠图冗余待清理
- launchd 服务待重新启用

---

## 2026-06-23: Phase 7 稳定性基础设施 ✅ + 管线文档

### 稳定性基础设施重构
- 基础设施层提取 `server_infra.py` (517行)：TaskManager + SharedState + 日志 + 信号处理 + Watchdog
- 线程安全加固：`SharedState` 统一锁替代 3 个裸全局变量
- 任务超时检测：Watchdog 后台线程每 30s 扫描，running > 5min 自动标记 error
- 启动任务恢复 + 重试队列
- 优雅关闭：SIGTERM 等待活跃任务完成（15s）
- 18 个自动化测试（7 单元 + 4 smoke + 7 集成）

### 上传入库管线完整文档化
- 四类图片处理路径文档
- 多用户验证（default 86件 / alice 3待确认 / becca 空）
- 全链路追踪：前端压缩→上传→SegFormer检测→Seedream白底→VLM分析→确认入库

### 杂项修复
- 修复分析完成后竞态条件导致单品闪现消失
- 全量 900w JPEG 预压缩（CDN 体积减 80%）
- Hero 图优先用 `_900w.jpg` 预压缩版
- 管线生图完成后自动预压缩 900w

---

## 2026-06-22: 每日自动推荐 + 手机端健康检查 + 穿搭周报系统

- **每日 cron**：Claude Cron 每天 5:57 触发完整穿搭管线（避开整点高峰），失败自动重试一次
- **管线并发锁**：`run_pipeline()` 入口加 `threading.Lock`，运行中拒绝重复请求，`/health` 实时返回 `running` 状态
- **手机端健康检查**：页面加载 JS 调 `/health` 判断 `today_ok`
  - ✅ 已有 → 正常展示 Hero 卡片
  - 🔄 运行中 → 加载动画 + 每 5s 轮询
  - ❌ 未生成 → 琥珀色警告卡片 + 「⚡ 立即生成」按钮（调 `/api/chat` → 轮询 task → 自动刷新）
- **GET /cmd 补今天穿什么**：`match_command` 的 `today` 动作加入 GET 白名单，cron 用 `curl -G --data-urlencode` 触发
- **改动**：`wechat_control.py` +56 行 / `build_prototype.py` +28 行（CSS+HTML+JS）/ `.claude/scheduled_tasks.json` +1 任务
- **Karpathy 视角参与设计**：用 March of Nines 思维设计失败兜底，用「Don't be a hero」原则选最简方案

## 2026-06-22: 周报增强 + 衣橱上传管线 6坑修复

> 详见 `devlog/2026-06-22.md`

- **风格 unknown→0**: STYLE_NAMES 8→18 + YAML frontmatter 解析 + 34条关键词回退
- **风格卡片图片**: 从周期内最高分 outfit 提取效果图，周报/月报各自独立
- **报告栏去图标**: 📊 统一去除
- **上传管线 6 坑**: Funnel超时/任务状态丢失/多件同图/ID碰撞/错误隐藏/多图映射错位 — 全部修复并写 memory
- **改动**: `rating_analyzer.py` +35行 / `wechat_control.py` +135行 / `build_prototype.py` +10行 / `mobile-v2.html` 同步

## 2026-06-22: 衣橱图片去重清理

> 详见 `devlog/2026-06-22.md`

- **PT-007/PT-008 合并**：入库时 PT-008 被错误分配了 PT-007 的图 A（MD5 一致），删除 PT-007 重复图保留正确映射
- **SH-004 残留清除**：6/17 已删 tags/JSON 但留下档案条目+原图+enhanced 3 文件，全清
- **TS-005 中文冗余**：标准命名 + 中文命名并存，删中文版 2 个
- **enhanced JPG 拷贝清理**：82 个原始图拷贝（品类目录均有原图），安全删除
- **后续待处理**：146 个 Image_ 命名抠图冗余（需先统一代码查找逻辑再删），已写 memory 提醒
- **清理统计**：90 文件 + 1 条目，enhanced/ 396 → 308 (-22%)

## 2026-06-19: 管线优化日

> 详见 `devlog/2026-06-19.md`

- **进度精简**：双消息→单消息+打勾，加预估时间/token，去排版图和文字摘要
- **管线瘦身**：5步→3步，移除 composite_v2.py + build_push.py + format_outfit_summary()
- **配件场景化**：按场景需要选择，有理由才加，不铺满；面料去 blanket
- **表情控制**：Seedream prompt 加 natural relaxed expression，禁面瘫脸
- **Pass 2 阈值**：1件配件并入 Pass 1，2+才跑两轮
- **死代码清理**：删 496 行（build_narrative_prompt/run_unified_pipeline/CLI main）
- **质量检查对齐**：两处 prompt 统一 11 项

## 2026-06-18: 推荐理由 + 放回主页 + 穿搭技巧

> 详见 `devlog/2026-06-18.md`

- **推荐理由 & 穿搭技巧**：Hero 新增两个区块，AI 自动生成 rationale + dressing_tips
- **放回主页**：历史卡片「📌 放回主页」按钮，纯前端 DOM 即时替换
- **5 套最爱补全**：补全推荐理由+技巧内容，修正风格标签
- **CSS 修复**：配色圆点居中、pinToHome 去「取消」文字
- **归档品修复**：API 可见 + 彻底删除 + 即时刷新

## 2026-06-17/18: 第四阶段 — 手机端完整实现 + 代码精简优化

### 手机端建设
- **推荐页完整改版**：Hero 区（AI 生图 + 风格标签 + 配色条）→ 单品清单（3 列网格 + Clothing-Icons 图标）→ 其他推荐（横向卡片 + 换一批）→ 历史推荐（可展开穿搭卡片 + 评分）
- **Tab Bar 五大页面**：🧠推荐 / 🧪探索 / 👔衣橱 / ➕添加 / ⚙️设置，全部联通 API
- **评分系统集成**：⭐⭐⭐ 三级评分直达，Hero 区和历史卡片均可评分
- **内容同步机制**：手机控制台与微信推送使用完全相同的内容（三层防御：stdout → 缓存 → 摘要）

### 统一推荐管线
- **AB 线合并**：`unified_pipeline.py` — AI 主导 + 数据支撑 + 规则验证
- **风格匹配**：五层评分引擎（文化/美学/场景/身形/新鲜度）
- **场景适配**：运动场景强制功能鞋、功能面料，从 JSON 标签动态读取场景标签
- **单品禁用**：仅一星差评才禁用单品，不再按"已穿过"盲目避开

### 两轮接力生图
- **Pass 1**：人物 + 上衣 + 下装 + 鞋子 → Seedream 基础穿搭（4 张）
- **Pass 2**：Pass1 最佳图 + 帽子/包/墨镜/袜子/配饰 → 精确配饰（2 张）
- 抠图透明自动补中性灰底 (#D9D9D9)
- Seedream prompt 七段结构：摄影风格/构图/光影/姿势/服装细节/场景/情绪

### 代码精简优化（三层）
- **第一层**：删除死函数 6 个（`_get_ark_key`/`wrap_text`/`build_hero_item_card`/`_detect_bline_from_hint`/`load_style_defaults`/`load_rules`）、未用导入 8 个、死常量 `OUTFIT_SYSTEM_PROMPT`
- **第二层**：创建 `tools/common.py` 共享模块，消除 15+ 处跨文件重复定义（`load_all_clothing` ×4→1、`load_score_cache` ×3→1、`load_style_fingerprint` ×2→1、`load_encyclopedia` ×2→1、`ITEM_ID_PATTERN` ×6→1）
- **第三层**：wechat_control 内部合并（`_find_item_thumb`+`_find_item_cutout`→`_find_item_asset`）、常量提取（`JUNK_PATTERNS`/`ALT_STYLES`）、`CATEGORY_NAMES`+`CATEGORY_CODE_TO_NAME` 合并

### 质量守则落实
- 配色色块先 git push 再发微信（防止 CDN 拿不到图片）
- 手机端 Hero 图优先 AI 原始生图
- 每次生成新穿搭后必须运行 `build_prototype.py` 重建原型
- JSON 标签是唯一数据源，禁止手改服装档案就以为完事

### 备份
- `phase-4` 标签 → `de55827`

---

## 2026-06-18: 代码精简优化 + 文档补全

### 上午：代码结构梳理
- 4 个 Explore Agent 并行扫描 `wechat_control.py`(174KB) / `build_prototype.py`(171KB) / `unified_pipeline.py`(84KB) / `composite_v2.py`+`build_push.py`
- 发现：死函数 6 个、跨文件重复定义 15+ 处、未用导入 8 个、内联 HTML 臃肿 ~200 行

### 下午：三层精简

**第一层 — 快速修剪**
| 文件 | 删除内容 |
|------|---------|
| `composite_v2.py` | `_get_ark_key()` + `wrap_text()` + 5 未用导入 |
| `build_prototype.py` | `build_hero_item_card()` + `import random` + 4 未用 kwargs + `junk_patterns` 常量化 |
| `wechat_control.py` | `OUTFIT_SYSTEM_PROMPT`(30行) + `_detect_bline_from_hint()` + `CATEGORY_NAMES` 合并到 `CATEGORY_CODE_TO_NAME` |
| `unified_pipeline.py` | `load_style_defaults()` + `load_rules()` + `RULES_FILE` + `DEFAULTS_FILE` + 2 未用导入 |
| `build_push.py` | `ALT_STYLES` 常量化 |

**第二层 — 去重合并**
- 新建 `tools/common.py` 共享模块（170 行）
  - `load_all_clothing()` — 4 处定义 → 1 处
  - `load_score_cache()` — 3 处 → 1 处
  - `load_style_fingerprint()` — 2 处 → 1 处
  - `load_encyclopedia()` — 2 处 → 1 处
  - `ITEM_ID_PATTERN` — 6 处内联正则 → 1 个编译常量
  - `CAT_CONFIG` — 统一品类配置（消歧 5+ 处不一致映射）
- `wechat_control.py` 内部合并：
  - `_find_item_thumb` + `_find_item_cutout` → `_find_item_asset` 通用查找
  - `get_cdn_url()` 复用 `_get_git_commit()`

### 晚间：文档同步
- 补全 `项目进程.md`（Phase 3/4 详情 + 四大类操作速查 + 标签速查表）
- 更新 `devlog.md` 第四阶段总结 + 今日操作记录
- `phase-4` 标签 → `de55827`（含推荐逻辑完善）

### 统计
- 3 次提交：`d136119`(🔥) `2da45d1`(📦) `65298ba`(🔧) `de55827`(📋)
- 净删 ~350 行冗余代码
- 新建 `tools/common.py` 消除 6 种跨文件重复

---

## 2026-06-16/17: 手机端三大模块 — 风格图库 + 探索页图片化 + 智能添加页

### 手机端优化
- **探索页卡片图片化**：49 个风格卡片左上角蓝底文字替换为代表性穿搭图（56×72px 竖版），点击可放大。`_load_style_cards()` 自动检测 `representative.jpg`。
- **风格百科图库**：修复 `generate_encyclopedia_html.py` 不支持的 `![图片]()` 语法，为 49 篇百科文章末尾插入「📸 风格图库」章节（152 张参考图）。
- **添加页重写**：从 tab 切换 → 两个直接操作卡片（拍照/上传），支持多图（连续拍摄 + 相册多选），豆包视觉 AI 自动识别品类/颜色/品牌/面料，审核确认后自动入库（ID 分配 → 图片增强 → 标签 JSON → 服装档案更新）。
- **NEW 徽标**：新入库单品在衣橱卡片上显示红色脉动徽标，点击进入详情自动消失。
- **布局优化**：双沙漏修复、按钮不下沉、徽标不裁剪、卡片比例均衡。

### 后端新增
- `tools/wechat_control.py` +180 行：4 个 API 端点（`/api/wardrobe/add`, `/add/confirm`, `/new-items`, `/new-items/dismiss`）+ 6 个辅助函数（入库/增强/档案更新/ID 分配/NEW 注册）
- 豆包视觉 API 多模态调用（复用 `call_doubao_chat` 函数，图片编码模式来自 `auto_orient.py`）

### 工具脚本
- `tools/fetch_style_images.py` — DDGS 自动搜索+下载风格穿搭图（50 主图 + 152 备选）
- `tools/insert_gallery_to_encyclopedia.py` — 批量插入图库到百科文章
- `tools/generate_encyclopedia_html.py` — 修复图片语法支持

### 代码优化
- 删除 2 处冗余 inline import (`shutil`, `subprocess`)
- 删除 1 处重复 CSS (`.rec-card`)
- 清理旧添加页死代码（`switchAddTab`, `handleAddImage` 单数版等）

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

## 2026-06-16: 手机端 5 Tab 完整建设

### 背景
手机控制台 (`prototype/mobile-v2.html`) 原只有「推荐」页完整，其余 4 个 Tab（探索/衣橱/添加/我的）均为占位符。

### 改动文件

| 文件 | 行数 | 改动 |
|------|------|------|
| `tools/wechat_control.py` | 1885→~1950 | 新增 9 个 API 端点 + `_load_recent_outfits()` + `_identify_clothing()` + `CATEGORY_NAMES` + `_find_item_thumb()` |
| `tools/build_prototype.py` | 1009→~1150 | 衣橱/探索/添加/我的 四个页面完整重写，CSS+JS 全量替换 |

### 新增 API 端点（9个）

| 端点 | 用途 |
|------|------|
| `GET /api/wardrobe/items` | 76件单品列表含缩略图路径 |
| `GET /api/wardrobe/stats` | 月度穿搭统计/利用率/最爱风格排行 |
| `GET /api/wardrobe/cold-items` | 38件闲置单品列表 |
| `GET /api/wardrobe/gaps` | 5条购买建议（高/中/低优先级） |
| `GET /api/explore/tweak` | 最近穿搭微调建议（3条） |
| `GET /api/explore/transform` | 风格转换建议（未尝试的风格） |
| `GET /api/explore/cross` | 跨界融合建议（随机两风格交叉） |
| `GET /api/trends` | 12个风格趋势 + 5个热门百科 |
| `GET /api/pref` | 推送偏好读取 |
| `GET /api/profile` | 用户身形档案+使用统计 |
| `POST /api/wardrobe/add` | 拍照识别（异步 task） |
| `POST /api/wardrobe/confirm` | 确认入库（生成ID+保存标签+移动图片） |

### 修复的 Bug

1. **Tab 图标消失** — `tab` 字典 key 从 `rec/exp/wrd/me` 改为 `recommend/explore/wardrobe/profile`
2. **所有 Tab 切换失效** — Tab Bar 的 `data-page` 值（`rec/exp/wrd/me`）与页面 ID（`page-recommend/explore/wardrobe/profile`）不匹配，导致 JS 无法找到对应页面
3. **JS 语法错误导致全部事件失效** — `__profLoaded` 行多了一个 `}}`，整个 `<script>` 块被 Node.js 拒绝解析，所有 Tab 切换/API 调用全部失效
4. **单品列表不可滚动** — `.wrd-item-detail` 在 `scroll-area` 外，无 `max-height` + `overflow-y:auto`，超出屏幕的单品不可见
5. **CSS 样式未注入** — 新增的探索页/我的页/添加页 CSS 在模板替换时位置错误，未进入最终输出

### 手机端验证

📱 `https://climatic-erupt-mandatory.ngrok-free.dev`

| Tab | 功能 | 数据源 |
|-----|------|--------|
| 🧠 推荐 | Hero图+单品清单+历史+输入框 | build 时注入 |
| 🧪 探索 | 4子页：微调/转换/跨界/趋势 | 5个API端点 |
| 👔 衣橱 | 4子页：品类网格/月度/闲置/缺口 | 5个API端点 |
| ➕ 添加 | 拍照/上传→AI识别→确认入库 | 2个API端点（异步task） |
| ⚙️ 我的 | 推送偏好/身形档案/使用统计 | 3个API端点 |

### 关键决策

- **统计数据采用前端 JS fetch**（非 build 时注入），保证实时性
- **异步识别**：`/api/wardrobe/add` 返回 `task_id`，前端轮询 `/api/task/{id}`
- **缓存策略**：HTML 设置 `Cache-Control: no-store`，`_load_chat_html()` 去除 2 秒缓存

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
