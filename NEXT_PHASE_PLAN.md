# 下一阶段开发方案

## 1. 背景与目标重申

本项目的原始目标，不是继续堆一个“能跑的脚本仓库”，而是建设一套**可开源、可复用、可被 OpenClaw / Claude Code / Codex / OpenCode 使用的研究情报技能库**。

首长的原始要求可归纳为：

1. **每天早上 9 点** 自动更新研究领域相关的最新 arXiv 论文简报
2. 自动整理**相关学术社区 / 热点研究**简报
3. 首长可按需指定某篇论文，交由：
   - Claude Code
   - Codex
   - OpenCode
   之一进行深度分析
4. 基于每日简报与深读结果，自动形成：
   - 学术周报
   - 学术月报
5. 支持研究主题的增删改
6. 技能库应符合通用技能开发规范，方便别人使用与部署
7. 报告正文用中文，论文元数据（标题、作者、机构、ID、venue、链接等）保留原文

---

## 2. 当前实际状态

### 2.1 当前已具备的真实能力

当前仓库已经有一个**可运行的 arXiv-only daily brief MVP**，具体包括：

- `scripts/fetch_arxiv.py`
  - 基于 topic 配置抓取 arXiv 候选论文
- `scripts/generate_daily_brief.py`
  - 读取 JSON 候选数据，进行去重、排序、生成 Markdown 日报
- `scripts/common.py`
  - 提供 topic scoring、candidate merge、dedup、路径提示、配置校验等基础能力
- `scripts/manage_topics.py`
  - 具备只读管理能力：
    - `--list`
    - `--detail`
    - `--validate`
    - `--query-plan`
    - `--print`
- `templates/daily-brief-template.md`
  - 已收口为当前 canonical 日报模板
- README / examples / skills
  - 已初步收口为“真实能力”与“脚手架能力”边界清晰的状态

### 2.2 当前仍是脚手架 / 半实现的部分

以下内容目前仍未形成真实可用能力：

- `scripts/fetch_semantic_scholar.py`
- `scripts/fetch_huggingface.py`
- `scripts/build_periodic_report.py`
- `paper-deep-dive` 自动化执行链路
- `research-weekly-review` 真正实现
- `research-monthly-review` 真正实现
- `research-topic-manager` 的写操作（新增 / 删除 / 修改 topic）
- OpenClaw 的实际任务编排与定时交付
- OpenCode 在产品能力层的接入
- Obsidian 的真正生产化落盘与索引维护

### 2.3 当前阶段判断

当前项目已经不再是“概念仓库”，但也还不是完整研究情报技能库。

更准确的定位是：

# 当前项目 = 可运行的 arXiv-only daily brief MVP + 研究情报技能库雏形

---

## 3. 下一阶段必须完成的事情

下一阶段开发，不能继续无序扩张，而要围绕“从 MVP 走向真正技能库”来推进。

### 必须完成的任务分组

#### A. 规范化（必须先做）

目的是让当前仓库成为一个真正适合别人使用的开源技能库基础版本。

需要完成：

1. **完成当前日报中文输出层收口**
   - 确认所有日报叙述、建议、结构性文案均为中文
   - 确认元数据仍保持原文
2. **统一 canonical 使用路径**
   - README
   - config
   - template
   - scripts
   必须完全一致
3. **清理或隔离运行产物**
   - output 目录中的样例文件与临时验证产物要么明确作为 example，要么移出正式仓库面
4. **统一 README / skills / examples 的能力边界描述**
   - 避免任何“看起来已实现，实际只是脚手架”的表述
5. **检查测试与实际 CLI 行为一致性**

#### B. 通用化（下一层必须做）

目的是让当前能力不只服务 OpenClaw 本机，而是成为真正可复用的技能层资产。

需要完成：

1. **明确“技能层 / 脚本层 / 编排层”分层**
   - skills：描述使用方式
   - scripts：执行核心逻辑
   - examples：宿主适配说明
2. **让 OpenClaw / Claude Code / Codex / OpenCode 的使用方式更清楚**
   - 至少在 README / examples 中明确当前适用方式
3. **把 topic manager 做到最小可用**
   - 当前已有只读能力，可进一步提升为：
     - 更明确的 query preview
     - 更清晰的校验输出
     - 更好的 topic 配置诊断

#### C. 产品化（真正向原始目标靠拢）

