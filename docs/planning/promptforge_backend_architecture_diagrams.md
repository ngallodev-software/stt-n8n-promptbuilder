# PromptForge Backend Architecture Diagrams

## 1. System Context

CURRENT STATE: local operator writes in Obsidian, the backend ingests to Postgres, n8n orchestrates workflows, and delivery targets and LLM providers are external. GAPS: no real auth and no live-session transport. FUTURE STATE: hardened provider routing and broader delivery targets.

```mermaid
flowchart LR
  OP[Local operator]
  VAULT[Obsidian vault]
  PF[PromptForge backend]
  PG[(Postgres 16)]
  N8N[n8n]
  LLM[LLM providers <br/> OpenAI / Anthropic / Ollama]
  TARGETS[Delivery targets<br/>obsidian_note / queue / future live sessions]

  OP -->|capture notes| VAULT
  VAULT -->|voice note intake| PF
  PF -->|persist canonical state| PG
  PF -->|webhook / orchestration| N8N
  N8N -->|read / update workflow state| PG
  PF -->|optional review / transform| LLM
  PF -->|dispatch artifacts| TARGETS
  PF -->|write-back processed notes| VAULT
```

## 2. Container / Service Architecture

CURRENT STATE: two Python runtimes inside Docker Compose, one for the watcher and one for the API/services, both backed by Postgres and the mounted vault. GAPS: no production auth boundary and no separate cache or broker. FUTURE STATE: support services can be added without breaking the monolith-first split.

```mermaid
flowchart TB
  subgraph HOST[Host filesystem]
    VAULTM[Obsidian vault bind mount]
  end

  subgraph NET[Docker Compose network]
    WATCHER[promptforge-watcher<br/>filesystem ingest <br/>+ import + write-back]
    API[promptforge-services<br/>FastAPI + Uvicorn]
    PG[(postgres:16)]
    N8N[n8n]
  end

  WATCHER -->|read / write notes| VAULTM
  WATCHER -->|import records| PG
  WATCHER -->|webhook payloads| N8N
  WATCHER -->|call pipeline modules| API
  API -->|query / persist| PG
  N8N -->|workflow state| PG
```

## 3. Component Diagram

CURRENT STATE: the watcher owns filesystem import and write-back, while the Python service owns parsing, preprocessing, validation, rendering, delivery dispatch, console mutations, and partial LLM routing. GAPS: live session adapters are not wired end to end. FUTURE STATE: the same modules can absorb more provider adapters without changing the architecture split.

```mermaid
flowchart LR
  subgraph WATCHER_COMP[Watcher runtime]
    FS[Filesystem scan / debounce]
    NP[Note parser]
    EL[Eligibility + hash guard]
    IMP[Importer]
    WB[Write-back lifecycle]
    WH[Webhook emitter]
  end

  subgraph SERVICES_COMP[Python services runtime]
    ROUTE[FastAPI routers]
    PRE[Deterministic preprocess]
    VAL[Validation layer]
    REN[Renderer]
    DISP[Delivery dispatcher]
    CON[Console API]
    LLM[LLM routing module]
  end

  subgraph PERSIST_COMP[Persistence layer]
    REPO[DB access layer]
    AUDIT[Audit / lineage tables]
  end

  FS --> NP --> EL --> IMP
  IMP --> REPO
  IMP --> WH
  WH --> ROUTE
  ROUTE --> PRE --> VAL --> REN --> DISP
  CON --> REPO
  DISP --> REPO
  LLM --> PRE
  WB --> REPO
  REPO --> AUDIT
```

## 4.1 Intake Flow

CURRENT STATE: the watcher reads a new voice note, parses it, deduplicates it, and writes canonical intake rows to Postgres. GAPS: malformed notes stay in error and are not silently repaired. FUTURE STATE: reimport policy can become more explicit without changing lineage.

```mermaid
sequenceDiagram
  participant U as Local operator
  participant V as Obsidian vault
  participant W as Watcher
  participant P as Postgres

  U->>V: create voice note
  W->>V: scan Inbox/Voice/
  W->>W: parse frontmatter + body
  W->>W: check eligibility + content hash
  W->>P: insert intake_notes
  W->>P: insert utterances
  W->>P: insert transcript_revisions(raw)
  W->>P: mark imported
```

