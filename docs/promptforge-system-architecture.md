# PromptForge Cross-System Architecture

## Modeling Assumptions
- Directly grounded: Obsidian vault intake, watcher-driven ingestion, backend-owned deterministic processing, Postgres as canonical store, console as operator control plane, optional n8n webhook orchestration, optional LLM usage, and delivery dispatch are all evidenced by `/lump/apps/prompt-forge/README.md`, `/lump/apps/prompt-forge/API_COMPAT.md`, `/lump/apps/prompt-forge/docs/planning/promptforge_backend_architecture_diagrams.md`, watcher/services code, and this repo's console architecture and API client.
- Minimally inferred: "PromptForge watcher" is modeled as the combined watcher runtime plus its repository/writeback/webhook responsibilities; "backend services" is modeled as the FastAPI plus deterministic pipeline plus console API plus dispatch layer because the code currently groups those concerns in one Python service runtime.
- Future-only: hardened auth/authz, stronger operator separation, richer observability, more complete delivery transports, and multi-user support are proposed only. They do not exist as current-state guarantees.

## 1. End-to-End System Context Diagram

**CURRENT STATE**

```mermaid
flowchart LR
  operator[Local operator]
  vault[Obsidian vault<br/>Primary intake surface]
  watcher[PromptForge watcher<br/>Filesystem scan, import, write-back]
  backend[PromptForge backend services<br/>Pipeline, console API, dispatch, audit]
  pg[(Postgres<br/>Canonical system of record)]
  console[PromptForge console<br/>Operator control plane]
  n8n[n8n<br/>Optional webhook orchestration]
  llm[LLM providers<br/>Optional, gated]
  targets[Delivery targets<br/>Obsidian note, queue, partial live sessions]

  operator -->|captures voice note| vault
  vault -->|markdown note events| watcher
  watcher -->|intake import, write-back, webhook emit| backend
  backend -->|canonical persistence| pg
  operator -->|monitor and mutate| console
  console -->|bootstrap, reads, admin mutations| backend
  backend -->|optional event webhook| n8n
  backend -->|optional review/inference| llm
  backend -->|dispatch artifacts| targets
  targets -->|ack/failure/attempt metadata| backend
  watcher -->|processed note write-back| vault

  subgraph local[Local trusted environment]
    operator
    vault
    watcher
    backend
    console
    pg
  end

  subgraph external[Peripheral external systems]
    n8n
    llm
    targets
  end
```

**GAPS**
- The system is still locally trusted and single-user by assumption; the console and API are not hardened for broader exposure.
- Live delivery targets exist in the domain model, but some transports remain partial or explicitly unsupported.
- n8n participates in orchestration but the exact ownership boundary is still evolving.

**FUTURE STATE**
- Keep backend and Postgres as central authority while hardening auth, observability, and delivery transport adapters.
- Preserve Obsidian as intake and console as control plane even as the stack grows.

**What this shows**
- Intake originates in the filesystem, not in the UI.
- Backend and Postgres are central; console, n8n, LLMs, and delivery endpoints are supporting systems around that core.

## 2. Layered Architecture Diagram

**CURRENT STATE**

```mermaid
flowchart TB
  subgraph intake[Intake Layer]
    vault[Obsidian vault]
    watcherfs[Watcher filesystem scan<br/>debounce, eligibility, hash guard]
  end

  subgraph processing[Processing Layer]
    importer[Importer + repository]
    pipeline[Deterministic pipeline<br/>parse, preprocess, validate, render]
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

  subgraph orchestration[Orchestration Layer]
    webhook[Webhook contract]
    n8n[n8n workflows]
  end

  subgraph external[External Services]
    llm[LLM providers]
    endpoints[Delivery endpoints / live sessions / queues]
  end

  subgraph persistence[Persistence Layer]
    pg[(Postgres)]
  end

  vault --> watcherfs --> importer --> pipeline --> dispatch
  pipeline --> lineage --> pg
  importer --> pg
  dispatch --> pg
  writeback --> vault
  browser --> console --> consoleapi --> pg
  consoleapi --> dispatch
  pipeline --> llm
  importer --> webhook --> n8n
  dispatch --> endpoints
  n8n --> pg
```

