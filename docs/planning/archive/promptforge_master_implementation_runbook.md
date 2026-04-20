# PromptForge Master Implementation Runbook

## Purpose

This is the single ordered implementation runbook for standing up the PromptForge MVP from zero to a working end-to-end system.

It ties together:

- Linux server preparation
- Docker and Compose installation
- directory and vault layout
- schema and seed data loading
- starter pack placement
- Postgres and n8n startup
- Obsidian setup on Windows
- voice note template setup
- watcher and services startup
- llama.cpp endpoint integration
- end-to-end smoke testing
- first operational verification

This is the document to follow when actually building the first working system.

---

## Target MVP architecture

### Windows side
- Obsidian desktop
- voice capture/transcription plugin
- access to Linux-hosted PromptForge vault

### Linux side
- Debian 12
- Docker Engine
- Docker Compose plugin
- Postgres container
- n8n container
- PromptForge watcher container or local process
- PromptForge services container or local process
- shared vault directory
- optional Samba share
- llama.cpp endpoint either local or LAN-accessible

---

## Artifact set used by this runbook

Use these artifacts together:

- `promptforge_postgres_schema.sql`
- `promptforge_seed_data.sql`
- `promptforge_docker_compose_mvp.yml`
- `promptforge_python_watcher_and_services_spec.md`
- `promptforge_structured_output_contracts.md`
- `promptforge_canonical_prompt_template_pack.md`
- `promptforge_installation_guide.md`
- `promptforge_seeded_example_intake_notes.md`
- `promptforge_starter_pack.zip`

---

## Phase 1: prepare the Linux host

## Step 1. Update and baseline package install

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y   ca-certificates   curl   git   unzip   jq   nano   vim   python3   python3-venv   python3-pip   rsync   smbclient   cifs-utils
```

### Verify
```bash
python3 --version
git --version
```

---

## Step 2. Install Docker and Compose

```bash
sudo apt remove -y docker docker-engine docker.io containerd runc || true
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

```bash
echo   "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian   $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |   sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
```

### Verify
```bash
docker --version
docker compose version
sudo docker run --rm hello-world
```

---

## Step 3. Create PromptForge service account and project root

```bash
sudo useradd -m -s /bin/bash promptforge || true
sudo usermod -aG docker promptforge
sudo mkdir -p /srv/promptforge
sudo chown -R promptforge:promptforge /srv/promptforge
```

Switch to the service user for the rest of the setup when practical.

---

## Phase 2: create the filesystem layout

## Step 4. Create folders

```bash
mkdir -p /srv/promptforge/{db/init,promptforge_watcher,promptforge_services}
mkdir -p /srv/promptforge/vault/Inbox/Voice
mkdir -p /srv/promptforge/vault/Processing/Voice
mkdir -p /srv/promptforge/vault/Processing/Error
mkdir -p /srv/promptforge/vault/Processed/Voice
mkdir -p /srv/promptforge/vault/Projects
```

### Verify
```bash
find /srv/promptforge -maxdepth 3 -type d | sort
```

Expected important paths:
- `/srv/promptforge/db/init`
- `/srv/promptforge/vault/Inbox/Voice`
- `/srv/promptforge/vault/Processed/Voice`

---

## Phase 3: place core artifacts

## Step 5. Place SQL and compose artifacts

Copy:
- `promptforge_docker_compose_mvp.yml` to `/srv/promptforge/docker-compose.yml`
- `promptforge_postgres_schema.sql` to `/srv/promptforge/db/init/001_schema.sql`
- `promptforge_seed_data.sql` to `/srv/promptforge/db/init/002_seed.sql`

### Verify
```bash
ls -lah /srv/promptforge
ls -lah /srv/promptforge/db/init
```

---

## Step 6. Place starter pack

Unzip `promptforge_starter_pack.zip` into `/srv/promptforge/`

Expected results:
- `/srv/promptforge/pyproject.toml`
- `/srv/promptforge/.env.example`
- `/srv/promptforge/promptforge_watcher/`
- `/srv/promptforge/promptforge_services/`

Example:
```bash
cd /srv/promptforge
unzip /path/to/promptforge_starter_pack.zip
```

### Verify
```bash
find /srv/promptforge/promptforge_watcher -maxdepth 2 -type f | sort
find /srv/promptforge/promptforge_services -maxdepth 2 -type f | sort
```

---

## Step 7. Create `.env`

Create `/srv/promptforge/.env`

