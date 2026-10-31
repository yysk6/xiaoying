# Project instructions

- This directory is the project root for the content-task-planning assessment (question 2).
- The current requirements and contracts are in root docs/ and contracts/. The existing content-planner-spec/ directory is an unchanged historical snapshot, not the maintenance source.
- Before starting or resuming work, read HANDOFF.md and the maintenance/validation section in docs/03-evaluation.md, then verify Git/worktree state rather than assuming the handoff snapshot is current.
- Follow spec-driven development and test-driven development. Change the specification and acceptance expectations before changing business behavior. Keep actual evaluation results separate from planned results.
- Use karpathy-guidelines: make assumptions explicit, implement the simplest sufficient change, keep edits scoped, and define verifiable success criteria.
- Apply the skill guidance below when its trigger is met. Public Markdown guides are development methods, not application/toolchain dependencies; usage and source versions are recorded in docs/04-ai-usage.md.
- Develop and accept one authorized stage at a time using the workflow below. Stop after the current review package and wait for explicit acceptance before a new stage, unless the user authorizes multiple stages. Do not implement future behavior during a planning-only turn.
- Update HANDOFF.md after each stage's implementation and self-validation, before delivering its review package. Update it again on user acceptance/revision requests, material blockers, or interruption handoff. Include actual scope, status vs user acceptance, decisions, test commands/results/evidence, baseline commit and known remote sync, open issues, next authorized step, and reproduction instructions. A stage handoff is incomplete until this file is updated. Never fabricate results or record secrets; preserve history through Git and stage reports.
- Use Python, LangGraph, Pydantic, SQLite, HTTPX and pytest as specified. Validate and lock candidate dependency versions before implementation.
- Use publicly available third-party packages, Python standard libraries, Git and ordinary CLI tools. Do not use Codex-internal plugins, MCP services, account credentials, workspace runtimes or Codex-specific commands as development or runtime dependencies.
- The application must run without Codex or any particular AI editor. Use portable paths and packaged data; never hard-code developer or Codex directories. Document PowerShell and POSIX setup commands.
- The selected real model is deepseek-v4-pro via the official DeepSeek HTTP API. The structured CLI reads credentials from environment variables; explicitly authorized interactive/evaluation entry points may read a hidden terminal prompt and inject credentials into process memory. Never put secrets in source, specs, fixtures, traces, logs or commits.
- Keep offline tests network-free. Validate portability in a clean environment; mark untested platforms and live scenarios honestly as NOT_RUN.
- Do not start paid API calls merely to update specs. Actual model validation belongs to the documented implementation/evaluation stage.

## Development workflow

- Keep docs recursively limited to 01-requirements.md through 05-retrospective.md. Put actual validation artifacts in examples/ and machine contracts in contracts/; use Git history for old prose, not new docs/stages or archive trees.
- Define behavior, public test seams and acceptance expectations before implementation. Use observed Red, minimum Green and scoped cleanup; missing imports are setup evidence, not proof of business rules.
- Replace external model/Clock boundaries in offline tests; use real temporary SQLite for transaction, uniqueness and recovery requirements. Honor the established public interfaces rather than mocking internal collaborators.
- Review the final changed scope, including working tree/staged/untracked files and an explicit baseline. Spec and Standards review are separate for business/evaluation behavior changes; pure prose maintenance uses diff and link checks.
- Run checks appropriate to the changed behavior. Finalize implementation/review before costly packaging or broad regression; do not repeat passing checks without new changes, failures or unresolved concerns. Consolidate evidence instead of creating a report per small step.
- A stage's self-validation is not user acceptance. An explicit next-stage/continuous authorization allows work but does not retrospectively mark prior stages accepted.
- Update root HANDOFF.md after implementation, material feedback or interruption, with scope, actual validation, baseline/remote facts and next authorized step. This overrides the generic handoff skill's temporary-directory default.
- Preserve original input/output/Trace/assessments and source hashes. Historical source verification must explicitly identify the Git commit; never make a changed working tree appear byte-identical to a frozen run.

## Skill guidance

| Trigger | Skill and adaptation |
|---|---|
| Writing/reviewing code | karpathy-guidelines: explicit assumptions, smallest sufficient change, verifiable outcome |
| Behavior or defect change | tdd plus tests.md/mocking.md: public seam, actual Red/Green; existing approved seams need no repeated confirmation |
| Business/evaluation review | code-review: two parallel reviewers for Spec and Standards, local five docs/contracts as spec; no issue-tracker setup required |
| Unexplained observed failure | diagnosing-bugs: reproducible feedback, distinguish hypotheses, preserve redacted evidence |
| Concrete module/interface problem | codebase-design: small interface, concentrated behavior, no speculative seams |
| Agent instructions/handoff | writing-for-agents and handoff: single authority, clear triggers, root HANDOFF and five-doc structure |

The Chinese guides' fixed public version and original installation checks are linked from docs/04-ai-usage.md and examples/tests/tooling/skills-installation.json. Reading/installing a guide alone is not evidence that it was applied. Repository-specific rules and user authorization take precedence.
