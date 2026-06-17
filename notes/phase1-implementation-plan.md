# 阶段一：4项快速修复 — 详细实施方案

> 生成时间：2026-06-17
> 基于实际代码分析

---

## 📋 总览

| # | 优化项 | 改动文件 | 改动量 | 风险 |
|---|--------|----------|--------|------|
| 1 | AI prompt 引入 style_matcher 排名 | `wechat_control.py` | ~15行 | 低 |
| 2 | 关键单品分改为累加 | `style_matcher.py` | ~5行 | 低 |
| 3 | 7天冷却期 | `wechat_control.py` | ~10行 | 低 |
| 4 | 一星精准反馈 | `rating.html` + `wechat_control.py` | ~20行 | 低 |

---

## 优化1: AI prompt 引入 style_matcher 排名

### 问题
当前 `OUTFIT_SYSTEM_PROMPT`（wechat_control.py:1501-1529）只是让 AI 从衣柜表格中自由选择，完全没用上 `style_matcher.py` 计算出的单品-风格兼容度分数。

### 改什么

**文件**: `tools/wechat_control.py`

**位置1**: `run_pipeline()` 函数中（约1581行），在调用 AI 之前，先跑 style_matcher 计算出每个候选风格下每件单品的分数，然后追加到 user_prompt 中。

**具体做法**:

```python
# 在 run_pipeline() 的 user_prompt 构建处（约1581行之前），插入：

# ── 风格匹配分（AI 推荐的量化依据）──
import sys as _sys
_sys.path.insert(0, os.path.join(BASE_DIR))
from style_matcher import auto_suggest_style, load_all_clothing, compute_compatibility

# 1. 推荐风格
suggestions = auto_suggest_style(temp_high=30, condition='晴', occasion='日常')
top_styles = [s['style_id'] for s in suggestions[:3]]

# 2. 对推荐风格，给每个单品打分
match_section = ''
if top_styles:
    all_clothes = load_all_clothing()
    for sid in top_styles:
        style = load_style(sid)  # 需要 import
        style_name = style.get('name_zh', sid) if style else sid
        match_section += f'\n### 🎯 {style_name} 单品匹配分（仅供参考，分数越高越适合此风格）\n'
        match_section += '| ID | 匹配分 | 关键单品 | 身形修饰 |\n'
        match_section += '|-----|--------|---------|----------|\n'
        for cid, item in sorted(all_clothes.items()):
            score, details = compute_compatibility(cid, sid)
            if score >= 30:
                bd = details.get('breakdown', {})
                key_str = '⭐' if bd.get('key_item_bonus', 0) > 0 else ''
                body_str = f'+{bd.get("body_modifier", 0)}' if bd.get('body_modifier', 0) > 0 else ''
                match_section += f'| {cid} | {score} {key_str} | {bd.get("key_item_bonus", 0)} | {body_str} |\n'

# 3. 把匹配分附加到 user_prompt
user_prompt = f"""...原有内容...

---
{match_section}
---

⚠️ 以上匹配分仅供参考，你仍然需要综合判断颜色协调、场景适配、整体搭配感。"""
```

**改动量**: 约15行代码插入到 `run_pipeline()` 中。

**效果**: AI 在选品时能看到每件单品对目标风格的量化匹配分（含关键单品⭐标记和身形修饰加分），推荐更有数据支撑。

---

## 优化2: 关键单品分改为累加（加 cap）

### 问题
`score_key_items()`（style_matcher.py:187-217）用 `max()` 取最高 bonus，多件关键单品不能累加。如果一套 outfit 有速干T恤(+15) + 运动鞋(+20) + 运动短裤(+10)，只加20分而不是45分。

### 改什么

**文件**: `tools/style_matcher.py`，第 187-217 行

**当前代码**:
```python
def score_key_items(clothing, style):
    """关键单品加分，取最大匹配 bonus（不叠加）"""
    max_bonus = 0
    ...
    for ki in style.get('key_items', []):
        ...
        if matches:
            max_bonus = max(max_bonus, ki.get('bonus', 0))
    return max_bonus
```