**GAPS**
- The processing and control-plane concerns still live inside one backend codebase and mostly one service runtime.
- No cache or broker layer exists between control plane, processing, and persistence.
- n8n and write-back are supportive layers, but the code-level separation is still practical rather than strongly isolated.

**FUTURE STATE**
- Stronger service boundaries can emerge without changing layer ownership: intake remains intake, processing remains authoritative, control plane remains observational/mutational, orchestration remains optional.

**What this shows**
- Persistence is authoritative, processing drives core behavior, and the console sits beside that path rather than in it.

## 3. Control Flow Diagram

**CURRENT STATE**

```mermaid
flowchart LR
  subgraph eventdriven[Event-driven control flow]
    note[New or changed vault note]
    watcher[Watcher]
    pipeline[Backend pipeline]
    dispatch[Delivery dispatch]
    writeback[Write-back]
    hook[Webhook emit]
    n8n[n8n]
  end

  subgraph operatordriven[Operator-driven control flow]
    op[Operator]
    console[Console]
    api[Console/admin API]
    mutate[Retry, reroute, reprioritize,<br/>settings, rules, templates, archive, assist]
  end

  note --> watcher
  watcher --> pipeline
  pipeline --> dispatch
  pipeline --> writeback
  watcher --> hook --> n8n

  op --> console --> api --> mutate
  mutate --> pipeline
  mutate --> dispatch

  style note fill:#d7f0d8,stroke:#2d6a32
  style op fill:#e6e0ff,stroke:#5a3db8
```

**GAPS**
- Operator mutations can trigger state transitions, but they do not replace the watcher- and pipeline-driven baseline control path.
- n8n currently reacts to backend-emitted events; it should not be misread as the primary driver.

**FUTURE STATE**
- Make operator-triggered actions more explicit as controlled interventions over canonical backend state.
- Keep event-driven ingestion primary even if more operator tools are added.

**What this shows**
- Filesystem events initiate the main pipeline.
- The console only initiates administrative interventions.

## 4. Data Flow & Lineage Diagram

**CURRENT STATE**

```mermaid
flowchart LR
  raw[Raw note markdown<br/>immutable human-readable source]
  intake[intake_notes]
  utter[utterances]
  rev[transcript_revisions<br/>append-only raw/normalized revisions]
  runs[processing_runs<br/>append-only stage execution]
  parsed[parsed directives / preprocess artifacts]
  prompt[prompt_generations]
  llmruns[llm_runs<br/>optional]
  deliv[deliveries]
  attempts[delivery attempt history / dispatch metadata]
  logs[audit logs / workflow errors / console audit]
  pg[(Postgres canonical store)]
  ui[Console views]
  n8n[n8n workflow state]

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
  pg --> n8n
```

**GAPS**
- The append-only story is partly distributed across multiple tables and logs rather than one dedicated lineage service.
- n8n can read and react to persisted state, but it must not become shadow state ownership.
- The console currently reconstructs lineage from backend read surfaces rather than from a dedicated lineage graph.

**FUTURE STATE**
- A clearer lineage projection can sit on top of the same canonical rows without changing ownership.

**What this shows**
- Raw text stays immutable at the source.
- Postgres-backed records, not UI state or n8n memory, define the lineage chain.

## 5. End-to-End Sequence Diagrams

### 5.1 Full Happy Path

**CURRENT STATE**

