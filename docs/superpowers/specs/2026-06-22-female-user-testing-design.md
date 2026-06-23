# 女性用户测试系统 — 设计文档

> 状态：待用户审阅
> 日期：2026-06-22
> 分支：`female-user-testing`

## 一、目标与范围

### 测试目标
将 Fashion Style Advisor（当前为单用户亚洲男性穿搭顾问）扩展为支持 5-10 名女性用户的端到端测试系统，定量验证推荐逻辑对女性的可用性。

### 成功指标

| 指标 | 目标 | 数据源 |
|------|------|--------|
| 用户采纳率 | >60% | `user_wore == true` / 总推荐数 |
| 平均评分 | >3.5/5 | 三级评分汇总 |
| 7天复推率 | >40% | 7天内回来≥2次的用户占比 |
| 入库完成率 | >80% | 上传≥10件的用户占比 |
| 首次推荐满意度 | >70% | 第一套穿搭评分≥3 |

### 非目标（明确不做）
- 不做微信推送（测试期间不使用）
- 不做用户登录/密码系统（URL 参数区分即可）
- 不做数据库/缓存层（文件系统足够）
- 不做自动化入库的完整品牌搜索（仅基础视觉识别，品牌标签标记 `unreviewed`）

---

## 二、架构总览

### 核心原则
**现有代码是房东，新功能是租客。** 不传 `--user` 参数时，所有工具行为完全不变。你现在的使用方式零影响。

### 三层隔离

| 层次 | 机制 | 说明 |
|------|------|------|
| Git 分支 | `female-user-testing` 分支 | main 分支不受任何影响，随时切回 |
| 文件系统 | 新增 `users/` `styles_women/` | 所有新数据在独立目录 |
| 配置 | `users/<id>/config.json` | 不改 `config/seedream.local.json` |

### 系统拓扑

```
Tailscale Funnel (永久不变)
https://macbook-pro-1.taildbfbc0.ts.net/
              │
    ┌─────────┴──────────┐
    │ wechat_control.py  │
    │ :8765              │
    │ + ?user= 路由       │
    └─────────┬──────────┘
              │
 ┌────────────┼────────────────────┐
 │            │                    │
users/alice/  users/becca/   users/carol/
├── profile.json
├── config.json
├── wardrobe/
│   ├── 服装档案.md
│   ├── enhanced/    (抠图)
│   └── tags/        (结构化标签JSON)
└── outfits/
    └── 2026-06-22_日常/
        ├── outfit.md
        ├── rating.json
        └── analytics.json

tools/        ← 共享管线，全部加 --user 可选参数
prototype/    ← 共享模板，按用户动态注入数据
```

---

## 三、用户数据隔离

### 目录结构

```
users/
├── _registry.json          # 用户索引：{user_id: {created, last_active, status}}
├── alice/
│   ├── profile.json        # 身形 + 偏好
│   ├── config.json         # 用户级配置
│   ├── wardrobe/
│   │   ├── 服装档案.md
│   │   ├── enhanced/       # 抠图 PNG
│   │   └── tags/           # <ID>.json 结构化标签
│   ├── outfits/
│   │   └── <日期>_<场景>/
│   ├── discovered_styles/  # 自动发现的个人风格（轻量版：仅图片）
│   └── cache/
│       └── prototype.html  # 按用户构建的原型缓存
```

### profile.json 结构

```json
{
  "user_id": "alice",
  "gender": "female",
  "created": "2026-06-22T10:00:00Z",
  "body": {
    "height_cm": 165,
    "weight_kg": 55,
    "shape": "pear",
    "skin_tone": "warm_white",
    "concerns": ["hip_width", "leg_length"]
  },
  "style_prefs": ["WF-01", "WF-02", "WF-06"],
  "onboarding_complete": true
}
```

### 用户发现
`wechat_control.py` 启动时扫描 `users/` 目录。`_registry.json` 记录所有有效用户。`?user=<id>` 不在 registry 中 → 自动进入 onboarding 流程。

---

## 四、Onboarding 流程

用户首次访问 `https://macbook-pro-1.taildbfbc0.ts.net/?user=<新ID>` 时触发。

**中断恢复**：每个步骤完成后立即保存到 `profile.json`（增量写入）。用户中途关闭浏览器后再打开同一个 URL，读取已保存的步骤，从断点继续。`profile.json` 中 `onboarding_step` 字段记录当前进度（1-4）。

