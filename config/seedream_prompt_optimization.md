# Seedream 生图 Prompt 优化方案

## 问题诊断

### 当前 prompt 症状
所有生图 prompt 都是同一个模板：

> "Full-body high-quality portrait of a 30-year-old Asian man, 179cm tall, slim, fair skin, wearing [服装清单], standing on a sunny Beijing street, natural lighting, slight smile, relaxed posture."

这导致生成的图片有以下问题：
- 🧍 **姿势呆板** — 永远是"standing"站立，像证件照
- 📷 **构图单一** — 永远是"full-body"全身正面，没有变化
- 🏙️ **场景疲劳** — 永远是"Beijing street"，千篇一律
- 😐 **表情僵硬** — "slight smile"每次都一样，缺乏情绪层次
- 🎬 **缺少摄影感** — 没有相机角度、光影风格、景深控制

### 根因分析

| 层面 | 问题 |
|------|------|
| **AI prompt 模板** (`unified_pipeline.py`) | seedream_prompt 要求只给了 "英文、详细描述服装、全身照、高质量写真"，没有给摄影指导 |
| **输出 JSON 约束** (`wechat_control.py`) | seedream_prompt 字段说明过于简单，AI 只会套模板 |
| **Pass 2 prompt** (`generate.py`) | 强制 "keep everything EXACTLY as image 1"，锁死所有变化空间 |
| **Seedream 5.0 限制** | 不支持 `negative_prompt` 和 `guidance_scale`，所有控制必须在 prompt 中完成 |

---

## 优化方案

### 一、Prompt 结构重构：从"说明书"到"摄影指导"

旧模板（三段式）：
```
[人物描述] + [服装清单] + [场景+光线]
```

新模板（七段式）：
```
[摄影风格标签] + [构图/角度] + [光影气氛] + [动态姿势] + [服装描述] + [场景环境] + [情绪故事感]
```

**新模板示例：**

```
Fashion editorial photography, shot on Fujifilm X-T5 with 35mm f/1.4 lens, 
 shallow depth of field with creamy bokeh.

Low angle shot from knee height, rule of thirds composition, subject
 slightly off-center, full-body framing with breathing room above head.

Golden hour late afternoon light, warm directional sunlight creating 
 rim light on shoulders, soft diffused shadows, sun-kissed skin tones.

[姿势 — 从姿势库选]
[服装 — 保持现有详细描述]
[场景 — 从场景库选]
[情绪 — 从情绪库选]
```

### 二、动态姿势库 Pose Library

按风格分类，每次随机或按风格选用：

#### 街头/休闲
- `walking confidently toward camera, mid-stride, one hand casually in pocket, head slightly tilted, looking ahead with quiet confidence`
- `leaning against a textured concrete wall, arms crossed loosely, gazing off to the side, one foot propped against wall`
- `crouching down tying shoelace, looking up at camera, candid street moment`
- `sitting on a low concrete ledge, elbows resting on knees, hands loosely clasped, looking down thoughtfully`

#### 日系 City Boy
- `adjusting headphones while looking down at phone, absorbed in music, relaxed shoulders, weight shifted to one leg`
- `holding a paper coffee cup, looking back over shoulder as if someone called his name, slight natural smile`
- `hands in jacket pockets, shoulders slightly hunched against a breeze, hair slightly windswept, walking along a riverside path`
- `sitting on steps outside a vintage shop, one knee up, arm resting on knee, looking at something off-frame with curiosity`

#### 通勤/商务休闲
- `checking wristwatch while walking purposefully, leather messenger bag slung across body, looking ahead with focused expression`
- `one hand adjusting collar/tie, other hand holding phone to ear, mid-conversation, natural business stride`
- `standing at a modern glass building entrance, one hand holding coffee tumbler, checking phone with other hand, morning light`

#### 运动/活力
- `mid-stride running pose, elbows bent, one foot off ground, athletic dynamic motion`
- `after workout, wiping forehead with back of hand, slight exhausted smile, standing on outdoor court`
- `serving a tennis ball, full action shot, racket overhead, body stretched upward`

