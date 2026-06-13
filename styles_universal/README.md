# 通用风格库操作手册

## 架构

```
双层体系:
  styles_universal/    ← 通用百科 (知识层) — 49风格完整文化知识库
  styles/              ← 个人指纹 (匹配层) — 8风格轻量JSON打分引擎

每个风格目录:
  <style_id>/
  ├── encyclopedia.md       📚 文化/历史/品牌/名人/秀场/趋势百科
  ├── brands.json           🏷️ 品牌列表
  ├── people.json           👤 名人/设计师列表
  ├── keywords.json         🔑 搜索关键词
  └── references/
      ├── images.json       📸 图片参考URL索引
      └── _scout_task.txt   🔍 图片搜集任务
```

## 操作指令速查

### 新建风格

```bash
# 1. 在 categories.json 注册新风格
#    编辑 styles_universal/categories.json → style_registry

# 2. 生成研究提示词
python3 tools/style_research.py <new_style_id>

# 3. 将提示词复制到 Claude，配合 WebSearch 研究
#    结果保存为 styles_universal/<style_id>/encyclopedia.md

# 4. 搜集参考图片
python3 tools/style_image_scout.py <style_id>
#    将生成的 _scout_task.txt 中的搜索词用于 WebSearch
#    结果保存为 references/images.json

# 5. 更新图库
python3 tools/style_image_scout.py --list
```

### 批量扩充

```bash
# 发现新趋势（搜索2025-2026最新风格）
python3 tools/style_research.py --discover

# 批量生成待研究提示词
python3 tools/style_research.py --batch

# 批量生成图片搜集任务
python3 tools/style_image_scout.py --batch

# 查看覆盖率
python3 tools/style_research.py --list          # 百科文字
python3 tools/style_image_scout.py --list       # 图片参考
```

### 充实已有风格

```bash
# 补充品牌/名人/秀场信息
python3 tools/style_research.py --enrich <style_id>

# 刷新图片参考
python3 tools/style_image_scout.py <style_id>
```

### 浏览图片

```bash
open styles_universal/references/gallery.html
```

## 一键搭建新风格库（如女士穿搭）

```bash
# 1. 创建分类体系 → styles_universal/categories.json 增加维度
# 2. 注册风格 → style_registry 添加条目
# 3. 批量研究 → python3 tools/style_research.py --batch
# 4. 代理编写 → 将提示词交给 Claude 代理撰写百科
# 5. 批量图片 → python3 tools/style_image_scout.py --batch
# 6. 生成图库 → gallery.html
```

## 自学习系统

```
发现趋势: --discover → WebSearch → 发现新风格 → 注册 → 研究 → 入库
内容充实: --enrich → WebSearch → 品牌/名人/秀场 → 追加到百科
图片搜集: --scout → WebSearch → 图片URL → images.json
```

## 文件索引

| 文件 | 作用 |
|------|------|
| `categories.json` | 49风格五维分类注册表 |
| `templates/encyclopedia_template.md` | 百科标准模板 |
| `references/gallery.html` | 图片浏览器 |
| `../tools/style_research.py` | 风格研究代理 |
| `../tools/style_image_scout.py` | 图片搜集代理 |
| `../tools/style_matcher.py` | 风格匹配引擎（个人指纹层） |
| `../tools/style_scorer.py` | 全量评分+缓存 |
