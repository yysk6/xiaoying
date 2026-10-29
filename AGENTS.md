# Project instructions

- This directory is the project root for the content-task-planning assessment (question 2).
- The current requirements and contracts are in root docs/ and contracts/. The existing content-planner-spec/ directory is an unchanged historical snapshot, not the maintenance source.
- Follow spec-driven development and test-driven development. Change the specification and acceptance expectations before changing business behavior. Keep actual evaluation results separate from planned results.
- Use karpathy-guidelines: make assumptions explicit, implement the simplest sufficient change, keep edits scoped, and define verifiable success criteria.
- Develop and accept one stage at a time according to docs/08-development-plan.md. Stop after the current stage's review package and wait for explicit user acceptance before starting the next stage, unless the user explicitly authorizes multiple stages. Do not implement future stages during a planning-only turn.
- Use Python, LangGraph, Pydantic, SQLite, HTTPX and pytest as specified. Validate and lock candidate dependency versions before implementation.
- Use publicly available third-party packages, Python standard libraries, Git and ordinary CLI tools. Do not use Codex-internal plugins, MCP services, account credentials, workspace runtimes or Codex-specific commands as development or runtime dependencies.
- The application must run without Codex or any particular AI editor. Use portable paths and packaged data; never hard-code developer or Codex directories. Document PowerShell and POSIX setup commands.
- The selected real model is deepseek-v4-pro via the official DeepSeek HTTP API. Read credentials only from environment variables. Never put secrets in source, specs, fixtures, traces, logs or commits.
- Keep offline tests network-free. Validate portability in a clean environment; mark untested platforms and live scenarios honestly as NOT_RUN.
- Do not start paid API calls merely to update specs. Actual model validation belongs to the documented implementation/evaluation stage.
