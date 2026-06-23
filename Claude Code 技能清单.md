# Claude Code 技能清单

> 📅 更新日期: 2026-06-22
> 📦 已安装技能: 14 个 | 内置技能: 13 个 | 合计: 27 个

---

## 一、已安装技能（14 个）

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

### 7. 🧠 Brainstorming

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |

**用途**: 任何创意/功能/修改工作前的强制设计讨论。探索用户意图、需求和设计方向，避免跳过设计直接写代码。

**调用方式**: 自动触发（写任何功能前必须经过此流程）

**流程**: 探索项目 → 提问澄清 → 2-3 方案对比 → 呈现设计 → 写设计文档 → 交付 writing-plans

---

### 8. 📝 Writing Plans

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |

**用途**: 有 spec 后、写代码前，编写面面俱到的实施计划（文件映射 + 任务拆解 + 测试策略），假设执行者零上下文。

**调用方式**: `/writing-plans` 或在 brainstorming 后自动衔接

**输出**: `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`

---

### 9. 🔧 Systematic Debugging

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |

**用途**: 遇到任何 bug/测试失败/异常行为时的系统化调试方法。**铁律：未找到根因前禁止修代码。**

**调用方式**: `/systematic-debugging` 或遇到 bug 时自动触发

**三阶段**: Phase 1 根因调查 → Phase 2 修复方案 → Phase 3 预防措施

---

### 10. 🧪 Test-Driven Development

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |

**用途**: 强制 TDD 流程——先写测试，看它失败，再写最小实现。**铁律：没有先失败的测试，就没有生产代码。**

**调用方式**: `/test-driven-development` 或写功能/修 bug 时自动触发

**例外**: 一次性原型 / 生成代码 / 配置文件

---

### 11. 👀 Requesting Code Review

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |

**用途**: 完成任务/实现功能/合并前，派发代码审查子代理，以独立视角检查工作成果。

**调用方式**: `/requesting-code-review` 或在完成 major feature 后

**强制时机**: 每个 task 完成后 / major feature 后 / 合并 main 前

---

### 12. 📷 Instagram Downloader

| 项目 | 详情 |
|------|------|
| **包名** | `serpapps/instagram-downloader` |
| **类型** | 浏览器扩展 |

**用途**: 下载 Instagram Reels / 帖子 / Story / 轮播图 / 文案。浏览器内直接保存，无需第三方网站。

**调用方式**: `/instagram-downloader` 或说 "下载这个 IG 帖子"

---

### 13. 🔬 Instagram Research

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 Superpowers 体系 |
| **依赖** | `APIFY_TOKEN` + `GEMINI_API_KEY` 环境变量 |

**用途**: 研究 Instagram 高表现内容（帖子和 Reels），识别异常值，AI 分析 Top 5 视频，生成可执行的 hook 公式报告。

**调用方式**: `/instagram-research` 或说 "分析 IG 趋势" / "找热门 Reels" / "竞品 IG 研究"

**触发词**: instagram research, ig research, trending reels, viral reels, content research

---

### 14. ⚡ Using Superpowers

| 项目 | 详情 |
|------|------|
| **安全评级** | 🟢 元技能 |

**用途**: Superpowers 技能体系的入口指南——解释如何发现和使用技能，强制技能优先于默认行为。

**调用方式**: 每次会话开始时自动参考（1% 可能性适用也必须调用技能）

**优先级**: 用户指令 > Superpowers 技能 > 系统默认

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
| 7 | 🧠 Brainstorming | 已安装 | 自动触发 | 写功能前设计讨论 |
| 8 | 📝 Writing Plans | 已安装 | `/writing-plans` | 编码前实施计划 |
| 9 | 🔧 Systematic Debug | 已安装 | `/systematic-debugging` | Bug 根因调查 |
| 10 | 🧪 TDD | 已安装 | `/test-driven-development` | 测试先行 |
| 11 | 👀 Request Review | 已安装 | `/requesting-code-review` | 完成后代码审查 |
| 12 | 📷 IG Downloader | 已安装 | `/instagram-downloader` | 下载 IG 内容 |
| 13 | 🔬 IG Research | 已安装 | `/instagram-research` | IG 趋势分析 |
| 14 | ⚡ Using Superpowers | 已安装 | 自动参考 | 技能体系入口 |
| 15 | 🔬 Deep Research | 内置 | `/deep-research` | 深度调研 |
| 16 | ⚙️ Update Config | 内置 | `/update-config` | 配置权限 |
| 17 | ⌨️ Keybindings | 内置 | `/keybindings-help` | 快捷键定制 |
| 18 | ✅ Verify | 内置 | `/verify` | 验证修改 |
| 19 | 📋 Code Review | 内置 | `/code-review` | 代码审查 |
| 20 | ✂️ Simplify | 内置 | `/simplify` | 代码简化 |
| 21 | 🔓 Fewer Prompts | 内置 | `/fewer-permission-prompts` | 减少弹窗 |
| 22 | 🔁 Loop | 内置 | `/loop` | 定时任务 |
| 23 | 🔧 Claude API | 内置 | 自动触发 | API 开发 |
| 24 | 🚀 Run | 内置 | `/run` | 启动应用 |
| 25 | 📝 Init | 内置 | `/init` | 初始化 |
| 26 | 👀 Review | 内置 | `/review` | PR Review |
| 27 | 🔒 Security | 内置 | `/security-review` | 安全审计 |

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

> 💡 **提示**: 当前已安装 14 个 skill（含 8 个 Superpowers 体系技能），删除了 4 个付费/不需要的 skill。Agent Reach 和 Superpowers 是主力工具链。
