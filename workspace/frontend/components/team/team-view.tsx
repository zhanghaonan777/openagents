'use client';

import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Users, RefreshCw, HelpCircle, Eye, MessageSquareWarning, Lock, AlertTriangle, ArrowRight, Network, Inbox } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { timeAgoShort as timeAgo } from '@/lib/helpers';
import { taskRequestText, taskStatusMeta } from '@/lib/a2a';
import { TaskDetail } from '@/components/tasks/task-detail';
import type { A2ATask, WorkspaceAgent } from '@/lib/types';

const ACTIVE_STATES = ['submitted', 'working', 'input-required'];

type AttnKind = 'clarify' | 'review' | 'rework' | 'blocked' | 'failed';
interface AttnItem { task: A2ATask; kind: AttnKind; label: string }

const KIND_META: Record<AttnKind, { Icon: typeof Eye; label: string; cls: string }> = {
  clarify: { Icon: HelpCircle, label: 'Needs input', cls: 'text-amber-700 bg-amber-500/12 dark:text-amber-300' },
  rework: { Icon: MessageSquareWarning, label: 'Rework', cls: 'text-red-700 bg-red-500/12 dark:text-red-300' },
  review: { Icon: Eye, label: 'Review', cls: 'text-amber-700 bg-amber-500/12 dark:text-amber-300' },
  blocked: { Icon: Lock, label: 'Blocked', cls: 'text-amber-700 bg-amber-500/12 dark:text-amber-300' },
  failed: { Icon: AlertTriangle, label: 'Failed', cls: 'text-red-700 bg-red-500/12 dark:text-red-300' },
};
const KIND_ORDER: Record<AttnKind, number> = { clarify: 0, rework: 1, review: 2, blocked: 3, failed: 4 };

/** A task is "done enough" to unblock others once completed or approved. */
function resolvedMap(tasks: A2ATask[]): Map<string, boolean> {
  return new Map(tasks.map((t) => [t.id, t.state === 'completed' || t.review?.state === 'approved']));
}

/** Team HQ: who's doing what right now, what needs a human, and the dependency
 *  graph across the board — the cross-cutting view the kanban can't give. */
