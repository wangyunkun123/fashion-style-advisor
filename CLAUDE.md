# Fashion Style Advisor

## 项目简介
这是用户的专属 AI 时尚顾问项目，专攻亚洲男性穿搭。包含完整的服装档案系统、个人形象分析、每日穿搭记录和 AI 生图功能。

## 用户画像
- 30岁中国男性，179cm，68kg，偏瘦，肤色偏白，有小肚子
- 北京自媒体从业者
- 穿搭目标：日系 city boy / 韩系简约 / Clean Fit

## 核心文件
- `wardrobe/服装档案.md` — 75件服装完整索引（TS-001 等 ID 体系）
- `wardrobe/` — 按品类分 13 个子目录存放衣物图片
- `profile/analysis.md` — 用户身形分析
- `profile/photos/` — 用户个人照片（IMG_8493 等）
- `outfits/` — 按 `日期_场景` 组织每日穿搭
- `config/seedream.json` — 火山引擎 Seedream API 配置 + Server酱 SendKey
- `tools/generate.py` — Seedream 生图脚本
- `tools/composite.py` — 单品标注合成，在效果图上贴原图缩略图
- `tools/notify.py` — 微信推送脚本（Server酱）
- `系统升级建议.md` — 功能优化建议池，有新想法随时追加
- `devlog/` — 每日开发日志，按 `YYYY-MM-DD.md` 命名

## 操作指令
- **"推荐穿搭"** → 读取 wardrobe + 天气，给出搭配方案
- **"生成效果图"** → 完整流程：Seedream生图 → 同步抠图 → composite_v2排版 → git push → 微信推送
- **"排版"/"合成"** → 运行 `python3 tools/composite_v2.py` 生成 `_方案1.jpg`
- **"同步"/"推送"** → 执行 `bash sync.sh` 推送到 GitHub
- **"添加新衣服"** → 放入 wardrobe → 更新服装档案.md → auto_orient → enhance_clothing
- **"新想法"/"优化建议"** → 记录到 `系统升级建议.md`

## 图片处理管线
新衣服入库：
```bash
python3 tools/auto_orient.py              # AI 检测方向并修正
python3 tools/enhance_clothing.py --force  # rembg抠图+精修 → wardrobe/enhanced/
```
排版时自动优先使用抠图PNG，回退到增强JPG。

## 排版标准 (composite_v2.py 方案1)
- **风格**：ACOC Lookbook 网格风 — 直角矩形、1px浅灰边框、无圆角无阴影
- **字体**：Didot (英文标题) + 宋体 (中文) + Georgia/STHeiti (正文)
- **配色**：豆包视觉API提取AI生图主色调 → COLOR PALETTE 色块
- **布局**：左列主衣 + 中AI原图 + 右列配饰 + 底部品牌信息
- **卡片规则**：1:1/3:4/4:3标准比例、严格透明裁剪(alpha≥200)、品类旋转(HAT0° JK+10° TS-10°)、名字16字上限

## 生图完整流程
1. Seedream API 生图 → `outfits/<日期>_<风格>/generated/`
2. 同步抠图：服装档案映射 → 复制 `_cutout.png` 到 `outfits/.../items/`
3. `python3 tools/composite_v2.py` → 生成 `_方案1.jpg`
4. `git add -A && git commit && git push`
5. `python3 tools/notify.py <标题> <GitHub Raw URL> <单品列表>`

## 双模型工作流
- **DeepSeek-V4（当前对话模型）**：负责逻辑推理、功能设计、代码开发、日常对话
- **Doubao-Seed-2.0-Code（API 调用）**：负责视觉类工作——识别衣服、判断朝向、打标签、图片理解等
- 视觉任务直接在代码中调用豆包 API，无需切换模型
- API 配置：`POST https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`，model=`doubao-seed-2.0-code`，key 见 `config/seedream.local.json`

## Git
- Remote: `git@github.com:wangyunkun123/fashion-style-advisor.git` (SSH)
- Web: https://github.com/wangyunkun123/fashion-style-advisor (public)
- 用户说"同步"时执行 sync.sh

## 回答规范
- 始终用中文回答
- 每次回答以"收到"开头（在服装档案上传完毕后）
