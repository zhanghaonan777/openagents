# Project mode — design (finalized)

The product shifts from **thread-centric** ("create a thread, hand-pick agents")
to **project-centric**: a **project** is the top-level unit you live inside; it has
its **own recruited team** and its **own work** (threads/tasks/etc.), assembled by
a **PM agent** from a role catalog.

This is the source of truth. It supersedes the earlier draft (which had the org,
not the project, at the top).

---

## 1. Hierarchy & model

```
Organisation  (= the workspace / account; rarely switched, lives as a subtitle)
  └── Project   ← THE top-level unit you operate in (replaces the old "Acme Team" header)
        ├── Team        — ProjectAgents: roles recruited INTO this project (isolated)
        ├── Threads     — conversations filed under this project
        ├── Tasks       — A2A tasks scoped to this project
        └── …Review / Timeline / Files / Browser / Routines (all project-scoped)

Shared, org-level (persistent — same across every project):
  • Skill Hub (the 154-role catalog you recruit FROM)
  • Connect Agent  • Inbox (your notifications)  • Settings
```

**Project is the top-level entity, the org is the container.** You switch projects
constantly; you switch orgs rarely. So the **project switcher sits at the very top**
of the sidebar (where "Acme Team" used to be), with the org as its subtitle.

**Roles vs hires.** A catalog *role* (e.g. `backend-developer`) is a template. A
**ProjectAgent** is the *hire* — the same role can be recruited into project A and
project B as two separate, isolated members, each with its own `working_dir`.

---

## 2. Isolation — be honest: two layers

| Layer | What it means | Status |
|---|---|---|
| **Logical** | Each project has its own team list + own threads/tasks. The UI shows different teams per project. | ✅ Built (ProjectAgent + recruit; roster scoped) |
| **Runtime** | Each project's agents are **separate processes** with their **own working_dir** and (ideally) their **own quota** — true parallelism, different codebases. | ⏳ **Not built** — this is the daemon/launcher's job |

⚠️ **The runtime layer is where the real value is** (parallel projects, different
codebases, no quota contention). Today the recruited members map to the **shared
workspace runtimes** — so a role recruited into two projects is still *one* running
agent underneath. The UI must not over-promise: a recruited role that has no
running instance shows **offline** ("recruited, not yet running").

**Open architectural fork (decide before building much more on top):**
- **A. Project-within-workspace + ProjectAgent** (current path) — one org dashboard
  spans projects; but runtime isolation must be built separately in the launcher.
- **B. Project = its own workspace** — reuses the daemon's existing per-workspace
  agent binding, so runtime isolation is almost free; cost is the org no longer has
  a single dashboard over projects. **Possibly simpler for the goal that matters.**

This is genuinely unresolved and worth settling before deep UI investment.

> Quota reality: even with isolation, throughput is bounded by how many Claude
> accounts/keys back the agents. Isolation ≠ more parallel throughput unless each
> project gets its own key. Architecture and quota are separate decisions.

---

## 3. Sidebar layout

```
┌─ [logo]  登录改版                ▾   ← project switcher (top); dropdown = projects + "New Project"
│          Acme Team · 3 threads · 4 members   (org subtitle + project stats)
├─ ┌───────────────────────────┐
│  │  +  New Thread            │      ← in-project primary action (creates a thread in this project)
│  └───────────────────────────┘
├─ Team · 4                          ← THIS project's recruited team (not the org roster)
│    ● backend-developer  online
│    ● security-auditor   offline · recruited
│    + Recruit                       ← opens Skill Hub → recruits the picked role into this project
├─ ── Project ──
│    Threads · Tasks · Team · Review · Timeline · Files · Browser · Routines   ← all project-scoped
├─ ── Workspace ──                    ← persistent / org-level, pinned to the bottom
│    Skill Hub · Connect Agent · Inbox · Settings
└─
"All projects" is a special state: org-wide roster + unscoped views (or a project-cards home).
```

---

