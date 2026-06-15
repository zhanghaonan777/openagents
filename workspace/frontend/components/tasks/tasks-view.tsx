'use client';

import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { ListTodo, RefreshCw } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { useLayout } from '@/components/layout/layout-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { colorFromName } from '@/lib/role-templates';
import type { A2ATask, A2ATaskState } from '@/lib/types';

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Kanban columns mapped to A2A TaskState. */
const BOARD_COLS: { id: string; label: string; dot: string; states: A2ATaskState[] }[] = [
  { id: 'submitted', label: 'To Do', dot: '#a1a1aa', states: ['submitted'] },
  { id: 'working', label: 'In Progress', dot: '#3b82f6', states: ['working'] },
  { id: 'review', label: 'Review', dot: '#f59e0b', states: ['input-required'] },
  { id: 'done', label: 'Done', dot: '#22c55e', states: ['completed', 'failed', 'canceled', 'rejected'] },
];

function taskText(t: A2ATask): string {
  const hist = t.history || [];
  const m = hist.find((h) => h.role === 'user' && h.parts?.[0]?.text) || hist.find((h) => h.parts?.[0]?.text);
  return m?.parts?.[0]?.text || '(task)';
}

function TaskCard({ task, flash, onOpen }: { task: A2ATask; flash: boolean; onOpen: () => void }) {
  const who = task.contractorName;
  const railColor = colorFromName(who);
  const terminal = ['completed', 'failed', 'canceled', 'rejected'].includes(task.state);
  const failed = task.state === 'failed' || task.state === 'rejected' || task.state === 'canceled';
  // The contractor's deliverable, reported via the A2A task status (artifact).
  const artifactText = (task.artifacts || [])
    .flatMap((a) => (a.parts || []).map((p) => p.text || ''))
    .join('\n')
    .trim();
  return (
    <button
      onClick={onOpen}
      style={{ borderLeftColor: railColor }}
      className={cn(
        'w-full text-left bg-background border border-border border-l-[3px] rounded-lg p-2.5 shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_16px_-8px_rgba(20,20,40,0.16)]',
        flash && 'ring-2 ring-primary/45',
      )}
    >
      <p className={cn('text-[12.5px] leading-snug text-pretty mb-2.5', terminal && 'text-muted-foreground', failed && 'line-through')}>
        {taskText(task)}
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
    </button>
  );
}

export function TasksView() {
  const { a2aTasks, refreshA2ATasks } = useWorkspace();
  const { flashTaskId, setSelectedAgentName } = useLayout();

  useEffect(() => {
    refreshA2ATasks();
  }, [refreshA2ATasks]);

  const totalActive = a2aTasks.filter((t) => t.state === 'submitted' || t.state === 'working').length;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListTodo className="size-4 text-indigo-500" />
          <h2 className="text-sm font-semibold">Tasks</h2>
          <span className="text-xs text-muted-foreground">
            {totalActive} active · A2A delegations
          </span>
        </div>
        <button
          onClick={refreshA2ATasks}
          className="p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-muted-foreground transition-colors"
        >
          <RefreshCw className="size-3.5" />
        </button>
      </div>

      {/* Board */}
      {a2aTasks.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground gap-2">
          <ListTodo className="size-8 opacity-30" />
          <p className="text-sm">No delegations yet</p>
          <p className="text-xs opacity-60">Delegate a task to an agent to see it tracked here</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 grid grid-cols-2 xl:grid-cols-4 gap-3 p-4">
          {BOARD_COLS.map((col) => {
            const items = a2aTasks.filter((t) => col.states.includes(t.state));
            return (
              <div
                key={col.id}
                className="flex flex-col min-h-0 rounded-xl border border-border bg-muted/40 dark:bg-zinc-900/40 p-1.5"
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
                      onOpen={() => setSelectedAgentName(t.contractorName)}
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
    </div>
  );
}