## 4.2 Processing Pipeline

CURRENT STATE: preprocessing, validation, and rendering are deterministic gates before any delivery is created. GAPS: LLM output is still partial wiring, so malformed structured output must fail before render. FUTURE STATE: additional deterministic transforms can be added without changing the stage order.

```mermaid
sequenceDiagram
  participant W as Watcher / n8n trigger
  participant S as PromptForge services
  participant P as Postgres

  W->>S: request preprocess
  S->>S: parse directives + normalize
  S->>P: persist preprocess artifacts
  W->>S: request validate
  S->>S: validate structured output
  W->>S: request render
  S->>S: render final prompt markdown
  S->>P: persist prompt_generation artifacts
```

## 4.3 Delivery Flow

CURRENT STATE: a rendered prompt becomes a delivery row, then the dispatcher sends it to an allowed target. GAPS: live `chat_session`, `claude_session`, and `codex_session` transports are unsupported. FUTURE STATE: additional adapters can attach without merging delivery with prompt generation.

```mermaid
sequenceDiagram
  participant S as PromptForge services
  participant P as Postgres
  participant D as Delivery dispatcher
  participant T as Delivery target

  S->>P: insert deliveries(status=queued)
  S->>D: prepare dispatch payload
  D->>T: dispatch artifact
  alt supported target
    T-->>D: success / ack
    D->>P: update delivery status
  else unsupported live session
    D->>P: persist failed attempt
  end
```

## 4.4 Failure + Retry Flow

CURRENT STATE: failures are retained in Postgres and the source note stays in the vault when processing or delivery fails. GAPS: retrying is append-only, not in-place mutation, so operators must not expect a failed row to become a success row. FUTURE STATE: richer reroute automation can sit on the same immutable attempt history.

```mermaid
sequenceDiagram
  participant D as Dispatcher
  participant P as Postgres
  participant V as Obsidian vault
  participant O as Operator
  participant C as Console API

  D-->>P: write failed delivery attempt
  D-->>P: write workflow_error_records row
  D-->>V: leave source note retained
  O->>C: request retry or reroute
  alt retry
    C->>P: create new delivery row
    C->>D: dispatch again
  else reroute
    C->>P: choose new target before terminal state
    C->>D: dispatch to new target
  end
```

## 4.5 Write-back Flow

CURRENT STATE: successful processing writes a processed artifact back into the vault and updates note state in Postgres. GAPS: failed runs do not generate processed write-back artifacts. FUTURE STATE: write-back templates can evolve without changing the canonical record model.

```mermaid
sequenceDiagram
  participant S as Services
  participant P as Postgres
  participant V as Obsidian vault

  S->>P: confirm processed state
  S->>V: update note frontmatter
  S->>V: move or rename processed note
  S->>P: record write-back completion
```

## 4.6 n8n Webhook Flow

CURRENT STATE: the watcher emits webhook payloads and n8n continues the orchestration path. GAPS: workflow sequencing is externalized, but canonical state still lives in Postgres. FUTURE STATE: the same webhook contract can feed more recovery and queue workflows.

```mermaid
sequenceDiagram
  participant W as Watcher
  participant N as n8n
  participant P as Postgres

  W->>N: webhook payload
  N->>P: create processing_run
  N->>P: load canonical context
  N->>P: update workflow state
  N-->>W: optional orchestration response
```

## 5. Deployment Diagram

CURRENT STATE: the stack is a local Docker Compose deployment with bind-mounted vault access and named volumes for durable service data. GAPS: no cloud deployment or external broker is assumed. FUTURE STATE: the same shape can be promoted to a hardened self-hosted install.

```mermaid
flowchart TB
  subgraph HOST[Host machine]
    VDIR[Obsidian vault directory]
    subgraph COMPOSE[Docker Compose]
      WATCHER[promptforge-watcher]
      API[promptforge-services]
      PG[(Postgres volume)]
      N8N[(n8n volume)]
    end
  end

  VDIR -->|bind mount| WATCHER
  WATCHER -->|internal network| API
  WATCHER -->|internal network| PG
  API -->|internal network| PG
  WATCHER -->|internal network| N8N
  API -->|internal network| N8N
```