### Step 1：身形档案（纯表单）
- 身高 / 体重 / 胸围 / 腰围 / 臀围
- 身形自评：苹果型 / 梨型 / 沙漏型 / 直筒型 / 倒三角
- 肤色自评：冷白 / 暖白 / 自然 / 小麦
- 穿衣困扰（多选）：肩宽 / 腰线 / 腿型 / 身高 / 手臂 / 其他
- → 写入 `users/<id>/profile.json`

### Step 2：风格偏好（多选卡片）
- 从 `styles_women/` 展示 12 个风格卡片（名称 + 参考图 + 一句话描述）
- 用户选 3-5 个喜欢
- → 写入 `profile.json` 的 `style_prefs`
- 触发后台异步：轻量版风格发现（详见第六节）

### Step 3：衣橱初始化（上传入口）
- 提示「请至少上传 10 件衣服开始，越多越准」
- 手机拍照或相册选择
- 前端 Canvas 压缩：1024px / JPEG quality 0.65 / FormData 二进制
- 每件上传后进入快速入库队列
- 显示入库进度：「已入库 3/10 件…」

### Step 4：首次推荐
- 入库 ≥10 件 → 系统自动触发第一次推荐
- 用户看到 Hero 效果图 + 单品清单 → 进入正常使用循环
- Tab Bar 五个标签全部可用

---

## 五、快速入库管线

测试期间不做完整的品牌/文化/场景标注。区分两个阶段：

### 阶段一：自动基础标注（上传后 30 秒内完成）

```
用户上传图片
  → YOLO 品类检测（上衣/下装/连身/外套/鞋）
  → 颜色直方图分析（主色 + 辅色 + 饱和度）
  → 面料纹理特征估算（可选，如果 YOLO 检测到明显纹理）
  → 生成 tags/<ID>.json 基础版
  → 复制原图到 wardrobe/<品类>/
  → 更新 服装档案.md
```

生成的标签字段：
```json
{
  "id": "TS-001",
  "category": "短袖上衣",
  "color_primary": "白",
  "color_secondary": [],
  "fabric_hint": "棉质",
  "silhouette": "常规",
  "reviewed": false,
  "reviewed_by_human": null,
  "created": "2026-06-22T10:01:00Z"
}
```

### 阶段二：人工补标（测试期间异步进行）
- 你定期检查 `reviewed == false` 的衣服
- 补充品牌/系列/文化/场景标签
- 标记 `reviewed: true`
- 不影响用户使用——他们已经在用基础标签生成推荐

### 入库状态机

```
上传 → [压缩] → [YOLO检测] → [颜色分析] → 基础标签生成
                                                │
                                     ┌──────────┴──────────┐
                                     │ 基础标签已就绪        │
                                     │ 用户可立即获得推荐    │
                                     └─────────────────────┘
                                                │
                                     （异步，你手动触发）
                                                │
                                     ┌──────────┴──────────┐
                                     │ reviewed: true      │
                                     │ 品牌/文化/场景已补充  │
                                     └─────────────────────┘
```

---

## 六、女性风格库

### 通用风格库：`styles_women/`

目录结构镜像 `styles_universal/`：

```
styles_women/
├── README.md
├── WF-01_french_effortless/
│   ├── encyclopedia.md       # 百科：历史/文化/品牌/穿搭规则
│   ├── fingerprint.json      # 五层评分指纹
│   └── images/               # 参考图片
├── WF-02_korean_girlie/
├── ...
└── WF-12_dark_academia/
```

**12 个核心风格**：

| ID | 名称 | 关键词（用于搜索参考图） |
|----|------|------------------------|
| WF-01 | 法式慵懒 French Effortless | french effortless style women 2025 |
| WF-02 | 韩系少女 Korean Girlie | korean girlie fashion 2025 |
| WF-03 | 日系森系 Mori Kei | mori kei japanese forest girl |
| WF-04 | 新中式 New Chinese | new chinese style women modern |
| WF-05 | 美式休闲 American Casual | american casual women street style |
| WF-06 | 极简 Minimalist | minimalist women capsule wardrobe |
| WF-07 | 学院风 Preppy | preppy women style academic |
| WF-08 | 运动休闲 Athleisure | athleisure women sporty chic |
| WF-09 | 波西米亚 Boho | boho chic women bohemian |
| WF-10 | Y2K 千禧复古 | y2k fashion women 2025 revival |
| WF-11 | 都市通勤 City Girl | city commute workwear women |
| WF-12 | 暗黑学院 Dark Academia | dark academia women aesthetic |

### 构建方式
复用 `tools/style_research.py`，每个风格跑一轮研究 + `fashion_image_search.py` 搜集参考图。

