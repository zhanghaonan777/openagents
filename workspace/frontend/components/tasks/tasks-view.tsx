'use client';

import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { ListTodo, RefreshCw, Eye, Check, MessageSquareWarning, BadgeCheck, Lock, Link2, MessageSquare, Search, Plus, ArrowDownUp, Bell, Ban, HelpCircle } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { useLayout } from '@/components/layout/layout-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { DelegateDialog } from '@/components/agents/delegate-dialog';
import { colorFromName } from '@/lib/role-templates';
import { timeAgoShort as timeAgo } from '@/lib/helpers';
import { taskRequestText, taskArtifactText } from '@/lib/a2a';
import { workspaceApi } from '@/lib/api';
import { TaskDetail } from './task-detail';
import type { A2ATask, A2ATaskState, TaskReviewState } from '@/lib/types';

/** A task is blocked when any task it waits on isn't finished/approved yet. */
function buildBlockedSet(tasks: A2ATask[]): Set<string> {
  const resolved = new Map(tasks.map((t) => [t.id, t.state === 'completed' || t.review?.state === 'approved']));
  const blocked = new Set<string>();
  for (const t of tasks) {
    if ((t.blockedBy || []).some((id) => !resolved.get(id))) blocked.add(t.id);
  }
  return blocked;
}

type SortKey = 'recent' | 'oldest' | 'agent';

/** Review overlay → which board column the card belongs in. A pending review
 *  pulls the card into Review; an approved one into Approved — regardless of
 *  the underlying protocol state. */
function columnOf(t: A2ATask, cols: typeof BOARD_COLS): string {
  if (t.review?.state === 'pending') return 'review';
  if (t.review?.state === 'approved') return 'approved';
  return cols.find((c) => c.states.includes(t.state))?.id ?? 'done';
}

const REVIEW_BADGE: Record<TaskReviewState, { label: string; cls: string }> = {
  pending: { label: 'In review', cls: 'text-amber-700 bg-amber-500/15 dark:text-amber-300' },
  approved: { label: 'Approved', cls: 'text-emerald-700 bg-emerald-500/15 dark:text-emerald-300' },
  changes_requested: { label: 'Changes requested', cls: 'text-red-700 bg-red-500/15 dark:text-red-300' },
};

/** Kanban columns mapped to A2A TaskState (5-column flow like agent-teams). */
const BOARD_COLS: { id: string; label: string; dot: string; states: A2ATaskState[] }[] = [
  { id: 'submitted', label: 'To Do', dot: '#a1a1aa', states: ['submitted'] },
  { id: 'working', label: 'In Progress', dot: '#3b82f6', states: ['working'] },
  { id: 'review', label: 'Review', dot: '#f59e0b', states: ['input-required'] },
  { id: 'done', label: 'Done', dot: '#22c55e', states: ['completed', 'failed', 'canceled', 'rejected'] },
  { id: 'approved', label: 'Approved', dot: '#10b981', states: [] },
];