## 6. ERD / Data Model

CURRENT STATE: the relational model keeps intake, prompt generation, delivery, rules, templates, dictionary terms, and audit rows separate. GAPS: LLM runs and workflow errors are append-only observability records, not application state substitutes. FUTURE STATE: more providers and targets can attach through the same FK structure.

```mermaid
erDiagram
  PROJECTS ||--o{ INTAKE_NOTES : owns
  PROJECTS ||--o{ PROMPT_GENERATIONS : scopes
  PROJECTS ||--o{ DELIVERY_TARGETS : scopes
  PROJECTS ||--o{ RULESETS : scopes
  PROJECTS ||--o{ TERM_DICTIONARY : scopes
  PROJECTS ||--o{ PROMPT_TEMPLATES : scopes

  INTAKE_NOTES ||--o{ UTTERANCES : contains
  UTTERANCES ||--o{ TRANSCRIPT_REVISIONS : versions
  UTTERANCES ||--o{ PROMPT_GENERATIONS : produces
  UTTERANCES ||--o{ PROCESSING_RUNS : drives

  RULESETS ||--o{ RULES : contains
  PROMPT_TEMPLATES ||--o{ PROMPT_GENERATIONS : selected_by
  RULESETS ||--o{ PROMPT_GENERATIONS : selected_by

  PROMPT_GENERATIONS ||--o{ DELIVERIES : emits
  DELIVERY_TARGETS ||--o{ DELIVERIES : receives
  PROMPT_GENERATIONS ||--o{ LLM_RUNS : records
  PROCESSING_RUNS ||--o{ WORKFLOW_ERROR_RECORDS : reports

  PROJECTS {
    uuid id
    text slug
  }

  INTAKE_NOTES {
    uuid id
    text status
    text vault_path
  }

  UTTERANCES {
    uuid id
    text raw_text
  }

  TRANSCRIPT_REVISIONS {
    uuid id
    text revision_kind
  }

  PROMPT_GENERATIONS {
    uuid id
    text status
    text prompt_type
  }

  DELIVERIES {
    uuid id
    text status
    text destination
  }

  DELIVERY_TARGETS {
    uuid id
    text target_type
    text target_identifier
  }

  PROCESSING_RUNS {
    uuid id
    text workflow_name
    text status
  }

  LLM_RUNS {
    uuid id
    text provider_name
    text status
  }

  RULESETS {
    uuid id
    text version
    bool is_active
  }

  RULES {
    uuid id
    text rule_type
  }

  TERM_DICTIONARY {
    uuid id
    text source_term
    text canonical_term
  }

  PROMPT_TEMPLATES {
    uuid id
    text version
    text prompt_type
  }

  WORKFLOW_ERROR_RECORDS {
    uuid id
    text stage_name
    text error_message
  }
```

## 7.1 Intake Note Lifecycle

CURRENT STATE: intake notes move from new to imported to processing to processed, with error and archived as terminal outcomes. GAPS: reimport is policy-driven and must not overwrite lineage. FUTURE STATE: reset/reimport can be explicit without breaking append-only history.

```mermaid
stateDiagram-v2
  [*] --> new
  new --> imported
  imported --> processing
  processing --> processed
  processing --> error
  processed --> archived
  error --> imported: reimport / reset
  error --> [*]
  archived --> [*]
  note right of error
    reimport is policy-driven,
    not silent overwrite
  end note
```

## 7.2 Prompt Generation Lifecycle

CURRENT STATE: prompt generation is deterministic-first and ends in rendered or failed. GAPS: failed generation is terminal unless an operator explicitly reruns it. FUTURE STATE: reset/retry can be added as an explicit control-path without mutating history.

```mermaid
stateDiagram-v2
  [*] --> created
  created --> preprocessed
  preprocessed --> transforming
  transforming --> structured_validating
  structured_validating --> rendered
  structured_validating --> failed
  transforming --> failed
  failed --> created: retry / reset
  rendered --> [*]
  failed --> [*]
  note right of failed
    retry requires a new generation
    or an explicit reset path
  end note
```

## 7.3 Delivery Lifecycle