### 个人发现风格：`users/<id>/discovered_styles/`

Onboarding 完成后，根据用户身形 + 衣橱 + 偏好拼接搜索 query，搜集相关风格图片：

```
query = "{身形特征} + {衣橱主导品类} + {偏好风格} women street style 2025"
```

- 搜索源：DuckDuckGo（免费无限次）
- 每个用户自动发现 2-5 个风格
- 仅收藏图片 + 来源 URL，不做完整百科
- 展示在手机端「其他推荐」区，用户可点击查看

---

## 七、工具改动清单

### 所有工具加 `--user` 可选参数

| 工具 | 改动 | 向下兼容 |
|------|------|---------|
| `wechat_control.py` | 所有 API 端点读 `?user=` 参数，路由到 `users/<id>/` | ✅ 无 `?user=` 时用默认单用户路径 |
| `build_prototype.py` | `--user <id>` 从 `users/<id>/outfits/` 扫描 | ✅ 无 `--user` 时扫描顶层 `outfits/` |
| `generate.py` | `--user <id>` 从 `users/<id>/wardrobe/` 取抠图 | ✅ |
| `composite_v2.py` | 输出到 `users/<id>/outfits/` | ✅ |
| `style_matcher.py` | `--user <id>` 读用户 profile + 风格偏好 | ✅ |
| `wardrobe_advisor.py` | `--user <id>` 分析用户衣橱 | ✅ |
| `rating_analyzer.py` | `--user <id>` 汇总用户评分 | ✅ |
| `build_push.py` | `--user <id>` 生成推送内容 | ✅ 暂不使用（无微信推送） |

### 新增工具

| 工具 | 功能 |
|------|------|
| `tools/user_manager.py` | 创建用户 / 扫描 registry / 生成 onboarding URL |
| `tools/quick_tag.py` | 快速入库：YOLO + 颜色 → 基础标签 JSON |
| `tools/style_scout_women.py` | 女性风格发现：按用户信号搜索图片 |

### `wechat_control.py` 路由改造

不改现有 Handler 结构，在 `do_GET` / `do_POST` 入口加一层路由：

```python
def resolve_user(handler):
    """从 URL 参数或 Cookie 解析当前用户"""
    qs = parse_qs(handler.path)
    user_id = qs.get('user', [None])[0]
    if user_id and user_id not in registry:
        return None, 'onboarding'  # 触发 onboarding
    return user_id or 'default', None

def get_user_dir(user_id):
    """返回用户数据根目录。
    user_id == 'default' → 项目根目录（现有单用户模式，wardrobe/outfits/在顶层）
    user_id == 'alice'  → users/alice/（多用户模式）
    """
    if user_id == 'default':
        return PROJECT_DIR  # 保持现有行为：wardrobe/ outfits/ 从项目根读
    return os.path.join(PROJECT_DIR, 'users', user_id)
```

### 关键端点行为

| 端点 | 无 `?user=` | 有 `?user=alice` |
|------|------------|-----------------|
| `GET /` | 返回现有单用户原型 | 返回 `users/alice/cache/prototype.html` |
| `GET /api/status` | 现有单用户状态 | Alice 的状态 |
| `POST /api/wardrobe/add` | 现有入库逻辑 | 入库到 `users/alice/wardrobe/` |
| `POST /api/recommend` | 现有推荐管线 | Alice 的衣橱 + 身形 + 女性风格库 |
| `GET /onboarding` | N/A | Onboarding 向导页面 |

---

## 八、手机端体验

### URL 结构
```
https://macbook-pro-1.taildbfbc0.ts.net/?user=alice
https://macbook-pro-1.taildbfbc0.ts.net/?user=becca
```

### 页面内容（与现有完全一致，数据按用户隔离）

```
┌─ Hero 区 ────────────────────────────────────┐
│  最新穿搭效果图 + 风格标签 + 配色条           │
├─ 单品清单（3列网格 + 图标）───────────────────┤
├─ 其他推荐（横向卡片 + 换一批）─────────────────┤
│  （含个人发现风格图片）                        │
├─ 历史推荐（可展开穿搭卡片）───────────────────┤
├─ 输入框 ─────────────────────────────────────┤
├─ Tab Bar ────────────────────────────────────┤
│  🧠推荐  🧪探索  👔衣橱  ➕添加  ⚙️设置        │
└──────────────────────────────────────────────┘
```

