# Prompt Forge Operating Policy

This is the canonical operating policy for this repo.

## Default rule

Do not start coding from a blank slate.

For any non-trivial change:
1. Find the relevant requirements or planning doc first.
2. Use `codebase-memory-mcp` first for code discovery.
3. Use the smallest relevant Cavekit context next.
4. Use `claude-flow` only when the task needs orchestration, parallel agents, or active task memory.
5. Implement the smallest change that satisfies the spec.
6. Validate, then backpropagate fixes into specs/plans when behavior changed.

## Tool order

### 1. Code discovery
Use `codebase-memory-mcp` first when the task touches code.

Use:
- `search_graph` to find exact functions, classes, routes, and modules
- `trace_path` to answer callers, callees, and impact questions
- `get_code_snippet` to read the exact implementation
- `get_architecture` for the high-level shape of a repo
- `detect_changes` before large edits

Fallback to `grep` / `Read` only for:
- string literals
- config values
- non-code files
- cases where the graph does not cover the question

### 2. Requirements and workflow
Use Cavekit when the task is anything beyond a trivial one-off edit.

Use:
- `ck:cavekit-writing` for requirements and acceptance criteria
- `ck:brownfield-adoption` for existing codebases
- `ck:validation-first` for testable gates
- `ck:prompt-pipeline` for numbered workflow prompts
- `ck:impl-tracking` for progress, dead ends, and handoff continuity
- `ck:revision` when a bug reveals a missing requirement
- `ck:peer-review` for critical review before declaring done

### 3. Orchestration
Use `claude-flow` only when the work benefits from coordination beyond one agent:
- multi-file or multi-domain work
- parallel tasks with clear ownership
- long-running sessions that need task/session memory
- workflow automation, routing, or swarm-style execution

Do not use `claude-flow` just to avoid reading the repo. It is not a substitute for specs or code discovery.

## Cherry-pick rule

Only pull the context you need.

From `codebase-memory-mcp`, cherry-pick:
- exact symbol names
- call chains
- architecture summaries
- impact analysis

From Cavekit, cherry-pick:
- only the relevant kit sections
- acceptance criteria
- exclusions
- implementation tracking for the current task
- revision notes tied to the current defect or feature

From `claude-flow`, cherry-pick:
- active task state
- workflow status
- routing decisions
- progress summaries
- short-lived memory for the current work batch

Do not duplicate the same context in all three places unless there is a clear reason.

## When to use which tool

| Need | First choice | Second choice | Last resort |
|---|---|---|---|
| Find code structure or callers | `codebase-memory-mcp` | `grep` / `Read` | manual search |
| Understand repo behavior | `codebase-memory-mcp` | targeted file reads | broad file reads |
| Define what should change | Cavekit | code discovery | implementation guesswork |
| Plan a non-trivial task | Cavekit + repo docs | `claude-flow` for orchestration | ad hoc list |
| Track active work across sessions | `ck:impl-tracking` | `claude-flow` task/session memory | chat memory |
| Find a bug root cause | `codebase-memory-mcp` + Cavekit | `ck:revision` | code-only patching |
| Coordinate parallel work | `claude-flow` | Cavekit ownership rules | serial handoff |

## Repo workflow

### Small, isolated task
Use direct edits only if all of these are true:
- the task fits in one screen of context
- the change is in one file or tightly coupled files
- no spec update is needed

Even then, check the relevant file and use `codebase-memory-mcp` if the task touches code.

### Normal task
1. Read the relevant planning/spec doc in `docs/planning/`.
2. Use `codebase-memory-mcp` to map the code surface.
3. Pull only the relevant Cavekit context.
4. Implement.
5. Run the repo’s expected validation.
6. Update the matching spec or plan if behavior changed.

### Larger task
If the work crosses modules, services, schemas, or multiple files:
1. Split ownership explicitly.
2. Use `claude-flow` for coordination if parallel work helps.
3. Keep Cavekit as the source of truth for acceptance criteria.
4. Use `codebase-memory-mcp` to verify boundaries and impact before editing.

## Hard rules

- Do not guess architecture when the graph can answer it.
- Do not invent requirements that are not in Cavekit or repo docs.
- Do not add duplicated context across tools without a reason.
- Do not treat `claude-flow` memory as authoritative over specs or code.
- When code changes expose a spec gap, fix the spec as part of the same work.

## Repo references

- `AGENTS.md` is the repo guidance baseline.
- `docs/planning/` is the source of truth for specs and implementation notes.
- `codebase-memory-mcp` is the source of truth for code topology.
- Cavekit is the source of truth for requirements, validation, and revision.
