# AI Coding Assistant Integration

This repository supports collaborative development with multiple AI coding assistants, such as Claude Code and GitHub Copilot. This document explains how to integrate them into the project and **which level should hold new AI collaboration conventions**.

## Core Principle: Three-Level Promotion

When adding any convention intended for AI assistants, start **from the lowest level and move upward** only when necessary:

| Level | Location | Committed? | Use case |
|---|---|:---:|---|
| **① Personal** | `CLAUDE.local.md` (and each tool's local files) | ❌ gitignored | Personal preferences and experimental conventions. **Try them here first.** |
| **② Project** | Tool-specific project files, such as `.claude/CLAUDE.md` and `.github/copilot-instructions.md`, or documents in `docs/develop/` | ✅ Committed | Team-shared content that is **specific to one tool**. |
| **③ Single source of truth** | Root-level `AGENTS.md` | ✅ Committed | Project knowledge that **applies across tools**, including architecture, hard constraints, and workflows. |

**Promotion path**: ① Personal → (proven useful to the team) → ② Project → (proven applicable across tools) → ③ `AGENTS.md`.

- **Tool-specific** content, such as Claude-specific uv / context7 rules, **does not belong in `AGENTS.md`**. Keep it in that tool's project-level file.
- Promote content to `AGENTS.md` only when every tool should know it.

## AGENTS.md: The Single Source of Truth

The root-level [AGENTS.md](../../../AGENTS.md) is the single source of truth across tools for project architecture, hard development constraints, and the commit workflow. See [spec/agent_guidelines.md](../spec/agent_guidelines.md) for detailed coding standards.

> Updating these two files effectively updates the behavior of every integrated tool, provided the content truly **applies across tools**. Otherwise, keep it one level lower in the hierarchy above.

## Tool Integration

> **Principle**: Prefer placing instruction entry files in each tool's own **configuration directory**, such as `.claude/` or `.github/`, rather than cluttering the project root. Ideally, the tool can read `AGENTS.md` directly, making an entry file unnecessary.

### Claude Code (Use `@` References, Not Hard Links)

- The repository includes a committed `.claude/CLAUDE.md` that **imports** `AGENTS.md` through `@../AGENTS.md`. Claude Code loads it automatically at startup; no configuration is needed.
- Write **Claude-specific** project rules **below** the `@` import in `.claude/CLAUDE.md` (committed and shared with the team). Examples include requiring `uv`, using context7, and running Bash commands in the background.
- Put **personal** preferences in the root-level `CLAUDE.local.md` (gitignored), which loads after `CLAUDE.md`.

### GitHub Copilot

- The repository includes a committed `.github/copilot-instructions.md` with the frontmatter `applyTo: '**'`, applying to all files. It is automatically injected into each session and refers to `AGENTS.md` for the full context.

### Other Tools (Without Native Import Support)

If a tool cannot read `AGENTS.md`, has no import syntax such as `@`, and only reads its own fixed entry file, use a **hard link** to mirror `AGENTS.md` through that file. Follow the same placement principle: prefer the tool's configuration directory, then the project root.

Example (the filename depends on the tool; `CLAUDE.md` is only a placeholder to illustrate the command):

```powershell
New-Item -ItemType HardLink -Path "CLAUDE.md" -Target "AGENTS.md"
```

- The entry file should be excluded by `.gitignore` and remain local (personal level).
- Maintain tool-specific project content in a separate **committed** file, not in `AGENTS.md`.
- If the tool later supports imports, prefer imports and stop using hard links. (Unix: `ln AGENTS.md CLAUDE.md`.)

## Where Content Belongs (Quick Reference)

| Content | Location |
|---|---|
| Personal preferences / experiments | ① Personal: `CLAUDE.local.md` |
| Team-shared but tool-specific content | ② Project: the tool's file, such as `.claude/CLAUDE.md` |
| Content shared across all tools | ③ `AGENTS.md` |

## MCP

- **Recommended**: [context7](https://github.com/upstash/context7) — look up library documentation. It is already enabled in this project's `.claude/settings.json` for Claude Code.
- **Project MCP server (observation and action tools implemented)**: Exposes game observation and control to agents through MCP, including window status, screenshots, OCR, entering the game, and querying or stopping runs, to support development and debugging. It uses the streamable-http transport (endpoint `/mcp`, default port 23001). Start the server with `uv run --env-file .env python -m zzz_od.backend.entry.server`, then run `claude mcp add --transport http zzz_od http://127.0.0.1:23001/mcp`. **See [zzz/backend/mcp.md](../zzz/backend/mcp.md) for the tool list**; it is not duplicated here to avoid becoming outdated as the implementation evolves. See [zzz/backend/](../zzz/backend/) for the overall design and [harness/README.md](../harness/README.md) for the roadmap.
- **Browser (chrome-devtools-mcp)**: Lets agents drive a local browser through CDP to read and interact with pages that WebSearch cannot find or retrieve, such as Miyoushe guides and event pages that require login. Use connect mode with Edge running in debugging mode. See [chrome-devtools-mcp.md](chrome-devtools-mcp.md) for installation and session pitfalls.

## Test Repository

Test code lives in the separate `zzz-od-test/` repository (excluded by `.gitignore`; clone it into the project root), not in the main repository. Claude Code's Grep/Glob respect `.gitignore` by default and **do not automatically search** `zzz-od-test/`. When locating or editing tests, explicitly specify the `zzz-od-test/` path with `Read`/`grep`. See [quickstart §②](quickstart.md#②-跑测试可选) for cloning instructions and [spec/agent_guidelines.md](../spec/agent_guidelines.md#测试代码规范) for test standards.

## LSP

The project uses **pyright launched through uv** as its LSP for code navigation (definitions, references, and symbols), rather than Claude Code's official global pyright integration. The global integration uses the system PATH, cannot resolve dependencies in the project's `.venv`, and conflicts with the uv environment. pyright is in the dev dependency group, with team-shared configuration under `[tool.pyright]`. See [claude-code/pyright-lsp.md](claude-code/pyright-lsp.md) for Claude Code plugin installation.

## Skills

A skill is a callable capability in Claude Code and a few other tools, such as Codex. The key point is that **each tool reads skills only from its own directory**: Claude Code reads `.claude/skills/`, **not the root-level `skills/` directory**. Skills also have no import mechanism such as `@import` to load content from elsewhere.

### Recommended: Install superpowers

**The project has standardized on [superpowers](https://github.com/anthropics/superpowers)** by team agreement. It provides a complete **development workflow methodology**, covering requirements exploration (`brainstorming`), planning (`writing-plans`), TDD implementation (`test-driven-development`), debugging (`systematic-debugging`), code review, and branch completion and merging (`finishing-a-development-branch`). Development in this project follows that workflow.

The project's development skills (`zzz-od-dev-*`) are **project-specific additions** on top of superpowers, not replacements. They cover topics such as adapting PR completion to CodeRabbit, mandatory skill-writing rules, and the fix decision framework. Users need superpowers installed as well. In Claude Code, search for `superpowers` in the plugin marketplace or run `/plugin install superpowers`.

### Recommended: Install mcp-server-dev (When Writing MCP Tools)

When writing backend MCP tools for this project (`src/zzz_od/backend/mcp/`), **follow Anthropic's official `mcp-server-dev` plugin for general MCP tool design methodology**. It is available in the `claude-plugins-official` marketplace and focuses exclusively on MCP development, with three skills and no unrelated extras. In particular, use `build-mcp-server/references/tool-design.md` for writing good tools: description contracts, tight schemas, annotations, structured returns, actionable errors, separation of reads and writes, and token efficiency. The project's [mcp-implementation.md](../zzz/backend/mcp-implementation.md) adds only **project-specific guidance**, such as which hints to assign to each tool, MCP/HTTP symmetry, screen_info CRUD, and sleeping after actions, without repeating general knowledge.

Claude Code installation from the `claude-plugins-official` marketplace takes two steps:

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install mcp-server-dev@claude-plugins-official   # 3 MCP skills (build-mcp-server/app/mcpb), focused exclusively on MCP
```

### Skill Categories and Naming

Skills fall into two categories. Use the `zzz-od-` project prefix for new skills, with an additional `dev-` prefix for development skills:

| Category | Prefix | Purpose |
|---|---|---|
| **Development** | `zzz-od-dev-` | Guide AI assistants in project development, configuration, and builds (superpowers-style) |
| **Legacy** | No prefix | Early skills temporarily retain their original names; the value of migrating them is still to be evaluated |

> See the [`skills/` directory](../../../skills/) for the current skill list. Each SKILL.md includes a trigger description in its frontmatter. The list is not duplicated here to avoid becoming outdated as skills are added or removed.
>
> `zzz-od-` also serves as the **project namespace**, preventing collisions with plugin and personal skills and grouping project skills together in the `/` command list. Naming examples: `zzz-od-dev-character` (adding a character), `zzz-od-dev-build` (build configuration), and `zzz-od-player` (installation and usage). If a third category is needed later, such as debugging, add the corresponding segment, for example `zzz-od-debug-*`.

### Skill Development: Three-Level Promotion

As with the overall three-level promotion model, start new skills at the lowest level:

| Level | Location | Committed? | Description |
|---|---|:---:|---|
| **① Personal** | `.claude/skills/<name>/` (`.claude/*` is already gitignored, so these are uncommitted by default) or `~/.claude/skills/` | ❌ | Experiment here first and promote the skill after proving it useful. |
| **② Tool-specific project level** | `.claude/skills/<name>/` (**committed** by allowing `.claude/skills/` in `.gitignore`) | ✅ | Shared with the team and specific to Claude Code. |
| **③ Project level (cross-tool source)** | Root-level `skills/<name>/` (**committed**) | ✅ | The single source of truth when multiple skill-aware tools need the skill. |

**Promotion path**: ① Personal experiment → (proven useful) → ② Commit to `.claude/skills/` → (needed by multiple tools) → ③ Use the root-level `skills/` as the cross-tool source.

> ⚠️ Tools do not automatically discover the root-level `skills/` directory. It only serves as the single source of truth at level ③. Use **directory junctions** (`mklink /J`, at the directory level) to link it into each tool's directory, such as `.claude/skills/`. Windows junctions do not require administrator privileges; symlinks require elevated privileges or Developer Mode. If Claude Code is the only consumer, stop at level ②; level ③ is unnecessary.

### Current Setup

The root-level [`skills/`](../../../skills/) directory is the single source of truth for skills (③). Development skills (`zzz-od-dev-*`, superpowers-style) are automatically loaded by Claude Code through junctions (`.claude/skills/<name>` → root-level `skills/<name>`). **See the directory itself for the current skill list**; each SKILL.md includes a trigger description in its frontmatter. The list is not duplicated here to avoid becoming outdated as skills are added or removed.

Use the `zzz-od-` prefix for new skills, following the naming rules above.

## Attribution for AI-Assisted Commits (Recommended)

When collaborating with AI coding tools, **use a `Co-Authored-By` trailer in commit messages to acknowledge AI participation**. This is recommended for transparency and traceability: the commit history shows which changes involved AI assistance, and GitHub recognizes the format and displays the co-author on the commit.

```
Co-Authored-By: <name> <email>
```

There are two approaches, progressing from relying on the model to full automation:

### Approach 1: Add Guidance to the Instruction File

Add a rule to the AI tool's instruction file asking it to append the trailer itself, for example: "When committing, append `Co-Authored-By: <tool> (<model>) <email>` to the end of the message."

- ✅ No configuration required; works across tools.
- ❌ **Relies on the model remembering**: it may forget or omit the trailer, or write the wrong model name.

### Approach 2: Inject Automatically with a Git Hook (Recommended)

Use Git's `prepare-commit-msg` hook to append the trailer automatically on every commit, without relying on the model's memory. Git invokes it for every commit, including commands chained with `&&`, `git -C <dir>`, and `--amend`. There are two variants:

- **2a. Hard-code the content in the hook (static)**: Use a fixed trailer. This is the simplest and most reliable option, but it does not reflect the actual model used.
- **2b. Combine a Git hook with an AI tool hook that writes the model name (dynamic)**: The Git hook injects the trailer, while the AI tool's own hook writes the **current model name** to an intermediary file before each `git commit`. The Git hook reads that file, so the trailer reflects the actual model and updates when the model changes. Disable the tool's default co-author instruction to avoid duplicates.

The implementation differs by tool. See [Claude Code: Automatically Inject Commit Trailers](claude-code/commit-trailer.md) for the Claude Code approach; use the equivalent hook mechanism for other tools.

> Note: Some tool or model vendors do not have an official GitHub bot email address. In that case, the email on the model's attribution line is only a placeholder and does not produce a GitHub avatar or contributor entry. Use the vendor's **official website domain**, such as `noreply@<official-domain>`, as the placeholder.

## Related Documentation

- [AGENTS.md](../../../AGENTS.md) — unified entry point for AI coding collaboration
- [spec/agent_guidelines.md](../spec/agent_guidelines.md) — detailed coding standards
- [Development Guide](../README.md)
- [AI Coding Harness Engineering](../harness/README.md)
