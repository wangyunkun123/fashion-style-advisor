# A/B线推荐规则体系 — 完整梳理

> 生成时间：2026-06-17
> 核心文件：style_lab.py(2267行) / style_matcher.py(482行) / wechat_control.py(3043行) / build_push.py(903行)
> 配置文件：recommendation_rules.json / scene_profiles.json / explore_strategies.json / style_defaults.json / style_lab_state.json

---

## 一、A线 vs B线：两套独立推荐系统

```
┌──────────────────────────────────────────────────────────────────┐
│                    A线 (安全推荐) 3:1 B线 (探索推荐)              │
│                                                                  │
│  A线: wechat_control.py → AI prompt → 从衣柜表格自由选品          │
│  B线: style_lab.py → 锚点发现 → 策略驱动 → 同伴匹配               │
│                                                                  │
│  判断逻辑: should_use_bline() → total_recommendations % 4 == 0   │
│            should_use_bold()  → bline_count % 4 == 0 (B线内的1/4) │
│                                                                  │
│  触发词: 微调(探索/新尝试/微调/尝鲜等) / 大胆(大胆/冒险/跨界等)    │
│  强制标志: --no-bline → A线  /  --bline → B线  /  --bold → 大胆   │
└──────────────────────────────────────────────────────────────────┘
```

### 当前状态

| 指标 | 数值 |
|------|------|
| 总推荐次数 | 29 |
| B线次数 | 3 |
| 大胆次数 | 0 |
| A:B 比例 | 26:3 ≈ 9:1 (远低于设计的 3:1) |
| 涉及单品 | 44件 (共76件) |
| 最高频 | ACC-003(14次) / HAT-004(12次) / SHOE-005(10次) |

> ⚠️ 实际 A:B 比严重偏离 3:1，可能因为手机端触发不走 state 递增逻辑。

---

## 二、A线推荐流程（5层递进）

```
Layer 1: 天气场合映射 (style_defaults.json)
  ├─ 温度4档: ≥35 / 28-34 / 22-27 / ≤21
  ├─ 天气: 晴/雨/阴
  └─ 场合: 运动/约会/通勤/度假/户外/聚会/居家 → 推荐2-4个风格

Layer 2: AI Prompt 选品 (wechat_control.py OUTFIT_SYSTEM_PROMPT)
  ├─ 输入: 衣柜动态摘要(get_wardrobe_summary) + 禁用清单 + 最近已穿
  ├─ 输出: JSON {items, reasoning, color_logic, seedream_prompt}
  └─ 场景约束: 运动→功能鞋/运动短裤/速干面料

Layer 3: 硬阻断检查 (recommendation_rules.json hard_blocks)
  ├─ 温度: ≥35°C禁长袖/外套, ≤12°C禁短裤, ≤8°C禁帆布鞋
  ├─ 天气: 雨天禁白色下装/皮质鞋
  ├─ 场合: 商务禁短裤/球衣/运动鞋, 运动禁皮鞋/靴子/帆布鞋/牛仔裤/手串
  └─ 套装: 禁重复品类(两裤/两鞋/两外套)

Layer 4: 风格指纹评分 (style_matcher.py → SCORE_CACHE.json)
  ├─ 硬约束 → 颜色(25) + 软约束(~30) + 关键单品(0-20) + 身形(0-13)
  └─ 归一化0-100 → 写入缓存供后续使用

Layer 5: 推送增强 (build_push.py)
  ├─ 百科增强: 冷知识/品牌/名人/风格故事
  ├─ 配色色块: 从单品提取颜色生成 swatch
  ├─ 备选风格: "今天也适合"动态生成
  └─ 评分链接: 三级评分反馈回路
```

### ⚠️ A线核心问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **AI prompt 没用到 style_matcher 排名** | 🔴 | AI 纯看衣柜表格+文字描述选品，不知道每件单品的量化匹配分 |
| **AI prompt 没用到推荐规则** | 🔴 | recommendation_rules.json 的实用/美观/舒适层评分完全没进入推荐流程 |
| **AI prompt 没用到场景画像** | 🟡 | scene_profiles.json 只在 style_lab.py 中用，A线不调它 |
| **风格匹配只用于展示不用于决策** | 🔴 | SCORE_CACHE 算出来了，但 AI 做推荐时不看 |
| **关键单品不加分** | 🟡 | score_key_items() 取 max，不累加 |

---

## 三、B线推荐流程（10步探索引擎）