CURRENT STATE: deliveries are append-only attempts with queued, dispatching, delivered, acked, and failed states. GAPS: retry creates a new row, and reroute is only valid before terminal states. FUTURE STATE: more transport adapters can share the same immutable attempt history.

```mermaid
stateDiagram-v2
  [*] --> not_started
  not_started --> queued
  queued --> dispatching
  dispatching --> delivered
  delivered --> acked
  dispatching --> failed
  queued --> failed
  queued --> queued: reroute before terminal
  failed --> queued: retry as new row
  acked --> [*]
  failed --> [*]
  note right of failed
    retry does not mutate the old row;
    it creates a new delivery attempt
  end note
```

## 8. Trust Boundary / Security

CURRENT STATE: the filesystem, API, database, and external provider boundaries are explicit, but production auth is missing and header hints are only operational metadata. GAPS: there is no real auth boundary and no hard trust layer for multi-user access. FUTURE STATE: a real auth boundary can be inserted without changing Postgres as source of truth.

```mermaid
flowchart LR
  subgraph FS[Filesystem boundary]
    VAULT[Obsidian vault]
  end

  subgraph APP[API boundary]
    WATCHER[Watcher]
    API[FastAPI services]
    AUTH[Missing real auth<br/>header hints only]
  end

  subgraph DB[Database boundary]
    PG[(Postgres 16)]
  end

  subgraph EXT[External boundary]
    N8N[n8n]
    LLM[LLM providers]
    TGT[Delivery targets]
  end

  VAULT --> WATCHER
  WATCHER --> API
  AUTH -. gap .- API
  API --> PG
  WATCHER --> PG
  API --> N8N
  API --> LLM
  API --> TGT
```

## 9. Gap Analysis

CURRENT STATE: the system is strong on deterministic ingestion, append-only lineage, and Postgres-backed state. GAPS: auth, observability, caching, robust queueing, live session transport, and multi-user support are intentionally missing. FUTURE STATE: those capabilities can be added as support-plane services without collapsing the core architecture.

```mermaid
flowchart TB
  subgraph CURRENT_STATE[CURRENT STATE]
    C1[Watcher + API split]
    C2[Postgres canonical state]
    C3[Deterministic preprocess / validate / render]
    C4[n8n webhook orchestration]
  end

  subgraph GAPS[GAPS]
    G1[No production auth]
    G2[Minimal observability]
    G3[No cache layer]
    G4[No robust queue / broker]
    G5[Live session transport unsupported]
    G6[No multi-user support]
  end

  subgraph FUTURE_STATE[FUTURE STATE]
    F1[Auth boundary]
    F2[Metrics + tracing + structured logs]
    F3[Optional cache]
    F4[Durable worker / queue plane]
    F5[Live session adapters]
    F6[Multi-user tenancy]
  end

  CURRENT_STATE --> GAPS
  GAPS --> FUTURE_STATE
```

## 10. Future-State Architecture

CURRENT STATE: the core remains a local-first monolith with Postgres as source of truth and deterministic stages first. GAPS: production concerns are not yet present. FUTURE STATE: a hardened self-hosted deployment adds auth, observability, queueing, and richer transport adapters without changing the core rules.

```mermaid
flowchart TB
  OP[Local operator / team]

  subgraph EDGE[Access boundary]
    AUTH[Auth + session gate]
  end

  subgraph CORE[PromptForge core]
    API[FastAPI service]
    WATCHER[Vault watcher]
    PROC[Deterministic processing engine]
    DISP[Delivery engine]
    AUDIT[Append-only lineage]
  end

  subgraph SUPPORT[Support plane]
    OBS[Logs / metrics / traces]
    QUEUE[Durable queue / worker plane]
    CACHE[Optional cache]
  end

  subgraph STATE[State plane]
    PG[(Postgres 16)]
  end

  subgraph EXTERNAL[External systems]
    VAULT[Obsidian vault]
    N8N[n8n]
    LLM[LLM providers]
    TGT[Delivery targets]
  end

  OP --> AUTH --> API
  VAULT --> WATCHER
  WATCHER --> PG
  API --> PROC --> PG
  API --> DISP --> PG
  API --> AUDIT --> PG
  API --> OBS
  API --> QUEUE
  API -. optional .-> CACHE
  API --> N8N
  API --> LLM
  DISP --> TGT
```
