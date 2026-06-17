# 风格百科制作手册

> 基于 City Boy 百科模板提炼，适用于所有 49 风格的百科条目制作与维护。
> 最后更新: 2026-06-17

---

## 一、百科文件结构

```
styles_universal/{style_id}/
├── encyclopedia.md          # 百科正文（Markdown）
├── encyclopedia.html        # 百科网页（generate_encyclopedia_html.py 生成）
├── representative.jpg       # 风格代表图（封面）
├── gallery/                 # 图库目录
│   ├── {style_id}_01.jpg    # 风格参考图
│   ├── xhs_{note_id}.webp   # 小红书帖子封面（从帖子实际下载）
│   └── ig_{style_id}_01.jpg # Instagram 帖子封面（从帖子实际下载）
├── images_meta.json         # 图片元数据索引
└── references/              # 参考资料来源
```

---

## 二、百科正文模板（必含章节，按顺序）

```
# 风格名称 (English Name)
> 状态 | 最后更新 | 分类

![封面](representative.jpg)

## 📖 概述
- 发源年代 / 发源地 / 风格关键词 / 一句话定义

## 📜 历史文化
- 起源 / 发展脉络 / 关键人物

## 🎨 美学特征
- 廓形 / 色板 / 面料 / 标志单品（表格）

## 🏷️ 代表品牌
- 核心品牌 + 平价替代

## 👤 风格偶像 & 名人

## 👗 秀场 & 时装周

## 🔗 关联风格

## 📈 流行趋势

## 💡 穿搭建议
- 适合体型 / 肤色 / 场合 / 入门建议

## 📕 小红书社区经验（2026-XX-XX 双平台采集）
- 5 篇热门帖子（详见第三节）
- 社区共识总结表

## 📸 Instagram 社区经验（2026-XX-XX 采集）
- 5 条热门帖子（详见第四节）
- 社区共识总结表

---
*本文基于多源研究 + 双平台社区采集整理，人工审核。*
```

---

## 三、小红书章节规范

### 3.1 单篇帖子模板

```markdown
### 🥇 作者名 — 《帖子标题》
> ❤️ 点赞  ⭐ 收藏  💬 评论  🔄 转发 | [原文](帖子URL)

![封面](gallery/xhs_{note_id前8位}.webp)

**核心观点**: 一句话概括核心穿搭观点。

**经验要点**:
- 🥇 最重要的要点
- 补充要点（3-5条，必须可操作）
```

### 3.2 封面图规则 ⚠️

- **必须下载帖子的实际封面图**，严禁用风格图库的 generic 图片替代
- 命名格式: `xhs_{note_id前8位}.webp`
- 如帖子无封面（极少见），标注 `⚠️ 无封面`

### 3.3 经验要点规则

- 每条必须是**可操作的穿搭建议**，不能是泛泛感叹
- 从帖子提炼，用自己的话总结
- 🥇 标记最核心的一条

### 3.4 社区共识表

| 维度 | 社区共识 |
|------|---------|
| 核心精神 / 黄金公式 / 入门门槛 / 核心单品 / 配色法则 / 适用场景 / 进阶方向 |

---

## 四、Instagram 章节规范

### 4.1 单篇帖子模板

```markdown
### 🥇 账号 (@handle) — 帖子简述
> 🔗 [Post](帖子URL) 或 [Reel](Reel URL)（需登录查看）

![封面](gallery/ig_{style_id}_01.jpg)

**标签**: #tag1 #tag2
**看点**: 2-3 句话穿搭参考价值。
```

### 4.2 封面图规则 ⚠️

- **必须下载帖子的实际封面图**，严禁用风格图库图片替代
- 命名格式: `ig_{style_id}_{序号}.jpg`（01-05）
- 图片来源优先级: Instagram SEO CDN > DuckDuckGo INS 索引图

### 4.3 帖子链接规则 ⚠️

- **必须是具体帖子**（`/p/` 或 `/reel/`），**禁止只放博主主页** `/username/`
- 每条标注 `（需登录查看）`

---

## 五、制作流程

### 新建百科
```bash
python3 tools/style_research.py <style_id>           # 研究风格
python3 tools/style_image_scout.py <style_id>        # 搜集代表图
python3 tools/xiaohongshu_scraper.py --search "关键词"  # 采集小红书
python3 tools/instagram_search.py --query "关键词"     # 采集 Instagram
# 下载 XHS + INS 封面到 gallery/
# 编辑 encyclopedia.md
python3 tools/generate_encyclopedia_html.py <style_id>  # 生成 HTML
```

### 更新已有百科（补社区经验）
```bash
# 1. 采集最新社区内容
# 2. 编辑 encyclopedia.md，替换旧的社区经验章节
# 3. ⚠️ 删除旧格式裸链接段落，避免重复
# 4. python3 tools/generate_encyclopedia_html.py <style_id>
```

---

## 六、质量检查清单

### 内容
- [ ] 所有必含章节均已填写
- [ ] XHS 章节: 5 篇帖子，每篇封面图 + 核心观点 + 3-5 经验要点
- [ ] INS 章节: 5 条帖子，每篇封面图 + 标签 + 看点
- [ ] 双平台均有社区共识总结表
- [ ] 旧格式裸链接已删除，无重复段落

### 图片
- [ ] `representative.jpg` 存在
- [ ] XHS 封面（`xhs_*.webp`）全部存在，从帖子实际下载
- [ ] INS 封面（`ig_*.jpg`）全部存在，从帖子实际下载
- [ ] 所有 `![封面](gallery/...)` 路径正确，图片文件存在

### 链接
- [ ] XHS: `https://www.xiaohongshu.com/explore/{note_id}`
- [ ] INS: `/p/` 或 `/reel/`（非 profile 主页）
- [ ] 所有链接可访问

---

## 七、常见错误

| 错误 | 正确 |
|------|------|
| INS 封面用风格图库 generic 图片 | 下载帖子实际封面 |
| INS 链接只放博主主页 `/username/` | 必须是 `/p/` 或 `/reel/` |
| 新旧章节并存（重复） | 写完新章节后删旧段落 |
| XHS 封面用 `{style}_01.jpg` | 用 `xhs_{note_id}.webp` |
| 经验要点写成感叹 | 提炼可操作建议 |

---

## 八、常用命令

| 操作 | 命令 |
|------|------|
| 研究风格 | `python3 tools/style_research.py <style_id>` |
| 搜集代表图 | `python3 tools/style_image_scout.py <style_id>` |
| 小红书搜索 | `python3 tools/xiaohongshu_scraper.py --search "关键词"` |
| 小红书读笔记 | `xhs read <note_id或url> --json` |
| Instagram 搜索 | `python3 tools/instagram_search.py --query "关键词"` |
| 免费图片搜索 | `python3 tools/fashion_image_search.py --query "关键词"` |
| 生成百科 HTML | `python3 tools/generate_encyclopedia_html.py <style_id>` |
| 查看所有风格 | `python3 tools/style_research.py --list` |
