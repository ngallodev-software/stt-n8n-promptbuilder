# PromptForge Installation Guide

## Purpose

This guide covers the recommended installation flow for a developer or new user standing up the PromptForge MVP on a Debian-based Linux server with a Windows workstation running Obsidian.

This installation path assumes:

- **Linux host:** Debian 12 server
- **Primary user workstation:** Windows 11
- **Vault storage:** hosted on the Linux server
- **Core stack:** Docker Compose, Postgres, n8n, Python watcher/services, llama.cpp
- **Capture surface:** Obsidian on Windows, writing voice notes into the shared vault

This guide is intentionally practical and installation-focused.

## Final target architecture

The installed system should look like this:

1. **Windows workstation**
   - Obsidian desktop app
   - voice capture/transcription plugin
   - shared access to the vault hosted on Linux

2. **Linux server**
   - Docker Engine + Docker Compose plugin
   - Postgres container
   - n8n container
   - PromptForge watcher container
   - PromptForge services container
   - shared vault directory
   - optional llama.cpp service running either directly on Linux or on another LAN machine

## Recommended installation order

1. Linux base packages
2. Docker Engine + Compose plugin
3. PromptForge project directory structure
4. Shared vault directory
5. Postgres + n8n via Docker Compose
6. PromptForge watcher/services code
7. Schema + seed data load
8. Obsidian on Windows
9. Obsidian vault access to Linux-hosted vault
10. Voice note template setup
11. llama.cpp endpoint integration
12. End-to-end smoke test

## Part 1: Linux host preparation

### 1.1 Update the server

```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 Install baseline packages

```bash
sudo apt install -y   ca-certificates   curl   git   unzip   jq   nano   vim   python3   python3-venv   python3-pip   rsync   smbclient   cifs-utils
```

### 1.3 Create a service user

```bash
sudo useradd -m -s /bin/bash promptforge
```

Add this user to the docker group after Docker is installed.

## Part 2: Install Docker and Compose

### 2.1 Remove conflicting old packages

```bash
sudo apt remove -y docker docker-engine docker.io containerd runc || true
```

### 2.2 Add Docker repository

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

```bash
echo   "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian   $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |   sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### 2.3 Install Docker Engine and Compose plugin

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 2.4 Enable Docker

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker promptforge
```

### 2.5 Verify installation

```bash
docker --version
docker compose version
sudo docker run --rm hello-world
```

## Part 3: Create PromptForge directory structure

Recommended root:

```bash
sudo mkdir -p /srv/promptforge
sudo chown -R promptforge:promptforge /srv/promptforge
```

Create this layout:

```text
/srv/promptforge/
  docker-compose.yml
  .env
  db/
    init/
  promptforge_watcher/
  promptforge_services/
  vault/
    Inbox/
      Voice/
    Processing/
      Voice/
      Error/
    Processed/
      Voice/
    Projects/
```

Example:

```bash
mkdir -p /srv/promptforge/{db/init,promptforge_watcher,promptforge_services}
mkdir -p /srv/promptforge/vault/Inbox/Voice
mkdir -p /srv/promptforge/vault/Processing/Voice
mkdir -p /srv/promptforge/vault/Processing/Error
mkdir -p /srv/promptforge/vault/Processed/Voice
mkdir -p /srv/promptforge/vault/Projects
```

## Part 4: Place PromptForge artifacts

Copy these files into `/srv/promptforge`:

- `promptforge_docker_compose_mvp.yml` -> `docker-compose.yml`
- `promptforge_postgres_schema.sql` -> `db/init/001_schema.sql`
- `promptforge_seed_data.sql` -> `db/init/002_seed.sql`

Copy the starter pack into:

- `/srv/promptforge/promptforge_watcher`
- `/srv/promptforge/promptforge_services`

## Part 5: Create environment file

Create `/srv/promptforge/.env`

```env
POSTGRES_PASSWORD=change_this_now
N8N_HOST=promptforge.local
N8N_PROTOCOL=http
WEBHOOK_URL=http://promptforge.local:5678/
PROMPTFORGE_DEFAULT_MODEL=llama3.1-local
```

## Part 6: Start Postgres and n8n

From `/srv/promptforge`:

```bash
docker compose up -d
docker compose ps
```

If you use `scripts/bootstrap_stack.sh`, it will also apply the operator catalog seed pack to an existing database when those catalogs are still empty, so the console pages do not depend on a brand-new Postgres volume.

Check logs:

```bash
docker compose logs -f postgres
docker compose logs -f n8n
```

## Part 7: Confirm schema and seed load

```bash
docker exec -it promptforge-postgres psql -U promptforge -d promptforge
```

Then:

```sql
\dt
SELECT slug, name FROM projects;
SELECT name, prompt_type FROM prompt_templates;
SELECT name, target_identifier FROM delivery_targets;
```

## Part 8: Share the vault from Linux to Windows

For MVP, SMB is the simplest.

### 8.1 Install Samba

```bash
sudo apt install -y samba
```

### 8.2 Add a Samba config block

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

### 8.3 Add Samba password

```bash
sudo smbpasswd -a promptforge
sudo systemctl restart smbd
```

### 8.4 Connect from Windows

Connect to:

```text
\\<linux-server-ip>\PromptForgeVault
```

Map it to a drive letter and open the vault from Obsidian.

## Part 9: Configure Obsidian for voice intake

1. Install Obsidian on Windows
2. Open the mapped Linux vault
3. Create a note template for `Inbox/Voice`
4. Configure a template or plugin so every new note in that folder gets the standard frontmatter block
5. Install a speech-to-text plugin that writes into the note

Minimum note structure:

```md
---
pf_version: 1
capture_type: voice
status: new
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

## Part 10: Install and point at llama.cpp

You can run llama.cpp on the Linux host or another machine on the LAN.

The important requirement is that `promptforge-services` can reach the endpoint.

Set the base URL in `.env` or service config, for example:

```env
PROMPTFORGE_LLAMA_BASE_URL=http://192.168.1.50:8080
```

## Part 11: First smoke test

1. Create a note in `Inbox/Voice`
2. Save it
3. Check watcher logs:

```bash
docker compose logs -f promptforge-watcher
```

4. Check n8n
5. Check DB state:

```sql
SELECT status, note_relative_path FROM intake_notes ORDER BY created_at DESC;
SELECT status, prompt_type FROM prompt_generations ORDER BY created_at DESC;
SELECT status, target_identifier FROM deliveries ORDER BY created_at DESC;
```

## Part 12: New-user onboarding flow

A new user should only need to know this:

1. Open the PromptForge vault in Obsidian
2. Create a new note in `Inbox/Voice`
3. The template appears automatically
4. Add a short control prefix if needed, such as:
   - `project is the-tax-machine`
   - `prompt type is coding-cli`
5. Dictate the request under `## Transcript`
6. Save the note

PromptForge handles import, processing, and routing on the backend.
