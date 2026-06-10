
# 👔 Fashion Style Advisor

> 专属 AI 时尚顾问 — 基于服装档案的 Asian Male 穿搭系统

## 项目结构

```
Fashion/
├── README.md                  # 本文件
├── sync.sh                    # 一键同步到 GitHub
├── config/
│   └── seedream.json          # 火山引擎 Seedream API 配置
├── wardrobe/                  # 👔 服装档案（75件，13品类）
│   ├── 服装档案.md             # 完整索引（含ID、颜色、风格）
│   ├── 短袖上衣/ 长袖上衣/ 外套/ 长裤/ 短裤/
│   ├── 衬衣/ 背心/ 鞋子/ 帽子/ 包/ 墨镜/ 手部配饰/ 袜子/
├── profile/                   # 👤 个人形象
│   ├── analysis.md            # 身材容貌详细分析
│   └── photos/                # 关键照片
├── outfits/                   # 📅 每日穿搭记录
│   └── 2026-06-10_骑行通勤/   # 日期_场景
│       ├── outfit.md          # 推荐理由
│       ├── items/             # 本次衣物图片
│       ├── prompts/           # 生图提示词
│       └── generated/         # AI 生成效果图
├── tools/
│   └── generate.py            # Seedream 生图脚本
└── archive/                   # 🗄️ 历史版本（不再使用）
```

## 操作逻辑

### 用法
1. **"推荐穿搭"** → AI 读取 wardrobe + 天气 → 搭配推荐
2. **"生成效果图"** → AI 调用 config/seedream.json → 火山引擎生图
3. **"同步"** → 自动执行 sync.sh → 推送到 GitHub
4. **"添加新衣服"** → AI 更新 wardrobe/ 目录 + 服装档案.md

### 生图模型
- **Model**: `doubao-seedream-5.0-lite` (火山引擎 Ark API)
- **Size**: 2048×2048
- **配置**: `config/seedream.json`

## 远程仓库
```bash
git@github.com:wangyunkun123/fashion-style-advisor.git
```
https://github.com/wangyunkun123/fashion-style-advisor (private)

## 快速开始
```bash
cd "/Users/rabbit/Claude code/Fashion"
bash sync.sh              # 同步到 GitHub
python3 tools/generate.py # 生图（需配置 API key）
```