```
Step 1: 触发判断 (should_use_bline / detect_bline_trigger)
  ├─ 自动: total % 4 == 0 (每4次1次B线)
  └─ 手动: 触发词检测 (微调/大胆)

Step 2: 策略选取 (pick_explore_strategies)
  ├─ 微调: 从 micro 策略池随机取1个 (13个策略)
  └─ 大胆: 从 micro+bold 策略池随机取2个叠加

Step 3: 锚点发现 (find_anchor_items)
  ├─ 表现力(0.3): 图案独特性 + 颜色饱和度 + 罕见面料 + 品牌辨识度
  ├─ 风格适配(0.3): 8风格平均分
  └─ 审美(0.4): 衬肤色 + 有色彩 + 质感面料 + 身形修饰

Step 4: 单品解读 (analyze_item_appeal)
  ├─ 视觉签名: 颜色+图案组合
  ├─ 廓形态度: 版型+肩部+躯干效果
  ├─ 材质语言: 面料+质感
  └─ 风格亲和度: 强(≥60)/中(≥40)/弱(≥20)

Step 5: 舒适区分析 (get_user_comfort_zone)
  ├─ 舒适风格: 3星好评的风格
  ├─ 已探索: 所有被评价过的
  ├─ 未探索: 从未评价过的
  └─ 厌恶: 1星差评的

Step 6: 探索方向生成 (generate_exploration_directions)
  ├─ 微调: 从舒适区+related_styles出发, min_score=30
  │   距离分级: adjacent(舒适区内) / step(related延伸) / leap(跨风格)
  └─ 大胆: 排除舒适区+related, 从未探索/conflicting出发, min_score=15

Step 7: 同伴匹配 (find_companions)
  ├─ 风格匹配(40%): SCORE_CACHE中的目标风格分
  ├─ 颜色和谐(20%): 同色系1.0 / 中性+中性0.9 / 中性+任意0.75
  ├─ 天气适配(10%): 季节面料匹配
  └─ 策略规则(30%): 基础色+20 / 同色系+25 / 材质对比+20 / 正式/休闲+20 等

Step 8: 方案组装 (assemble_exploratory_outfit)
  └─ 锚点 + 同伴 + 方向 + 策略 → 完整方案

Step 9: 叙事生成 (generate_exploration_narrative)
  ├─ 锚点介绍: 视觉签名 + 材质语言 + 穿搭点评
  ├─ 探索方向: 目标风格 + 距离 + 理由
  ├─ 搭配逻辑: 每件同伴的颜色关系(和谐呼应/中性平衡/冲突张力)
  └─ 穿法建议: 根据锚点版型给出具体穿法

Step 10: 生图+推送 (prepare_bline_outfit)
  └─ outfit.md → 豆包提示词 → Seedream生图 → composite排版 → git push → CDN
```

### B线的13个探索策略

| 策略ID | 名称 | 难度 | 核心品类 | 搭配规则 |
|--------|------|------|----------|----------|
| category_flip | 品类反转 | 微调 | SHIRT/LS | 衬衫当外套,内搭贴身 |
| formal_casual_mix | 正式休闲混搭 | 微调 | JK/PT/SHIRT | 正式+休闲反向搭配 |
| same_color_diff_material | 同色异材质 | 微调 | TS/SH/PT | 同色系不同面料 |
| half_half_style | 上下风格对半 | 微调 | SHIRT/JK/PT/SH | 上半身正式→下半身休闲 |
| light_layering | 轻叠穿 | 微调 | TS/LS/SHIRT | 两件不同色叠穿 |
| accessory_lead | 配饰主导 | 微调 | HAT/ACC/SUN/SOCK | 全身基础色+亮色配饰 |
| hidden_gem | 冷门挖掘 | 微调 | 不限 | 低频单品+高频基础款 |
| sock_highlight | 袜子点睛 | 大胆 | SOCK | 全身基础色+图案袜 |
| hat_style_switch | 帽子换风格 | 大胆 | HAT | 帽子定基调 |
| shirt_untucked_unbuttoned | 衬衫不塞不扣 | 大胆 | SHIRT | 长衬衫垂坠+素T内搭 |
| shorts_long_socks | 短裤×长袜×皮鞋 | 大胆 | SH | 及膝短裤+中筒袜+皮质鞋 |
| short_over_long | 短袖叠长袖 | 大胆 | TS/SHIRT | 短袖外+长袖内层次 |
| cold_color_clash | 冷门配色碰撞 | 大胆 | TS/LS/SHIRT/JK | 刻意制造颜色冲突 |

---

## 四、推荐规则引擎（recommendation_rules.json）

### 四层评分体系

