# 服装推荐系统 — 完整优化计划

> 版本：v1.0 | 日期：2026-06-17
> 基于：CLAUDE.md / 22 memory文件 / style_lab.py(2267行) / style_matcher.py(482行)
>       / wechat_control.py(3043行) / build_push.py(903行) / 6个配置文件 / 8风格指纹 / 78服装标签

---

## 目录

1. [现状总览](#一现状总览)
2. [问题全景图](#二问题全景图)
3. [优化方案矩阵](#三优化方案矩阵)
4. [三阶段执行计划](#四三阶段执行计划)
5. [每项详细方案](#五每项详细方案)
6. [风险评估与回滚](#六风险评估与回滚)

---

## 一、现状总览

### 系统架构（6层 + AB双线）

```
                    ┌──────────────┐
                    │  用户请求     │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        触发词检测    should_use_bline  直接推荐
        (微调/大胆)   (每4次1次B线)    (日常)
              │            │            │
      ┌───────┴──────┐     │     ┌─────┴──────┐
      ▼              ▼     ▼     ▼            ▼
   B线微调        B线大胆  A线   A线         A线
  (13策略选1)  (13策略选2)  (AI自由)    (AI自由)

Layer 6: 评分学习  rating_analyzer.py  ← 三级评分→风格权重调整
Layer 5: 质量守则  CLAUDE.md          ← 6条硬约束
Layer 4: AI 推荐   wechat_control.py  ← A线主力（不调规则引擎）
Layer 3: 风格匹配  style_matcher.py   ← 算分但A线不用 ❌
Layer 2: 风格指纹  styles/*.json ×8   ← 只有8个可用，49个百科闲置
Layer 1: 天气映射  style_defaults.json ← 温度档太粗
         +场景画像  scene_profiles.json ← 只在B线用 ❌
         +推荐规则  recommendation_rules.json ← 只在B线用 ❌
```

### 核心数据

| 指标 | 数值 |
|------|------|
| 总推荐次数 | 29 |
| A线次数 | 26 (90%) |
| B线次数 | 3 (10%，设计目标25%) |
| 大胆次数 | 0 |
| 衣橱单品 | 76件 (44件穿过，32件从未推荐) |
| 风格指纹 | 8个可用 + 41个百科无指纹 |
| 风格百科 | 49个（含文化/历史/品牌/秀场/图片） |
| 探索策略 | 13个（7微调 + 6大胆） |
| 场景画像 | 10个 |
| 硬阻断规则 | 15条 |
| 评分缓存 | 76×8=608组 |

---

## 二、问题全景图

### 🔴 结构性缺陷（4个）

| # | 问题 | 严重度 | 影响范围 |
|---|------|--------|----------|
| P1 | **A线不使用风格匹配分** | 致命 | AI 纯靠文字描述选品，608组量化评分被浪费 |
| P2 | **A线不使用推荐规则引擎** | 致命 | 实用/美观/舒适三层评分(9条规则)从未进入推荐流程 |
| P3 | **A线不使用场景画像** | 严重 | 品类boost/避雷/关键词匹配只对B线生效 |
| P4 | **49个百科只有8个有指纹** | 严重 | 大量风格研究投入无法转化为推荐能力 |

### 🟡 精度问题（5个）

| # | 问题 | 说明 |
|---|------|------|
| P5 | **关键单品分不累加** | max()→只取最高分，全套匹配被低估 |
| P6 | **无颜色协调检查** | 红上衣+绿裤子可能被选，单品各自都符合风格 |
| P7 | **B线同伴匹配权重独立** | 40%风格+20%颜色+10%天气+30%策略，不与compute_compatibility对齐 |
| P8 | **身形修饰不区分部位** | 可能3件都修饰肩部但忽略腹部 |
| P9 | **天气温度档太粗** | 35°C和28°C推荐相同风格 |

### 🟢 体验问题（6个）

| # | 问题 | 说明 |
|---|------|------|
| P10 | **一星差评连坐** | 讨厌1件封杀整套5-7件 |
| P11 | **无冷却期** | ACC-003被穿14次，HAT-004被穿12次 |
| P12 | **B线占比严重不足** | 10% vs 设计25%，手机端可能不走state递增 |
| P13 | **32件单品从未被推荐** | 衣橱利用率仅58% |
| P14 | **无 outfit 级评分** | 只评单品不评搭配整体 |
| P15 | **无季节智能** | 不区分北京4月和10月（同温度不同穿衣逻辑） |

---

## 三、优化方案矩阵

### 完整方案清单（12项）

| ID | 方案 | 类型 | 复杂度 | 效果 | 优先级 |
|----|------|------|--------|------|--------|
| F1 | A线 prompt 引入风格匹配分 | 数据打通 | ⭐ | 🔥🔥🔥 | P0 |
| F2 | A线 prompt 引入场景画像 | 数据打通 | ⭐ | 🔥🔥🔥 | P0 |
| F3 | A线 prompt 引入推荐规则 | 数据打通 | ⭐⭐ | 🔥🔥 | P0 |
| F4 | 关键单品评分改为累加 | 算法修正 | ⭐ | 🔥🔥 | P0 |
| F5 | B线过A线硬阻断 | 安全加固 | ⭐ | 🔥🔥 | P1 |
| F6 | B线同伴匹配统一用 compute_compatibility | 算法对齐 | ⭐⭐ | 🔥🔥 | P1 |
| F7 | 7天冷却期机制 | 体验提升 | ⭐ | 🔥🔥 | P1 |
| F8 | 一星精准禁用 | 体验提升 | ⭐⭐ | 🔥🔥 | P1 |
| F9 | outfit 级颜色协调评分 | 精度提升 | ⭐⭐ | 🔥 | P1 |
| F10 | 风格指纹半自动化生成 | 知识层打通 | ⭐⭐⭐ | 🔥🔥🔥 | P2 |
| F11 | A:B比例自适应 | 体验提升 | ⭐⭐ | 🔥 | P2 |
| F12 | 冷门单品唤醒机制 | 体验提升 | ⭐ | 🔥 | P2 |

### 效果-成本矩阵

```
高效果 ↑
      │ F10(指纹生成)    F2(场景画像)  F1(匹配分)
      │                  F3(推荐规则)
      │ F6(同伴对齐)     F5(B线硬阻断) F4(关键单品累加)
      │ F9(颜色协调)     F7(冷却期)    F8(精准禁用)
      │ F11(AB自适应)   F12(冷门唤醒)
低效果 ─┼──────────────────────────────────→
      低成本                              高成本
```

---

## 四、三阶段执行计划

### 阶段一：打通数据断层（P0 — 4项）

> 目标：让A线AI能看到所有已有数据，推荐从"凭感觉"变为"有依据"
> 工时：约1-2小时

| ID | 方案 | 改动文件 | 行数 |
|----|------|----------|------|
| F1 | A线 prompt 引入风格匹配分 | wechat_control.py | +20 |
| F2 | A线 prompt 引入场景画像 | wechat_control.py | +15 |
| F3 | A线 prompt 引入推荐规则 | wechat_control.py | +15 |
| F4 | 关键单品评分改为累加 | style_matcher.py | -3+5 |

**F1: A线 prompt 引入风格匹配分**

```
改前：AI 看到的 prompt
  ## 短袖上衣
  | ID | 品牌·系列 | 颜色 | 场景标签 | 穿搭提示 |
  | TS-001 | Lululemon Metal Vent Tech | 藏青色 | ... | ... |

改后：AI 看到的 prompt（追加在衣柜表格之后）
  ─── 风格匹配参考（分数越高越适合此风格）───
  ### 🎯 Clean Fit (推荐风格)
  | ID | 匹配分 | 关键单品 | 颜色 | 身形 |
  |-----|--------|---------|------|------|
  | TS-001 | 78 ⭐ | +20 | +8 | +5 |
  | TS-003 | 65 | 0 | +5 | +3 |
  | PT-002 | 72 | +15 | +6 | 0 |
  ...
  
  ### 🎯 韩系简约 (备选)
  | ID | 匹配分 | 关键单品 | 颜色 | 身形 |
  ...
```

**F2: A线 prompt 引入场景画像**

```
改前：场景约束只在 OUTFIT_SYSTEM_PROMPT 中一句话
  "运动场景必须选功能运动鞋，不可选工装靴、帆布鞋"

改后：动态注入场景画像
  📋 场景画像：运动
  - 必备品类：TS(短袖) + SH(短裤) + SHOE(运动鞋)
  - 品类加分：TS+15 / SH+15 / SHOE+25
  - 避雷品类：JK(外套) / SHIRT(衬衫) / ACC(手串)
  - 偏好面料：涤纶/速干/棉
  - 偏好版型：宽松/合身
  - 关键词匹配加分：运动/足球/篮球/曼联/速干/健身 (+30分)
```

**F3: A线 prompt 引入推荐规则**

```
改后：在 prompt 中追加
  ⚠️ 推荐质量检查清单：
  □ 三件套齐全（上衣+下装+鞋子）
  □ 配色协调无冲突撞色
  □ 单品风格分≥30
  □ 上宽下窄/外松内紧廓形平衡
  □ 偏瘦体型修饰（增加肩宽/体量感）
  □ 面料舒适度（棉/麻优先）
  □ 衬偏白肤色
```

**F4: 关键单品评分改为累加**

```python
# style_matcher.py:187-217
# 改前：max_bonus = max(max_bonus, ki.get('bonus', 0))
# 改后：total_bonus += ki.get('bonus', 0); return min(total_bonus, 30)
```

---

### 阶段二：系统对齐+体验修复（P1 — 5项）

> 目标：AB两线统一评分标准，修复连坐/高频复用等问题
> 工时：约2-3小时

| ID | 方案 | 改动文件 | 行数 |
|----|------|----------|------|
| F5 | B线过A线硬阻断 | style_lab.py | +10 |
| F6 | B线同伴匹配统一评分 | style_lab.py | ~30 |
| F7 | 7天冷却期 | wechat_control.py | ~10 |
| F8 | 一星精准禁用 | wechat_control.py + rating.html | ~50 |
| F9 | outfit 级颜色协调评分 | 新建 score_outfit() | ~60 |

**F5: B线也要过A线硬阻断**

`prepare_bline_outfit()` 在创建 outfit 之前调用 `check_recommendation_rules(rule_set='hard')`，确保 B线不会选出运动场景穿皮鞋这类违规搭配。

**F6: B线同伴匹配统一用 compute_compatibility**

`find_companions()` 当前用 `风格40%+颜色20%+天气10%+策略30%`。改为 `compute_compatibility()×60% + 策略规则×30% + 颜色和谐×10%`，与A线评分体系统一。

**F7: 7天冷却期**

- `get_recent_outfit_items(limit=3)` → `limit=7`
- prompt 中明确"7天内已穿核心单品请避免"
- 软约束（"至少换两件"），不硬性禁用

**F8: 一星精准禁用**

`get_banned_items()` 重写：
- `item_issue` + 指定ID → 只禁用该单品
- `combo_dislike` / `style_mismatch` / `scene_mismatch` → 不禁用
- 无二级反馈（老数据）→ 保持原行为
- rating.html 一星时增加单品勾选框

**F9: outfit 级颜色协调评分**

新建 `score_outfit(items)` 函数：
```
评分维度：
- 主色调统一度 (40%): 所有单品色相族是否和谐
- 明度节奏 (30%): 上浅下深/上深下浅/全明/全暗
- 饱和度平衡 (20%): 高低饱和搭配是否合理
- 冲突检测 (10%): 红+绿/橙+蓝等冲突色扣分
```

---

### 阶段三：知识层打通+智能进化（P2 — 3项）

> 目标：49个百科→指纹、AB比例自适应、冷门唤醒
> 工时：约4-6小时

| ID | 方案 | 改动文件 | 行数 |
|----|------|----------|------|
| F10 | 风格指纹半自动化生成 | 新建工具脚本 | ~200 |
| F11 | A:B比例自适应 | style_lab.py | ~30 |
| F12 | 冷门单品唤醒 | style_lab.py | ~20 |

**F10: 风格指纹半自动化生成**

从 `encyclopedia.md` 提取关键信息 → 生成初始指纹JSON → 人工审核。

```
输入: styles_universal/gorpcore/encyclopedia.md
处理: LLM 提取 →
  - 一句话定义 → description
  - 起源章节 → 文化背景
  - 品牌章节 → 代表品牌
  - 配色逻辑 → color_rules
  - 面料特征 → fabric preferences
  - 关键单品 → key_items
输出: styles/gorpcore.json (初始指纹)
```

目标：将8个指纹扩展到15-20个，覆盖高优先级百科。

**F11: A:B比例自适应**

根据用户评分反馈动态调整：
- 用户对B线穿搭评分高 → B线频率从25%提升到40%
- 用户对B线评分低 → 降回15%
- 用户从未评价B线 → 保持25%

**F12: 冷门单品唤醒**

`find_anchor_items()` 中增加"冷门优先"模式：
- 32件零穿着单品自动获得 +0.2 coldness bonus
- B线微调时，30%概率启用冷门优先
- 推送中标注"🆕 首次登场"增加新鲜感

---

## 五、每项详细方案

### F1: A线 prompt 引入风格匹配分

**现状**:
```python
# wechat_control.py:1581 — AI 只看到衣柜表格
user_prompt = f"""...
以下是完整衣柜档案：
---
{wardrobe_summary}
---
请输出 JSON 格式的穿搭方案。"""
```

**改为**:
```python
# wechat_control.py run_pipeline() 中，构建 user_prompt 之前

# ── 计算推荐风格 ──
from style_matcher import auto_suggest_style, load_all_clothing, compute_compatibility, load_style as load_style_matcher

temp_high = 30  # 可从天气API获取
suggestions = auto_suggest_style(temp_high, '晴', '日常')
top_styles = [s['style_id'] for s in suggestions[:3]]

# ── 为推荐风格计算每件单品匹配分 ──
match_sections = []
all_clothes = load_all_clothing()

for sid in top_styles:
    style = load_style_matcher(sid)
    style_name = style.get('name_zh', sid) if style else sid
    
    # 只取匹配分≥30的关键品类（上衣/下装/鞋子）
    key_cats = {'TS','LS','SHIRT','TANK','PT','SH','SHOE'}
    rows = []
    for cid, item in sorted(all_clothes.items()):
        if item.get('category_code','') not in key_cats:
            continue
        score, details = compute_compatibility(cid, sid)
        if score >= 30:
            bd = details.get('breakdown', {})
            key_str = '⭐' if bd.get('key_item_bonus', 0) > 0 else ''
            rows.append(f"| {cid} | {score} {key_str} | {bd.get('color_compatibility',0)} | {bd.get('key_item_bonus',0)} | {bd.get('body_modifier',0)} |")
    
    if rows:
        match_sections.append(f"""### 🎯 {style_name} 单品匹配分（仅供参考）
| ID | 匹配分 | 颜色 | 关键单品 | 身形 |
|-----|--------|------|---------|------|
{chr(10).join(rows)}""")

match_text = '\n\n'.join(match_sections)

user_prompt = f"""...
以下是完整衣柜档案：
---
{wardrobe_summary}
---

{'─── 风格匹配参考（分数越高越适合此风格，⭐=关键单品）───' if match_text else ''}
{match_text}

请输出 JSON 格式的穿搭方案。"""
```

**效果**: AI 选品时有量化数据支撑，不再纯靠文字描述猜测。

---

### F2: A线 prompt 引入场景画像

**现状**: 场景约束只在 OUTFIT_SYSTEM_PROMPT 中一句话。

**改为**: 动态读取 scene_profiles.json，匹配当前场合，注入到 prompt。

```python
# 在 run_pipeline() 中，构建 user_prompt 之前

import json as _json
scene_profiles_path = os.path.join(PROJECT_DIR, 'config', 'scene_profiles.json')
scene_section = ''
if os.path.exists(scene_profiles_path):
    with open(scene_profiles_path) as f:
        profiles = _json.load(f).get('profiles', {})
    
    # 匹配场合（从 style_hint 中提取）
    occasion = '日常'
    for kw in ['运动','网球','跑步','通勤','约会','度假','户外','聚会','居家','商务']:
        if kw in style_hint:
            occasion = kw
            break
    
    profile = profiles.get(occasion, profiles.get('日常', {}))
    if profile:
        required = ' + '.join(profile.get('required', []))
        avoid_cats = '、'.join(profile.get('avoid', [])) or '无'
        boost_cats = '、'.join(f"{k}(+{v})" for k, v in profile.get('category_boost', {}).items()) or '无'
        fabrics = '、'.join(profile.get('traits', {}).get('fabric', [])) or '不限'
        fits = '、'.join(profile.get('traits', {}).get('fit', [])) or '不限'
        formality = profile.get('traits', {}).get('formality', [1,2,3,4,5])
        keywords = '、'.join(profile.get('keywords', [])) or '无'
        
        scene_section = f"""
📋 场景画像：{occasion}
- 必备品类：{required}
- 品类加分：{boost_cats}
- 避雷品类：{avoid_cats}
- 偏好面料：{fabrics}
- 偏好版型：{fits}
- 正式度范围：{min(formality)}-{max(formality)}
- 关键词匹配加分：{keywords}（单品标签含这些词+30分）
"""
```

**效果**: AI 有完整的场景约束信息，不会出现运动场景选皮鞋。

---

### F3: A线 prompt 引入推荐规则

**改为**: 在 OUTFIT_SYSTEM_PROMPT 末尾追加推荐质量检查清单。

```python
OUTFIT_SYSTEM_PROMPT = """...原有内容...

⚠️ 推荐质量检查（请在选品时逐项确认）：
□ 三件套齐全：上衣 + 下装 + 鞋子，缺一不可
□ 配色协调：无红绿/橙蓝等冲突撞色，整体色调统一
□ 风格连贯：每件单品对目标风格的匹配分 ≥ 30
□ 廓形平衡：上宽下窄 或 外松内紧，避免全身同宽
□ 体型修饰：偏瘦体型优先选增加肩宽/体量感的单品
□ 面料舒适：优先棉/麻/亚麻等亲肤面料
□ 衬肤色：偏白肤色优先选低饱和冷色调"""
```

**效果**: AI 有明确的质量自检清单，减少不协调搭配。

---

### F5: B线过A线硬阻断

**现状**: `prepare_bline_outfit()` 直接创建 outfit，不过硬阻断。

**改为**: 在创建 outfit 之前检查：

```python
# style_lab.py prepare_bline_outfit() 中，创建目录之前

from style_lab import check_recommendation_rules

# 组装 outfit_items 用于规则检查
outfit_items = [anchor_item] + [c['item'] for c in companions[:5]]

# 硬阻断检查
passed, violations, _ = check_recommendation_rules(
    outfit_items=outfit_items,
    weather_temp=weather_temp,
    weather_cond=weather_cond,
    occasion='日常',
    rule_set='hard'
)

if not passed:
    print(f"  [B线] 硬阻断: {violations}")
    # 降级：只用锚点+风格匹配最高的2件
    companions = sorted(companions, key=lambda c: c.get('style_score', 0), reverse=True)
    # 重新检查...
```

**效果**: B线不会选出运动场景穿皮鞋的违规搭配。

---

### F6: B线同伴匹配统一评分

**现状**: `find_companions()` 综合分 = 风格40% + 颜色20% + 天气10% + 策略30%

**改为**: 综合分 = compute_compatibility×60% + 策略规则×30% + 颜色和谐×10%

```python
# style_lab.py find_companions() 中
from style_matcher import compute_compatibility

for cid, item in wardrobe.items():
    ...
    # 旧：style_score = score_cache[cid][target_style_id].get('score', 0)
    # 新：统一用 compute_compatibility
    compat_score, compat_details = compute_compatibility(cid, target_style_id)
    
    # 旧：composite = style_score*0.4 + harmony*100*0.2 + weather_score*100*0.1 + rule_bonus*100/30*0.3
    # 新：
    composite = compat_score * 0.6 + rule_bonus * 100/30 * 0.3 + harmony * 100 * 0.1
```

**效果**: AB两线对同一件单品的评分可比较，风格匹配不再被边缘化。

---

## 六、风险评估与回滚

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| F1 匹配分表格使 prompt 过长 | 中 | AI 截断丢失信息 | 只展示分≥30的关键品类，每个风格限20行 |
| F1-F3 同时注入使 prompt 超长 | 中 | API 调用失败 | 总长度控制在8000 tokens内，超出则缩略 |
| F4 关键单品累加导致某件虚高 | 低 | 某单品被过度推荐 | cap=30 限制，只在风格评估中使用 |
| F5 B线过硬阻断后无候选 | 低 | B线生成失败 | 降级到只用锚点+top2同伴 |
| F6 统一评分后B线推荐变保守 | 中 | B线失去探索性 | 策略规则权重保持30%，保留探索空间 |
| F8 精准禁用遗漏问题单品 | 低 | 问题单品再次出现 | 保留"无二级反馈→全禁用"向后兼容 |

### 回滚策略

每项改动都是独立的，可以在 `git revert` 单独回滚。建议每完成一项就 commit 一次，commit message 格式：

```
🔧 F1: A线 prompt 引入风格匹配分
🔧 F2: A线 prompt 引入场景画像
...
```

---

## 附录：改动的文件清单

| 文件 | 阶段一 | 阶段二 | 阶段三 |
|------|--------|--------|--------|
| tools/wechat_control.py | F1 F2 F3 | F7 F8 | — |
| tools/style_matcher.py | F4 | — | — |
| tools/style_lab.py | — | F5 F6 | F11 F12 |
| templates/rating.html | — | F8 | — |
| tools/score_outfit.py | — | F9(新建) | — |
| tools/generate_fingerprints.py | — | — | F10(新建) |

---

> 以上计划涵盖了之前三轮分析（阶段一4项 + AB线断层 + 新发现）的全部发现。
> 共12项优化，分3阶段执行，每阶段完成后可独立验证效果。
