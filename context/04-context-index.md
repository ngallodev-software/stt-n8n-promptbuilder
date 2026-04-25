# Context Index

## Read Order
1. [05-refs-existing-behavior.md](./05-refs-existing-behavior.md)
2. [06-kit-recursive-voice-routing.md](./06-kit-recursive-voice-routing.md)
3. [02-ticket-index.md](./02-ticket-index.md)
4. [07-validation.md](./07-validation.md)
5. [10-detailed-tickets.md](./10-detailed-tickets.md)

## Existing Behaviors to Preserve
- recursive watcher intake below `Inbox/Voice`
- note parsing from Obsidian markdown
- n8n webhook delivery
- prompt generation import/render pipeline
- Kanban import and queue fallback already proven in the harness

## Key Surfaces
- `promptforge_watcher/watcher.py`
- `promptforge_watcher/config.py`
- `promptforge_services/console_api.py`
- `promptforge_services/kanban_client.py`
- `promptforge_console/src/pages/Settings.tsx`
- `promptforge_console/src/pages/Intake.tsx`
- `promptforge_console/src/pages/IntakeDetail.tsx`
