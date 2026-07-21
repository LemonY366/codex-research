# Repository Guidelines

## Documentation Update Policy

**Critical: every repository content change must include a synchronized check and update of the root `README.md` and `AGENTS.md`.**

- `README.md` is user-facing. Keep it current for workspace purpose, structure, navigation, environment principles, data boundaries, submodules, and maintenance conventions. Keep detailed run commands in the relevant subproject README instead of the root README.
- `AGENTS.md` is agent-facing. Keep it current for project structure, validation commands, maintenance conventions, submodule boundaries, and AI-agent workflows.
- Even when a change appears to affect only one document, confirm before committing that both documents still match the repository state.
- For submodule-only changes, update the submodule's own documentation first. If the change affects root-level usage or agent workflow, also update the root `README.md` and `AGENTS.md`.
- Keep this file in English unless the user explicitly asks otherwise.

## Project Structure & Module Organization

Keep the current effective research contract, global workflow state, compact phase-one actions, field confirmations, durable decision summaries, authorizations, evidence summaries, and phase transitions in `RESEARCH.md`. Put detailed phase-one query provenance, source metadata, atomic claims, decision evidence chains, and compact RQ summaries in `research/` according to its README. Do not put search-result streams, source full text, long reading notes, command output, debug logs, experiment configurations, or metric details in `RESEARCH.md`; do not use `research/` as a full-text or private-material store. Keep phase-two tasks in `experiments/TODO.md` and phase-three tasks in `paper/TODO.md`; these stage files contain only active, next, blocked, and compact completed summaries, never command output or detailed execution history. Patent work is optional in phase three: do not create or update patent materials unless the user explicitly requests it. Put reusable paper-method, training, and evaluation code in `src/`; put externally cloned comparison-method source in `baselines/` and pin its upstream revision; put data preparation and environment helpers in `scripts/`. Each concrete experiment needs a standalone entry script in `experiments/scripts/` and an immutable run record in `experiments/runs/<run-id>/`. Draft prose belongs in `paper/draft_zh.md`; edit `paper/main.tex` only when explicitly preparing the formal manuscript. Store paper-ready figures and their sources in `paper/images/`. Store patent technical disclosures, claim drafts, prior-art notes, and patent figures in `patents/`; do not represent a draft as legal advice or a filing-ready application.

## Research Intake

Before beginning research, inspect `RESEARCH.md`, `docs/PHASE_ONE_PROTOCOL.md`, and `docs/WORKFLOW_GATES.md`. Follow the persisted phase-one substate through `INTAKE`, `DIVERGE`, `SEARCH`, `COMPARE`, `DRAFT`, `CONFIRM`, and `GATE_CHECK`; use the documented rollback paths when an earlier premise changes. Before experiments, also inspect `experiments/TODO.md`; before writing, inspect `paper/TODO.md` and the experiment evidence handoff. Do not convert one broad user prompt directly into a final contract. Populate the ordered intake table for research intent, object, core problem, expected contribution, success criteria, data conditions, baseline, metrics, time/cost, API/GPU, licensing/privacy, and out-of-scope work. User-provided information may be recorded out of turn, but Codex questions and gate resolution follow that dependency order. For every critical contract field, record the current value or stable-ID reference, information source, one of `已确认`/`暂定`/`待确认`/`存在冲突`/`不适用`, the latest confirmation date or turn, and applicable decision and evidence IDs. `不适用` requires an explicit reason. Use the stable ID formats declared in `RESEARCH.md`. Record the agreed direction and compact phase-one actions in `RESEARCH.md`, phase-two actions in `experiments/TODO.md`, and phase-three actions in `paper/TODO.md`.

Create at least two substantively different `DIR-<nnn>` candidates before `SEARCH`, even when the user initially prefers one option. Compare each candidate on research value, novelty risk, data needs, compute cost, validation difficulty, and expected deliverables. Before `DRAFT`, require exactly one `已选定` direction linked to a defined research question and decision; mark every other candidate `已否决` with a concrete reason. If the user combines candidates, create one new bounded direction and reject the originals as standalone options. Never carry multiple final directions into stage two, and preserve rejected alternatives and reasons in `research/decisions.yaml`.