## 4. Panel classification (project-scoped vs persistent)

**Project-scoped** — content changes with the active project:
`Threads, Tasks, Team, Review, Timeline, Files, Browser, Routines`. Switching from
"登录改版" to "计费看板" shows that project's threads/tasks/team/etc.

**Persistent (org-level)** — same regardless of project, pinned at the bottom:
`Skill Hub` (the catalog), `Connect Agent`, `Inbox` (your notifications, optionally
project-filterable), `Settings`. `Knowledge` is a judgement call — org-shared = here;
project docs = project-scoped (could be both).

Mechanically, project-scoped views filter by `currentProjectId`; persistent views
ignore it.

---

## 5. Recruitment (how a project gets its team)

```
Manual now:   In a project → "Recruit"/"Add role" → Skill Hub (search 154 roles)
              → pick a role → POST /projects/{id}/recruit → ProjectAgent created.

PM-driven (next): state a goal → the PM agent searches the catalog (GET /v1/roles)
              → proposes a LEAN team with a one-line rationale per role
              → human approves/tweaks → recruit the approved set.
```

Guardrails: **lean default** (recruit the minimum; quota + the shared-account limit
make over-staffing harmful); **grounded picks** (PM may only pick real `roleId`s the
search returns); **human approves** the PM's team in v1.

---

## 6. Backend data model

- `projects(id, workspace_id, name, goal, status, created_by, created_at, archived_at)`
  status ∈ recruiting | active | paused | done | archived  ✅
- `project_agents(id, project_id, role_id, agent_name, working_dir, status, created_at)`
  uniq (project_id, agent_name)  ✅
- `channels.project_id` — a thread filed under a project  ✅
- A2A tasks: scope by `context_id`/channel (add an optional `project_id` filter)  ⏳

## 7. API surface

- `GET /v1/roles?q&category&skill` — catalog search (for PM + Skill Hub)  ✅
- `POST /v1/projects` · `GET /v1/projects` · `GET /v1/projects/{id}` (team + threads)  ✅
- `POST /v1/projects/{id}/recruit` · `POST /v1/projects/{id}/agents/remove`  ✅
- `POST /v1/projects/{id}/archive`, delete-thread/archive (closes a real gap)  ⏳
- PM tooling: MCP `search_roles` / `propose_team` (so the PM works through tools)  ⏳

---

## 8. Status & remaining order

Done: role catalog API; Project + ProjectAgent + channels.project_id (migrations
027/028); recruit/remove; project switcher as the top header; sidebar roster scoped
to the project's team; "Add role" recruits into the active project; sidebar nav split
into Project vs Workspace groups; **Threads scoped** end-to-end (discover serializes
`project_id`, new threads filed under the active project); **Tasks/Review/Files
scoped** via `useProjectChannels()` (derive a channel→project link from the threads;
channel-less items show only under All projects); sidebar Review/Team badges scoped.

Next, in order:
1. **Scope the last two project panels** — Timeline (agent-lane based → filter lanes
   to the project's team roster) and Browser (filter tabs by their channel). Both use
   a different key than the channel→project derivation above. Routines similar (by
   `channelName`).
2. **PM recruitment loop** — `search_roles`/`propose_team` MCP tools + a
   propose→approve→recruit wizard on "New Project".
3. **Settle the isolation fork (§2)** — launcher provisioning of per-project runtimes
   (own working_dir), or pivot to project = workspace. This is the gate on whether
   "isolation" becomes real rather than logical.
4. **Polish** — delete/archive projects & threads; per-project quota/keys.

## 9. Open decisions (need a call)

- **Isolation fork (§2)**: project-within-workspace + launcher provisioning, vs
  project = workspace. Biggest one — decide before more UI.
- **Org rename / settings home**: moved out of the header; needs a settings entry.
- **Auto vs approved recruitment**: human approves the PM team in v1 — when (if ever)
  full auto?
- **Role library**: keep all 154, or curate to a sharper vetted set?