function TaskCard({ task, flash, blocked, onOpen, onChanged }: { task: A2ATask; flash: boolean; blocked: boolean; onOpen: () => void; onChanged: () => void }) {
  const who = task.contractorName;
  const railColor = colorFromName(who);
  const terminal = ['completed', 'failed', 'canceled', 'rejected'].includes(task.state);
  const failed = task.state === 'failed' || task.state === 'rejected' || task.state === 'canceled';
  // The contractor's deliverable, reported via the A2A task status (artifact).
  const artifactText = taskArtifactText(task);
  const review = task.review || null;
  const commentCount = task.comments?.length || 0;
  const blockedByCount = task.blockedBy?.length || 0;
  const blocksCount = task.blocks?.length || 0;
  const needsInput = !!task.clarification;
  // Review can be requested once there's something to review and the delegator
  // is an agent (the default reviewer); offered on working/completed tasks.
  const canRequestReview = !review && task.delegator.startsWith('openagents:') &&
    (task.state === 'working' || task.state === 'completed');
  const [busy, setBusy] = useState(false);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); onChanged(); } finally { setBusy(false); }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      draggable
      onDragStart={(e) => { e.dataTransfer.setData('text/plain', task.id); e.dataTransfer.effectAllowed = 'move'; }}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
      style={{ borderLeftColor: railColor }}
      className={cn(
        'w-full text-left bg-background border border-border border-l-[3px] rounded-lg p-2.5 shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_16px_-8px_rgba(20,20,40,0.16)] cursor-pointer',
        flash && 'ring-2 ring-primary/45',
      )}
    >
      <p className={cn('text-[12.5px] leading-snug text-pretty mb-2.5', terminal && 'text-muted-foreground', failed && 'line-through')}>
        {taskRequestText(task)}
      </p>
      {artifactText && (
        <div
          title={artifactText}
          className="mb-2.5 text-[11px] leading-snug text-foreground/75 bg-muted/60 border border-border/60 rounded-md px-2 py-1.5 whitespace-pre-wrap line-clamp-4"
        >
          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">Result · </span>
          {artifactText}
        </div>
      )}

      {/* Review overlay: badge + (optional) reviewer feedback */}
      {review && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className={cn('inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded', REVIEW_BADGE[review.state].cls)}>
            <BadgeCheck className="size-3" />
            {REVIEW_BADGE[review.state].label}
            {review.reviewer && <span className="font-normal opacity-80">· {review.reviewer}</span>}
          </span>
          {review.comment && review.state !== 'pending' && (
            <span className="text-[10.5px] text-muted-foreground italic truncate max-w-full">“{review.comment}”</span>
          )}
        </div>
      )}

      {/* Live signals: needs-input / blocked / dependencies / comments */}
      {(needsInput || blocked || blockedByCount > 0 || blocksCount > 0 || commentCount > 0) && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px]">
          {needsInput && (
            <span className="inline-flex items-center gap-1 font-semibold px-1.5 py-0.5 rounded text-amber-700 bg-amber-500/20 dark:text-amber-300" title={task.clarification?.question}>
              <HelpCircle className="size-2.5" /> Needs input
            </span>
          )}
          {blocked && !terminal && (
            <span className="inline-flex items-center gap-1 font-semibold px-1.5 py-0.5 rounded text-amber-700 bg-amber-500/15 dark:text-amber-300">
              <Lock className="size-2.5" /> Blocked
            </span>
          )}
          {blockedByCount > 0 && (
            <span className="inline-flex items-center gap-0.5 text-muted-foreground" title={`Blocked by ${blockedByCount} task(s)`}>
              <Link2 className="size-2.5" /> {blockedByCount}
            </span>
          )}
          {blocksCount > 0 && (
            <span className="inline-flex items-center gap-0.5 text-muted-foreground" title={`Blocks ${blocksCount} task(s)`}>
              <Link2 className="size-2.5 rotate-90" /> {blocksCount}
            </span>
          )}
          {commentCount > 0 && (
            <span className="inline-flex items-center gap-0.5 text-muted-foreground" title={`${commentCount} comment(s)`}>
              <MessageSquare className="size-2.5" /> {commentCount}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 min-w-0 text-[11px] text-muted-foreground">
          <AgentAvatar name={who} size={18} />
          <span className="truncate">{who}</span>
        </span>
        <span className="text-[10.5px] font-mono text-muted-foreground/70 shrink-0">
          {timeAgo(task.updatedAt || task.createdAt)}
          {failed && task.state !== 'canceled' && ` · ${task.state}`}
        </span>
      </div>

      {/* Review + coordination actions */}
      {(canRequestReview || review?.state === 'pending' || !terminal) && (
        <div className="mt-2 pt-2 border-t border-border/60 flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          {canRequestReview && (
            <button
              disabled={busy}
              onClick={() => act(() => workspaceApi.requestA2AReview(task.id))}
              className="inline-flex items-center gap-1 text-[10.5px] font-medium px-2 py-1 rounded-md border border-border hover:bg-muted text-foreground/80 disabled:opacity-50"
            >
              <Eye className="size-3" /> Request review
            </button>
          )}
          {review?.state === 'pending' && (
            <>
              <button
                disabled={busy}
                onClick={() => act(() => workspaceApi.approveA2AReview(task.id))}
                className="inline-flex items-center gap-1 text-[10.5px] font-medium px-2 py-1 rounded-md border border-emerald-300 dark:border-emerald-900/60 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-50"
              >
                <Check className="size-3" /> Approve
              </button>
              <button
                disabled={busy}
                onClick={() => {
                  const comment = window.prompt('What changes are needed?') || undefined;
                  act(() => workspaceApi.requestA2AReviewChanges(task.id, { comment }));
                }}
                className="inline-flex items-center gap-1 text-[10.5px] font-medium px-2 py-1 rounded-md border border-red-300 dark:border-red-900/60 text-red-700 dark:text-red-400 hover:bg-red-500/10 disabled:opacity-50"
              >
                <MessageSquareWarning className="size-3" /> Changes
              </button>
            </>
          )}
          {/* Always-available coordination on a live task */}
          {!terminal && (
            <div className="ml-auto flex items-center gap-1.5">
              <button
                disabled={busy}
                onClick={() => act(() => workspaceApi.nudgeA2ATask(task.id))}
                className="inline-flex items-center gap-1 text-[10.5px] font-medium px-1.5 py-1 rounded-md text-muted-foreground hover:bg-muted disabled:opacity-50"
                title="Nudge the agent"
              >
                <Bell className="size-3" />
              </button>
              <button
                disabled={busy}
                onClick={() => { if (window.confirm('Cancel this task?')) act(() => workspaceApi.cancelA2ATask(task.id)); }}
                className="inline-flex items-center gap-1 text-[10.5px] font-medium px-1.5 py-1 rounded-md text-muted-foreground hover:text-red-500 hover:bg-red-500/10 disabled:opacity-50"
                title="Cancel task"
              >
                <Ban className="size-3" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function TasksView() {
  const { a2aTasks, refreshA2ATasks, agents, currentUser } = useWorkspace();
  const { flashTaskId } = useLayout();
  const [detailId, setDetailId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [ownerFilter, setOwnerFilter] = useState<string>('all');
  const [sort, setSort] = useState<SortKey>('recent');
  const [delegateOpen, setDelegateOpen] = useState(false);
  const [dragOverCol, setDragOverCol] = useState<string | null>(null);
  const detailTask = detailId ? a2aTasks.find((t) => t.id === detailId) || null : null;

  // Drag-and-drop the *review workflow* (the human-driven transitions). Dragging
  // a card onto a column maps to a review action; protocol-driven columns (the
  // agent owns submitted→working→done) ignore drops that would force state.
  async function handleDrop(colId: string, taskId: string) {
    setDragOverCol(null);
    const t = a2aTasks.find((x) => x.id === taskId);
    if (!t || columnOf(t, BOARD_COLS) === colId) return;
    let action: (() => Promise<unknown>) | null = null;
    if (colId === 'review' && !t.review && (t.state === 'working' || t.state === 'completed')) {
      action = () => workspaceApi.requestA2AReview(t.id);
    } else if (colId === 'approved' && t.review?.state === 'pending') {
      action = () => workspaceApi.approveA2AReview(t.id);
    } else if ((colId === 'submitted' || colId === 'working') && t.review?.state === 'pending') {
      const comment = window.prompt('What changes are needed?') || undefined;
      action = () => workspaceApi.requestA2AReviewChanges(t.id, { comment });
    }
    if (!action) return;          // not a meaningful move — ignore
    await action();
    refreshA2ATasks();
  }
  // Which columns can accept the card currently being dragged-over (visual hint).
  function canDrop(colId: string, t: A2ATask | undefined): boolean {
    if (!t) return false;
    if (colId === 'review') return !t.review && (t.state === 'working' || t.state === 'completed');
    if (colId === 'approved') return t.review?.state === 'pending';
    if (colId === 'submitted' || colId === 'working') return t.review?.state === 'pending';
    return false;
  }

  useEffect(() => { refreshA2ATasks(); }, [refreshA2ATasks]);

  const blockedSet = useMemo(() => buildBlockedSet(a2aTasks), [a2aTasks]);
  const owners = useMemo(() => Array.from(new Set(a2aTasks.map((t) => t.contractorName))).sort(), [a2aTasks]);

  // Apply search + owner filter + sort once; columns slice the result.
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = a2aTasks.filter((t) => {
      if (ownerFilter !== 'all' && t.contractorName !== ownerFilter) return false;
      if (q && !(`${taskRequestText(t)} ${t.contractorName}`.toLowerCase().includes(q))) return false;
      return true;
    });
    list = [...list].sort((a, b) => {
      if (sort === 'agent') return a.contractorName.localeCompare(b.contractorName);
      const ta = new Date(a.updatedAt || a.createdAt || 0).getTime();
      const tb = new Date(b.updatedAt || b.createdAt || 0).getTime();
      return sort === 'oldest' ? ta - tb : tb - ta;
    });
    return list;
  }, [a2aTasks, query, ownerFilter, sort]);

  const done = a2aTasks.filter((t) => ['completed', 'failed', 'canceled', 'rejected'].includes(t.state)).length;
  const inProgress = a2aTasks.filter((t) => t.state === 'working').length;
  const pending = a2aTasks.filter((t) => t.state === 'submitted').length;
  const inReview = a2aTasks.filter((t) => t.review?.state === 'pending' || t.state === 'input-required').length;
  const pct = a2aTasks.length ? Math.round((done / a2aTasks.length) * 100) : 0;

  async function createTask(contractor: string, text: string, skillId?: string) {
    await workspaceApi.createA2ATask({
      source: `human:${currentUser?.name || currentUser?.id || 'you'}`,
      contractor, text, skillId,
    });
    refreshA2ATasks();
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header + controls */}
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <ListTodo className="size-4 text-indigo-500 shrink-0" />
        <h2 className="text-sm font-semibold shrink-0">Tasks</h2>
        <div className="relative ml-1">
          <Search className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks…"
            className="h-7 w-44 pl-7 pr-2 text-[12px] rounded-md bg-muted/50 border border-border outline-none focus:ring-1 focus:ring-primary/40"
          />
        </div>
        <select
          value={ownerFilter}
          onChange={(e) => setOwnerFilter(e.target.value)}
          className="h-7 text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none max-w-[140px]"
        >
          <option value="all">All agents</option>
          {owners.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <button
          onClick={() => setSort((s) => (s === 'recent' ? 'oldest' : s === 'oldest' ? 'agent' : 'recent'))}
          className="h-7 inline-flex items-center gap-1 text-[12px] rounded-md bg-muted/50 border border-border px-2 hover:bg-muted"
          title="Cycle sort"
        >
          <ArrowDownUp className="size-3" /> {sort === 'recent' ? 'Newest' : sort === 'oldest' ? 'Oldest' : 'By agent'}
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => setDelegateOpen(true)}
            disabled={agents.length === 0}
            className="h-7 inline-flex items-center gap-1 text-[12px] font-medium rounded-md bg-primary text-primary-foreground px-2.5 hover:opacity-90 disabled:opacity-40"
          >
            <Plus className="size-3.5" /> Delegate
          </button>
          <button onClick={refreshA2ATasks} className="p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-muted-foreground" title="Refresh">
            <RefreshCw className="size-3.5" />
          </button>
        </div>
      </div>

      {/* Status summary strip */}
      {a2aTasks.length > 0 && (
        <div className="shrink-0 px-4 py-2 border-b border-border flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-[140px] flex-1 max-w-xs">
            <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[11px] font-medium text-muted-foreground tabular-nums">{done}/{a2aTasks.length}</span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-zinc-400" />{pending} to do</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-blue-500" />{inProgress} in progress</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-amber-500" />{inReview} in review</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-emerald-500" />{done} done</span>
          </div>
        </div>
      )}

      {/* Board */}
      {a2aTasks.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground gap-2">
          <ListTodo className="size-8 opacity-30" />
          <p className="text-sm">No delegations yet</p>
          <button onClick={() => setDelegateOpen(true)} disabled={agents.length === 0} className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline disabled:opacity-40">
            <Plus className="size-3.5" /> Delegate the first task
          </button>
        </div>
      ) : (
        <div className="flex-1 min-h-0 grid grid-cols-2 xl:grid-cols-5 gap-3 p-4">
          {BOARD_COLS.map((col) => {
            const items = visible.filter((t) => columnOf(t, BOARD_COLS) === col.id);
            return (
              <div
                key={col.id}
                onDragOver={(e) => { e.preventDefault(); setDragOverCol(col.id); }}
                onDragLeave={() => setDragOverCol((c) => (c === col.id ? null : c))}
                onDrop={(e) => { e.preventDefault(); handleDrop(col.id, e.dataTransfer.getData('text/plain')); }}
                className={cn(
                  'flex flex-col min-h-0 rounded-xl border bg-muted/40 dark:bg-zinc-900/40 p-1.5 transition-colors',
                  dragOverCol === col.id ? 'border-primary/60 ring-1 ring-primary/40 bg-primary/[0.04]' : 'border-border',
                )}
              >
                <div className="flex items-center gap-2 px-2 pt-1.5 pb-2">
                  <span className="size-2 rounded-full" style={{ background: col.dot }} />
                  <span className="text-xs font-semibold">{col.label}</span>
                  <span className="ml-auto text-[11px] text-muted-foreground bg-background border border-border rounded-full min-w-5 text-center px-1.5">
                    {items.length}
                  </span>
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1.5 px-0.5 pb-1.5">
                  {items.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      flash={t.id === flashTaskId}
                      blocked={blockedSet.has(t.id)}
                      onOpen={() => setDetailId(t.id)}
                      onChanged={refreshA2ATasks}
                    />
                  ))}
                  {items.length === 0 && (
                    <div className="text-center text-[11px] text-muted-foreground/70 py-3.5 border border-dashed border-border rounded-lg">
                      No cards
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {detailTask && (
        <TaskDetail task={detailTask} onClose={() => setDetailId(null)} onChanged={refreshA2ATasks} />
      )}
      <DelegateDialog
        open={delegateOpen}
        onOpenChange={setDelegateOpen}
        agents={agents}
        onDelegate={createTask}
      />
    </div>
  );
}
