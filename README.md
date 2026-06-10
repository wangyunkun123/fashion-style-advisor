# 👔 Fashion Style Advisor

> 专属 AI 时尚顾问 — 基于服装档案的 Asian Male 穿搭系统

## 项目结构

```
Fashion/
├── README.md                  # 本文件 — 操作手册
├── CLAUDE.md                  # AI 自动加载的项目配置
├── sync.sh                    # 一键同步到 GitHub
├── config/
│   ├── seedream.json          # 公开配置（模型、尺寸）
│   └── seedream.local.json    # 🔑 本地密钥（不提交Git，需手动创建）
├── wardrobe/                  # 👔 服装档案（75件，13品类）
│   ├── 服装档案.md             # 完整索引（含ID、颜色、风格）
│   └── 短袖上衣/ 长袖上衣/ 外套/ 长裤/ 短裤/ 衬衣/ 背心/ 鞋子/ 帽子/ 包/ 墨镜/ 手部配饰/ 袜子/
├── profile/                   # 👤 个人形象
│   ├── analysis.md            # 身材容貌详细分析
│   └── photos/                # 关键照片（IMG_8493等）
├── outfits/                   # 📅 每日穿搭记录
│   └── <日期>_<风格>/
│       ├── outfit.md          # 推荐理由+天气+搭配方案
│       ├── items/             # 本次衣物图片（ID+名称命名）
│       ├── prompts/           # 生图提示词+API结果
│       └── generated/         # AI 生成效果图
├── tools/
│   ├── generate.py            # Seedream 生图脚本
│   └── notify.py              # 微信推送脚本（Server酱）
└── archive/                   # 🗄️ 历史版本（不再使用）
```

---

## 📖 完整操作手册

### 一、推荐穿搭
```
你对AI说："推荐穿搭" 或 "推荐明天的穿搭"
    ↓
① AI 查询北京天气（WebSearch）
② AI 读取 wardrobe/服装档案.md 选择搭配
③ AI 输出方案：单品、理由、配色逻辑、风格说明
④ AI 创建 outfits/<日期>_<风格>/ 目录
⑤ AI 复制所用单品图片到 items/
⑥ AI 写入 outfit.md
⑦ 你确认方案，或要求调整
```

### 二、生成效果图
```
你对AI说："生成效果图"
    ↓
① AI 读取 outfits/<日期>_<风格>/outfit.md
② AI 构建详细中文提示词（含身形+每件单品描述）
③ AI 调用火山引擎 Seedream API 生图（~30秒）
④ 图片保存到 generated/穿搭参考图.jpg
⑤ git add + commit + push → GitHub
⑥ AI 调用 tools/notify.py → Server酱 → 微信推送 📱
⑦ 你手机秒收穿搭效果图
```

### 三、添加新衣服
```
你对AI说："添加新衣服"
    ↓
① 你提供衣服照片
② AI 分配下一个可用ID
③ AI 将图片放入 wardrobe/<品类>/
④ AI 更新 wardrobe/服装档案.md 表格
⑤ git push 同步
```

### 四、同步到 GitHub
```
你对AI说："同步" 或 "推送"
    ↓
① AI 执行 bash sync.sh
② 所有变更推送到 GitHub
```

---

## 🔑 安全配置

### 密钥文件（首次配置，仅需一次）

创建 `config/seedream.local.json`：
```json
{
  "api_key": "你的火山引擎API Key",
  "wechat_sendkey": "你的Server酱SendKey"
}
```

此文件已在 `.gitignore` 中排除，**不会被提交到 Git**。
公开 repo 中不含任何密钥。

### API 配置
- **生图模型**: `doubao-seedream-5.0-lite` (火山引擎 Ark API)
- **图片尺寸**: 2048×2048
- **微信推送**: Server酱 (sctapi.ftqq.com)
- **公开配置**: `config/seedream.json`（不含密钥）
- **本地密钥**: `config/seedream.local.json`（需手动创建）

---

## 🌐 远程仓库

```bash
git@github.com:wangyunkun123/fashion-style-advisor.git
```
https://github.com/wangyunkun123/fashion-style-advisor (public)

### 快速开始（新机器）
```bash
git clone git@github.com:wangyunkun123/fashion-style-advisor.git
cd fashion-style-advisor
# 创建 config/seedream.local.json（参考上方安全配置）
cd "/Users/rabbit/Claude code/Fashion" && claude
```

### 通过 Claude Code 调用
```bash
cd "/Users/rabbit/Claude code/Fashion" && claude
# AI 自动读取 CLAUDE.md，了解全部项目信息
```