**改为**:
```python
def score_key_items(clothing, style):
    """关键单品加分，累加但上限 30 分"""
    total_bonus = 0
    ...
    for ki in style.get('key_items', []):
        ...
        if matches:
            total_bonus += ki.get('bonus', 0)
    return min(total_bonus, 30)  # 上限 30 分，防止某件单品匹配过多关键项
```

**同时调整** `compute_compatibility()` 中的 `max_possible`：
```python
# 第259行
max_possible = 88  # 旧值
max_possible = 98  # 新值（关键单品从 max 20 → max 30，增加10）
```

**改动量**: 改2行 + 1行常量调整。

**效果**: "全套匹配"的 outfit 得到更高的合理分数。

---

## 优化3: 7天冷却期

### 问题
目前只有一星差评禁用，没有日常避免重复的机制。同一天多次请求时已经通过 `get_recent_outfit_items(limit=3)` 有了一定避免，但跨度不够。

### 改什么

**文件**: `tools/wechat_control.py`

**位置1**: 增强 `get_recent_outfit_items()` 函数（约332行），从 limit=3 改为 limit=7（覆盖一周），但保持输出简洁。

**当前**:
```python
def get_recent_outfit_items(limit=3):
```

**改为**:
```python
def get_recent_outfit_items(limit=7):
```

**位置2**: 在 `run_pipeline()` 的 user_prompt 中，把冷却期规则写得更明确。

**当前**（约1579行）:
```python
recent_section = '\n📌 最近已穿（请避开这些核心单品，至少换掉上衣/下装/鞋子中的两件）:\n' + ...
```

**改为**:
```python
recent_section = '\n📌 7天内已穿核心单品（请避开这些单品，确保上衣+下装+鞋子至少换掉两件）:\n' + ...
```

**位置3**: 在 `OUTFIT_SYSTEM_PROMPT`（约1501行）中加冷却期规则：
```python
OUTFIT_SYSTEM_PROMPT = """...
- ⚠️ 场景匹配：运动场景（网球/跑步/健身）必须选功能运动鞋/跑鞋/网球鞋，不可选工装靴、帆布鞋、拖鞋、亚麻裤等非运动单品
- ⚠️ 7天冷却期：prompt中列出的「最近已穿」核心单品请尽量避免使用，优先选7天内未穿过的单品"""
```

**改动量**: 改3处，约10行。

**效果**: AI 有明确的7天冷却意识，提升穿搭多样性。

---

## 优化4: 一星精准反馈（不连坐）

### 问题
当前一星差评 → 整个 outfit 的所有单品加入禁用清单（`get_banned_items()` 扫描 rating==1 的 outfit 中所有ID）。用户可能只讨厌其中一件，但连带封杀了5-7件好单品。

### 现状分析
好消息是 `templates/rating.html` 已经做了一星二级反馈！

**已有功能**（rating.html:58-65）:
```html
<div class="form2" id="form2">
  <h3>哪里不满意？</h3>
  <label><input type="radio" name="reason" value="style_mismatch"> 风格不匹配</label>
  <label><input type="radio" name="reason" value="scene_mismatch"> 场景不适用</label>
  <label><input type="radio" name="reason" value="combo_dislike"> 搭配不喜欢</label>
  <label><input type="radio" name="reason" value="item_issue"> 单品不合适</label>
  <textarea id="note" placeholder="补充说明（可选）"></textarea>
</div>
```

**但问题在于**: 反馈数据虽然被收集到 `rating.json` 的 `feedback` 字段中，`get_banned_items()` 并没有读取 `feedback` 来区分"整套搭配不喜欢"和"某件单品不合适"。它粗暴地把整个 outfit 的所有单品都禁用了。

### 改什么

**方案**: 利用已有的二级反馈数据，实现精准禁用。

**改动1**: `wechat_control.py` 的 `get_banned_items()`（约303行）

