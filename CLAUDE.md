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
- `tools/notify.py` — 微信推送脚本（Server酱）

## 操作指令
当用户说以下关键词时，执行对应操作：
- **"推荐穿搭"** → 读取 wardrobe + 天气，给出搭配方案
- **"生成效果图"** → 调用 Seedream API 生图 → git push → 调用 tools/notify.py 微信推送（完整流程自动执行）
- **"同步"/"推送"** → 执行 `bash sync.sh` 推送到 GitHub
- **"添加新衣服"** → 将图片放入 wardrobe 对应目录，更新服装档案.md 表格

## API 配置
- 火山引擎 Ark API: `https://ark.cn-beijing.volces.com/api/plan/v3/images/generations`
- Model: `doubao-seedream-5.0-lite`
- Size: 2048x2048
- 配置: `config/seedream.json`
- 微信推送: Server酱 `SCT362418...` (sctapi.ftqq.com)

### 生图完整流程
1. 调用 Seedream API 生成穿搭图
2. 图片保存到 `outfits/<日期>_<风格>/generated/`
3. `git add -A && git commit && git push`
4. 调用 `python3 tools/notify.py <标题> <GitHub Raw URL> <单品列表>`
5. 用户微信实时收到效果图通知

## Git
- Remote: `git@github.com:wangyunkun123/fashion-style-advisor.git` (SSH)
- Web: https://github.com/wangyunkun123/fashion-style-advisor (public)
- 用户说"同步"时执行 sync.sh

## 回答规范
- 始终用中文回答
- 每次回答以"收到"开头（在服装档案上传完毕后）