```mermaid
sequenceDiagram
  participant O as Operator
  participant V as Obsidian vault
  participant W as Watcher
  participant S as Backend services
  participant P as Postgres
  participant D as Delivery target

  O->>V: capture structured voice note
  W->>V: detect new or changed markdown
  W->>W: parse frontmatter, control text, transcript
  W->>S: build import bundle / call deterministic pipeline
  S->>S: preprocess, validate, render, prepare delivery
  S->>P: persist intake, revisions, runs, prompt generation, delivery
  S->>D: dispatch rendered artifact
  D-->>S: ack / delivered response
  S->>P: persist delivery status and dispatch attempt
  W->>V: write processed note and frontmatter updates
```

**GAPS**
- Some target types still fail explicitly instead of completing the happy path.
- Write-back and dispatch success are coupled operationally today even though their state is separately recorded.

**FUTURE STATE**
- More delivery adapters can slot into the same happy path without changing ownership.

**What this shows**
- The full path starts from vault intake and ends in persisted delivery/write-back artifacts.

### 5.2 Failure Path

**CURRENT STATE**

```mermaid
sequenceDiagram
  participant V as Obsidian vault
  participant W as Watcher
  participant S as Backend services
  participant P as Postgres
  participant C as Console
  participant O as Operator

  W->>S: process note
  S->>S: deterministic stage fails or dispatch fails
  S->>P: persist failed processing run or failed delivery attempt
  W->>V: retain source note, skip processed write-back
  C->>S: poll bootstrap/read endpoints
  S->>P: read failed rows and lineage context
  S-->>C: failure surfaced in review/lineage/delivery views
  O->>C: inspect failure and choose recovery action
```

**GAPS**
- Failure visibility is present, but observability depth and operator diagnostics are still limited compared with the underlying state kept in Postgres.

**FUTURE STATE**
- Stronger recovery surfaces can remain append-only and still expose richer diagnostics.

**What this shows**
- Failures are retained, not hidden or overwritten.

### 5.3 Operator Intervention Path

**CURRENT STATE**

```mermaid
sequenceDiagram
  participant O as Operator
  participant C as Console
  participant A as Console API
  participant P as Postgres
  participant X as Backend execution path

  O->>C: retry, reroute, reprioritize, archive, or config change
  C->>A: admin mutation request
  A->>P: validate and mutate canonical rows
  A->>X: trigger dispatch or downstream processing when required
  X->>P: persist new state / attempt history
  A-->>C: mutation result
  C->>A: refetch bootstrap or page data
  A->>P: read canonical updated state
  A-->>C: refreshed view
```

**GAPS**
- Current role/actor handling is minimal header-based signaling, not hardened authorization.
- Some operator actions still depend on partial backend capability.

**FUTURE STATE**
- Hardened auth and audit can preserve the same control path while making it safe for broader use.

**What this shows**
- Operator actions always travel through backend-owned transitions.

### 5.4 n8n Orchestration Path

**CURRENT STATE**

```mermaid
sequenceDiagram
  participant W as Watcher
  participant N as n8n
  participant S as Backend services
  participant P as Postgres
  participant T as Downstream automation

  W->>N: emit webhook payload
  N->>P: read or update workflow-related rows
  N->>T: run optional automation branch
  N-->>S: optional callback or side effect
  S->>P: persist any resulting canonical state changes
```

**GAPS**
- The boundary between backend-native orchestration and n8n-managed workflow steps is still pragmatic, not fully formalized.
- n8n persistence can become confusing if read as authoritative rather than supportive.

**FUTURE STATE**
- Keep n8n strictly reactive to backend events with clearer contracts and bounded side effects.

**What this shows**
- n8n is a reacting orchestrator, not the system of record.

### 5.5 LLM-Assisted Path

**CURRENT STATE**

```mermaid
sequenceDiagram
  participant W as Watcher or console-triggered backend path
  participant S as Backend services
  participant V as Deterministic validation gates
  participant L as LLM provider
  participant P as Postgres

  W->>S: request processing or assist
  S->>V: deterministic preprocess and validation gate
  alt LLM enabled and allowed
    V->>L: gated review or inference request
    L-->>S: optional model output
    S->>P: persist llm_run metadata and accepted result
  else deterministic-only mode
    S->>P: persist deterministic artifacts only
  end
```