Separate direction, data, metric, budget, and authorization confirmations. Phrases such as “可以考虑”, “先看看”, or general approval permit exploration only and must not be promoted to formal confirmation. Never infer paid use, external transfer, restricted access, or other high-risk authority from a broader confirmation. State the exact fields and IDs covered by each request, record confirmed research choices as `DEC-<nnn>` and applicable permissions as `AUTH-<nnn>`, and invalidate affected downstream confirmations whenever a critical field changes. Before ending each phase-one interaction, update every item in the `RESEARCH.md` session-recovery summary, using “无” with a reason where appropriate; a new session resumes from that summary rather than reconstructing state from chat history.

Before stage two, map every `RQ-<nnn>` to at least one confirmed data, baseline, metric, success criterion, and planned `exp-<nnn>` relation. Each contribution must name a defined comparison baseline. The corresponding `experiments/TODO.md` task must reference the same research-question and success-criterion IDs. Do not treat removing placeholders as evidence that the contract is semantically complete.

For every actual stage-one search, append one sanitized `QRY-<nnn>` JSON object to `research/search_log.jsonl`. Register every formally used source as `SRC-<nnn>` in `research/sources.yaml`, every atomic factual claim as `CLM-<nnn>` in `research/claims.yaml`, and every durable research decision as `DEC-<nnn>` in `research/decisions.yaml`. Use only the flat, JSON-scalar YAML subset documented in `research/README.md`. Never invent entries to satisfy a gate. Contract evidence and decision IDs in `RESEARCH.md` must resolve to these detailed records; only verified claims marked eligible may support the current contract.

Treat query records as append-only after execution and confirmed decisions as immutable in meaning. Correct or supersede them with new stable IDs and explicit links. Source and claim metadata may gain verification or lifecycle status without erasing prior conflicts or unfavorable evidence. At phase-one completion, compact only duplicate narrative summaries; preserve all IDs referenced by the contract, stage-two work, or later writing.

Use GPT-5.6 Sol with Ultra reasoning for the first 1–3 open-ended brainstorming rounds, then Sol with Medium reasoning to finalize `RESEARCH.md`. For stage two and stage three, use GPT-5.6 Terra with Low reasoning and a `/goal` objective tied respectively to `experiments/TODO.md` or `paper/TODO.md`. Goals must name the expected outcome, constraints, and verification criteria. Patent work remains opt-in and requires an explicit user request.

Users normally clone the repository, enter its relative project directory, launch `codex` from the repository root, and interact through prompts; do not require them to run routine setup, experiment, or writing commands manually. Treat API keys, tokens, database credentials, and restricted-data access as user-managed setup. Do not ask users to paste secrets or read `.env` files.

Do not modify `.agents/` unless the task explicitly requests it. Read the nearest directory README before adding files.

## Content Ownership

`docs/TEMPLATE_BOUNDARIES.md` is the authoritative source for which paths are template-maintained, dynamically generated by Codex, user-managed and local, runtime-generated and immutable, or optional and authorization-gated. Classify a target with that document before creating, editing, deleting, or committing it. Stable template rules change only for an explicit template-maintenance task or when shared workflow, structure, capability, or safety behavior genuinely changes; do not place one-off experiment details in them.

Within an approved research scope, create and maintain dynamic research content without asking the user to perform routine file work. Never create, fill, read, reveal, or commit user-secret files; code may consume credentials only from the process environment at runtime. Never overwrite historical run evidence. Do not generate formal LaTeX, patent materials, externally transmitted data, new paid usage, or other authorization-gated outputs without the required user approval. If a path is not classified by the boundary document or its nearest README, inspect references and history first and treat unresolved ownership as a template-maintenance decision rather than guessing from an empty file or stale configuration.

## Dependency Management

Keep the template's core dependency set minimal and limited to capabilities shared across intended projects. Add research-specific packages only when an approved method, experiment, data pipeline, evaluation, or deliverable requires them. Before adding or removing any dependency, explain its purpose, affected workflow, viable alternatives, version or source constraints, license and platform implications, and expected environment cost to the user, then obtain confirmation. Give special scrutiny to large or hardware-specific stacks such as GPU frameworks, OCR systems, plotting suites, model runtimes, and vendor SDKs; prefer optional or task-scoped installation when practical.

Do not treat a package used by one research topic as a permanent template dependency, and do not remove an existing package merely because current Python files do not import it: first check documentation, skills, scripts, lockfile sources, and planned workflows. Record confirmed research-specific dependency decisions in `RESEARCH.md` and actionable environment work in the TODO file for the affected stage. Every accepted dependency change must update `pyproject.toml` and `uv.lock` together, preserve explicit indexes or platform constraints, avoid untrusted sources, and be validated with `uv sync` plus a focused import or executable check. Never place credentials in dependency URLs or configuration.

