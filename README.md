# 👔 Fashion Style Advisor

> 专属 AI 时尚顾问 —— 基于个人服装档案与身形分析的智能穿搭系统，支持多用户、男女双线、手机远程操控与 AI 效果图生成。

## ✨ 核心能力

- **个性化推荐**：读取用户服装档案 + 身形分析 + 实时天气 → 五层评分引擎匹配风格 → 给出穿搭方案
- **AI 效果图**：两轮接力 Seedream 生图（抠图参考）→ 智能排版合成 → CDN 分发
- **手机远程操控**：HTML 控制面板 + ngrok/Tailscale 内网穿透，手机端一键生成、评分、探索
- **风格百科**：男性 53 + 女性 50 风格知识库，涵盖文化 / 历史 / 品牌 / 名人 / 秀场 / 参考图
- **偏好学习**：三级评分体系，持续调整风格权重与单品优先级

## 🗂️ 项目结构

```
Fashion/
├── README.md                   # 本文件
├── CLAUDE.md                   # AI 助手操作手册（核心指令集）
├── sync.sh                     # 一键同步到 GitHub
│
├── users/                      # 👥 多用户数据（多用户架构）
│   ├── _registry.json          #   用户注册表
│   ├── male/{kun,becca}/        #   男性用户：wardrobe + outfits + profile
│   └── female/{nan}/            #   女性用户
│
├── styles_universal/           # 📚 男性风格百科（53 风格，知识层）
│   ├── <style>/references/      #   文化/历史/品牌/名人/秀场/参考图
│   └── categories.json          #   六维趋势分类体系
│
├── styles/                     # 🎯 风格指纹（匹配层）
│   ├── male/                    #   18 男性风格五层评分引擎
│   └── female/                  #   50 女性风格（WF-01 ~ WF-50）
│
├── prototype/                  # 📱 手机控制台原型
│   ├── mobile-v2.html           #   主控制台（build_prototype.py 生成）
│   ├── gender_gate.html         #   性别 / 用户选择入口
│   └── icons-set.html           #   自定义图标库预览
│
├── config/                     # ⚙️ 配置
│   ├── seedream.json            #   Seedream 生图配置
│   ├── seedream.local.json      #   API 密钥（不提交 Git）
│   └── style_defaults*.json     #   天气-场合-风格映射
│
├── tools/                      # 🔧 48+ Python 工具脚本
└── docs/ devlog/ notes/        # 📝 文档与开发日志
```

## 🚀 常用操作

| 需求 | 命令 / 指令 |
|------|-------------|
| 推荐穿搭 | 对 AI 说 **"推荐穿搭"** → 读档案 + 天气 → 风格匹配筛选 |
| 生成效果图 | **"生成效果图"** → 两轮接力 Seedream 生图 → 排版 → push |
| 风格排名 | `python3 tools/style_matcher.py <style_id>` |
| 自动推荐风格 | `python3 tools/style_matcher.py --auto <温度> <天气> <场合>` |
| 研究新风格 | `python3 tools/style_research.py <style_id>` |
| 搜集风格图片 | `python3 tools/style_image_scout.py <style_id>` |
| 偏好分析报告 | `python3 tools/rating_analyzer.py --report` |
| 衣橱分析 | `python3 tools/wardrobe_advisor.py --report` |
| 排版合成 | `python3 tools/composite_v2.py <outfit_dir>` |
| 重建原型 | `python3 tools/build_prototype.py` |
| 手机远程控制 | `bash tools/start_wechat_control.sh` |
| 同步到 GitHub | `bash sync.sh` |

## 🎨 生图管线（两轮接力抠图参考）

1. 复制抠图（`enhanced/{ID}_cutout.png`）到生图目录
2. **Pass 1**：人物 + 上衣 + 下装 + 鞋子抠图 → Seedream 生成 4 张基础穿搭
3. **Pass 2**：Pass1 最佳图 + 帽子 / 包 / 墨镜 / 袜子抠图 → 精确配饰（2 张）
4. `composite_v2.py` 排版合成 → `git push` → CDN → 重建原型

> 参考图使用**抠图**（去背景），透明部分自动补中性灰底（#D9D9D9）。
> Seedream API 参数名为 `image`。

## 🎭 风格库

- **知识层** `styles_universal/`：53 个男性风格百科，每个含文化背景 / 历史脉络 / 代表品牌 / 名人 / 秀场 / 参考图库
- **匹配层** `styles/male` (18) + `styles/female` (50)：五层评分引擎，量化风格指纹
- **趋势分类**：每个风格标注三级分类 🔥 流行趋势 / 🏛️ 经典风格 / 🎭 小众领域

## 📱 手机控制台

```
┌─ Hero 区（最新穿搭效果图 + 风格标签 + 配色条）─┐
├─ 单品清单（3列网格 + Clothing-Icons 图标）────┤
├─ 其他推荐 / 历史推荐 ──────────────────────────┤
├─ 输入框 + Tab Bar（🧠推荐 🧪探索 👔衣橱 ➕添加 ⚙️设置）┤
└────────────────────────────────────────────────┘
```

手机通过 ngrok / Tailscale HTTPS URL 访问控制面板，可远程触发推荐、生图、评分、探索。

## ⭐ 评分与偏好学习

| 评分 | 含义 | 系统动作 |
|------|------|---------|
| ⭐⭐⭐ | 满意 | 增加风格权重 + 单品优先级提升 |
| ⭐⭐ | 一般 | 累积 ≥3 次后分析重合点，降低频率 |
| ⭐ | 失望 | 二级反馈 → 该套单品加入不推荐清单 |

评分数据存于各用户 `outfits/<id>/rating.json`（不提交 Git）。

## 🛠️ 生图模型

- **Model**: `doubao-seedream-5.0-lite`（火山引擎 Ark API）
- **配置**: `config/seedream.json` + `config/seedream.local.json`（密钥）

## 📦 远程仓库

```bash
git@github.com:wangyunkun123/fashion-style-advisor.git
```
https://github.com/wangyunkun123/fashion-style-advisor

## ⚡ 快速开始

```bash
cd "/Users/rabbit/Claude code/Fashion"
bash tools/start_wechat_control.sh   # 启动手机远程控制
python3 tools/build_prototype.py     # 重建手机控制台原型
bash sync.sh                         # 同步到 GitHub
```
