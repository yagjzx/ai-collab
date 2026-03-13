# AI-Collab: 多模型协作开发工作站

> **Product Requirements Document v0.1 (Draft)**
>
> 最后更新: 2026-03-13

---

## 1. 产品定义

### 1.1 一句话描述

**AI-Collab** 是一个终端原生的多 AI 模型协作调度系统，让开发者在一个统一的工作站中同时使用 Claude、Codex、Gemini 等多个 AI 编程助手，各模型按角色分工（架构师、执行者、审查者、灵感来源），通过结构化的协议进行跨模型协作。

### 1.2 核心问题

现状：开发者同时使用多个 AI 编程助手（Claude Code、Codex CLI、Gemini CLI 等），但：

| 问题 | 现状痛点 |
|------|---------|
| **上下文隔离** | 所有项目共享全局日志、配置、状态文件，项目 A 的对话泄露到项目 B |
| **会话管理** | 手工 tmux 布局，嵌套 attach 崩溃，无生命周期管理 |
| **模型通信** | 模型间通过 ad-hoc 的 shell 脚本传话，无标准协议 |
| **角色调度** | 硬编码在 CLAUDE.md 的 markdown 表格里，无法动态调整 |
| **状态散落** | 配置在 ~/.claude/CLAUDE.md，脚本在 ~/.local/bin/，日志在 ~/.local/share/，残留在 ~/.ccb/ |
| **可移植性** | 完全绑定一台机器的特定目录结构，无法复用 |

### 1.3 目标用户

- **主要用户**：使用 CLI AI 工具（Claude Code、Codex CLI、Gemini CLI）的全栈开发者
- **次要用户**：需要多 AI 模型协作完成复杂任务的技术团队
- **非目标用户**：只使用单一 AI IDE（如 Cursor）的开发者

### 1.4 核心价值主张

```
一条命令启动 → 多模型自动就位 → 按角色分工协作 → 项目级完全隔离
```

---

## 2. 竞品与市场分析

> 基于 2026-03-13 的系统调研，涵盖 GitHub、产品发布、学术论文等渠道。

### 2.1 市场全景

2025-2026 年多模型 AI 编码协作市场爆发。核心趋势：**git worktree 隔离**成为行业标准（每个 Agent 独立分支+工作目录），但**没有成熟产品**同时解决 CLI Agent 编排 + 角色协作 + 项目隔离的完整问题。

### 2.2 Tier 1: 专为多 Agent 编排而生

| 工具 | ⭐ | 架构 | 核心能力 | 局限 |
|------|-----|------|---------|------|
| **CCManager** (kbwo) | ~928 | PTY-based CLI | 管理 8 种 Agent，worktree 管理，上下文复制 | 无角色/协作协议，纯会话复用器 |
| **Parallel Code** (johannesjo) | ~363 | Electron + SolidJS | Git worktree per agent，统一 GUI，手机 QR 监控 | GUI 依赖，无 Agent 间通信 |
| **ccswarm** (nwiizo) | ~125 | Rust Actor 模型 | 专业 Agent 池（前端/后端/DevOps/QA），channel 编排 | 早期阶段，生态小 |
| **Overstory** (jayminwest) | 新 | SQLite 邮箱 + 插拔运行时 | 运行时无关，分层合并策略 | 非常早期 |
| **Claude Code Router** (musistudio) | ~29.6K | 本地代理 (port 3456) | 按任务类型路由到不同模型/Provider | 只是路由，无协作 |

### 2.3 Tier 2: 带多模型支持的 CLI 工具

| 工具 | ⭐ | 多模型方式 | 与本项目差异 |
|------|-----|-----------|-------------|
| **Aider** | ~39K | Architect/Editor 双模型（一个规划，一个编辑） | 固定双模型模式，不支持 N 个 Agent 自由编排 |
| **OpenCode** (anomalyco) | ~95K | 75+ provider，多会话并行 | 单 Agent 多模型切换，非多 Agent 协作 |
| **Kilo Code** | N/A | 500+ 模型，Orchestrator 模式分发子 Agent | IDE 绑定(VS Code/JetBrains)，非终端原生 |
| **Crush** (Charmbracelet) | N/A | 会话内切换模型 | 单 Agent 切模型，非并行协作 |
| **Goose** (Block) | N/A | 模型无关 + MCP | 单 Agent 工作流 |

### 2.4 Tier 3: 厂商官方 CLI

