'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, Plus, Check } from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '@/lib/workspace-context';
import { useOpenAgentsAuth } from '@/lib/openagents-auth-context';
import { workspaceApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { Workspace } from '@/lib/types';

// In the project=workspace model each workspace IS a project: its own agents,
// threads and isolated runtime. This switcher moves between them. Switching is a
// full navigation to /<slug> so the WorkspaceProvider re-initialises cleanly.
// Under Firebase auth the bearer token authorises every owned workspace; for
// local/token auth we re-attach a per-slug token stashed in this browser (we
// only have a workspace's token at create time or for the one we're in now).

const TOKEN_STORE = 'oa_ws_tokens';

function readTokens(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(TOKEN_STORE) || '{}'); } catch { return {}; }
}
function stashToken(slug: string, token: string) {
  try {
    const m = readTokens();
    if (m[slug] === token) return;
    m[slug] = token;
    localStorage.setItem(TOKEN_STORE, JSON.stringify(m));
  } catch { /* ignore quota/availability */ }
}
function navigateTo(slug: string) {
  const t = readTokens()[slug];
  window.location.href = t ? `/${slug}?token=${encodeURIComponent(t)}` : `/${slug}`;
}

export function WorkspaceSwitcher() {
  const { workspace, token, agents } = useWorkspace();
  const { user } = useOpenAgentsAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  // Remember the current workspace's token so we can navigate back to it later
  // (local/token auth). Harmless under Firebase auth.
  useEffect(() => {
    if (workspace?.slug && token) stashToken(workspace.slug, token);
  }, [workspace?.slug, token]);

  const load = useCallback(async () => {
    try { setWorkspaces(await workspaceApi.listWorkspaces(user?.email)); } catch { /* best-effort */ }
  }, [user?.email]);
  useEffect(() => { if (open) load(); }, [open, load]);

  async function create() {
    const n = name.trim();
    if (!n || busy) return;
    setBusy(true);
    try {
      const ws = await workspaceApi.createWorkspace({ name: n, creatorEmail: user?.email });
      stashToken(ws.slug, ws.token);
      toast.success(`Workspace "${ws.name}" created`);
      navigateTo(ws.slug);  // full navigation into the new (isolated) workspace
    } catch (e) {
      toast.error(`Could not create workspace: ${e instanceof Error ? e.message : 'unknown error'}`);
      setBusy(false);
    }
  }

  const currentName = workspace?.name || 'Workspace';
  const onlineCount = agents.filter((a) => a.status === 'online').length;

  return (
    <div className="relative flex-1 min-w-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-muted/60 transition-colors text-left"
      >
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-semibold truncate">{currentName}</span>
          <span className="block text-[11px] text-muted-foreground truncate">
            {onlineCount}/{agents.length} agents{workspace?.slug ? ` · ${workspace.slug}` : ''}
          </span>
        </span>
        <ChevronDown className={cn('size-4 text-muted-foreground shrink-0 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => { setOpen(false); setCreating(false); }} />
          <div className="absolute z-30 left-0 right-0 mt-1 rounded-lg border border-border bg-popover shadow-lg p-1 max-h-[60vh] overflow-y-auto">
            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Projects</div>
            {workspaces.map((w) => (
              <button
                key={w.workspaceId}
                onClick={() => { if (w.slug === workspace?.slug) { setOpen(false); return; } navigateTo(w.slug); }}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] hover:bg-muted text-left"
              >
                <span className="flex-1 min-w-0 truncate">{w.name}</span>
                <span className="text-[10px] text-muted-foreground shrink-0">{w.agents.length}</span>
                {w.slug === workspace?.slug && <Check className="size-3.5 text-primary shrink-0" />}
              </button>
            ))}
            {workspaces.length === 0 && (
              <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No other projects yet</div>
            )}
            <div className="border-t border-border my-1" />
            {!creating ? (
              <button
                onClick={() => setCreating(true)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] text-primary hover:bg-muted text-left font-medium"
              >
                <Plus className="size-3.5" /> New Project
              </button>
            ) : (
              <div className="p-1.5 space-y-1.5">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Project name"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') create(); if (e.key === 'Escape') setCreating(false); }}
                  className="w-full h-7 text-[12px] rounded-md bg-muted/50 border border-border px-2 outline-none focus:ring-1 focus:ring-primary/40"
                />
                <div className="flex gap-1.5">
                  <button onClick={create} disabled={busy || !name.trim()} className="flex-1 h-7 text-[12px] rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90">
                    {busy ? 'Creating…' : 'Create'}
                  </button>
                  <button onClick={() => { setCreating(false); setName(''); }} className="h-7 px-2 text-[12px] rounded-md border border-border hover:bg-muted">
                    Cancel
                  </button>
                </div>
                <p className="text-[10px] text-muted-foreground leading-snug px-0.5">
                  Creates a new isolated workspace with its own agents and threads.
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