#### 约会/精致
- `waiting outside a restaurant, leaning against a vintage bicycle, slight nervous smile, adjusting cuff`
- `walking through a park with dappled tree light, looking relaxed and happy, candid laugh at something off-camera`

### 三、摄影指导词库

#### 相机/镜头 (选1组)
```
- shot on Fujifilm X-T5, 35mm f/1.4 lens, film simulation
- shot on Leica M6, 50mm Summicron, Kodak Portra 400 film grain
- shot on Sony A7IV, 85mm f/1.4 GM, crisp modern rendering
- shot on Contax T2, 38mm, cinematic look
```

#### 构图角度 (选1)
```
- eye-level shot, centered composition, direct eye contact with camera
- low angle from ground level, making subject look taller and commanding
- slightly elevated angle, subject looking up, bright open sky background
- Dutch angle ~5 degrees, adding dynamic tension and editorial feel
- rule of thirds, subject occupying left two-thirds, negative space on right
- waist-level framing (3/4 shot), intimate portrait feel
```

#### 光影 (选1)
```
- golden hour backlight, warm rim light outlining shoulders and hair, soft lens flare
- overcast soft diffused light, even skin tones, subtle shadow definition
- late afternoon side light, long dramatic shadows, warm amber tones
- morning crisp light, clean blue sky bounce, fresh and energetic feel
- neon sign ambient light at dusk, cinematic cyan and magenta tones
- dappled tree-filtered sunlight, patchy light patterns on clothing and face
```

#### 景深 (选1)
```
- shallow f/1.4 depth of field, creamy bokeh background, sharp subject isolation
- f/2.8 moderate depth, background slightly blurred but recognizable
- deep focus, sharp from foreground to background, environmental context
```

### 四、场景环境库

替换单一的 "Beijing street"，根据风格匹配：

#### 街头/潮流
- `narrow Harajuku backstreet lined with vintage clothing shops, colorful signage, afternoon`
- `Shanghai French Concession, plane tree-lined avenue, old brick buildings, late afternoon`
- `Beijing Gulou hutongs, grey brick walls, bicycles leaning against walls, morning light`
- `Seoul Hongdae street art alley, colorful murals on walls, urban creative district`

#### 日系/清新
- `quiet Daikanyama residential street, clean minimal architecture, potted plants, soft afternoon light`
- `riverside path with cherry blossom trees, gentle breeze, petals scattered on ground`
- `wooden deck outside a minimalist cafe, concrete walls with climbing ivy, zen atmosphere`

#### 通勤/商务
- `modern glass office building lobby, polished concrete floors, morning rush hour`
- `subway station platform, clean tiled walls, train arriving in background, motion blur`
- `elevated walkway between buildings, city skyline in background, golden hour`

#### 休闲/周末
- `outdoor park bench under large oak tree, dappled sunlight through leaves`
- `rooftop terrace with city view, string lights, late afternoon golden light`
- `art district gallery wall, abstract mural background, weekend afternoon`

#### 运动
- `outdoor tennis court, blue surface, chain-link fence, bright morning sun`
- `running track with stadium seating in background, early morning mist`
- `outdoor basketball court, painted concrete ground, urban setting`

### 五、情绪故事感

```
- candid moment caught mid-laugh, genuine joy, editorial street style
- quiet contemplative mood, eyes slightly squinting against sunlight, cinematic still
- effortlessly cool, caught off-guard by photographer, paparazzi-style spontaneous shot
- playful energy, mid-motion, wind catching hair and clothing, alive and dynamic
- introspective moment, looking out of frame, lost in thought, photojournalism style
```

---

## 三、实施计划

### Phase 1: Prompt 模板升级（核心，立即见效）

修改 `unified_pipeline.py` 中的 `OUTFIT_SYSTEM_PROMPT`（在 `wechat_control.py` 中），将 seedream_prompt 的生成指引从简单的一句话变为详细的分段指引。