这一层不要求一下子全做完，但至少要明确顺序。

优先候选：

1. **学术热点源接入**（至少落一个真实源）
   - 建议优先：Hugging Face 热点 / 其它容易稳定接入的源
2. **深度研读链路**
   - 指定论文后，支持路由：
     - Claude Code
     - Codex
     - OpenCode
3. **周报 / 月报真实生成**
   - 基于日报与深读结果，而不是模板占位
4. **OpenClaw 调度与定时交付**
   - 9:00 日报
   - 周报 / 月报的 cron 方案
5. **Obsidian 真正落盘**
   - 将输出写入约定目录
   - 保持命名规则与目录规范一致

---

## 4. 下一阶段开发优先级

### P0：规范化收口（必须优先完成）

目标：
让当前仓库从“可跑原型”变成“合格的开源 MVP 技能库”。

本阶段交付物：
- 收口后的 README
- 一致的 canonical CLI 路径
- 清晰的 scaffold-only 边界
- 干净的输出模板与示例说明
- 中文日报输出行为稳定

### P1：最小真实增量（Topic 管理与体验增强）

目标：
在不扩太多功能的前提下，再补一个真实好用的小能力。

建议优先做：
- topic manager 的最小可用增强
- topic / query-plan / config validation 的体验优化

### P2：进入产品化能力

目标：
开始逐步补原始目标里真正缺失的高层能力。

建议顺序：
1. 热点源接入
2. 深读自动化链路
3. 周报
4. 月报
5. OpenClaw 调度
6. Obsidian 真落盘

---

## 5. 建议的下一阶段实施方案

### 阶段 1：完成当前 MVP 的规范化收口

本阶段任务：

1. 完成日报模板与日报生成脚本的中文输出收口
2. 确认 README、examples、skills 与脚本行为一致
3. 统一默认路径：
   - `config/research-topics.local.yaml`
   - `templates/daily-brief-template.md`
   - `output/arxiv.json`
   - `output/daily-brief.md`
4. 将非实现能力明确标注为 scaffold-only
5. 跑一轮完整本地验证
6. 整理仓库中不必要的输出产物

### 阶段 2：完成最小可用的 Topic 管理层

本阶段任务：

1. 增强 `scripts/manage_topics.py`
2. 保持“只读 + 诊断 + 预览”能力扎实可用
3. 不急着进入自动写配置，先把：
   - list
   - detail
   - validate
   - query-plan
   做稳
4. 为未来 mutation 能力留干净接口

### 阶段 3：补第一项真正的新产品能力

建议优先项：

#### 方案 A（推荐）：热点源接入
- 最小真实接入一个社区热点源
- 让“论文日报 + 热点信号”开始形成真正研究情报感

#### 方案 B：深度研读链路
- 实现 paper-deep-dive 的宿主级调用约定
- 让指定论文可以进入 Claude Code / Codex / OpenCode 的分析链路

建议先做 A，再做 B。

---

## 6. 宿主与执行器协同方案

为符合首长的要求，下一阶段必须始终遵循：

### 项目级开发方式
- 默认使用 **coding-agent 技能**
- 默认执行器使用 **Codex**
- 若首长另行指定，再切换 Claude Code / OpenCode

### 产品使用层定位
- **OpenClaw**：调度、定时、汇总、交付
- **Claude Code**：适合学术内容深读与表达整理
- **Codex**：适合结构化实现、脚本、架构、工程审阅
- **OpenCode**：后续可作为另一类执行器接入，但当前仓库尚未真正体现其使用层

---

## 7. 下一阶段完成标准

下一阶段完成后，至少要达到以下状态：

1. 外部用户读 README 就能知道：
   - 当前能做什么
   - 不能做什么
   - 如何开始跑 MVP
2. 当前 arXiv-only 日报链路稳定可跑
3. 中文输出规则贯彻一致
4. topic manager 至少具备可靠的只读诊断能力
5. 非实现能力不会误导用户
6. 仓库整体看起来像“可继续扩展的技能库”，而不是“脚本堆积”

---

## 8. 结论

下一阶段开发的核心，不是继续盲目加功能，而是：

# 先把当前已实现的 MVP 做成一个规范、诚实、可复用、方便别人使用的开源技能库基础版本

在这个基础上，再逐步补热点源、深读、周报月报、OpenClaw 调度等真正的上层能力。
