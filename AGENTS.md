# Repository Guidelines

## Documentation Update Policy

**Critical: every repository content change must include a synchronized check and update of the root `README.md` and `AGENTS.md`.**

- `README.md` is user-facing. Keep it current for workspace purpose, structure, navigation, environment principles, data boundaries, submodules, and maintenance conventions. Keep detailed run commands in the relevant subproject README instead of the root README.
- `AGENTS.md` is agent-facing. Keep it current for project structure, validation commands, maintenance conventions, submodule boundaries, and AI-agent workflows.
- Even when a change appears to affect only one document, confirm before committing that both documents still match the repository state.
- For submodule-only changes, update the submodule's own documentation first. If the change affects root-level usage or agent workflow, also update the root `README.md` and `AGENTS.md`.
- Keep this file in English unless the user explicitly asks otherwise.

## Project Structure & Module Organization

Keep the research contract in `RESEARCH.md` and active work in `TODO.md`. Put reusable paper-method, training, and evaluation code in `src/`; put externally cloned comparison-method source in `baselines/` and pin its upstream revision; put data preparation and environment helpers in `scripts/`. Each concrete experiment needs a standalone entry script in `experiments/scripts/` and an immutable run record in `experiments/runs/<run-id>/`. Draft prose belongs in `paper/draft_zh.md`; edit `paper/main.tex` only when explicitly preparing the formal manuscript. Store paper-ready figures and their sources in `paper/images/`.

Do not modify `.agents/` unless the task explicitly requests it. Read the nearest directory README before adding files.

## Build, Test, and Development Commands

Use Python 3.10+ and `uv`:

```bash
uv sync                         # create/update the project environment
uv run python main.py           # run the current top-level entry point
uv run python scripts/<tool>.py --help
uv run python experiments/scripts/exp-001-baseline.py --seed 1337 --output-dir experiments/runs/<run-id>
```

The repository currently has no committed automated test suite or configured formatter. Validate changed Python files with a focused executable command, and add tests alongside new reusable behavior when a test framework is introduced.

## Coding Style & Naming Conventions

Target Python 3.10+, use four-space indentation, type hints for public functions, and clear docstrings for reusable modules. Use `snake_case` for modules, functions, variables, and CLI options. Name experiment scripts `exp-<nnn>-<short-description>.py` and run directories `run-<timestamp>-<short-description>/`. Avoid hard-coded machine paths, credentials, and hidden configuration.

## Experiment and Paper Evidence

Persist every actual run's command, configuration snapshot, metadata, log, and metrics. Never overwrite an existing run directory or retroactively edit metrics. Generate data plots with Seaborn and keep the corresponding Python script. Numerical claims in the paper must identify the supporting experiment ID; mark unverified content as `TODO`.

## Commit & Pull Request Guidelines

**所有提交信息必须使用中文书写。** 格式遵循 conventional commit 规范，例如 `fix(analysis): 修复 best_bpb 定义` 或 `feat(experiments): 添加 baseline runner`。保持提交聚焦。Pull request 应说明研究或工程变更，列出验证命令，链接相关 issue，并附上结果证据或可视化截图。

## Security

Keep `.env` untracked. Never print API keys, tokens, passwords, or complete environment dumps in code, logs, issues, or commits.
