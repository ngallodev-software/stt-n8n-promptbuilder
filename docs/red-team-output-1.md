{"author":"/root/agent3_frontend_control_plane","recipient":"/root","other_recipients":[],"content":"<subagent_notification>\n{"agent_path":"/root/agent3_frontend_control_plane","status":
  {"completed":"Core take: console already bloated beyond honest ‘control plane’. Backend exposes 40 console routes in one 3.2k-line module vs 7 core API routes in 118 lines. That is not a
  thin operator surface. It is becoming a second product with weak boundaries. Sources: promptforge_services/console_api.py, promptforge_services/api.py, route/LOC counts from repo.\n\nTop
  criticisms\n- Bootstrap payload is absurdly broad. console_bootstrap() returns projects, intake notes, utterances, transcript revisions, prompt generations, deliveries, delivery history,
  processing runs, llm runs, rulesets, rules, dictionary, templates, targets, logs, settings, health snapshot in one response. That is not a dashboard bootstrap; that is dumping half the
  database into the UI contract. tests/test_console_read_endpoints.py:66\n- Control-plane scope is incoherent. Read endpoints, settings, metrics, lineage, dispatch, retry/reroute, ruleset
  simulation, template versioning, prompt cloning, archive actions, LLM assist, admin purge all live under same surface. That is an accumulation of admin pages, not one clear operator
  workflow. promptforge_services/console_api.py:812, promptforge_services/console_api.py:2378, promptforge_services/console_api.py:2928, promptforge_services/console_api.py:3215\n- UI
  ownership is fake. Architecture doc says console observes and requests mutations, but bootstrap and lineage APIs make the backend precompose giant denormalized view models for it. That is
  server-side UI composition masquerading as clean control-plane separation. docs/promptforge-system-architecture.md:309, tests/test_console_read_endpoints.py:66\n- Operational UX is
  dangerous because permission model is cosmetic. Role/actor are caller-supplied headers, default role falls back to admin if absent, and actor defaults to derived role strings. That means
  the UI cannot represent trustworthy operator identity or safe approvals. promptforge_services/console_api.py:247, promptforge_services/console_api.py:275\n- Console advertises capabilities
  that are still stubs. Dictionary upsert, secrets rotation, purge archived notes, and often LLM assist return structured 501s. Good that they fail explicitly; bad that this surface is
  already modeled as if mature. promptforge_services/console_api.py:914, promptforge_services/console_api.py:930, promptforge_services/console_api.py:2928, tests/
  test_console_settings.py:181\n\nArchitectural risks\n- Frontend/backend contract drift will get worse because API_COMPAT.md still says diagnostics/ops query surfaces are not yet exposed,
  but they already exist and are sprawling. Doc no longer matches reality. API_COMPAT.md:65\n- The console will turn into a schema hostage. Every new table gets pressure to appear in
  bootstrap or lineage.\n- Any auth hardening later will be painful because current route design assumes one operator can do nearly everything from one surface.\n\nComplexity smells\n- Mega-
  bootstrap.\n- Single mega-module for all console concerns.\n- Mixed vocabulary: dashboard, admin, control plane, settings, assist, metrics, lineage. No tight product boundary.\n- Backward-
  compat pressure around a bloated payload shape.\n\nHidden assumptions\n- Single-user trusted local environment forever.\n- UI can safely know almost everything.\n- Operators benefit from
  broad visibility more than from narrow action-specific screens.\n- Read-heavy admin console can share a codepath with mutation-heavy lifecycle actions without becoming brittle.\n\nLikely
  failure modes\n- Bootstrap gets slower and more fragile as rows grow.\n- Frontend becomes tightly coupled to denormalized response quirks instead of stable task-oriented endpoints.\n-
  Hardening auth later breaks current operator flows because no principle of least privilege exists in the API design.\n- Users see actions in UI that are unsupported or partially wired and
  lose trust in the system model.\n\nBetter alternatives\n- Treat console as 3 surfaces only: queue/review board, delivery ops, settings. Everything else secondary or deferred.\n- Replace
  mega-bootstrap with small task-specific queries.\n- Keep lineage drilldown separate from dashboard summary.\n- Hide or remove stubbed actions instead of giving them permanent first-class
  routes.\n\nWhat to remove or simplify\n- Remove bootstrap inclusion of utterances, transcript revisions, llm runs, raw logs unless a screen truly needs them.\n- Defer dictionary editing
  and prompt cloning if they are not core to phase-2 operator jobs.\n- Collapse metrics endpoints into one compact ops summary if only one operator exists.\n\nExplicit answers\n1.
  Overengineered: bootstrap payload, route surface breadth, server-precomposed UI contract, template/rules admin depth for MVP.\n2. Underdesigned: auth/authz, trustworthy actor identity,
  operator workflow prioritization, task-focused information hierarchy.\n3. Misleadingly named/framed: ‘control plane’ and ‘bootstrap’. This is an admin kitchen sink.\n4. Painful in phase 2:
  contract drift, permission retrofitting, frontend coupling to giant denormalized payloads, inability to simplify because UI depends on everything.\n5. Change first: cut console scope to
  queue/review, delivery ops, and settings; redesign bootstrap around those jobs only."}}\n</subagent_notification>","trigger_turn":false}