**修改位置**：`tools/wechat_control.py` 第 1538 行附近

```python
# 旧 (line 1538):
"seedream_prompt": "英文 Seedream 生图提示词，描述一个30岁亚洲男性179cm偏瘦白皙，穿着上述服装的全身照，高质量写真风格"

# 新:
"seedream_prompt": """英文 Seedream 生图提示词。必须包含以下七个维度，每个维度用逗号分隔组成一个完整段落：

1. 摄影风格: 指定相机型号（Fujifilm X-T5/Leica M6/Sony A7IV）、镜头焦段（35mm/50mm/85mm）、光圈和风格标签（fashion editorial photography/lookbook style/street style candid）
2. 构图角度: 从以下选一个并稍作变体——low angle shot from knee height / eye-level centered / slightly elevated / Dutch angle / rule of thirds / 3/4 waist-level framing
3. 光影气氛: 从以下选一个并稍作变体——golden hour backlight with rim light / overcast soft diffused light / late afternoon side light with long shadows / morning crisp light / neon dusk ambient / dappled tree-filtered sunlight
4. 动态姿势: 根据服装风格选择一个自然动态姿势（禁止"standing"站立不动！）——walking mid-stride / leaning against wall / sitting on ledge / adjusting accessory / looking back over shoulder / mid-laugh candid / checking phone while walking / athletic motion
5. 服装细节: 详细列出每件单品的颜色、面料、品牌、版型特征
6. 场景环境: 根据风格选择具体地点——Harajuku backstreet / Shanghai French Concession / hutong alley / modern glass lobby / rooftop terrace / tennis court / park bench under tree / minimalist cafe outdoor
7. 情绪: 选一个情绪氛围——effortlessly cool candid / quiet contemplative / genuine joyful moment / editorial sophistication / playful dynamic energy

禁止事项：
- ❌ 禁止用"standing"或"standing casually"（呆板站立）
- ❌ 禁止只写"high-quality portrait"而不给具体摄影参数
- ❌ 禁止场景只写"Beijing street"
- ❌ 禁止姿势和情绪留空

完整示例（200-300字符）：
"Fashion editorial lookbook, shot on Fujifilm X-T5 35mm f/1.4, shallow depth of field with creamy bokeh. Low angle from knee height, rule of thirds composition. Golden hour backlight creating warm rim light on shoulders, sun-kissed skin. Walking confidently toward camera, mid-stride, one hand casually in jeans pocket, slight natural smile looking slightly off-frame. Wearing [服装清单]. Background: quiet Daikanyama residential street, clean minimal architecture, soft afternoon shadows. Effortlessly cool candid energy, caught mid-motion." """
```

### Phase 2: Pass 2 prompt 松绑（`generate.py`）

当前 Pass 2 prompt 过于保守，锁死了所有创造性。改为"基于底图风格，微调配饰并允许姿势微调"。

**修改位置**：`tools/generate.py` 第 288-297 行

```python
# 旧:
pass2_prompt = (
    f"Image 1 is a base outfit photo. Keep the person's face, body pose, "
    f"skin tone, hairstyle, and the basic clothing (top, pants, shoes) EXACTLY "
    f"as shown in image 1 — do not alter them. ..."
)

# 新:
pass2_prompt = (
    f"Image 1 is a base outfit photo showing the person's face, body shape, "
    f"skin tone, hairstyle, and basic clothing (top, pants, shoes). "
    f"Use image 1 as style and identity reference — preserve the person's identity "
    f"and overall aesthetic, but feel free to subtly adjust the pose, expression, "
    f"or camera angle for a more dynamic fashion photograph. "
    f"Images 2-{len(pass2_images)} are reference cutouts of accessories to ADD or REFINE: "
    f"{'; '.join(accessory_hints)}. "
    f"Accurately render these specific accessories onto the person. "
    f"The new image should be a natural, dynamic evolution of image 1 — "
    f"same person, same outfit, but more editorial and alive. "
    f"Fashion editorial photography, high quality, photorealistic."
)
```

