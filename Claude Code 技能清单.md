# Claude Code 技能清单

> 📅 更新日期: 2026-06-17
> 📦 已安装技能: 6 个 | 内置技能: 13 个 | 合计: 19 个

---

## 一、已安装技能（6 个）

---

### 1. 🧠 Andrej Karpathy Perspective

| 项目 | 详情 |
|------|------|
| **包名** | `alchaincyf/karpathy-skill@andrej-karpathy-perspective` |
| **安装量** | 2.3K+ |
| **类型** | 思维框架 / 角色扮演 |
| **安全评级** | 🟢 Gen Safe / Snyk Med Risk |

**用途**: 以 Andrej Karpathy 的思维框架和表达方式分析问题。

**调用方式**: 说 "Karpathy 模式" / "用 Karpathy 的视角"

---

### 2. 🎨 Frontend Design

| 项目 | 详情 |
|------|------|
| **包名** | `nexu-io/open-design@frontend-design` |
| **安装量** | 1.5K+ |
| **安全评级** | 🟢 Gen Safe / Snyk Med Risk |

**用途**: 创建有强烈视觉方向、精致排版的生产级前端界面。

**调用方式**: 描述设计需求即可触发

---

### 3. 🎬 GSAP Animation

| 项目 | 详情 |
|------|------|
| **包名** | `martinholovsky/claude-skills-generator@gsap` |
| **安装量** | 1.2K+ |
| **安全评级** | ⚠️ Gen Critical Risk / Snyk Low Risk |

**用途**: 为 JARVIS HUD 风格界面创建 GSAP 动画。

**调用方式**: 在 Vue/Nuxt 项目中描述动画需求

---

### 4. 👁️ Agent Reach

| 项目 | 详情 |
|------|------|
| **包名** | `Panniantong/Agent-Reach` |
| **安装方式** | `pip install agent-reach`（Python CLI，非 npx） |
| **安全评级** | 🟢 开源 MIT |

**用途**: 让 AI 读取 13 个互联网平台（小红书、Twitter、B站、YouTube、Reddit、GitHub、V2EX 等），零 API 费用。

**调用方式**: 说 "帮我搜小红书 XXX"、"调研 XXX"、"看看 XXX 上有什么讨论"

**使用前需配置**:
- 小红书: `xhs login` 或 Cookie-Editor 导出
- Twitter: `twitter-cli` + Cookie
- 其他 6 个渠道装好即用

---

### 5. 🔍 Find Skills（内置）

**用途**: 在开放的 Agent Skills 生态系统中搜索和发现技能。

**调用方式**: `/find-skills` 或说 "帮我找一个 X 技能"

---

### 6. 🛠️ Skill Creator（内置）

**用途**: 创建新技能、修改已有技能、评估技能效果。

**调用方式**: `/skill-creator` 或说 "帮我创建一个技能"

---

## 二、内置技能（13 个）

| # | 技能 | 调用方式 | 用途 |
|---|------|---------|------|
| 7 | 🔬 Deep Research | `/deep-research` | 多源深度调研 |
| 8 | ⚙️ Update Config | `/update-config` | 配置权限/Hook |
| 9 | ⌨️ Keybindings | `/keybindings-help` | 快捷键定制 |
| 10 | ✅ Verify | `/verify` | 验证修改生效 |
| 11 | 📋 Code Review | `/code-review` | 代码审查 |
| 12 | ✂️ Simplify | `/simplify` | 代码简化 |
| 13 | 🔓 Fewer Prompts | `/fewer-permission-prompts` | 减少权限弹窗 |
| 14 | 🔁 Loop | `/loop 5m <命令>` | 定时重复任务 |
| 15 | 🔧 Claude API | 自动触发 | API 开发 |
| 16 | 🚀 Run | `/run` | 启动应用 |
| 17 | 📝 Init | `/init` | 项目初始化 |
| 18 | 👀 Review | `/review` | PR Review |
| 19 | 🔒 Security | `/security-review` | 安全审查 |

---

## 三、快速参考表

| # | 技能 | 类型 | 调用方式 | 最常用于 |
|---|------|------|---------|---------|
| 1 | 🧠 Karpathy | 已安装 | 说 "Karpathy 模式" | AI 思维框架 |
| 2 | 🎨 Frontend Design | 已安装 | 描述设计需求 | 网页/仪表盘设计 |
| 3 | 🎬 GSAP | 已安装 | 描述动画需求 | 界面动画/动效 |
| 4 | 👁️ Agent Reach | 已安装 | 说 "搜小红书/调研" | 13 平台数据采集 |
| 5 | 🔍 Find Skills | 内置 | `/find-skills` | 搜索新技能 |
| 6 | 🛠️ Skill Creator | 内置 | `/skill-creator` | 创建/修改技能 |
| 7 | 🔬 Deep Research | 内置 | `/deep-research` | 深度调研 |
| 8 | ⚙️ Update Config | 内置 | `/update-config` | 配置权限 |
| 9 | ⌨️ Keybindings | 内置 | `/keybindings-help` | 快捷键定制 |
| 10 | ✅ Verify | 内置 | `/verify` | 验证修改 |
| 11 | 📋 Code Review | 内置 | `/code-review` | 代码审查 |
| 12 | ✂️ Simplify | 内置 | `/simplify` | 代码简化 |
| 13 | 🔓 Fewer Prompts | 内置 | `/fewer-permission-prompts` | 减少弹窗 |
| 14 | 🔁 Loop | 内置 | `/loop` | 定时任务 |
| 15 | 🔧 Claude API | 内置 | 自动触发 | API 开发 |
| 16 | 🚀 Run | 内置 | `/run` | 启动应用 |
| 17 | 📝 Init | 内置 | `/init` | 初始化 |
| 18 | 👀 Review | 内置 | `/review` | PR Review |
| 19 | 🔒 Security | 内置 | `/security-review` | 安全审计 |

---

## 四、已删除的技能

| 技能 | 原因 |
|------|------|
| 🔎 Brave 图片搜索 | 需 Brave Search API Key（付费） |
| 🖼️ Google 图片搜索 | 需 Google Custom Search API Key（付费） |
| 🤖 多模态识别 (LinkFox) | 需 LinkFox API（付费） |
| 🎬 Video Edit | 暂时用不到 |

**替代方案**: `tools/fashion_image_search.py`（DuckDuckGo/Pexels/Unsplash 免费搜索）+ `tools/clothing_analyzer.py`（YOLOv8/HuggingFace/OpenClip 本地识别）

---

## 五、安装新技能的流程

```bash
# 1. 搜索技能
npx skills find <关键词>

# 2. 安装技能（全局）
npx skills add <owner/repo@skill> -g -y

# 3. 检查更新
npx skills check

# 4. 更新所有技能
npx skills update

# 5. 浏览技能市场
# 访问: https://skills.sh/
```

---

> 💡 **提示**: 当前已安装 6 个 skill，删除了 4 个付费/不需要的 skill。Agent Reach 是新装的主力工具。