Example:
```env
POSTGRES_PASSWORD=change_this_now
N8N_HOST=promptforge.local
N8N_PROTOCOL=http
WEBHOOK_URL=http://promptforge.local:5678/
PROMPTFORGE_DEFAULT_MODEL=llama3.1-local
PROMPTFORGE_LLAMA_BASE_URL=http://192.168.1.50:8080
```

For a first LAN-only build, using the server IP is fine.

---

## Phase 4: bring up the server-side stack

## Step 8. Start Docker Compose stack

From `/srv/promptforge`:

```bash
docker compose up -d
```

### Verify
```bash
docker compose ps
```

Expected services:
- postgres
- n8n
- promptforge-watcher
- promptforge-services

---

## Step 9. Check logs and health

```bash
docker compose logs --tail=100 postgres
docker compose logs --tail=100 n8n
docker compose logs --tail=100 promptforge-watcher
docker compose logs --tail=100 promptforge-services
```

Expected:
- Postgres healthy
- n8n healthy
- watcher starts without crashing
- services API starts without crashing

---

## Step 10. Verify schema and seed load

Open Postgres shell:

```bash
docker exec -it promptforge-postgres psql -U promptforge -d promptforge
```

Run:

```sql
\dt
SELECT slug, name FROM projects ORDER BY slug;
SELECT name, prompt_type FROM prompt_templates ORDER BY name;
SELECT name, target_identifier FROM delivery_targets ORDER BY name;
SELECT source_term, canonical_term FROM term_dictionary ORDER BY source_term LIMIT 20;
```

Expected:
- `inbox`
- `the-tax-machine`
- `promptforge`
- several prompt templates
- several delivery targets
- seeded canonical term mappings

---

## Phase 5: configure Windows + Obsidian

## Step 11. Share the vault from Linux

Install Samba if needed:

```bash
sudo apt install -y samba
```

Add to `/etc/samba/smb.conf`:

```ini
[PromptForgeVault]
   path = /srv/promptforge/vault
   browseable = yes
   read only = no
   guest ok = no
   valid users = promptforge
   force user = promptforge
   create mask = 0664
   directory mask = 0775
```

Set Samba password:

```bash
sudo smbpasswd -a promptforge
sudo systemctl restart smbd
```

### Verify from Linux
```bash
testparm -s
```

---

## Step 12. Connect to the vault from Windows

From Windows File Explorer:
- connect to `\\<linux-server-ip>\PromptForgeVault`
- map it to a drive letter such as `O:`

### Verify
- you can browse `Inbox/Voice`
- you can create and delete a test text file

---

## Step 13. Install and configure Obsidian

On Windows:
- install Obsidian
- open the vault from the mapped drive
- confirm the folder structure is visible

Create or configure:
- note template for `Inbox/Voice`
- automatic template insertion for new notes in that folder
- speech-to-text plugin that writes into the note

### Minimum note template

```md
---
pf_version: 1
capture_type: voice
status: new
created_by: obsidian
project: inbox
destination: queue_only
prompt_type: general
target_type: none
target_identifier: ""
mode: queue
priority: normal
requires_review: false
template_profile: default
source_device: windows-main
watch_eligible: true
imported_at: null
utterance_id: null
prompt_generation_id: null
delivery_status: not_started
tags_generated: []
---

## Control

## Transcript
```

---

## Phase 6: verify Python services locally

## Step 14. Optional local Python startup for development

If you want to run watcher/services locally instead of only in containers during development:

```bash
cd /srv/promptforge
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

Start services:
```bash
uvicorn promptforge_services.api:app --host 0.0.0.0 --port 8090 --reload
```

Start watcher:
```bash
python -m promptforge_watcher
```

This is useful for early implementation and debugging.

---

## Phase 7: connect llama.cpp

## Step 15. Confirm llama.cpp endpoint reachability

Wherever llama.cpp is running, verify from the Linux server or from inside the services container that it is reachable.

Example container-side check:
```bash
docker exec -it promptforge-services python - <<'PY'
import os, httpx
url = os.getenv("PROMPTFORGE_LLAMA_BASE_URL", "http://host.docker.internal:8080")
print("Checking", url)
try:
    r = httpx.get(url, timeout=5.0)
    print(r.status_code)
    print(r.text[:200])
except Exception as e:
    print("ERROR:", e)
PY
```

If this fails, fix network routing before continuing.

---

## Phase 8: load a real test note

## Step 16. Create a seeded test note

Use the example from `promptforge_seeded_example_intake_notes.md`.

Suggested first test:

```md
---
pf_version: 1
capture_type: voice
status: new
created_by: obsidian
project: inbox
destination: queue_only
prompt_type: general
target_type: none
target_identifier: ""
mode: queue
priority: normal
requires_review: false
template_profile: default
source_device: windows-main
watch_eligible: true
imported_at: null
utterance_id: null
prompt_generation_id: null
delivery_status: not_started
tags_generated: []
---

