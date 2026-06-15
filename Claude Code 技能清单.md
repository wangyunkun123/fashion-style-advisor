# Claude Code 技能清单

> 📅 更新日期: 2026-06-15
> 📦 已安装技能: 3 个 | 内置技能: 16 个 | 合计: 19 个

---

## 一、已安装技能（3 个）

这些技能通过 `npx skills add` 从技能市场安装。

---

### 1. 🎨 Frontend Design

| 项目 | 详情 |
|------|------|
| **包名** | `nexu-io/open-design@frontend-design` |
| **安装量** | 1.5K+ |
| **来源** | 改编自 Anthropic 官方 frontend-design 技能 |
| **安全评级** | 🟢 Gen Safe / Snyk Med Risk |

**用途**: 创建有强烈视觉方向、精致排版、合理布局的生产级前端界面。

**适用场景**:
- 网站/落地页设计
- SaaS 仪表盘/管理后台
- React/Vue/Svelte 组件设计
- UI 美化与重设计
- 移动端响应式界面

**设计理念**:
- 选定明确的美学方向（极致简约/编辑风/工业/复古未来/企业级等）
- 避免 AI 常见套路（紫蓝渐变、模糊玻璃卡片、过度圆角）
- 构建真实界面（含空/加载/错误状态）
- 精雕字体配对、配色角色分离、有意识的间距节奏

**调用方式**:
- 直接描述设计需求即可触发
- 触发词: `frontend design`、`ui design`、`web design`、`landing page`、`dashboard design`、`react component design`
- 示例: "帮我设计一个数据分析仪表盘"，"为我的 SaaS 产品做一个 landing page"

**安装命令**:
```bash
npx skills add nexu-io/open-design@frontend-design -g -y
```

---

### 2. 🎬 GSAP Animation

| 项目 | 详情 |
|------|------|
| **包名** | `martinholovsky/claude-skills-generator@gsap` |
| **安装量** | 1.2K+ |
| **技术栈** | GSAP 3.12+ / Vue / Nuxt / ScrollTrigger |
| **安全评级** | ⚠️ Gen Critical Risk / Snyk Low Risk |

**用途**: 为 JARVIS HUD 风格界面创建 GSAP 动画，涵盖面板入场退场、状态指示器过渡、数据可视化和滚动触发效果。

**适用场景**:
- HUD 面板入场/退场动画
- 状态指示器过渡（活跃/警告/错误）
- 数据可视化动态增长
- 复杂时间线编排（多阶段序列）
- 滚动触发动画（ScrollTrigger）
- SVG 路径变形（MorphSVG）
- FLIP 布局动画

**核心原则**:
- ✅ 仅使用 transform/opacity（GPU 加速）
- ✅ 组件卸载时 `kill()` 所有动画（防内存泄漏）
- ✅ 尊重 `prefers-reduced-motion`（无障碍）
- ✅ 使用 Timeline 编排复杂序列
- ❌ 不动画化布局属性（width/height = CPU reflow）

**调用方式**:
- 在 Vue/Nuxt 项目中描述动画需求即可
- 示例: "给这个面板加上入场动画"，"做一个柱状图增长动画"

**安装命令**:
```bash
npx skills add martinholovsky/claude-skills-generator@gsap -g -y
```

**高级模式参考**: `~/.agents/skills/gsap/references/advanced-patterns.md`
- 自定义缓动方程、物理弹簧动画、SVG 路径变形、FLIP 布局动画、quickSetter 高性能更新

---

### 3. 🧠 Andrej Karpathy Perspective

| 项目 | 详情 |
|------|------|
| **包名** | `alchaincyf/karpathy-skill@andrej-karpathy-perspective` |
| **安装量** | 2.3K+ |
| **类型** | 思维框架 / 角色扮演 |
| **安全评级** | 🟢 Gen Safe / Snyk Med Risk |

**用途**: 以 Andrej Karpathy 的思维框架和表达方式分析问题。基于 20+ 篇博文、16 段深度访谈、100+ 条 X 帖子蒸馏而成。

**适用场景**:
- AI 技术可靠性评估
- 学习方法与路径建议
- LLM 本质与能力边界分析
- AI 行业趋势判断
- "vibe coding" 话题讨论
- Software 2.0/3.0 范式讨论
- 神经网络训练策略

**六大心智模型**:
1. **Software X.0 范式思维** — 编程语言的三次根本性变革
2. **构建即理解** — 理解的终极检验是从零重建
3. **LLM = 召唤的幽灵** — LLM 是互联网数据中涌现的人类思维模拟
4. **March of Nines** — 从 90% 到 99.9% 的工程爬坡
5. **锯齿状智能** — LLM 能力分布不均匀，有"凸出点"和"凹陷点"
6. **Iron Man 套装 > Iron Man 机器人** — AI 应当增强人，而非替代人

