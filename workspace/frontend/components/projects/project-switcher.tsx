'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, Plus, FolderKanban, Check } from 'lucide-react';
import { useLayout } from '@/components/layout/layout-context';
import { workspaceApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { Project } from '@/lib/types';

/** Project mode: switch the active project (or "All projects"), and create one.
 *  The active project scopes the threads/roster (project-scoped views are wired
 *  incrementally). */
export function ProjectSwitcher() {
  const { currentProjectId, setCurrentProjectId } = useLayout();
  const [projects, setProjects] = useState<Project[]>([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setProjects((await workspaceApi.listProjects()).projects); } catch { /* best-effort */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const current = projects.find((p) => p.id === currentProjectId) || null;

  async function create() {
    const n = name.trim();
    if (!n || busy) return;
    setBusy(true);
    try {
      const p = await workspaceApi.createProject({ name: n, goal: goal.trim() || undefined });
      setName(''); setGoal(''); setCreating(false); setOpen(false);
      await load();
      setCurrentProjectId(p.id);
    } finally { setBusy(false); }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-muted/60 transition-colors text-left"
      >
        <span className="size-6 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
          <FolderKanban className="size-3.5" />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-[12px] font-semibold truncate">{current ? current.name : 'All projects'}</span>
          <span className="block text-[10px] text-muted-foreground truncate">
            {current ? `${current.threadCount} threads · ${current.team.length} members` : `${projects.length} project${projects.length === 1 ? '' : 's'}`}
          </span>
        </span>
        <ChevronDown className={cn('size-3.5 text-muted-foreground transition-transform shrink-0', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute z-30 left-0 right-0 mt-1 rounded-lg border border-border bg-popover shadow-lg p-1 max-h-[60vh] overflow-y-auto">
          <button
            onClick={() => { setCurrentProjectId(null); setOpen(false); }}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] hover:bg-muted text-left"
          >
            <span className="flex-1">All projects</span>
            {!currentProjectId && <Check className="size-3.5 text-primary" />}
          </button>
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => { setCurrentProjectId(p.id); setOpen(false); }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] hover:bg-muted text-left"
            >
              <span className="flex-1 min-w-0 truncate">{p.name}</span>
              <span className="text-[10px] text-muted-foreground shrink-0">{p.threadCount}</span>
              {p.id === currentProjectId && <Check className="size-3.5 text-primary shrink-0" />}
            </button>
          ))}
          <div className="border-t border-border my-1" />
          {!creating ? (
            <button
              onClick={() => setCreating(true)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] text-primary hover:bg-muted text-left"
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
                onKeyDown={(e) => { if (e.key === 'Enter') create(); }}
                className="w-full h-7 text-[12px] rounded-md bg-muted/50 border border-border px-2 outline-none focus:ring-1 focus:ring-primary/40"
              />
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Goal (optional)"
                onKeyDown={(e) => { if (e.key === 'Enter') create(); }}
                className="w-full h-7 text-[12px] rounded-md bg-muted/50 border border-border px-2 outline-none focus:ring-1 focus:ring-primary/40"
              />
              <div className="flex gap-1.5">
                <button onClick={create} disabled={busy || !name.trim()} className="flex-1 h-7 text-[12px] rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90">
                  Create
                </button>
                <button onClick={() => { setCreating(false); setName(''); setGoal(''); }} className="h-7 px-2 text-[12px] rounded-md border border-border hover:bg-muted">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