## Dynamic Registries and Workspace Validation

Create `datasets/registry.yaml`, `models/registry.yaml`, `baselines/registry.yaml`, or `experiments/registry.yaml` only when the first real object of that type is confirmed. Do not pre-create empty registries or populate them with fictional examples. The pre-created empty `research/` evidence collections are a separate phase-one schema and may remain empty until real queries, sources, claims, or decisions exist; never add fictional entries. Follow the nearest directory README for required fields, keep entries non-secret, and update references as objects and runs are added without rewriting historical evidence.

Run `uv run python scripts/validate_workspace.py` after changing workflow state, research-contract IDs or confirmations, phase-one evidence, registries, experiment evidence, or paper claims, and before handoff or commit when relevant. Use `--strict` for release-style validation, and run `python3 -m unittest discover -s tests -v` after validator changes. The validator reads the global phase and phase-one substate from `RESEARCH.md`, rejects a legacy root `TODO.md`, checks ordered requirement intake, multi-candidate comparison, unique final-direction selection, field confirmation evidence, recovery completeness, stable ID definitions, RQ-to-experiment relations, stage-two task back-references, phase-one JSONL/YAML evidence schemas and references, evidence quality warnings, minimal-disclosure limits, forbidden full-text/sample fields, common personal-data patterns, unresolved placeholders, and document size. The validator is read-only: it must not start Codex, read `.env`, create evidence entries or registries, repair records, or generate research content. Its Markdown and semantic checks establish structural consistency, not scientific validity, candidate novelty, or source truth; treat them, the secret scan, and the Git-based immutability check as safeguards rather than proofs. Investigate findings without printing sensitive values. End-to-end tests may generate fictional evidence only inside an automatically deleted temporary workspace; never place test fixtures in the live `research/` registries or create fake experiment runs.

Do not treat the root `main.py` file or the `research` command declared in project metadata as required workflow entry points. Ignore them during normal research generation and workspace validation; do not implement, invoke, or document them unless the user opens a separate maintenance task for those legacy placeholders.

## Skill Selection Across Research Stages

`docs/SKILL_USAGE.md` is the authoritative inventory and stage mapping for repository-level Skills. Repository Skills that Codex may discover belong under `.agents/skills/<skill-name>/`; do not treat a Skill stored elsewhere as active. Select Skills from the concrete task and their descriptions, not merely from the current phase. A user may invoke a Skill explicitly; otherwise use implicit selection only when the task matches. Do not load or run every Skill at a phase transition.

Stage one may use input-reading, PDF, OCR, spreadsheet, or paper-knowledge Skills only for real source material and an agreed research need. Stage two may use them for approved preparation or analysis, but they never replace standalone experiment scripts, immutable run evidence, or registry updates. Stage three may reuse verified paper Skills for source navigation; DOCX, PPTX, XLSX, generated PDF, new paper Skills, and other format-specific outputs remain opt-in deliverables unless the user explicitly requests them.

Before using a Skill that uploads data, incurs cost, needs credentials, installs dependencies, persists source documents, or modifies `.agents/`, satisfy the applicable data-transfer, budget, dependency, license, and authorization gates. Check secret variables only for presence and never read or report their values. Repository safety and evidence rules override conflicting Skill advice, including instructions to display complete extracted content. Record material Skill choices and approvals in `RESEARCH.md`, generate actionable setup in the applicable stage TODO file, and record non-secret tool/version provenance when a Skill participates in an experiment. The legacy `.agents/skill-creator/` copy is not active; use the current environment's `skill-creator` for an explicitly authorized Skill-maintenance task.

## Stage Gates

`docs/WORKFLOW_GATES.md` is the authoritative protocol for entering, completing, pausing, resuming, and rolling back the three research phases; `docs/PHASE_ONE_PROTOCOL.md` is authoritative for phase-one substates, confirmation, and session recovery. Read both as applicable before beginning research or changing status. Do not perform substantive work in a later phase until stage one reaches `GATE_CHECK` and its entry gate passes. At every transition, update the current phase, phase-one substate, status, gate result, pause reason, resume condition, user confirmations, scope changes, privacy decisions, and other durable decisions in `RESEARCH.md`; update task details only in the applicable stage TODO file.