### Phase 3: 新增 Seedream 辅助参数（`generate.py`）

虽然 5.0 不支持 `guidance_scale` 和 `negative_prompt`，但可以尝试：
- `size`: 从 `2048x2048` 改为 `936x1664`（竖构图 9:16，更像手机人像照）
- `max_images`: Pass 1 保持 4 张，Pass 2 保持 2 张

**修改位置**：`config/seedream.json`

```json
{
  "size": "936x1664",
  "_comment_size": "9:16 竖构图，更像时尚人像摄影，避免正方形构图的证件照感"
}
```

> ⚠️ 注意：竖构图可能影响 composite_v2 排版布局，需要同步调整排版参数。

### Phase 4: AI 自动选择姿势/场景/光影

在 `unified_pipeline.py` 的 `build_enhanced_prompt` 中，根据目标风格自动匹配摄影风格：

```python
# 风格 → 摄影风格映射
STYLE_PHOTO_MAP = {
    'japanese_city_boy': {
        'pose': 'hands in pockets, relaxed weight shift, looking down at phone, absorbed in music',
        'scene': 'quiet Daikanyama residential street, minimal architecture, soft afternoon',
        'light': 'overcast soft diffused light, even skin tones, subtle shadows',
        'vibe': 'effortlessly cool, candid street snap, Japanese magazine editorial'
    },
    'clean_fit': {
        'pose': 'leaning against white wall, arms crossed loosely, direct eye contact',
        'scene': 'modern minimalist gallery space, white walls, polished concrete floors',
        'light': 'morning crisp light through large windows, clean shadows',
        'vibe': 'architectural editorial, sharp and clean, Scandinavian cool'
    },
    'street_style': {
        'pose': 'walking mid-stride, one hand in pocket, looking ahead with confidence',
        'scene': 'Shanghai French Concession, plane tree avenue, old brick textures',
        'light': 'late afternoon side light, long dramatic shadows, warm amber',
        'vibe': 'papaprazzi-style candid, caught mid-motion, alive and dynamic'
    },
    'korean_oppa': {
        'pose': 'sitting on low concrete ledge, elbows on knees, looking up at camera',
        'scene': 'Seoul Hongdae street art alley, colorful murals, creative district',
        'light': 'golden hour backlight, warm rim light, soft lens flare',
        'vibe': 'K-drama still cut, soft romantic, cinematic'
    },
    # ... 更多风格
}
```

### Phase 5: 效果验证与迭代

每轮优化后对比：
1. 同一套穿搭旧 prompt vs 新 prompt 生成效果
2. 收集好的 prompt 模板作为"种子模板"
3. 根据用户反馈（rating）自动调优 prompt 风格偏好

---

## 四、文件修改清单

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `tools/wechat_control.py` (L1538) | seedream_prompt 生成指引从1行→30行 | 🔴 P0 |
| `tools/generate.py` (L288-297) | Pass 2 prompt 从"锁定"→"松绑微调" | 🔴 P0 |
| `config/seedream.json` | size 改为竖构图 936x1664 | 🟡 P1 |
| `tools/unified_pipeline.py` | 新增 `STYLE_PHOTO_MAP` + 摄影参数自动匹配 | 🟡 P1 |
| `tools/composite_v2.py` | 适配竖构图排版（如需要） | 🟢 P2 |

---

## 五、预期效果

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 姿势 | 永远站立 | 走路/靠墙/坐/回头/看手机 随机 |
| 构图 | 正方全身正面 | 竖构图 + 低角度/3/4身/规则线 |
| 场景 | 北京街头 | 东京/上海/首尔/画廊/网球场 |
| 光影 | "natural light" | 黄金时刻逆光/柔光/侧光/斑驳 |
| 情绪 | "slight smile" | 抓拍笑/沉思/自信/活力 |
| 摄影感 | 无 | Fujifilm/Leica + 大光圈 + 景深 |

---

*最后更新: 2026-06-18*