export function TeamView() {
  const { agents, a2aTasks, refreshA2ATasks } = useWorkspace();
  const [detailId, setDetailId] = useState<string | null>(null);
  const detailTask = detailId ? a2aTasks.find((t) => t.id === detailId) || null : null;

  useEffect(() => { refreshA2ATasks(); }, [refreshA2ATasks]);

  const resolved = useMemo(() => resolvedMap(a2aTasks), [a2aTasks]);

  // Each member with their current focus + open workload, online first.
  const members = useMemo(() => {
    const rank = (a: WorkspaceAgent) => (a.status === 'online' ? 0 : 1);
    return [...agents]
      .sort((a, b) => rank(a) - rank(b) || a.agentName.localeCompare(b.agentName))
      .map((agent) => {
        const open = a2aTasks.filter((t) => t.contractorName === agent.agentName && !t.deleted && ACTIVE_STATES.includes(t.state));
        const now = open.find((t) => t.state === 'working') || open.find((t) => t.state === 'input-required') || open[0] || null;
        return { agent, now, openCount: open.length };
      });
  }, [agents, a2aTasks]);

  const onlineCount = members.filter((m) => m.agent.status === 'online').length;

  // The "needs a human" queue — one entry per task, highest-urgency reason wins.
  const attention = useMemo<AttnItem[]>(() => {
    const items: AttnItem[] = [];
    for (const t of a2aTasks) {
      if (t.deleted) continue;
      if (t.clarification) items.push({ task: t, kind: 'clarify', label: t.clarification.question || 'Needs your input' });
      else if (t.review?.state === 'changes_requested') items.push({ task: t, kind: 'rework', label: t.review.comment || 'Changes requested' });
      else if (t.review?.state === 'pending') items.push({ task: t, kind: 'review', label: `Review ${t.contractorName}'s deliverable` });
      else if ((t.blockedBy || []).some((id) => !resolved.get(id))) items.push({ task: t, kind: 'blocked', label: 'Waiting on unfinished work' });
      else if (t.state === 'failed' || t.state === 'rejected') items.push({ task: t, kind: 'failed', label: 'Ended without completing' });
    }
    return items.sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
  }, [a2aTasks, resolved]);

  // Dependency edges: blocker → dependent (skip soft-deleted endpoints).
  const edges = useMemo(() => {
    const byId = new Map(a2aTasks.map((t) => [t.id, t]));
    const out: { blocker: A2ATask; dependent: A2ATask }[] = [];
    for (const t of a2aTasks) {
      if (t.deleted) continue;
      for (const id of t.blockedBy || []) {
        const blocker = byId.get(id);
        if (blocker && !blocker.deleted) out.push({ blocker, dependent: t });
      }
    }
    return out;
  }, [a2aTasks]);

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center gap-2">
        <Users className="size-4 text-indigo-500 shrink-0" />
        <h2 className="text-sm font-semibold">Team</h2>
        <span className="text-[11px] text-muted-foreground">{onlineCount}/{members.length} online</span>
        <button onClick={refreshA2ATasks} className="ml-auto p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-muted-foreground" title="Refresh">
          <RefreshCw className="size-3.5" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-6">
        {/* Now — live member focus */}
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">Working now</h3>
          {members.length === 0 ? (
            <p className="text-[12.5px] text-muted-foreground/70">No agents in this workspace yet.</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {members.map(({ agent, now, openCount }) => {
                const online = agent.status === 'online';
                const m = now ? taskStatusMeta(now.state) : null;
                return (
                  <button
                    key={agent.agentName}
                    onClick={() => now && setDetailId(now.id)}
                    disabled={!now}
                    className={cn(
                      'text-left bg-background border border-border rounded-lg p-2.5 transition-colors',
                      now ? 'hover:border-primary/40 cursor-pointer' : 'cursor-default',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <AgentAvatar name={agent.agentName} size={26} status={agent.status} showStatus className={cn(!online && 'opacity-60')} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[12.5px] font-medium truncate">{agent.agentName}</div>
                        <div className="text-[10.5px] text-muted-foreground truncate">
                          {online ? 'online' : agent.lastHeartbeatAt ? `seen ${timeAgo(agent.lastHeartbeatAt)}` : 'offline'}
                          {openCount > 0 && ` · ${openCount} open`}
                        </div>
                      </div>
                    </div>
                    {now ? (
                      <div className="mt-2 flex items-start gap-1.5">
                        {m && <span className="mt-[3px] size-1.5 rounded-full shrink-0" style={{ background: m.dot }} />}
                        <span className="text-[11.5px] leading-snug text-foreground/80 line-clamp-2">{taskRequestText(now)}</span>
                      </div>
                    ) : (
                      <div className="mt-2 text-[11px] text-muted-foreground/60">idle</div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* Needs attention */}
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
            <Inbox className="size-3" /> Needs attention
            {attention.length > 0 && <span className="font-mono text-muted-foreground/60">{attention.length}</span>}
          </h3>
          {attention.length === 0 ? (
            <p className="text-[12.5px] text-muted-foreground/70">All clear — nothing waiting on you.</p>
          ) : (
            <ul className="space-y-1.5">
              {attention.map(({ task, kind, label }) => {
                const { Icon, label: kindLabel, cls } = KIND_META[kind];
                return (
                  <li key={task.id}>
                    <button
                      onClick={() => setDetailId(task.id)}
                      className="w-full text-left flex items-center gap-2.5 bg-background border border-border rounded-lg px-3 py-2 hover:border-primary/40 transition-colors"
                    >
                      <span className={cn('inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0', cls)}>
                        <Icon className="size-2.5" /> {kindLabel}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[12.5px] truncate">{taskRequestText(task)}</div>
                        <div className="text-[10.5px] text-muted-foreground truncate">{label}</div>
                      </div>
                      <AgentAvatar name={task.contractorName} size={18} className="shrink-0" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Dependencies */}
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
            <Network className="size-3" /> Dependencies
            {edges.length > 0 && <span className="font-mono text-muted-foreground/60">{edges.length}</span>}
          </h3>
          {edges.length === 0 ? (
            <p className="text-[12.5px] text-muted-foreground/70">No dependencies between tasks.</p>
          ) : (
            <ul className="space-y-1.5">
              {edges.map(({ blocker, dependent }, i) => {
                const bm = taskStatusMeta(blocker.state);
                const dm = taskStatusMeta(dependent.state);
                const cleared = resolved.get(blocker.id);
                return (
                  <li key={i} className="flex items-center gap-2 bg-background border border-border rounded-lg px-3 py-2 text-[12px]">
                    <button onClick={() => setDetailId(blocker.id)} className="min-w-0 flex-1 flex items-center gap-1.5 hover:underline">
                      <span className="size-1.5 rounded-full shrink-0" style={{ background: bm.dot }} />
                      <span className={cn('truncate', cleared && 'line-through text-muted-foreground')}>{taskRequestText(blocker)}</span>
                    </button>
                    <ArrowRight className={cn('size-3.5 shrink-0', cleared ? 'text-emerald-500' : 'text-amber-500')} />
                    <button onClick={() => setDetailId(dependent.id)} className="min-w-0 flex-1 flex items-center gap-1.5 hover:underline">
                      <span className="size-1.5 rounded-full shrink-0" style={{ background: dm.dot }} />
                      <span className="truncate">{taskRequestText(dependent)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      {detailTask && (
        <TaskDetail task={detailTask} onClose={() => setDetailId(null)} onChanged={refreshA2ATasks} />
      )}
    </div>
  );
}
