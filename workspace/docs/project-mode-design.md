# Project mode — design (PM-driven recruitment, isolated teams)

Moving from a thread-centric model ("create a thread, hand-pick agents") to a
**project-centric** one: you state a goal, a **PM agent recruits a team** from the
154-role library, the team is **instantiated with isolated working dirs**, and the
project runs on the existing A2A task layer.

This doc covers the data model, the recruitment flow, backend endpoints, the
**frontend changes**, the launcher integration point, and a build order.

---

## 1. Concept & entity model

```
Workspace  (= the org / "Acme Team")
  ├── role catalog        (154 roles — shared, org-level, read-only library)
  └── Project  (goal + status)                     ← NEW
        ├── ProjectAgent   (a role recruited INTO this project)   ← NEW
        │     • role_id (from catalog) + instance name + working_dir
        │     • isolated: its own working dir / runtime, not shared across projects
        ├── threads        (channels scoped to the project)
        └── tasks          (A2A TaskRecords scoped to the project)
```

**Key structural decision — agents are recruited *per project*, not shared.**
Today an agent is a `WorkspaceMember` keyed `(workspace_id, agent_name)` → one
global instance, one `working_dir`, shared across all threads. That's the source
of the contention / one-codebase problem. Project mode makes the recruited unit a
**`ProjectAgent`**: the same catalog role (e.g. `backend-developer`) can be
recruited into project A and project B as **two isolated instances**, each with
its own `working_dir`. The catalog role is the *template*; the ProjectAgent is the
*hire*.

> Alternative considered: **project = its own workspace** (reuse the existing
> isolation boundary). Cleaner isolation but the org loses a natural "owns many
> projects" parent, and every project spins a full workspace. Chose the
> Project-within-workspace + ProjectAgent model so one org dashboard spans
> projects while still isolating each hire. Revisit if true cross-project
> account/quota separation is needed.

---

## 2. The role catalog (already exists, just needs a query surface)

`frontend/lib/role-templates.data.ts` — **154 roles, 10 categories**, each:
`{ id, name, cat, model, tagline, skills[], abilities[] }`. This is the hiring
pool. It's static/generated, so it can be served read-only.

**The PM must not be handed all 154 in its prompt.** Add a search surface:

- `GET /v1/roles?q=&category=&skill=&limit=` → ranked role summaries
  `{id, name, cat, tagline, skills}`. Ranking = keyword/skill match.
- (Backend mirrors the same data, or the PM hits it via an MCP tool — see §4.)

---

## 3. Recruitment flow (the PM closes the loop)

```
Human: "Build a billing dashboard with Stripe + audit logging."
  │
  ▼  POST /v1/projects  {goal}                         → Project(status=recruiting)
  │
  ▼  PM agent (the recruiter) runs:
       1. search the catalog by the goal's needs (frontend, payments, security…)
       2. propose a LEAN team — each role + one-line rationale
       3. write the proposal back  → POST /v1/projects/{id}/proposal
  │
  ▼  Human reviews the proposed team in the UI → approve / add / drop
  │
  ▼  POST /v1/projects/{id}/recruit  {roleIds, workingDirs}
       → create a ProjectAgent per role, assign isolated working_dir
       → signal the daemon to launch those runtimes (see §6)
       → Project(status=active)
  │
  ▼  PM decomposes the goal into A2A tasks → delegates to the hired agents
     → existing task lifecycle / board takes over.
```

**Three guardrails (non-negotiable):**
1. **Lean default** — PM recruits the minimum viable team; more on demand. (Cost
   + the shared-account rate limit make over-staffing actively harmful.)
2. **Grounded picks** — PM may only pick `roleId`s returned by the search tool,
   never invented names.
3. **Human-in-the-loop (v1)** — PM *proposes*, the human *approves*. Full
   auto-recruit is a later opt-in.

**PM is a coordinator, not a coder** — it recruits, decomposes, assigns, tracks.

---

## 4. Backend — data model + endpoints

New tables:
- `projects(id, workspace_id, name, goal, status, created_by, created_at, archived_at)`
  status ∈ recruiting | active | paused | done | archived
- `project_agents(id, project_id, role_id, agent_name, working_dir, status, created_at)`
  `agent_name` = the instance handle (e.g. `backend-developer` or
  `backend-developer-2` if the role is hired twice org-wide).