**调用方式**:
- 触发词: `Karpathy`、`卡帕西`、`用 Karpathy 的视角`、`karpathy 模式`
- 也适用于: `Software 2.0`、`vibe coding`、`march of nines`、`构建即理解`、`锯齿状智能`
- 退出方式: 说 `退出`、`切回正常`、`不用扮演了`
- ⚠️ 激活后直接以第一人称"我"回应，模拟 Karpathy 的思维和语气

**安装命令**:
```bash
npx skills add alchaincyf/karpathy-skill@andrej-karpathy-perspective -g -y
```

---

## 二、内置技能（16 个）

这些技能随 Claude Code 预装，无需额外安装。

---

### 4. 🔍 Find Skills

**用途**: 在开放的 Agent Skills 生态系统中搜索和发现技能。

**适用场景**:
- 想找特定领域的技能时
- 不确定有没有现成的技能可用时
- 浏览热门技能

**调用方式**:
- `/find-skills` 或说 "帮我找一个 X 技能"
- 搜索命令: `npx skills find <关键词>`

---

### 5. 🛠️ Skill Creator

**用途**: 创建新技能、修改已有技能、评估技能效果。

**适用场景**:
- 从零创建自定义技能
- 优化现有技能的触发准确性
- 运行 evals 测试技能表现

**调用方式**:
- `/skill-creator` 或说 "帮我创建一个技能"
- 创建命令: `npx skills init <技能名>`

---

### 6. 🎬 Video Edit

**用途**: 通过 RunComfy 对视频进行编辑（风格转换、背景替换、动作迁移、换装等）。

**适用场景**:
- 视频风格转换 / 重新调色
- 背景替换
- 参考视频动作迁移
- 换装效果

**调用方式**:
- 触发词: `video edit`、`edit video`、`restyle video`、`motion control`、`outfit swap video`
- 自动匹配最佳模型（Wan 2.7 / Kling 2.6 / Lucy Edit Restyle）

---

### 7. 🔬 Deep Research

**用途**: 多源深度研究 — 展开式网络搜索、获取来源、对抗性验证、生成带引用的报告。

**适用场景**:
- 需要多源、事实核查的深度研究报告
- 技术调研、市场分析、竞争对手分析

**调用方式**:
- `/deep-research` 或说 "帮我做一个深度研究"
- ⚠️ 如果问题不够具体，会先追问 2-3 个澄清问题

---

### 8. ⚙️ Update Config

**用途**: 通过 `settings.json` 配置 Claude Code 的行为（权限、环境变量、Hooks 等）。

**适用场景**:
- 添加/移除权限（"允许 npm 命令"）
- 设置环境变量
- 配置自动化 Hook（"当 X 时自动执行 Y"）
- 排查配置文件问题

**调用方式**:
- `/update-config` 或说 "添加权限"、"设置环境变量"、"配置 Hook"
- 简单设置（主题/模型）建议用 `/config`

---

### 9. ⌨️ Keybindings Help

**用途**: 自定义键盘快捷键、按键绑定、和弦快捷键。

**适用场景**:
- 重新绑定快捷键
- 添加和弦快捷键
- 修改提交键

**调用方式**:
- `/keybindings-help` 或说 "重新绑定 ctrl+s"、"修改快捷键"
- 修改文件: `~/.claude/keybindings.json`

---

### 10. ✅ Verify

**用途**: 通过运行应用验证代码变更是否按预期工作。

**适用场景**:
- 验证 PR 是否修复了问题
- 确认修复在真实环境中生效
- 手动测试功能变更

**调用方式**:
- `/verify` 或说 "帮我验证这个修改"、"测试一下这个修复"

---

### 11. 📋 Code Review

**用途**: 对当前 diff 进行代码审查，检查正确性 Bug 和代码简化/复用优化。

**适用场景**:
- 提交前自查代码质量
- PR Review 辅助
- 代码优化建议

**调用方式**:
- `/code-review` — 基础审查
- `--comment` — 以行内评论形式发布到 PR
- `--fix` — 审查后自动应用修复
- 可选 effort 级别: `low` / `medium` / `high` / `max`

---

### 12. ✂️ Simplify

**用途**: 审查变更代码的复用性、简化度、效率和抽象层级，自动应用修复。

**适用场景**:
- 代码重构优化
- 消除冗余
- 提升代码可读性

**调用方式**:
- `/simplify`
- ⚠️ 仅关注代码质量，不检查 Bug（用 `/code-review` 做 Bug 检查）

---

### 13. 🔓 Fewer Permission Prompts

