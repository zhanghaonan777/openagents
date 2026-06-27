# Project mode — design (finalized: project = workspace)

A **project IS a workspace**. Each project is a self-contained workspace with its
own agents, threads, tasks and — crucially — its own **isolated runtime** (the
daemon already binds agents per-network/workspace, with per-agent working dirs).
You are always inside exactly one project; you switch between projects the way you
switch Slack workspaces. There is no cross-project "All" view and no org layer
above projects — projects are top-level siblings.

This supersedes the earlier project-within-workspace design (option A). The history
below records why.

---

## 1. Why project = workspace (the decision)

Two ways to make "project" the top-level isolated unit were on the table:

- **A — project within a workspace** (`Project`/`ProjectAgent` rows, `channels.
  project_id`): one org dashboard spans projects, but **isolation is only logical**
  — recruited roles still map to the single shared workspace runtime. Real runtime
  isolation (separate processes, own working dirs, own quota) would have to be built
  from scratch in the launcher.
- **B — project = its own workspace** ✅ **chosen**: reuses the daemon's existing
  per-workspace agent binding, so **runtime isolation is real and essentially free**
  — two projects get genuinely separate agent runtimes and working dirs. The cost is
  no single dashboard spanning projects, which is fine: the product intentionally has
  **no "All projects" firehose** (you're always in one project, like Linear/Jira/
  Vercel/Slack).

The user's own instinct — "there shouldn't be an All-projects view, just project 1/
2/3" — is exactly what separate workspaces already are, which is what made B the
clear call.

---

## 2. Model & hierarchy

```
Account (a user, by email — owns/collaborates on workspaces)
  └── Project = Workspace   ← top-level, isolated unit you operate inside
        ├── Agents     — the workspace's own team (daemon-bound, own working dirs)
        ├── Threads    — channels in this workspace
        ├── Tasks / Review / Timeline / Files / Browser / Routines
        └── Skill Hub / Connect Agent / Inbox / Settings (per-workspace)
```

Switching projects = navigating to another workspace (`/<slug>`). Creating a project
= creating a new workspace (`POST /v1/workspaces`), which spins up a fresh isolated
runtime context. Recruiting from the role catalog ("Add role") adds an agent to the
current workspace's team via the launcher.

Isolation is now **real (runtime)**, not just logical — that was the whole point of B.

---

## 3. What's built

- **Workspace switcher** (`components/workspace/workspace-switcher.tsx`) replaces the
  old project switcher as the sidebar header: lists the account's workspaces
  (`GET /v1/workspaces?creator_email=`), switches by full-navigating to `/<slug>`,
  and "+ New Project" creates an isolated workspace (`POST /v1/workspaces`) and
  navigates into it.
- **Auth on switch**: under Firebase auth the bearer token authorises every owned
  workspace, so `/<slug>` just works. For local/token auth there's no account, so the
  switcher stashes each workspace's token (from create-time, or the current one) in
  `localStorage` and re-attaches it as `?token=` on navigation.
- **Backend already had everything**: `POST /v1/workspaces` (create → slug+token),
  `GET /v1/workspaces` (list), claim, collaborators, and the daemon's per-network
  agent binding (`~/.openagents/daemon.yaml` `networks[]`, `agent.network=slug`,
  per-agent `working_dir`). No backend changes were needed for the pivot.
- **Removed** the now-vestigial A-frontend: project switcher, `useProjectChannels`
  scoping, `currentProjectId` plumbing, the orphan-thread reconcile, the dead project
  API methods + types. Each workspace is self-contained, so nothing needs filtering.

The sidebar nav keeps its two groups: **Collaboration** (Threads/Tasks/Team/Review/
Timeline/Files/Browser/Routines) and the persistent **Workspace** group (Skill Hub/
Knowledge/Inbox) + Connect Agent — all scoped to the current workspace by definition.

---

## 4. Follow-ups (not yet done)

1. **List collaborator workspaces too.** `GET /v1/workspaces?creator_email=` returns
   only owned workspaces; the switcher should also show ones the user collaborates on
   (needs an owner+collaborator aggregation, or a second query).
2. **Drop the dead A tables.** `Project`, `ProjectAgent`, `channels.project_id`,
   `routers/projects.py` and the discover `project_id` serialization are left in place
   (unused, harmless) — remove them in a non-destructive migration once B is settled.
3. **Create-workspace UX.** First-run / empty-account state ("create your first
   project"); optionally seed a default agent on create (`POST /v1/workspaces` takes
   an `agent_name`).
4. **Local-dev switching** only reaches workspaces whose token this browser has seen
   (created or visited). Fine for dev; the product path is Firebase auth. Could add a
   dev-only "paste token" entry if needed.
5. **Recruit = real launcher join.** "Add role" currently toasts the launcher command
   (`agn create … + connect`); wiring it to actually provision the agent into the
   workspace is the remaining launcher integration — now meaningful because the
   runtime is genuinely isolated per workspace.

---

## 5. Role catalog (unchanged, still used)

154 roles, 10 categories (`backend/app/data/roles.json`, `GET /v1/roles?q&category&
skill`), surfaced in the Skill Hub. This is what "Add role" recruits from. A PM-style
recruiter that proposes a lean team from a goal (search → propose → human approves →
recruit) remains a good future addition, now scoped to a single workspace's team.