```
总分 = 硬阻断(一票否决) → 实用(0.5) + 美观(0.35) + 舒适(0.25)
```

| 层级 | 权重 | 规则数 | 作用 |
|------|------|--------|------|
| 硬阻断 | 一票否决 | 15条 | 温度/天气/场合不合适的直接淘汰 |
| 实用层 | 0.5 | 5条 | 三件套齐全(30)/场景匹配(40)/季节(20)/防晒(5)/防雨(5) |
| 美观层 | 0.35 | 4条 | 配色协调(30)/风格连贯(25)/廓形平衡(25)/体型修饰(20) |
| 舒适层 | 0.25 | 4条 | 面料舒适(30)/宽松版型(25)/衬肤色(25)/用户偏好(20) |

### 硬阻断规则详情

| ID | 条件 | 场景 |
|----|------|------|
| hot_no_heavy_jacket | ≥30°C + 厚外套(羊毛/皮质/灯芯绒) | 非商务/约会 |
| hot_no_long_sleeve | ≥35°C + 长袖上衣 | 所有 |
| hot_no_boots | ≥32°C + 靴子 | 所有 |
| extreme_hot_no_jacket | ≥35°C + 任何外套 | 所有 |
| cold_no_shorts | ≤12°C + 短裤 | 所有 |
| cold_no_canvas | ≤8°C + 帆布鞋/拖鞋 | 所有 |
| rain_no_white_bottom | 雨天 + 白色/米白下装 | 所有 |
| rain_no_leather_shoe | 雨天 + 皮质鞋 | 所有 |
| formal_no_shorts | 商务/正式 + 短裤 | 商务/正式 |
| formal_no_jersey | 商务/正式/约会 + 球衣/运动外套 | 商务/正式/约会 |
| formal_no_athletic_shoe | 商务/正式 + 运动鞋 | 商务/正式 |
| sport_no_leather_shoe | 运动 + 皮鞋/靴子/帆布鞋 | 运动 |
| sport_no_accessories | 运动 + 手串 | 运动 |
| sport_no_jeans | 运动 + 牛仔裤/西裤 | 运动 |
| no_jersey_on_date | 约会/聚会 + 球衣 | 约会/聚会 |
| no_tank_on_date | 约会 + 背心外穿 | 约会 |

---

## 五、场景画像（scene_profiles.json）

### 10个场景的详细定义

| 场景 | 必备品类 | 偏好面料 | 偏好版型 | 正式度 | 避雷品类 | 关键词 |
|------|---------|---------|---------|--------|---------|--------|
| 跑步 | TS+SH+SHOE | 涤纶/速干 | 宽松/合身 | 1-2 | JK/SHIRT/ACC/BAG/HAT | 跑步/运动/速干/健身 |
| 网球 | TS+SH+SHOE | 涤纶/速干/棉 | 合身/宽松 | 1-2 | JK/SHIRT/ACC | 网球/运动/速干 |
| 运动 | TS+SH+SHOE | 涤纶/速干/棉 | 宽松/合身 | 1-2 | JK/SHIRT/ACC | 运动/足球/篮球/曼联 |
| 商务 | SHIRT+PT+SHOE | 羊毛混纺/棉/皮质 | 合身/修身 | 3-5 | SH/TANK/TS | 商务/正式/西装 |
| 通勤 | TS+PT+SHOE | 棉/麻/羊毛混纺 | 合身/宽松 | 2-3 | SH/TANK | 通勤/上班/商务休闲 |
| 约会 | TS+PT+SHOE | 棉/亚麻/皮质/羊毛 | 合身/修身 | 2-4 | SH/TANK | 约会/轻熟/质感/干净 |
| 聚会 | TS+PT+SHOE | 棉/皮质/羊毛混纺 | 合身/宽松 | 2-3 | SH/TANK | 聚会/个性/街头/潮流 |
| 度假 | TS+SH+SHOE | 棉/亚麻/麻 | 宽松 | 1-2 | JK/LS | 度假/热带/印花/亚麻 |
| 户外 | TS+PT+SHOE | 涤纶/棉/速干 | 宽松/合身 | 1-2 | SHIRT/SH | 户外/骑行/运动/速干 |
| 居家 | TS+SH+SHOE | 棉/麻 | 宽松 | 1 | JK/SHIRT/BAG | 居家/休闲/舒适 |
| 日常 | TS+PT+SHOE | 不限 | 不限 | 1-3 | 不限 | 不限 |

### 场景评分函数：match_scene_profile()