| 工具 | 厂商 | 关键架构 |
|------|------|---------|
| **Claude Code** | Anthropic | Subagent + worktree 隔离，`/model` 切换 |
| **Codex CLI** | OpenAI | Rust agent loop，Item/Turn/Thread 协议 |
| **Gemini CLI** | Google | 60 req/min 免费层，1M 上下文，Web grounding |
| **GitHub Copilot CLI** | Microsoft | Claude Sonnet 4.5 + GPT-5，原生 GitHub 集成 |

### 2.5 IDE / 平台级方案

| 平台 | 方案 | 评价 |
|------|------|------|
| **VS Code 1.109** (2026-01) | Agent Sessions 视图，Claude+Codex+Copilot 统一订阅管理 | 最成熟的 IDE 方案，但绑定 VS Code |
| **Warp + Oz** (2026-02) | 终端内同时运行 Claude/Codex/Gemini，Oz 平台支持云端并行+定时调度 | 商业产品，最接近我们的定位，但闭源 |
| **Windsurf Arena Mode** | 两模型盲评对比 | 评测工具，非协作 |

### 2.6 行业架构模式总结

| 模式 | 代表工具 | 特点 | 复杂度 |
|------|---------|------|--------|
| **Router/Proxy** | Claude Code Router | 按任务分类路由到不同模型，无 Agent 间通信 | 低 |
| **Architect/Editor** | Aider | 一个规划一个执行，最成熟，benchmark 最优 | 中 |
| **Orchestrator/Swarm** | ccswarm, Kilo | Master 分解任务→专业 Agent 并行执行 (15x token，90% 更好结果) | 高 |
| **Session Manager** | CCManager, Parallel Code | 管理多个独立 Agent 会话，人工协调 | 低 |
| **Platform Hub** | VS Code 1.109, Warp Oz | 平台级集成，多 Agent 一等公民 | 极高(平台) |

### 2.7 关键发现

1. **无成熟的 CLI 多 Agent 协作方案**：最接近的 CCManager (928⭐) 只是会话管理器，不做 Agent 间通信
2. **Git worktree 是隔离标准**：但只隔离文件系统，不隔离运行时（端口、数据库、服务）
3. **Agent 间通信几乎空白**：大多数工具让人工协调，只有 ccswarm/Overstory 尝试消息传递但极早期
4. **Warp Oz 是最大竞争对手**：商业闭源终端，但验证了市场需求
5. **Aider 的 Architect/Editor 模式**最成熟，值得作为默认工作流参考

### 2.8 差异化定位

```
CCManager/Parallel Code = 多 Agent 会话管理器（人工协调）
Aider                   = 双模型 Pair Programming（固定模式）
ccswarm                 = Rust 专业 Agent Swarm（复杂度高）
Warp Oz                 = 商业终端平台（闭源）
─────────────────────────────────────────────────────
AI-Collab               = 终端原生 CLI Agent Orchestrator
                          N 个独立 CLI Agent + 声明式角色 + 结构化通信
                          开源，可移植，不绑定任何 IDE/终端
```

**我们的独特卡位**：
- 比 CCManager 多了**角色协作协议**
- 比 Aider 多了**N 模型支持 + 自定义角色**
- 比 ccswarm 更**易用**（Python + TOML，不需要 Rust）
- 比 Warp Oz 更**开放**（开源 + 不绑定终端）

---

## 3. 架构设计

### 3.1 核心概念

```
┌─────────────────────────────────────────────────────┐
│                    Workspace                         │
│  一个项目目录的完整协作环境                             │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Agent    │  │  Agent    │  │  Agent    │          │
│  │ (Claude)  │  │ (Codex)   │  │ (Gemini)  │          │
│  │ role:exec │  │ role:rev  │  │ role:idea │          │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        │              │              │                │
│        └──────────────┼──────────────┘                │
│                       │                              │
│              ┌────────▼────────┐                     │
│              │   Message Bus    │                     │
│              │  (项目级隔离)     │                     │
│              └────────┬────────┘                     │
│                       │                              │
│              ┌────────▼────────┐                     │
│              │  Session State   │                     │
│              │  (日志/历史/配置)  │                     │
│              └─────────────────┘                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
~/.ai-collab/                          # 全局配置
├── config.toml                        # 全局默认配置
├── agents/                            # Agent 定义
│   ├── claude.toml                    # Claude Code Agent 配置
│   ├── codex.toml                     # Codex CLI Agent 配置
│   └── gemini.toml                    # Gemini CLI Agent 配置
└── workflows/                         # 工作流模板
    ├── default.toml                   # 默认: architect + reviewer + executor
    └── pair.toml                      # 简单: 只有两个模型

<project>/.ai-collab/                  # 项目级配置 (可选，覆盖全局)
├── config.toml                        # 项目专属配置
├── workflow.toml                      # 项目专属工作流
└── sessions/                          # 会话状态 (gitignored)
    ├── <session-id>/
    │   ├── state.json                 # 会话元数据
    │   ├── messages/                  # Agent 间消息
    │   │   ├── 001_claude_to_codex.json
    │   │   └── 002_codex_to_claude.json
    │   └── logs/                      # 各 Agent 日志
    │       ├── claude.log
    │       ├── codex.log
    │       └── gemini.log
    └── latest -> <session-id>/        # 最新会话软链
```

