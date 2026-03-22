# Skills 安装与挂载指南

本仓库的 `skills/` 目录包含纯 Markdown 技能契约。各平台挂载方式如下。

## Claude Code

Claude Code 读取项目根目录的 `CLAUDE.md`，其中已描述了所有 skills。只需将本仓库作为工作目录即可：

```bash
cd /path/to/academic-intel-skillkit
claude
```

如需注册为自定义斜杠命令（如 `/daily-brief`），可将 skill 文件链接到 `.claude/commands/`：

```bash
mkdir -p .claude/commands
# 创建自定义命令
cat > .claude/commands/daily-brief.md << 'EOF'
Read skills/research-daily-brief/SKILL.md and execute the workflow described there.
Use the crawer conda environment for all script execution.
EOF
```

之后在 Claude Code 中输入 `/daily-brief` 即可调用。

## Codex (OpenAI)

Codex 通过 `AGENTS.md` 或项目说明文件获取上下文。将 skill 内容引入 Codex 的方式：

1. 在 `AGENTS.md` 中引用 skill 文件：

```markdown
## Available Skills
- See `skills/research-daily-brief/SKILL.md` for the daily brief workflow
- See `skills/research-topic-manager/SKILL.md` for topic inspection
```

2. 或在 Codex 对话中直接指定工作目录为本仓库根目录，Codex 会自动发现 `skills/` 下的文件。

## OpenCode

OpenCode 的配置文件（通常为 `opencode.json` 或项目级指令）中引用 skill 路径：

```json
{
  "instructions": [
    "Read skills/research-daily-brief/SKILL.md for the daily brief workflow.",
    "All scripts must run in the crawer conda environment."
  ]
}
```

## OpenClaw

OpenClaw 直接调度 `scripts/run_daily_pipeline.py`，不需要显式加载 SKILL.md。参见 `examples/openclaw-cron-notes.md` 了解推荐的定时任务配置。

## 通用注意事项

- 所有平台都需要先完成 Setup（见 CLAUDE.md 的 Setup 章节）
- 运行环境必须使用 `crawer` conda 环境
- `config/research-topics.local.yaml` 和 `configs/sources.local.yaml` 必须在首次运行前创建
- LLM 摘要翻译功能需要配置 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 环境变量