```python
def get_banned_items():
    """获取因一星评价被禁用的单品清单。
    
    规则：
    - 如果用户标记了 item_issue + 在 note 中指定了单品ID → 只禁用该单品
    - 如果用户标记了 combo_dislike/style_mismatch/scene_mismatch → 不禁用单品（是搭配/场景问题，不是单品问题）
    - 如果没有二级反馈（老数据）→ 保持原有行为（整 outfit 禁用），向后兼容
    """
    outfit_base = os.path.join(PROJECT_DIR, 'outfits')
    banned = []
    for d in os.listdir(outfit_base):
        dp = os.path.join(outfit_base, d)
        if not os.path.isdir(dp):
            continue
        rating_file = os.path.join(dp, 'rating.json')
        if not os.path.exists(rating_file):
            continue
        try:
            with open(rating_file, 'r') as f:
                rating_data = json.load(f)
            if rating_data.get('rating') != 1:
                continue
            
            feedback = rating_data.get('feedback', {})
            reason = feedback.get('reason', '')
            detail = feedback.get('detail', '')
            
            md = os.path.join(dp, 'outfit.md')
            if not os.path.exists(md):
                continue
            with open(md, 'r') as f:
                content = f.read()
            all_ids = list(set(re.findall(
                r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                content
            )))
            
            if reason == 'item_issue':
                # 精准禁用：只禁用用户在 note 中指定的单品
                mentioned = re.findall(
                    r'\b(TS-\d+|SH-\d+|PT-\d+|JK-\d+|SHIRT-\d+|SHOE-\d+|BAG-\d+|HAT-\d+|SUN-\d+|SOCK-\d+|ACC-\d+|TANK-\d+|LS-\d+)',
                    detail
                )
                if mentioned:
                    banned.extend(mentioned)
                else:
                    # 用户选了"单品不合适"但没写具体ID → 不禁用，因为没有具体目标
                    pass
            elif reason in ('combo_dislike', 'style_mismatch', 'scene_mismatch'):
                # 搭配/风格/场景问题 → 不禁用单品
                pass
            else:
                # 没有二级反馈（老数据）→ 保持原有行为
                banned.extend(all_ids)
        except:
            pass
    return list(set(banned))
```

**改动2**: `templates/rating.html` 中增加单品选择器（选填）

在一星表单中增加一个单品多选，让用户可以精准指出是哪件不满意：

```html
<!-- 在 form2 中，textarea 之前加入 -->
<div id="item-select" style="display:none;margin-top:12px;text-align:left">
  <p style="font-size:13px;color:#888;margin-bottom:8px">具体是哪件不满意？（可选）</p>
  <div id="item-list" style="display:flex;flex-wrap:wrap;gap:6px"></div>
</div>
```

对应 JS：
```javascript
// 在 selectRating(1) 时加载单品列表
if (n === 1) {
  fetch('/api/outfit/' + outfitId)
    .then(r => r.json())
    .then(d => {
      let html = (d.items||[]).map(i => 
        `<label style="display:inline-flex;align-items:center;padding:6px 10px;border:1px solid #e0d5c5;border-radius:6px;font-size:12px;cursor:pointer">
          <input type="checkbox" name="bad_item" value="${i.id}" style="margin-right:4px">${i.id} ${i.name}
        </label>`
      ).join('');
      document.getElementById('item-list').innerHTML = html;
      document.getElementById('item-select').style.display = 'block';
    });
}
```

**改动量**: 
- `get_banned_items()` 重写约40行
- `rating.html` 增加单品选择器约15行

**效果**: 
- 用户选"单品不合适"+勾选TS-005 → 只禁用TS-005
- 用户选"搭配不喜欢" → 不禁用任何单品
- 老数据（无二级反馈）→ 保持原有行为

---

## 实施顺序建议

```
Step 1: 优化2（关键单品累加）     ← 最简单，改1个函数
Step 2: 优化3（7天冷却期）       ← 改参数+prompt
Step 3: 优化1（引入匹配分）       ← 核心改动，需要测试
Step 4: 优化4（精准禁用）         ← 逻辑最复杂，需要仔细测试
```

## 风险评估

| 风险 | 缓解 |
|------|------|
| 匹配分表格可能让 prompt 过长 | 只展示分数≥30的单品，每个风格限制在关键品类 |
| 关键单品累加可能导致某件单品虚高 | cap=30 限制，且只在单品对风格的评估中使用 |
| 冷却期可能让 AI 无单品可选 | 保留"至少换两件"的软约束而非绝对禁止 |
| 精准禁用可能遗漏问题单品 | 保留"无二级反馈→全禁用"的向后兼容 |

---

> 以上所有改动基于对实际代码的完整分析。
> 确认后我将按 Step 1→4 顺序逐步实施。