**GAPS**
- Provider support is partial today; OpenAI and Anthropic remain incomplete in current wiring.
- LLM usage is optional but the console needs to continue presenting it as such.

**FUTURE STATE**
- More provider adapters and stricter acceptance policies can fit into the same gated model.

**What this shows**
- LLM calls are optional branches behind backend-controlled gates.

## 6. State Ownership Diagram

**CURRENT STATE**

```mermaid
flowchart TB
  subgraph owners[State owners]
    vault[Obsidian vault<br/>owns raw note file contents]
    backend[Backend services + watcher<br/>own lifecycle transitions]
    pg[(Postgres<br/>owns canonical persisted state)]
    console[Console<br/>observes and requests mutations]
    n8n[n8n<br/>owns only workflow-local execution state]
  end

  intake[Intake state]
  processing[Processing state]
  prompt[Prompt generation state]
  delivery[Delivery state]
  retry[Retry/reroute attempt state]
  ui[Navigation, filters, draft forms]

  vault --> intake
  backend --> intake
  backend --> processing
  backend --> prompt
  backend --> delivery
  backend --> retry
  pg --> intake
  pg --> processing
  pg --> prompt
  pg --> delivery
  pg --> retry
  console --> ui
  n8n --> orchestration[n8n workflow-local state]
```

**GAPS**
- Watcher and backend services are logically distinct owners of behavior but practically part of one backend authority today.
- The console can mutate state, but it does not own any lifecycle.

**FUTURE STATE**
- Stronger internal service boundaries can clarify execution ownership while keeping backend + Postgres authoritative.

**What this shows**
- Core lifecycle state belongs to the backend and is persisted in Postgres.
- The browser owns only temporary UI state.

## 7. Trust Boundary Diagram

**CURRENT STATE**

```mermaid
flowchart TB
  subgraph filesystem[Local filesystem boundary]
    vault[Obsidian vault]
  end

  subgraph containers[Docker / local container boundary]
    watcher[Watcher container/runtime]
    backend[Backend API/services]
    console[Console frontend]
    pg[(Postgres)]
    n8n[n8n]
  end

  subgraph browser[Browser boundary]
    operator[Local operator]
  end

  subgraph external[External network boundary]
    llm[LLM providers]
    targets[Delivery endpoints / live sessions]
  end

  operator --> console
  vault --> watcher
  console --> backend
  watcher --> backend
  backend --> pg
  backend --> n8n
  backend --> llm
  backend --> targets

  weak1[[Current weakness:<br/>header-based role/actor hints only]]
  weak2[[Current weakness:<br/>console/API unsafe if exposed beyond trusted local env]]
  weak3[[Current weakness:<br/>secret-management UX and transport hardening incomplete]]
  weak4[[Current weakness:<br/>external targets and providers cross trust boundary]]

  console -.-> weak1
  backend -.-> weak2
  n8n -.-> weak3
  llm -.-> weak4
  targets -.-> weak4
```

**GAPS**
- Real authN/authZ is absent.
- Secrets and privileged operations rely on local-trust assumptions.
- External providers and endpoints sit across the network boundary with partial hardening.

**FUTURE STATE**
- Add hardened auth, better secret handling, and tighter network exposure controls without changing core system ownership.

**What this shows**
- PromptForge is safe only under a local-trusted deployment assumption today.

## 8. Cross-System Gap Analysis Diagram

**CURRENT STATE**

```mermaid
flowchart TB
  core[Current system]

  auth[No real auth/authz]
  operator[Weak separation between operator identity and system actions]
  cache[No dedicated cache or broker layer]
  observe[Limited observability UX over rich backend state]
  llm[Partial LLM integration and provider coverage]
  transport[Incomplete live delivery transports]
  n8nboundary[Evolving backend vs n8n orchestration boundary]
  singleuser[Single-user trusted-environment assumption]
  controlplane[Control plane not yet hardened]

  core --> auth
  core --> operator
  core --> cache
  core --> observe
  core --> llm
  core --> transport
  core --> n8nboundary
  core --> singleuser
  core --> controlplane
```