### 原型构建
- `build_prototype.py --user alice` → 扫描 `users/alice/outfits/` → 生成 `users/alice/cache/prototype.html`
- 首次访问时自动触发构建；后续通过「推荐」按钮触发重建
- 模板共享，数据按用户动态注入

---

## 九、分析面板（`/admin`）

仅供你查看的汇总面板，不向测试用户暴露。

### 端点
```
https://macbook-pro-1.taildbfbc0.ts.net/admin
```

### 显示内容

```
┌─────────────────────────────────────────────┐
│  女性用户测试 — 数据看板                      │
│  测试天数: 14  活跃用户: 8                   │
├─────────────────────────────────────────────┤
│  核心指标                                    │
│  ├─ 采纳率: 65% ████████░░░░  (目标>60%)     │
│  ├─ 平均评分: 3.8/5 ████████░░ (目标>3.5)    │
│  ├─ 7天复推率: 50% ██████████ (目标>40%)      │
│  ├─ 入库完成率: 90% ██████████ (目标>80%)     │
│  └─ 首次满意度: 75% █████████  (目标>70%)     │
├─────────────────────────────────────────────┤
│  用户列表                                     │
│  alice  │ 推荐12套 │ 评分3.9 │ 最近: 2h前     │
│  becca  │ 推荐8套  │ 评分3.2 │ 最近: 1天前    │
│  ...                                        │
├─────────────────────────────────────────────┤
│  入库队列                                     │
│  alice:  3件待review                        │
│  becca:  7件待review                        │
└─────────────────────────────────────────────┘
```

数据源：各用户 `outfits/*/analytics.json` 汇总。

---

## 十、实施阶段

### Phase A：基础架构（预计 1-2 天）

| # | 任务 | 产出 |
|---|------|------|
| A1 | 创建 `users/` 目录结构 + `_registry.json` | 数据隔离就绪 |
| A2 | `wechat_control.py` 加 `?user=` 路由 | 多用户请求分发 |
| A3 | 所有工具加 `--user` 可选参数 | 管线支持多用户 |
| A4 | `build_prototype.py --user` 支持 | 原型按用户构建 |
| A5 | 默认路径 fallback 验证 | 不传 `--user` 行为不变 |

### Phase B：女性适配（预计 3-5 天）

| # | 任务 | 产出 |
|---|------|------|
| B1 | 建立 `styles_women/` 12 个风格百科 | 女性风格库 |
| B2 | `style_scout_women.py` 个人风格发现 | 按用户信号搜图 |
| B3 | Onboarding HTML 页面（4步向导） | 用户注册流程 |
| B4 | `quick_tag.py` 快速入库管线 | YOLO+颜色自动标签 |
| B5 | 修改推荐引擎支持女性身形维度 | 生成提示词含女性身形 |
| B6 | Seedream prompt 适配女性 | 生图 prompt 改为女性主体 |

### Phase C：测试上线（预计 1-2 天）

| # | 任务 | 产出 |
|---|------|------|
| C1 | `/admin` 分析面板 | 指标看板 |
| C2 | `analytics.json` 自动记录 | 每套穿搭记录指标 |
| C3 | 邀请 5-10 名女性用户 | 用户就位 |
| C4 | 2 周数据收集 | 定量验证 |
| C5 | 测试报告 | 结论 + 后续方向 |

---

## 十一、风险与回退

### 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Seedream 生图对女性不友好 | 推荐效果差 | 先跑 5 张女性 prompt 验证，不行就跳过生图只做搭配推荐 |
| 快速入库基础标签太粗糙 | 推荐不准 | 用户前 3 天集中手动 review 标签 |
| Tailscale Funnel 带宽瓶颈 | 多用户同时上传卡顿 | 上传改为异步队列，一次只处理一张 |
| 用户流失 | 数据不够 | 首发邀请 10 人，预期 5 人持续使用即可达标 |

### 回退方案
- 所有改动在 `female-user-testing` 分支
- 如果测试期间你自己的系统出问题：`git checkout main` → 立即恢复
- 如果女性测试完全失败：删除 `users/` 和 `styles_women/`，分支保留作为参考

---

## 十二、待定项

1. **Seedream 女性生图效果**：需要先验证。如果效果差，考虑降级为「仅搭配推荐 + 实物平铺排版」，不生 AI 效果图。
2. **入库 review 节奏**：你有多少时间做品牌/文化补标？如果时间少，可能需要把基础标签的详细度提高（加面料和廓形检测）。
3. **用户邀请方式**：口头邀请 + 直接发 URL（`?user=alice`），还是做一个邀请码页面？
