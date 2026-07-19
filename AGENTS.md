# Repository Guidelines

## Documentation Update Policy

**Critical: every repository content change must include a synchronized check and update of the root `README.md` and `AGENTS.md`.**

- `README.md` is user-facing. Keep it current for workspace purpose, structure, navigation, environment principles, data boundaries, submodules, and maintenance conventions. Keep detailed run commands in the relevant subproject README instead of the root README.
- `AGENTS.md` is agent-facing. Keep it current for project structure, validation commands, maintenance conventions, submodule boundaries, and AI-agent workflows.
- Even when a change appears to affect only one document, confirm before committing that both documents still match the repository state.
- For submodule-only changes, update the submodule's own documentation first. If the change affects root-level usage or agent workflow, also update the root `README.md` and `AGENTS.md`.
- Keep this file in English unless the user explicitly asks otherwise.

## Project Structure & Module Organization

Keep the research contract in `RESEARCH.md` and active work in `TODO.md`. `TODO.md` is the user-facing progress view: update in-progress, next-step, and completed items within its three fixed phases—research and design, experiments and analysis, and paper writing—as work advances. Patent work is optional in phase three: do not create or update patent materials unless the user explicitly requests it. Put reusable paper-method, training, and evaluation code in `src/`; put externally cloned comparison-method source in `baselines/` and pin its upstream revision; put data preparation and environment helpers in `scripts/`. Each concrete experiment needs a standalone entry script in `experiments/scripts/` and an immutable run record in `experiments/runs/<run-id>/`. Draft prose belongs in `paper/draft_zh.md`; edit `paper/main.tex` only when explicitly preparing the formal manuscript. Store paper-ready figures and their sources in `paper/images/`. Store patent technical disclosures, claim drafts, prior-art notes, and patent figures in `patents/`; do not represent a draft as legal advice or a filing-ready application.

## Research Intake

Before beginning research or experiments, inspect both `RESEARCH.md` and `TODO.md`. If neither provides a sufficiently complete objective, research questions, constraints, and next actions, proactively brainstorm with the user. Clarify the problem, success criteria, available data, baselines, budget, and stage-one deliverables before implementing code or launching runs. Record the agreed direction in `RESEARCH.md` and the actionable work in `TODO.md`.

Use GPT-5.6 Sol with Ultra reasoning for the first 1–3 open-ended brainstorming rounds, then Sol with Medium reasoning to finalize stage-one documents. For stage two and stage three, use GPT-5.6 Terra with Low reasoning and a `/goal` objective tied to the relevant `TODO.md` phase. Goals must name the expected outcome, constraints, and verification criteria. Patent work remains opt-in and requires an explicit user request.

Users normally clone the repository, enter its relative project directory, launch `codex` from the repository root, and interact through prompts; do not require them to run routine setup, experiment, or writing commands manually. Treat API keys, tokens, database credentials, and restricted-data access as user-managed setup. Do not ask users to paste secrets or read `.env` files.

Do not modify `.agents/` unless the task explicitly requests it. Read the nearest directory README before adding files.

## Experiment Resources

Experiments may use a local GPU, an external model API, or both in the same run. External model APIs currently target OpenAI-compatible interfaces. During experiment design, define the separate role of each resource and their data flow, record the intended use in `RESEARCH.md` and the actionable preparation in `TODO.md`, and confirm the GPU-time and external-API budgets with the user before execution. Do not impose a fixed API/GPU split when the research question calls for a different design. Every experiment script must include a top-level docstring declaring its experiment ID and purpose, API and GPU usage and roles, their data flow, applicable budgets, inputs, outputs, and run command; follow `experiments/scripts/README.md` for the exact template.

Before launching a run, check the required resources independently. For GPU work, verify the selected device and record the GPU model, CUDA version, PyTorch version, available or relevant VRAM, and the local model or checkpoint version. For API work, verify only that the required configuration is available; do not read or reveal secret values from `.env`. Experiment code may consume a user-provided credential from the process environment at runtime, but it must never print, serialize, snapshot, or embed the credential in source code, commands, configuration files, metadata, logs, issues, or commits. Record the external API protocol and model name, but never the API key.

Persist the actual API and GPU roles, versions, resource usage, and failures in the immutable run record. Never silently switch an API provider, external model, local model, checkpoint, device, or resource type after a failure; follow a fallback only when it was agreed in advance, otherwise preserve the failure evidence and stop or create a separately identified run after the plan is revised. Paper results must identify the supporting experiment IDs and disclose which external and local models produced or evaluated the reported results.

Before any resource-dependent work begins, complete this preflight in order: verify that the research question and success criteria are defined; confirm the API/GPU roles and data flow; identify the external API model and each local model or checkpoint; confirm the API-call, API-cost, and GPU-time limits; select an unused run ID and output path; then let the experiment process check GPU availability and report required API variables only as configured or missing, never by value. Create the immutable run record before executing the experiment so a failed preflight or partial run can still be preserved.

Apply explicit failure behavior. Stop a GPU-dependent run and record failure when the GPU is unavailable or out of memory; never substitute an API model. When an API credential is missing, tell the user to configure it locally without asking them to paste it. Retry API failures only up to the predeclared limit, stop new requests when the call or cost budget is reached, and never silently switch providers or models. Any run that completes only part of its declared data flow remains failed and must not support a paper claim. Follow `experiments/runs/README.md` for the required resource metadata and metrics.

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