**GAPS**
- These are active architecture constraints, not edge cases.

**FUTURE STATE**
- Each gap can be addressed incrementally without changing the core local-first, Obsidian-first, Postgres-authoritative model.

**What this shows**
- The main architectural risks are around hardening and boundary clarity, not around the core domain model.

## 9. Current vs Future System Architecture

**CURRENT STATE**

```mermaid
flowchart LR
  subgraph current[CURRENT]
    c1[Local-first monolith-first backend]
    c2[Watcher + services share authority]
    c3[Console as thin operator plane]
    c4[Postgres as canonical store]
    c5[n8n optional but boundary still soft]
    c6[Minimal auth, single-user trust model]
  end

  subgraph future[FUTURE]
    f1[Hardened operator control plane]
    f2[Clearer internal domain boundaries]
    f3[Explicit orchestration contracts with n8n]
    f4[Stronger observability and lineage projections]
    f5[Safer secret and destructive-action workflows]
    f6[Multi-operator readiness with real auth/RBAC]
  end

  c1 --> f1
  c2 --> f2
  c3 --> f1
  c4 --> f4
  c5 --> f3
  c6 --> f6
```

**GAPS**
- Current architecture is viable for a trusted MVP but not yet for broader operational exposure.

**FUTURE STATE**
- The evolution path is refinement and hardening, not a change in core ownership.

**What this shows**
- Future state should preserve the current domain truths while fixing boundary and hardening weaknesses.

## 10. Failure Domains & Isolation Diagram

**CURRENT STATE**

```mermaid
flowchart TB
  watcher[Watcher failure]
  pipeline[Processing pipeline failure]
  db[Postgres failure]
  n8n[n8n failure]
  llm[LLM/provider failure]
  delivery[Delivery target failure]

  wimpact[New note ingestion stalls;<br/>existing persisted state remains]
  pimpact[Current note/run fails;<br/>source note retained;<br/>other persisted state remains]
  dbimpact[Canonical system unavailable;<br/>console, processing, delivery all degrade]
  nimpact[Optional automation breaks;<br/>core backend can still own state]
  limpact[Deterministic path can still continue<br/>if LLM branch is optional]
  dimpact[Delivery attempt fails;<br/>prompt generation and intake lineage remain]

  watcher --> wimpact
  pipeline --> pimpact
  db --> dbimpact
  n8n --> nimpact
  llm --> limpact
  delivery --> dimpact
```

**GAPS**
- Recovery tooling exists, but isolation is mostly logical rather than enforced with separate infrastructure domains.
- Database failure remains the highest-blast-radius event because Postgres is the canonical store.

**FUTURE STATE**
- Stronger health checks, alerting, and replay/recovery flows can improve isolation without changing ownership.

**What this shows**
- Most external failures are recoverable without losing canonical lineage.
- Postgres is the critical dependency.

## 11. Operational Model Diagram

**CURRENT STATE**

```mermaid
flowchart LR
  passive[Passive ingestion<br/>vault note appears]
  autonomous[Backend autonomous processing<br/>watch, parse, validate, render, dispatch]
  monitor[Operator monitors via console]
  intervene[Operator intervenes only when needed<br/>retry, reroute, config, archive, assist]
  orchestrate[Optional n8n orchestration]

  passive --> autonomous --> monitor
  monitor --> intervene
  autonomous --> orchestrate
  intervene --> autonomous
```

**GAPS**
- The operational model is correct, but the UI and auth model still need hardening to match the sensitivity of the actions exposed.

**FUTURE STATE**
- Keep the system autonomous by default, with operators acting as supervisors rather than request-by-request users.

**What this shows**
- PromptForge is not a request/response SaaS app.
- It is an autonomous local pipeline with an operator control plane layered beside it.