- `projects.proposal` JSONB overlay (the PM's proposed team, pre-approval).

Endpoints:
- `POST /v1/projects {goal,name?}` → create (recruiting)
- `GET /v1/projects` / `GET /v1/projects/{id}` → list / detail (team, threads, tasks, status)
- `GET /v1/roles?q&category&skill` → catalog search (for the PM + the UI)
- `POST /v1/projects/{id}/proposal {team:[{roleId,reason}]}` → PM writes proposal
- `POST /v1/projects/{id}/recruit {roleIds, workingDirs}` → instantiate + launch + activate
- `POST /v1/projects/{id}/archive` / `…/agents/{id}` add/remove a hire later
- Scope existing surfaces by project: threads (`context`/channel), A2A tasks
  (already have `context_id`; add an optional `project_id` filter).

**PM tooling (MCP):** extend `workspace/mcp-a2a` with `search_roles` and
`propose_team` so the PM works through tools, not raw curl (and ride the loop
guard + the launcher follow-ups we already filed).

---

## 5. Frontend — the bigger shift

The app is thread-centric today (`layout/wrapper.tsx` switches viewMode →
ThreadList / Tasks / Team / …, sidebar shows the whole workspace roster). Project
mode adds a **project layer above** and scopes the existing views to the active
project.

New / changed:
1. **Project switcher** (top of the left sidebar, where "Acme Team / 5dcbf8cd" is)
   — dropdown or a slim projects rail to switch the active project; "+ New Project".
2. **New-Project wizard** (replaces the manual agent-pick in `NewThreadDialog` as
   the primary create path):
   - Step 1: describe the goal.
   - Step 2: **PM proposes a team** — cards per recruited role (name, tagline,
     why-recruited), each toggleable; "+ add role" opens catalog search.
   - Step 3: confirm working dirs → "Open project".
3. **Project view** = the current Threads + Tasks(board) + Team, but **scoped to
   the project**. The sidebar **roster becomes the project's hired team**, not the
   global workspace roster.
4. **Recruitment panel** (in Team view): the hired team + the PM's rationale +
   add/remove roles (re-recruit) later.
5. **Role library browser** (new view): browse/search the 154 roles by category —
   for manual add and for transparency into what the PM picked from.
6. Existing views (Threads, Tasks, Timeline, Review) take a `projectId` scope.

Reused as-is: chat/message components, A2A task board, view-as-agent panel,
kickoff. The WeChat-style surfaces don't change — they just render a
project-scoped roster + threads.

---

## 6. Launcher integration point (cross-repo — flagged, not built here)

Recruiting creates DB rows, but an agent only *works* when a runtime is launched.
Today that's static (`~/.openagents/daemon.yaml` + role folders). Project mode
needs the daemon to **launch a recruited ProjectAgent on demand** with the
project's `working_dir` (its own codebase checkout) and a binding to the
project's threads. Backend emits the intent (a `project.agent.recruited` event or
a provisioning record); the daemon picks it up and spawns the runtime. This is
the one piece that lives in the launcher repo — track alongside
`docs/launcher-followups.md`.

---

## 7. Build order

1. **Catalog search** — `GET /v1/roles` + a role-library browser view. (Self-contained, immediately useful.)
2. **Project entity + threads/tasks scoping** — projects table, create/list/detail, scope existing views by `projectId`. (No recruitment yet — manual team.)
3. **PM recruitment loop** — `search_roles`/`propose_team` MCP tools, the proposal→approve→recruit flow, the New-Project wizard.
4. **Launcher provisioning** — daemon launches recruited agents with isolated working dirs (cross-repo).
5. **Polish** — re-recruit, archive/delete (also closes the current "can't delete a thread" gap), per-project quota/keys for real parallelism.

---

## 8. Open decisions (need your call)

- **Isolation unit**: Project-within-workspace + per-project ProjectAgent
  (this doc), or project = its own workspace? (Affects whether one dashboard
  spans projects.)
- **Auto vs approved recruitment**: human approves the PM's team in v1 — when (if
  ever) do we allow one-click full-auto?
- **Quota**: shared account (isolation only, no extra parallel throughput) vs
  per-project key (true parallelism). Architecture is the same; this is a config/ops call.
- **Role library**: keep the full generated 154, or curate down to a vetted set
  so the PM's matches are sharper?