**用途**: 扫描历史会话中的常用只读命令，自动添加允许列表以减少权限弹窗。

**适用场景**:
- 权限弹窗太多，想减少打断
- 批量添加常用命令到白名单

**调用方式**:
- `/fewer-permission-prompts`
- 修改文件: 项目 `.claude/settings.json`

---

### 14. 🔁 Loop

**用途**: 按固定间隔重复运行指定命令。

**适用场景**:
- 定时检查部署状态
- 周期性监控任务
- 轮询某个外部状态

**调用方式**:
- `/loop 5m /foo` — 每 5 分钟执行 `/foo`
- 默认间隔: 10 分钟
- ⚠️ 不适用于一次性任务

---

### 15. 🔧 Claude API

**用途**: 构建、调试和优化 Claude API / Anthropic SDK 应用。支持 prompt caching、模型版本迁移。

**触发条件**（满足任一即触发）:
- 代码中 `import anthropic` 或 `import @anthropic-ai/sdk`
- 用户询问 Claude API、Anthropic SDK 或 Managed Agents
- 代码中配置 Claude 功能（caching、thinking、tool use、batch 等）
- 模型版本迁移（4.5 → 4.6、4.6 → 4.7）

**跳过条件**:
- 代码使用 OpenAI 或其他非 Anthropic SDK
- 文件名含 `-openai.py` 或 `-generic.py`
- 通用编程问题

**调用方式**:
- `/claude-api` 或自然提及相关技术时会自动触发

---

### 16. 🚀 Run

**用途**: 启动并驱动项目应用，验证代码改动在真实环境中的效果。

**适用场景**:
- 查看应用运行效果
- 截图/录屏确认 UI 变更
- 在真实环境中验证功能

**调用方式**:
- `/run` 或说 "运行应用"、"启动项目"、"截图看看效果"

---

### 17. 📝 Init

**用途**: 为当前项目初始化 CLAUDE.md 文件，包含代码库文档。

**适用场景**:
- 新项目首次配置
- 为已有项目补充 AI 上下文文档

**调用方式**:
- `/init` 或说 "初始化项目文档"

---

### 18. 👀 Review

**用途**: 对 Pull Request 进行全面审查。

**适用场景**:
- Review GitHub PR
- 代码合并前评审

**调用方式**:
- `/review` 或说 "Review 这个 PR"

---

### 19. 🔒 Security Review

**用途**: 对当前分支的待提交变更进行安全审查。

**适用场景**:
- 提交前的安全检查
- 识别安全漏洞和风险

**调用方式**:
- `/security-review` 或说 "做安全审查"

---

## 三、快速参考表

| # | 技能 | 类型 | 调用方式 | 最常用于 |
|---|------|------|---------|---------|
| 1 | 🎨 Frontend Design | 已安装 | 描述设计需求 | 网页/仪表盘/组件设计 |
| 2 | 🎬 GSAP | 已安装 | 描述动画需求 | 界面动画/动效 |
| 3 | 🧠 Karpathy | 已安装 | 说 "Karpathy 模式" | AI 思维框架 |
| 4 | 🔍 Find Skills | 内置 | `/find-skills` | 搜索新技能 |
| 5 | 🛠️ Skill Creator | 内置 | `/skill-creator` | 创建自定义技能 |
| 6 | 🎬 Video Edit | 内置 | 说 "编辑视频" | 视频处理 |
| 7 | 🔬 Deep Research | 内置 | `/deep-research` | 深度调研 |
| 8 | ⚙️ Update Config | 内置 | `/update-config` | 配置权限/Hook |
| 9 | ⌨️ Keybindings | 内置 | `/keybindings-help` | 快捷键定制 |
| 10 | ✅ Verify | 内置 | `/verify` | 验证修改生效 |
| 11 | 📋 Code Review | 内置 | `/code-review` | 代码审查 |
| 12 | ✂️ Simplify | 内置 | `/simplify` | 代码简化 |
| 13 | 🔓 Fewer Prompts | 内置 | `/fewer-permission-prompts` | 减少权限弹窗 |
| 14 | 🔁 Loop | 内置 | `/loop 5m <命令>` | 定时重复任务 |
| 15 | 🔧 Claude API | 内置 | 自动触发 | API 开发 |
| 16 | 🚀 Run | 内置 | `/run` | 启动应用 |
| 17 | 📝 Init | 内置 | `/init` | 项目初始化 |
| 18 | 👀 Review | 内置 | `/review` | PR Review |
| 19 | 🔒 Security | 内置 | `/security-review` | 安全审计 |

---

## 四、安装新技能的流程

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

> 💡 **提示**: 本文件同时保存在当前项目和 Fashion 项目中，方便随时查阅。