Treat missing authority, unresolved data licensing or privacy, unapproved external data transfer, missing required access, and material scope changes as pause conditions. Data not explicitly approved for external transfer must remain local. Minimize any approved transfer, redact personal or restricted content as agreed, and inspect both inputs and external-service outputs before persisting or publishing them. A negative result or an unmet target does not by itself prevent phase completion when the agreed evaluation is complete and the evidence is intact. When a writing claim lacks evidence, roll back to experiments; when the research question, data, metric, budget, or scope changes materially, roll back to research and design. Never erase or rewrite historical run evidence during a rollback.

## Experiment Resources

Experiments may use a local GPU, an external model API, or both in the same run. External model APIs currently target OpenAI-compatible interfaces. During experiment design, define the separate role of each resource and their data flow, record the intended use in `RESEARCH.md` and the actionable preparation in `experiments/TODO.md`, and confirm the GPU-time and external-API budgets with the user before execution. Do not impose a fixed API/GPU split when the research question calls for a different design. Every experiment script must include a top-level docstring declaring its experiment ID and purpose, API and GPU usage and roles, their data flow, applicable budgets, inputs, outputs, and run command; follow `experiments/scripts/README.md` for the exact template.

Before launching a run, check the required resources independently. For GPU work, verify the selected device and record the GPU model, CUDA version, PyTorch version, available or relevant VRAM, and the local model or checkpoint version. For API work, verify only that the required configuration is available; do not read or reveal secret values from `.env`. Experiment code may consume a user-provided credential from the process environment at runtime, but it must never print, serialize, snapshot, or embed the credential in source code, commands, configuration files, metadata, logs, issues, or commits. Record the external API protocol and model name, but never the API key.

Persist the actual API and GPU roles, versions, resource usage, and failures in the immutable run record. Never silently switch an API provider, external model, local model, checkpoint, device, or resource type after a failure; follow a fallback only when it was agreed in advance, otherwise preserve the failure evidence and stop or create a separately identified run after the plan is revised. Paper results must identify the supporting experiment IDs and disclose which external and local models produced or evaluated the reported results.

Before any resource-dependent work begins, complete this preflight in order: verify that the research question and success criteria are defined; confirm the API/GPU roles and data flow; identify the external API model and each local model or checkpoint; confirm the API-call, API-cost, and GPU-time limits; select an unused run ID and output path; then let the experiment process check GPU availability and report required API variables only as configured or missing, never by value. Create the immutable run record before executing the experiment so a failed preflight or partial run can still be preserved.

Apply explicit failure behavior. Stop a GPU-dependent run and record failure when the GPU is unavailable or out of memory; never substitute an API model. When an API credential is missing, tell the user to configure it locally without asking them to paste it. Retry API failures only up to the predeclared limit, stop new requests when the call or cost budget is reached, and never silently switch providers or models. Any run that completes only part of its declared data flow remains failed and must not support a paper claim. Follow `experiments/runs/README.md` for the required resource metadata and metrics.

## Build, Test, and Development Commands

Use Python 3.10+ and `uv`:

```bash
uv sync                         # create/update the project environment
uv run python scripts/<tool>.py --help
uv run python scripts/validate_workspace.py
python3 -m unittest discover -s tests -v
uv run python experiments/scripts/exp-001-baseline.py --seed 1337 --output-dir experiments/runs/<run-id>
```

The repository uses the Python standard-library `unittest` suite for validator regression coverage and has no configured formatter. Validate changed Python files with a focused executable command and extend tests alongside reusable validator behavior.

## Coding Style & Naming Conventions

Target Python 3.10+, use four-space indentation, type hints for public functions, and clear docstrings for reusable modules. Use `snake_case` for modules, functions, variables, and CLI options. Name experiment scripts `exp-<nnn>-<short-description>.py` and run directories `run-<timestamp>-<short-description>/`. Avoid hard-coded machine paths, credentials, and hidden configuration.

## Experiment and Paper Evidence

Persist every actual run's command, configuration snapshot, metadata, log, and metrics. Never overwrite an existing run directory or retroactively edit metrics. Generate data plots with Seaborn and keep the corresponding Python script. Numerical claims in the paper must identify the supporting experiment ID; mark unverified content as `TODO`.

## Commit & Pull Request Guidelines

**所有提交信息必须使用中文书写。** 格式遵循 conventional commit 规范，例如 `fix(analysis): 修复 best_bpb 定义` 或 `feat(experiments): 添加 baseline runner`。保持提交聚焦。Pull request 应说明研究或工程变更，列出验证命令，链接相关 issue，并附上结果证据或可视化截图。

## Security

Keep `.env` untracked. Never print API keys, tokens, passwords, or complete environment dumps in code, logs, issues, or commits.
