# PromptForge System Architecture

## Runtime Overview

PromptForge is a single-user, local-only Obsidian-to-prompt pipeline.

**Python owns all workflow.** Intake, parse, compile, queue, dispatch, and retry are all Python-owned. No external system drives these steps.

**Postgres is canonical truth.** All durable state — intake records, processing runs, prompt generations, delivery attempts, audit logs — lives in Postgres. Nothing else is authoritative.

**Obsidian vault is intake and output surface only.** Source notes arrive via the vault. Processed prompts are written back to the vault. The vault does not own state; Postgres does.

**n8n is an optional reactive sidecar.** Python may fire webhook events to n8n after state has been written to Postgres. n8n can react to those events (run automations, send notifications) but it does not own workflow, queue, retries, or canonical state.

**No auth/role model.** Single-user local deployment. No RBAC, no session auth.

**No live-session (tmux) delivery.** Removed in phase 2.

---

## 1. System Context

```mermaid
flowchart LR
  operator[Local operator]
  vault[Obsidian vault<br/>Intake surface / output surface]
  watcher[PromptForge watcher<br/>Filesystem scan, import, write-back]
  backend[PromptForge backend<br/>Python: pipeline, dispatch, queue, retry]
  pg[(Postgres<br/>Canonical system of record)]
  console[PromptForge console<br/>Operator control plane]
  n8n[n8n<br/>Optional reactive sidecar]
  llm[LLM providers<br/>Optional, gated]
  targets[Delivery targets<br/>Obsidian note, queue]

  operator -->|creates note| vault
  vault -->|markdown note events| watcher
  watcher -->|import, write-back| backend
  backend -->|all durable state| pg
  operator -->|monitor, mutate| console
  console -->|reads, admin mutations| backend
  backend -->|webhook event after state write| n8n
  backend -->|optional inference| llm
  backend -->|dispatch artifacts| targets
  targets -->|ack/failure| backend
  watcher -->|processed note write-back| vault

  subgraph local[Local trusted environment]
    operator
    vault
    watcher
    backend
    console
    pg
  end

  subgraph peripheral[Optional peripheral systems]
    n8n
    llm
    targets
  end
```

---

## 2. Layer Diagram

```mermaid
flowchart TB
  subgraph intake[Intake Layer]
    vault[Obsidian vault<br/>source notes]
    watcherfs[Watcher<br/>scan, debounce, eligibility, hash guard]
  end

  subgraph processing[Processing Layer — Python owns all]
    importer[Importer + repository]
    pipeline[Deterministic pipeline<br/>parse, preprocess, validate, render]
    queue[Queue + retry manager]
    lineage[Audit, lineage, processing runs]
  end

  subgraph control[Control Plane]
    browser[Browser]
    console[Console SPA]
    consoleapi[Console API routes]
  end

  subgraph execution[Execution Layer]
    dispatch[Delivery dispatch]
    writeback[Vault write-back]
  end

  subgraph persistence[Persistence Layer]
    pg[(Postgres — canonical truth)]
  end

  subgraph sidecar[Optional Sidecar]
    webhook[Webhook emit]
    n8n[n8n — reactive only]
    llm[LLM providers]
  end

  vault --> watcherfs --> importer --> pipeline --> dispatch
  pipeline --> queue --> dispatch
  pipeline --> lineage --> pg
  importer --> pg
  dispatch --> pg
  writeback --> vault
  browser --> console --> consoleapi --> pg
  consoleapi --> dispatch
  pipeline --> llm
  dispatch --> webhook --> n8n
  dispatch --> writeback
```

n8n sits outside the processing and persistence layers. It receives events after Python has already committed state.

---

## 3. Control Flow

```mermaid
flowchart LR
  subgraph pythondriven[Python-driven control flow]
    note[New or changed vault note]
    watcher[Watcher]
    pipeline[Python pipeline]
    queue[Queue / retry]
    dispatch[Delivery dispatch]
    writeback[Vault write-back]
  end

  subgraph operatordriven[Operator-driven control flow]
    op[Operator]
    console[Console]
    api[Console API]
    mutate[Retry, reroute, reprioritize,<br/>settings, rules, archive]
  end

  subgraph sidecar[Optional sidecar — fires after state write]
    webhook[Webhook event]
    n8n[n8n]
  end

  note --> watcher --> pipeline --> queue --> dispatch --> writeback
  dispatch --> webhook --> n8n

  op --> console --> api --> mutate
  mutate --> pipeline
  mutate --> dispatch

  style note fill:#d7f0d8,stroke:#2d6a32
  style op fill:#e6e0ff,stroke:#5a3db8
```

Python drives the full path. n8n receives an event after dispatch writes state — it does not control any step in the pipeline.

---

## 4. Data Flow & Lineage