```
关键词精确匹配 +30  (单品标签含场景关键词)
品类匹配 +15~30     (运动鞋在运动场景+30)
正式度匹配 +5       (正式度在场景范围内)
面料匹配 +5         (面料在偏好列表中)
版型匹配 +3         (版型在偏好列表中)
必备品类缺失 -20    (缺少必备品类)
避雷品类命中 -15    (含有避雷品类)
基础分 +30
```

---

## 六、两套系统的关系与断层

### 数据流对比

```
A线数据流:
  weather + occasion → style_defaults.json → 推荐风格列表
  → AI prompt (OUTFIT_SYSTEM_PROMPT) → 自由选品
  → 硬阻断检查 (只做了场景约束在prompt中)
  → (style_matcher 的 SCORE_CACHE 被算出来但没被用)
  → (recommendation_rules 的实用/美观/舒适层完全没进入流程)

B线数据流:
  style_lab_state → 触发判断 → 策略选取
  → find_anchor_items (自己的表现力/审美评分体系)
  → generate_exploration_directions (自己的舒适区/距离体系)
  → find_companions (风格40% + 颜色20% + 天气10% + 策略30%)
  → SCORE_CACHE 被查询但只占40%权重
  → 不调 style_matcher.compute_compatibility()
```

### 🔴 关键断层

| 断层 | A线 | B线 | 影响 |
|------|-----|-----|------|
| **评分体系** | style_matcher 算分 | style_lab 自己的综合分 | 两套分不可比 |
| **推荐规则** | 基本不用 | check_recommendation_rules() | 规则只在B线生效 |
| **场景画像** | 只靠 prompt 约束 | match_scene_profile() | 场景匹配精度不同 |
| **风格匹配** | 算但不用 | 用但只有40%权重 | 风格匹配被边缘化 |
| **单品评分** | compute_compatibility | compute_statement_score | 两个评分维度不同 |

---

## 七、优化方向建议

### 短期（对齐两套系统）

| # | 建议 | 说明 |
|---|------|------|
| 1 | **A线 prompt 引入风格匹配分** | 让 AI 看到每件单品的量化分 |
| 2 | **A线 prompt 引入推荐规则** | 实用/美观/舒适层的 check 结果 |
| 3 | **A线 prompt 引入场景画像** | 品类 boost/避雷信息 |
| 4 | **统一评分权重** | B线的同伴匹配应该也用 compute_compatibility 而非自己的40%权重 |
| 5 | **关键单品累加** | score_key_items() max→sum+cap |

### 中期（让B线更智能）

| # | 建议 | 说明 |
|---|------|------|
| 6 | **B线也要过 A线的硬阻断** | 目前 B线 prepare_bline_outfit 不调 check_recommendation_rules |
| 7 | **策略效果追踪** | 记录每个策略的用户反馈，好的策略加权，差的降权 |
| 8 | **锚点发现加场景过滤** | 目前 find_anchor_items 不看天气/场合 |
| 9 | **A:B 比例自适应** | 根据用户满意度动态调整（喜欢探索→多B线，喜欢安全→多A线） |

### 长期（知识层打通）

| # | 建议 | 说明 |
|---|------|------|
| 10 | **49百科 → 风格指纹自动化** | 让更多百科能参与匹配 |
| 11 | **穿搭历史画像** | "你70%是Clean Fit，从没试过国风"→主动推荐 |
| 12 | **季节性智能** | 月份+地域感知，不只是温度档 |

---

## 八、当前 state 数据洞察

从 `style_lab_state.json`：

- **B线占比严重不足**: 29次推荐中只有3次B线(10.3%)，远低于设计的25%
- **高频单品 Top 5**: ACC-003(14次)/HAT-004(12次)/SHOE-005(10次)/SOCK-005(7次)/SOCK-006(7次)
- **零穿着单品**: 32件(76-44)从未被推荐过
- **大胆模式从未触发**: bold_count=0，因为 B线次数不够(需要 bline_count%4==0 且>0)

> 这说明 B线触发机制在实际使用中可能没有正常工作（手机端调用可能不经过 state 递增路径），导致用户几乎没体验过探索推荐。

---

> 以上基于对所有相关文件的完整阅读：
> - style_lab.py (2267行) — B线完整引擎
> - style_matcher.py (482行) — 风格匹配引擎
> - wechat_control.py (3043行) — A线推荐入口
> - build_push.py (903行) — 推送+AB线决策
> - recommendation_rules.json (228行) — 4层推荐规则
> - scene_profiles.json (410行) — 10个场景画像
> - explore_strategies.json (204行) — 13个探索策略
> - style_defaults.json — 天气场合映射
> - style_lab_state.json — 当前状态快照