### 3.3 Agent 定义

```toml
# ~/.ai-collab/agents/claude.toml
[agent]
name = "claude"
display_name = "Claude Code"
binary = "claude"                       # CLI 命令
launch_args = []                        # 默认启动参数
healthcheck = "claude --version"        # 健康检查命令

[agent.capabilities]
can_edit_files = true
can_run_commands = true
can_search_web = false
has_tool_use = true

[agent.communication]
mode = "stdin"                          # stdin | tmux-keys | api | file
input_format = "text"                   # text | json
output_capture = "terminal"             # terminal | stdout | file
```

```toml
# ~/.ai-collab/agents/codex.toml
[agent]
name = "codex"
display_name = "Codex CLI"
binary = "codex"
launch_args = []
healthcheck = "codex --version"

[agent.communication]
mode = "tmux-keys"                      # 通过 tmux send-keys 发送
input_format = "text"
output_capture = "terminal"             # 用户在 tmux pane 看输出
```

```toml
# ~/.ai-collab/agents/gemini.toml
[agent]
name = "gemini"
display_name = "Gemini CLI"
binary = "gemini"
launch_args = ["-p", "--yolo", "-o", "text"]   # headless 模式
healthcheck = "gemini --version"

[agent.communication]
mode = "subprocess"                     # 作为子进程运行，捕获 stdout
input_format = "text"
output_capture = "stdout"               # 直接捕获输出
timeout = 120
```

### 3.4 工作流定义

```toml
# ~/.ai-collab/workflows/default.toml
[workflow]
name = "default"
description = "标准三模型协作: 设计师 + 审查者 + 灵感"

[[workflow.roles]]
role = "designer"
agent = "claude"
description = "Primary planner and architect"
is_primary = true                       # 用户直接交互的 Agent

[[workflow.roles]]
role = "reviewer"
agent = "codex"
description = "Code review and quality gate"

[[workflow.roles]]
role = "inspiration"
agent = "gemini"
description = "Creative brainstorming (reference only)"
trust_level = "low"                     # 输出需要人工确认

[workflow.review]
enabled = true
checkpoints = ["plan", "code"]          # 在哪些阶段触发 review
pass_threshold = 7.0
max_rounds = 3

[workflow.layout]
type = "tmux"
template = """
┌──────────────────────┬──────────────┐
│                      │   {reviewer}  │
│   {designer}         ├──────────────┤
│                      │ {inspiration} │
└──────────────────────┴──────────────┘
"""
primary_pane_width = "60%"
```

### 3.5 消息协议

Agent 之间的通信使用结构化的 JSON 消息：

```json
{
  "id": "msg_001",
  "timestamp": "2026-03-13T04:00:00Z",
  "session_id": "sess_abc123",
  "from": {"agent": "claude", "role": "designer"},
  "to": {"agent": "codex", "role": "reviewer"},
  "type": "review_request",
  "payload": {
    "checkpoint": "plan",
    "content": "...",
    "context": {
      "project": "clawforce",
      "branch": "main",
      "files_changed": ["api/v1/endpoints/tasks.py"]
    }
  },
  "metadata": {
    "round": 1,
    "max_rounds": 3
  }
}
```

---

## 4. 功能规格

### 4.1 P0 — 核心功能 (MVP)

#### 4.1.1 项目级完全隔离
- 每个项目有独立的会话状态、日志、消息队列
- 不同项目的 Agent 进程完全隔离
- 配置支持全局默认 + 项目级覆盖

#### 4.1.2 Workspace 生命周期管理
```bash
ai-collab start [project-dir]     # 启动工作站
ai-collab stop [project-name]     # 停止工作站
ai-collab list                    # 列出运行中的工作站
ai-collab status [project-name]   # 查看详细状态
ai-collab attach [project-name]   # 重新进入工作站
```

