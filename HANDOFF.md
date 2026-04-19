 No vault name is required by app right now. Only vault path.

  Current expected config:

- PROMPTFORGE_VAULT_PATH: root of mounted Obsidian vault, default /vault
- PROMPTFORGE_WATCH_FOLDER: intake folder inside vault, default Inbox/Voice
- PROMPTFORGE_PROCESSED_FOLDER: success/writeback folder, default Processed/Voice
- PROMPTFORGE_ERROR_FOLDER: error folder, default Processing/Error

  Current code behavior:

- watcher builds watch_path = Path(cfg.vault_path) / cfg.watch_folder in promptforge_watcher/watcher.py:27
- then it does one rglob("*.md") scan and processes what it finds in promptforge_watcher/watcher.py:33
- then process exits
- so today it is not a live hook
- also not a long-running poll loop

  So current answer is:

- app expects a mounted vault path
- intake source is Inbox/Voice/
- but live pickup of new STT notes is not implemented yet

  Docs plan vs code:

- spec says MVP could use polling plus content hashing or filesystem watch plus stable delay before import in docs/planning/promptforge_python_watcher_and_services_spec.md:154
- safe flow is:
      1. file appears
      2. wait short stabilization interval
      3. read/hash/parse
      4. import once
- current code has stabilization_seconds config in promptforge_watcher/config.py:18 but does not yet run a real watch loop

- do filesystem events, not minute polling
- use watchdog/inotify on the vault path
- watch only Inbox/Voice/
- on create or modify, debounce per file for PROMPTFORGE_STABILIZATION_SECONDS
- ignore temp/hidden files
- hash content so rewrites do not double-import
- keep one startup scan for backlog recovery, then switch to event-driven mode

  So the real plan should be:

- startup catch-up scan
- then event-driven watcher
- Ops guardrail:
  - Do not stop, restart, or reconfigure containers from other apps/projects (for example `grounded-*`) without explicit user approval in same session.
  - For PromptForge port conflicts, change PromptForge host port mappings instead of touching other app containers.