```mermaid
flowchart LR
  raw[Raw note markdown<br/>human-readable source]
  intake[intake_notes]
  utter[utterances]
  rev[transcript_revisions<br/>append-only]
  runs[processing_runs<br/>append-only stage execution]
  parsed[parsed directives / preprocess artifacts]
  prompt[prompt_generations]
  llmruns[llm_runs<br/>optional]
  deliv[deliveries]
  attempts[delivery attempt history]
  logs[audit logs]
  pg[(Postgres — canonical store)]
  ui[Console views]

  raw --> intake --> utter --> rev
  utter --> runs
  rev --> parsed --> prompt
  prompt --> deliv --> attempts
  prompt --> llmruns
  intake --> logs
  runs --> logs
  deliv --> logs

  intake --> pg
  utter --> pg
  rev --> pg
  runs --> pg
  prompt --> pg
  llmruns --> pg
  deliv --> pg
  attempts --> pg
  logs --> pg

  pg --> ui
```

Postgres-backed records define the lineage chain. Vault files are the source for intake; after ingestion, Postgres owns state.

---

## 5. Sequence Diagrams

### 5.1 Happy Path

```mermaid
sequenceDiagram
  participant O as Operator
  participant V as Obsidian vault
  participant W as Watcher
  participant S as Python backend
  participant P as Postgres
  participant D as Delivery target

  O->>V: create voice note
  W->>V: detect new/changed markdown
  W->>W: parse frontmatter, control text, transcript
  W->>S: import bundle → deterministic pipeline
  S->>S: preprocess, validate, render, queue, dispatch
  S->>P: persist intake, revisions, runs, prompt, delivery
  S->>D: dispatch rendered artifact
  D-->>S: ack / delivered
  S->>P: persist delivery status and attempt
  S->>V: write-back processed note and frontmatter
```

### 5.2 Failure Path

```mermaid
sequenceDiagram
  participant V as Obsidian vault
  participant W as Watcher
  participant S as Python backend
  participant P as Postgres
  participant C as Console
  participant O as Operator

  W->>S: process note
  S->>S: pipeline stage or dispatch fails
  S->>P: persist failed run or failed delivery attempt
  W->>V: retain source note, skip write-back
  C->>S: poll bootstrap/read endpoints
  S->>P: read failed rows and lineage
  S-->>C: failure surfaced in review/delivery views
  O->>C: inspect and choose recovery action
```

### 5.3 Operator Intervention

```mermaid
sequenceDiagram
  participant O as Operator
  participant C as Console
  participant A as Console API
  participant P as Postgres
  participant X as Python execution

  O->>C: retry, reroute, reprioritize, archive, or config change
  C->>A: mutation request
  A->>P: validate and mutate canonical rows
  A->>X: trigger dispatch or downstream processing
  X->>P: persist new state / attempt history
  A-->>C: mutation result
  C->>A: refetch bootstrap or page data
  A->>P: read updated canonical state
  A-->>C: refreshed view
```

### 5.4 n8n Sidecar Path

```mermaid
sequenceDiagram
  participant S as Python backend
  participant P as Postgres
  participant N as n8n
  participant T as Downstream automation

  S->>P: write canonical state (dispatch, delivery)
  S->>N: emit webhook event after state write
  N->>T: run optional automation branch
  Note over N: n8n does not write back to Postgres<br/>n8n does not own retries or queue
```

n8n is notified after Python has finished. It cannot initiate or control pipeline steps.

### 5.5 LLM-Assisted Path

```mermaid
sequenceDiagram
  participant S as Python backend
  participant V as Deterministic validation gate
  participant L as LLM provider
  participant P as Postgres

  S->>V: preprocess and validation gate
  alt LLM enabled and allowed
    V->>L: gated inference request
    L-->>S: model output
    S->>P: persist llm_run metadata and accepted result
  else deterministic-only mode
    S->>P: persist deterministic artifacts only
  end
```

---

## 6. State Ownership

| State domain | Owner |
|---|---|
| Raw note file contents | Obsidian vault (input surface only) |
| Intake, processing, prompt, delivery lifecycle | Python backend |
| All durable canonical state | Postgres |
| Temporary UI state | Console browser |
| Optional automation reactions | n8n (does not own canonical state) |

---

## 7. Failure Domains

| Component failure | Impact |
|---|---|
| Watcher | New note ingestion stalls; existing persisted state intact |
| Processing pipeline | Current run fails; source note retained; other state intact |
| Postgres | Canonical system unavailable; console, processing, delivery all degrade |
| n8n | Optional automation breaks; Python backend continues normally |
| LLM provider | Deterministic path continues if LLM branch is optional |
| Delivery target | Delivery attempt fails; prompt generation and lineage remain |

Postgres is the highest-blast-radius failure. n8n failure has no effect on core pipeline.

---

## 8. Operational Model

PromptForge is not a request/response app. It is an autonomous local pipeline:

- Vault note appears → watcher detects → Python pipeline runs automatically
- Postgres records every stage
- Console lets the operator monitor and intervene (retry, reroute, config) when needed
- n8n may react to events fired by Python after state is committed

The operator is a supervisor, not a per-request user.