#### 4.1.3 Agent 启动与健康检查
- 启动前自动检查 Agent binary 是否存在
- 启动后健康检查
- Agent 崩溃自动重启（可配置）
- 优雅退出（向所有 Agent 发送退出信号）

#### 4.1.4 tmux 布局管理
- 根据工作流定义自动创建 tmux 布局
- 支持从 tmux 内部和外部启动
- Pane 标题显示 Agent 名称和角色
- 焦点自动定位到 primary Agent

#### 4.1.5 Agent 间通信 (ask-model)
- 项目感知：自动识别当前项目
- 日志隔离：每个项目+Agent 独立日志
- 支持多种通信模式：subprocess（Gemini）、tmux-keys（Codex）、stdin（未来）
- 超时和错误处理

### 4.2 P1 — 增强功能

#### 4.2.1 工作流引擎
- 声明式工作流定义（TOML）
- 支持 review checkpoint 自动触发
- 支持自定义角色和评分标准
- 工作流模板市场

#### 4.2.2 配置注入
- 自动生成 CLAUDE.md 中的角色和协作规则
- 不再手动维护 CCB_CONFIG 块
- `ai-collab init` 自动配置项目

#### 4.2.3 会话持久化
- 跨会话保留协作历史
- 支持 resume 上次的工作站状态
- 消息历史可查询

### 4.3 P2 — 高级功能

#### 4.3.1 动态 Agent 管理
- 运行时添加/移除 Agent
- Agent 角色动态切换
- 支持同一模型多实例（如两个 Claude 分别做不同任务）

#### 4.3.2 插件系统
- 自定义 Agent 适配器
- 自定义通信协议
- Hook 系统（pre-send / post-receive）

#### 4.3.3 可观测性
- 统一 dashboard（消息流、Agent 状态、错误）
- Token 用量统计
- 协作效率指标

---

## 5. 技术方案

### 5.1 语言选择

**Python** — 理由：
- 目标用户（开发者）的机器几乎都有 Python
- 丰富的 CLI 框架（Click/Typer）
- tmux 控制库（libtmux）
- 快速原型，容易贡献

备选：Go（单二进制分发更方便，但开发速度慢）、Rust（性能好但门槛高）

### 5.2 核心依赖

```
click >= 8.0          # CLI 框架
libtmux >= 0.37       # tmux 编程控制
tomli / tomllib       # TOML 配置解析
pydantic >= 2.0       # 数据模型验证
rich >= 13.0          # 终端美化输出
```

### 5.3 项目结构

```
ai-collab/
├── pyproject.toml
├── src/
│   └── ai_collab/
│       ├── __init__.py
│       ├── cli.py              # CLI 入口 (click)
│       ├── config.py           # 配置加载 (全局 + 项目)
│       ├── workspace.py        # Workspace 生命周期
│       ├── agent.py            # Agent 抽象 + 适配器
│       ├── layout.py           # tmux 布局管理
│       ├── messenger.py        # Agent 间消息通信
│       ├── session.py          # 会话状态管理
│       ├── workflow.py         # 工作流引擎
│       └── adapters/           # Agent 适配器
│           ├── base.py
│           ├── claude.py
│           ├── codex.py
│           └── gemini.py
├── configs/                    # 默认配置模板
│   ├── agents/
│   └── workflows/
├── tests/
└── docs/
```

---

## 6. 与现状的对比

### 6.1 当前系统的问题清单

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | Gemini 日志全局共享，项目间泄露 | 🔴 | 硬编码 `~/.local/share/gemini-live.log` |
| 2 | tmux 嵌套 attach 崩溃 | 🔴 | 未检测 `$TMUX` 环境 |
| 3 | Codex pane fallback 到错误项目 | 🟡 | `find_codex_pane` 的 fallback 逻辑硬编码 `bladeai` |
| 4 | 角色定义散落在 CLAUDE.md | 🟡 | 无统一配置源 |
| 5 | CCB 残留文件污染 | 🟡 | 旧系统迁移不彻底 |
| 6 | ask-model 脚本无项目感知 | 🟡 | 只用 `os.getcwd()` 猜测项目 |
| 7 | 无 Agent 健康检查 | 🟢 | 脚本直接 send-keys，不检查 Agent 是否存活 |
| 8 | 无会话持久化 | 🟢 | tmux session kill 后一切丢失 |
| 9 | 脚本散落各处 | 🟢 | `~/.local/bin/` + `~/.local/share/codex-dual/bin/` |
| 10 | 不可移植 | 🟢 | 绝对路径、硬编码项目名 |

