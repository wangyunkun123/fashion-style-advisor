# Instagram 采集流程

## 前置条件
- `pipx install instaloader`（已装，但搜索需登录）
- `python3 tools/instagram_search.py`（无需登录，通过 DuckDuckGo + Bing 搜索）
- 无需 Instagram 账号，无需 API Key

## 三步流程

### 1️⃣ 搜索
```bash
python3 tools/instagram_search.py --query "<英文关键词>" --count 10 --json
```

示例：
```bash
python3 tools/instagram_search.py --query "cityboy outfit japan menswear"
python3 tools/instagram_search.py --query "men linen shirt summer style" --all-sources
```

### 2️⃣ 下载封面图
```bash
python3 tools/instagram_search.py --query "<关键词>" --save ./ig_results/<目录名>
```

或手动下载特定图片 URL（来自搜索结果中的 `image_url` 或 `thumbnail`）。

### 3️⃣ 写入百科
打开 `styles_universal/<style_id>/encyclopedia.md`，在「📸 Instagram 社区经验」章节新增条目：

```markdown
### 🥇 username — 标题
> 🔗 [Post/Reel](URL)

![封面](gallery/ig_style_XX.jpg)

**标签**: #tag1 #tag2
**看点**: 简要描述这个帖子的穿搭亮点。
```

同时更新 `images_meta.json` 中的 `_dual_platform_collection.instagram` 数组。

## 双平台采集流程（小红书 + Instagram）

```bash
# 1. 小红书搜索（取 Top 5）
xhs search "City Boy 穿搭" --json > /tmp/xhs.json

# 2. Instagram 搜索（取 Top 5）
python3 tools/instagram_search.py --query "cityboy outfit japan" --json > /tmp/ig.json

# 3. 下载封面图到 gallery/
# 小红书：需要带 Referer 请求头 + 新鲜 CDN token
# Instagram：用 search 结果中的 image_url 或 Bing thumbnail

# 4. 读取小红书帖子详情
xhs read "FULL_URL_WITH_XSEC" --json

# 5. 写入 encyclopedia.md
# - 小红书章节：按点赞数排序，带封面图和原文链接
# - Instagram 章节：用搜索引擎预览信息，带封面图和帖子链接

# 6. 更新 images_meta.json
# - _dual_platform_collection.xiaohongshu
# - _dual_platform_collection.instagram
```

## 注意事项
- Instagram 未登录状态下无法查看帖子详情和文案，只能通过搜索引擎预览获取标题和标签
- 图片优先用 `lookaside.instagram.com/seo/google_widget/crawler/` 的 SEO 预览图
- 如果 SEO 图 403，改用 Bing thumbnail（`tse*.mm.bing.net/th/id/`）
- 搜索关键词建议用英文（DuckDuckGo 对英文支持更好）
- 每次搜索间隔 2-3 秒避免触发频率限制
- Instagram Reel 的 SEO 预览图通常质量更高

## 搜索关键词模板
| 风格 | 英文关键词 |
|------|-----------|
| City Boy | `cityboy outfit japan menswear popeye` |
| 韩系简约 | `korean men minimalist outfit casual` |
| 日系山系 | `japanese yama style outdoor gorpcore men` |
| 街头工装 | `streetwear workwear men japan wtaps` |
| Clean Fit | `clean fit outfit men minimal style` |
