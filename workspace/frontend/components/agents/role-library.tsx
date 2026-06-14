'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import {
  ROLE_TEMPLATES,
  ROLE_CATEGORIES,
  ROLE_MODELS,
  RUNTIMES,
  runtimeById,
  type RoleTemplate,
} from '@/lib/role-templates';

export function CategoryChip({ cat }: { cat: string }) {
  const c = ROLE_CATEGORIES[cat];
  if (!c) return null;
  return (
    <span
      className="inline-flex items-center text-[10.5px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ color: c.color, background: `${c.color}1f` }}
    >
      {c.label}
    </span>
  );
}

export function ModelBadge({ model }: { model: string }) {
  const m = ROLE_MODELS[model];
  if (!m) return null;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10.5px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded-[5px] whitespace-nowrap"
      title={m.label}
    >
      <span className="size-1.5 rounded-[2px]" style={{ background: m.tint }} />
      {m.short}
    </span>
  );
}

function RoleCard({
  role,
  joined,
  onAdd,
}: {
  role: RoleTemplate;
  joined: boolean;
  onAdd: (runtime: string) => void;
}) {
  const [open, setOpen] = useState(false);
  // A role's persona is runtime-agnostic — the runtime is chosen here, at add time.
  const [runtime, setRuntime] = useState(
    RUNTIMES.some((r) => r.id === role.model) ? role.model : 'claude',
  );
  const rt = runtimeById(runtime);
  const shownSkills = open ? role.skills : role.skills.slice(0, 4);
  return (
    <div
      className={cn(
        'flex flex-col gap-2.5 rounded-2xl border border-input bg-background p-3.5 transition-shadow hover:border-zinc-300 dark:hover:border-zinc-600 hover:shadow-[0_8px_22px_-12px_rgba(20,20,40,0.18)]',
        joined && 'opacity-70',
      )}
    >
      <div className="flex items-center gap-2.5">
        <AgentAvatar name={role.name} size={42} square />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-[15px] font-bold tracking-tight truncate">{role.name}</h3>
            <CategoryChip cat={role.cat} />
          </div>
          {/* Runtime is a choice, not a fixed property of the role. */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground">runs on</span>
            <div
              className="inline-flex items-center gap-1 bg-muted border border-border rounded-[5px] pl-1.5 pr-1 py-0.5"
              title={rt ? `${rt.hint}${rt.personaFidelity === 'full' ? ' · full persona' : ' · persona varies by runtime'}` : ''}
            >
              <span className="size-1.5 rounded-[2px]" style={{ background: rt?.tint }} />
              <select
                value={runtime}
                onChange={(e) => setRuntime(e.target.value)}
                className="text-[10.5px] font-mono bg-transparent text-muted-foreground outline-none cursor-pointer"
              >
                {RUNTIMES.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </select>
            </div>
            {rt?.personaFidelity === 'partial' && (
              <span className="text-[9.5px] text-amber-600 dark:text-amber-400" title="This runtime may not inject the role's full persona (CLAUDE.md) — Claude does.">
                persona varies
              </span>
            )}
          </div>
        </div>
      </div>

      <p className="text-[12.5px] leading-relaxed text-muted-foreground">{role.tagline}</p>

      <div className="flex flex-wrap gap-1.5">
        {shownSkills.map((s) => (
          <span
            key={s}
            className="text-[10.5px] font-medium text-zinc-600 dark:text-zinc-300 bg-muted border border-border rounded-md px-2 py-0.5"
          >
            {s}
          </span>
        ))}
        {!open && role.skills.length > 4 && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="text-[10.5px] font-medium text-primary bg-muted border border-border rounded-md px-2 py-0.5"
          >
            +{role.skills.length - 4}
          </button>
        )}
      </div>

      {open && (
        <div className="flex flex-col gap-1.5">
          {role.abilities.map((a, i) => (
            <div key={i} className="flex gap-2 text-[11.5px] leading-snug text-muted-foreground">
              <span className="mt-1.5 size-[5px] shrink-0 rounded-full bg-indigo-500" />
              {a}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-0.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs font-semibold text-muted-foreground hover:text-foreground rounded-lg px-2.5 py-1.5 hover:bg-muted transition-colors"
        >
          {open ? 'Less' : 'Abilities'}
        </button>
        <button
          type="button"
          onClick={() => onAdd(runtime)}
          disabled={joined}
          className={cn(
            'text-[12.5px] font-semibold rounded-lg px-3 py-1.5 transition-colors',
            joined
              ? 'bg-muted text-muted-foreground cursor-default'
              : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-[0_2px_8px_-3px_var(--primary)]',
          )}
        >
          {joined ? '✓ Added' : '+ Add to workspace'}
        </button>
      </div>
    </div>
  );
}

export function RoleLibrary({
  open,
  onOpenChange,
  joinedNames,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  joinedNames: Set<string>;
  onAdd: (role: RoleTemplate, runtime: string) => void;
}) {
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('all');

  const filtered = useMemo(
    () =>
      ROLE_TEMPLATES.filter((r) => {
        if (cat !== 'all' && r.cat !== cat) return false;
        if (!q) return true;
        return (r.name + r.tagline + r.skills.join('')).toLowerCase().includes(q.toLowerCase());
      }),
    [cat, q],
  );

  const catList = [{ id: 'all', label: 'All' }, ...Object.values(ROLE_CATEGORIES)];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-none w-[min(1060px,96vw)] max-h-[86vh] p-0 gap-0 overflow-hidden rounded-2xl">
        {/* Header */}
        <div className="px-[22px] pt-5 pb-3.5">
          <DialogTitle className="text-[19px] font-bold tracking-tight">Add a role</DialogTitle>
          <DialogDescription className="mt-1 text-[12.5px]">
            Pick a role template to spin up a new agent in this workspace · {ROLE_TEMPLATES.length} available
          </DialogDescription>
        </div>

        {/* Tools */}
        <div className="flex flex-wrap items-center gap-3 px-[22px] pb-3.5">
          <div className="flex flex-1 max-w-[340px] min-w-[240px] items-center gap-2 rounded-lg bg-muted border border-input px-3 py-2 text-muted-foreground">
            <Search className="size-[15px] shrink-0" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search roles, specialties, skills..."
              autoFocus
              className="flex-1 min-w-0 border-0 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {catList.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCat(c.id)}
                className={cn(
                  'text-xs font-medium rounded-lg px-3 py-1.5 border transition-colors',
                  cat === c.id
                    ? 'text-foreground bg-zinc-200 dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 font-semibold'
                    : 'text-muted-foreground border-input hover:text-foreground hover:bg-muted',
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* Grid */}
        <div className="grid gap-3 overflow-y-auto px-[22px] pb-[22px] pt-1 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]">
          {filtered.map((r) => (
            <RoleCard
              key={r.id}
              role={r}
              joined={joinedNames.has(r.name.toLowerCase())}
              onAdd={(runtime) => onAdd(r, runtime)}
            />
          ))}
          {filtered.length === 0 && (
            <div className="col-span-full text-center text-[13px] text-muted-foreground py-12">
              No roles match your search.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