## Control
project is thtaxmachine
prompt type is codingcli
destination is cli
target is claude-tax-main

## Transcript
um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan
```

Save this under:
- `Inbox/Voice/2026-04-14 retry-state-plan.md`

---

## Step 17. Watch watcher logs

```bash
docker compose logs -f promptforge-watcher
```

Expected eventual behavior once implemented:
- file detected
- note parsed
- intake note created
- utterance created
- raw transcript revision created
- webhook sent to n8n

---

## Step 18. Verify database rows

Run:

```sql
SELECT status, note_relative_path FROM intake_notes ORDER BY created_at DESC LIMIT 10;
SELECT id, raw_text FROM utterances ORDER BY created_at DESC LIMIT 10;
SELECT revision_kind, producer_name FROM transcript_revisions ORDER BY created_at DESC LIMIT 20;
```

Expected:
- imported note row
- utterance row
- at least raw revision row

---

## Phase 9: create and verify n8n workflow

## Step 19. Build the intake orchestration workflow in n8n

Following the workflow outline artifact, create:

### Workflow A
- webhook trigger
- create processing run
- load context
- call preprocess service
- call transform step / llama.cpp
- call validate service
- call render service
- create delivery row
- finalize note state

### Workflow B
- queue processor for `deliveries.status = queued`

### Workflow C
- review/error scan

### Verify
- webhook receives payload
- workflow executes without node-level errors
- DB state transitions occur as expected

---

## Step 20. Verify services endpoints

From Linux:

```bash
curl http://localhost:8090/health
```

Expected:
```json
{"ok": true}
```

Test preprocess stub:
```bash
curl -X POST http://localhost:8090/preprocess   -H 'Content-Type: application/json'   -d '{"utterance_id":"test"}'
```

Expected:
- JSON response from stub endpoint

---

## Phase 10: operational smoke test

## Step 21. Full-path smoke test checklist

A full successful smoke test should confirm all of the following:

- a note can be created from Windows in `Inbox/Voice`
- the note template is inserted automatically
- watcher sees the note
- watcher imports canonical DB rows
- n8n workflow triggers
- preprocess service runs
- llama.cpp endpoint is reachable
- validation succeeds
- render succeeds
- delivery row is created
- note can be moved or marked processed
- final DB state is queryable

---

## Step 22. Verification queries

### Latest intake notes
```sql
SELECT
  created_at,
  status,
  note_relative_path
FROM intake_notes
ORDER BY created_at DESC
LIMIT 20;
```

### Latest utterances
```sql
SELECT
  created_at,
  raw_text
FROM utterances
ORDER BY created_at DESC
LIMIT 20;
```

### Latest prompt generations
```sql
SELECT
  created_at,
  prompt_type,
  status,
  requires_review
FROM prompt_generations
ORDER BY created_at DESC
LIMIT 20;
```

### Latest deliveries
```sql
SELECT
  created_at,
  destination,
  target_identifier,
  mode,
  status,
  error_text
FROM deliveries
ORDER BY created_at DESC
LIMIT 20;
```

---

## Phase 11: first implementation priorities after install

Once the stack is installed, implement in this order:

1. note parser
2. importer DB writes
3. directive parser
4. canonicalization layer
5. preprocess endpoint
6. validation contracts
7. renderer
8. n8n integration
9. delivery adapter logic
10. Obsidian write-back

This gives you a working backbone fastest.

---

## Phase 12: common failure points

## Problem: note appears in Obsidian but watcher ignores it
Check:
- file is really under `Inbox/Voice`
- `watch_eligible: true`
- `status: new`
- file extension is `.md`
- watcher path matches real vault path

## Problem: watcher imports note but n8n never runs
Check:
- watcher webhook URL
- n8n webhook node path
- container networking
- n8n logs

## Problem: prompt renders but delivery fails
Check:
- delivery target config
- adapter implementation
- target session availability

## Problem: project resolution is wrong
Check:
- term dictionary entries
- fuzzy threshold
- project aliases
- ruleset precedence

## Problem: llama.cpp unreachable
Check:
- service base URL
- LAN routing
- firewall rules
- whether the endpoint is exposed on the right interface

---

## Final implementation rule

Do not treat “containers are up” as success.

Success means:
- note created
- note imported
- canonical rows written
- workflow triggered
- prompt rendered
- delivery queued or routed to review
- state trace remains understandable end to end

That is the actual MVP definition of done.