### 6.2 迁移路径

```
Phase 0 (现在)    → 修补现有脚本的关键 bug（已完成日志隔离、tmux 修复）
Phase 1 (MVP)     → Python 包，替代 ai-collab + ask-model 脚本
Phase 2 (v0.2)    → 工作流引擎 + 配置注入
Phase 3 (v1.0)    → 插件系统 + 可观测性 + 公开发布
```

---

## 7. 开放问题

1. **项目名**：`ai-collab` 够好吗？考虑过 `aicrew`、`polyglot`、`ensemble`、`chorus`
2. **Codex 通信**：tmux send-keys 是否可靠？Codex CLI 有无 headless/API 模式？
3. **配置格式**：TOML vs YAML vs JSON？ TOML 最适合 CLI 工具，但 YAML 更普及
4. **分发方式**：pip install？brew？单二进制（PyInstaller）？
5. **是否需要 daemon**：当前设计是 tmux-based 前台运行。是否需要后台 daemon 模式？
6. **Agent SDK 标准**：是否对齐 Anthropic Agent SDK 或 OpenAI Agent SDK 的概念？

---

## 附录 A: 用户故事

### 故事 1: 基本启动
```
作为开发者，我执行 `ai-collab start ~/workspace/myproject`，
系统自动启动 Claude + Codex + Gemini 三个 Agent，
各自在独立的 tmux pane 中运行，
所有状态都隔离在 myproject 下。
```

### 故事 2: 跨模型审查
```
作为开发者，我在 Claude 中完成了一个功能开发，
Claude 自动将 git diff 发送给 Codex 进行 code review，
Codex 返回评分和建议，
Claude 根据反馈修改代码，
整个过程我只在 Claude pane 中操作。
```

### 故事 3: 多项目并行
```
作为开发者，我同时开了两个工作站：
  ai-collab start ~/workspace/project-a
  ai-collab start ~/workspace/project-b
两个工作站的 Agent 完全隔离，
project-a 的 Gemini 对话不会出现在 project-b 的面板中。
```

### 故事 4: 灵感咨询
```
作为开发者，我需要设计一个新的 UI 组件，
Claude 调用 `ask-model gemini "给这个表单设计3种布局方案"`，
Gemini 返回创意建议，
Claude 评估后展示给我选择，
我选定方案后 Claude 执行实现。
```

---

## 附录 B: 市场调研参考来源

- [Agentic Coding 2026: AI Agent Teams Guide](https://halallens.no/en/blog/agentic-coding-in-2026-the-complete-guide-to-plugins-multi-model-orchestration-and-ai-agent-teams)
- [The 2026 Guide to Coding CLI Tools: 15 AI Agents Compared (Tembo)](https://www.tembo.io/blog/coding-cli-tools-comparison)
- [Parallel Code - GitHub](https://github.com/johannesjo/parallel-code)
- [CCManager - GitHub](https://github.com/kbwo/ccmanager)
- [ccswarm - GitHub](https://github.com/nwiizo/ccswarm)
- [Overstory - GitHub](https://github.com/jayminwest/overstory)
- [Claude Code Router - GitHub](https://github.com/musistudio/claude-code-router)
- [Unrolling the Codex Agent Loop (OpenAI)](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [VS Code: Your Home for Multi-Agent Development](https://code.visualstudio.com/blogs/2026/02/05/multi-agent-development)
- [GitHub: Pick Your Agent - Claude and Codex on Agent HQ](https://github.blog/news-insights/company-news/pick-your-agent-use-claude-and-codex-on-agent-hq/)
- [Warp: The Agentic Development Environment](https://www.warp.dev/)
- [Kilo Code Orchestrator Mode](https://kilo.ai/docs/code-with-ai/agents/orchestrator-mode)
- [OpenHands - GitHub](https://github.com/OpenHands/OpenHands)
- [Aider - AI Pair Programming](https://aider.chat/)
- [Git Worktrees for Parallel AI Coding Agents (Upsun)](https://devcenter.upsun.com/posts/git-worktrees-for-parallel-ai-coding-agents/)
- [Claude Code Swarms: Multi-Agent AI Coding](https://zenvanriel.com/ai-engineer-blog/claude-code-swarms-multi-agent-orchestration/)
- [Microsoft Multi-Agent Reference Architecture](https://microsoft.github.io/multi-agent-reference-architecture/docs/context-engineering/Agents-Orchestration.html)
