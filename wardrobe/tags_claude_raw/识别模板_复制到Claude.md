# 服装识别模板 — 复制到 claude.ai 使用

## 使用说明

每次上传 5-8 张服装照片，附带以下提示词。照片按顺序对应下方列出的 ID。

---

## 提示词模板（复制下面全部内容）

```
你是一位专业的服装分析师。请逐一分析我上传的服装照片，对每件衣服输出一个 JSON 对象。所有对象放在一个 JSON 数组中返回。

【照片对应的服装 ID 列表（按上传顺序）】
<!-- 这里填入本批次的 ID 列表，例如：TS-001, TS-002, TS-003, TS-004, TS-005 -->

【输出格式 — 严格按此 Schema】
{
  "clothing_id": "TS-001",
  "category": "短袖上衣",
  "category_code": "TS",
  "color": {
    "hue_family": "暖色|冷色|中性",
    "hue_name": "具体色名，如焦糖色、藏青色、橄榄绿、米白、麻灰",
    "saturation": "低饱和|中饱和|高饱和",
    "lightness": "低明度|中明度|高明度",
    "is_neutral": true或false,
    "friendly_for_pale_skin": true或false
  },
  "silhouette": {
    "fit": "紧身|合身|宽松|廓形",
    "shoulder_effect": "无特殊效果|增加肩宽|缩窄肩部",
    "torso_effect": "无特殊效果|遮盖小肚子|增加上半身体量感",
    "length_ratio": "短款|标准|长款"
  },
  "pattern": {
    "type": "纯色|条纹|格纹|印花|Logo|拼接|其他",
    "density": "无|稀疏|密集",
    "logo_visible": true或false
  },
  "fabric": {
    "primary": "棉|麻|牛仔|合成|皮质|针织|羊毛混纺|速干|牛津纺|灯芯绒|帆布|亚麻",
    "texture": "平纹针织|螺纹针织|斜纹|光滑|磨毛|网眼|肌理感",
    "weight": "轻薄|中厚|厚重",
    "seasonality": ["春","夏","秋","冬"]
  },
  "brand": {
    "name": "品牌名称，如 Nike、Adidas、FILA、Champion、匡威、Timberland、Jordan、Puma、Uniqlo、无品牌 等",
    "collection": "系列/联名，如 Air Force 1、曼联合作款、U系列 等，无则填 null",
    "confidence": "确定|推测|未知"
  },
  "formality": 1到5的整数,
  "style_modifiers": ["标签数组，如颜色显白、增加肩宽、遮盖小肚子、增加上半身体量感"],
  "fit_comment": "这件衣服对偏瘦体型（179cm/68kg，四肢纤细有小肚子）的修饰效果的简短评价"
}

【字段说明】
- color.hue_family: 红/橙/黄=暖色，蓝/绿/紫=冷色，黑白灰米棕=中性
- color.saturation: 颜色鲜艳程度，灰色调多为"低饱和"，鲜艳颜色为"高饱和"
- color.lightness: 颜色明暗，"低明度"=深色/暗色，"高明度"=浅色/亮色
- color.is_neutral: 是否为黑白灰米棕等中性色
- color.friendly_for_pale_skin: 是否衬偏白肤色（浅色系、柔和色系通常友好；荧光色、土黄色通常不友好）
- silhouette.fit: 判断衣服的剪裁宽松度，不要仅看模特穿着效果，要看衣服本身的版型
- silhouette.shoulder_effect: 有垫肩/硬挺肩部结构=增加肩宽，落肩/插肩=无特殊效果
- silhouette.torso_effect: 前幅有结构/硬挺面料=遮盖小肚子，宽松落肩=增加上半身体量感
- pattern.type: 如果既有图案又有Logo，选最显著的特征
- fabric.primary: 看面料纹理判断主材质
- brand.name: 仔细观察衣服上的 Logo、标牌、织标、扣子刻字等识别品牌。不确定填"未知"
- brand.collection: 如果衣服有明显系列特征（如 Air Force 1 鞋型、曼联队徽）则标注系列名，否则 null
- brand.confidence: Logo/标牌清晰可见=确定，有特征但不太确定=推测，完全看不出=未知
- formality: 1=极休闲(居家/运动) 2=日常休闲 3=休闲偏精致 4=半正式(商务休闲) 5=正式
- style_modifiers: 根据衣服特征列出对偏瘦体型的修饰效果
- fit_comment: 一句话评价，如"宽松落肩设计可增加上半身体量感，适合偏瘦体型"

【重要】
- 只输出纯 JSON 数组，不要任何 markdown 标记或额外解释
- 每个对象一行也可以，但必须是合法 JSON
- 确保 JSON 中所有字符串使用双引号
```

---

## 批次规划（76件 / 每批5-8件 ≈ 10-12批）

| 批次 | 品类 | ID 列表 | 件数 |
|------|------|--------|------|
| 1 | 短袖上衣 | TS-001 ~ TS-008 | 8 |
| 2 | 短袖上衣 | TS-009 ~ TS-011 | 3 |
| 3 | 长袖上衣 | LS-001 ~ LS-004 | 4 |
| 4 | 外套 | JK-001 ~ JK-006 | 6 |
| 5 | 长裤 | PT-001 ~ PT-006 | 6 |
| 6 | 短裤 | SH-001 ~ SH-008 | 8 |
| 7 | 衬衣 | SHIRT-001 ~ SHIRT-004 | 4 |
| 8 | 背心 | TANK-001 ~ TANK-003 | 3 |
| 9 | 鞋子 | SHOE-001 ~ SHOE-006 | 6 |
| 10 | 鞋子+帽子 | SHOE-007~010, HAT-001~005 | 9 |
| 11 | 包+墨镜 | BAG-001~007, SUN-001~003 | 10 |
| 12 | 配饰+袜子 | ACC-001~003, SOCK-001~006 | 9 |

> 注：可自行调整批次，确保每批上传照片顺序与 ID 列表一致即可。
