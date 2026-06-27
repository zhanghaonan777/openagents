'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { ClipboardCheck, RefreshCw, Check, MessageSquareWarning, Eye, Inbox } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { useProjectChannels, inProjectChannels } from '@/lib/use-project-scope';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { timeAgoShort as timeAgo } from '@/lib/helpers';
import { taskRequestText, taskArtifactText } from '@/lib/a2a';
import { workspaceApi } from '@/lib/api';
import type { A2ATask } from '@/lib/types';

/** A single delegation in the review queue, with the deliverable and the
 *  reviewer's actions inline. */
function ReviewCard({ task, onChanged }: { task: A2ATask; onChanged: () => void }) {
  const review = task.review || null;
  const artifact = taskArtifactText(task);
  const [busy, setBusy] = useState(false);
  const canRequest = !review && task.delegator.startsWith('openagents:') &&
    (task.state === 'working' || task.state === 'completed');

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); onChanged(); } finally { setBusy(false); }
  }

  return (
    <div className="bg-background border border-border rounded-xl p-3.5 shadow-xs">
      <div className="flex items-center gap-2 mb-2">
        <AgentAvatar name={task.contractorName} size={22} />
        <span className="text-[13px] font-semibold truncate">{task.contractorName}</span>
        <span className="text-[11px] text-muted-foreground">delivered</span>
        {review?.reviewer && (
          <span className="ml-auto text-[11px] text-muted-foreground inline-flex items-center gap-1">
            reviewer <span className="font-medium text-foreground">{review.reviewer}</span>
          </span>
        )}
      </div>

      <p className="text-[13px] leading-snug text-foreground/90 mb-2">{taskRequestText(task)}</p>

      {artifact && (
        <div className="mb-2.5 text-[12px] leading-snug text-foreground/80 bg-muted/60 border border-border/60 rounded-lg px-2.5 py-2 whitespace-pre-wrap line-clamp-[8]">
          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">Result · </span>
          {artifact}
        </div>
      )}

      {review?.comment && review.state !== 'pending' && (
        <p className="mb-2.5 text-[12px] italic text-muted-foreground border-l-2 border-border pl-2">“{review.comment}”</p>
      )}

      <div className="flex items-center gap-2">
        {canRequest && (
          <button
            disabled={busy}
            onClick={() => act(() => workspaceApi.requestA2AReview(task.id))}
            className="inline-flex items-center gap-1.5 text-[12px] font-medium px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-50"
          >
            <Eye className="size-3.5" /> Request review
          </button>
        )}
        {review?.state === 'pending' && (
          <>
            <button
              disabled={busy}
              onClick={() => act(() => workspaceApi.approveA2AReview(task.id))}
              className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-emerald-500/90 text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              <Check className="size-3.5" /> Approve
            </button>
            <button
              disabled={busy}
              onClick={() => {
                const comment = window.prompt('What changes are needed?') || undefined;
                act(() => workspaceApi.requestA2AReviewChanges(task.id, { comment }));
              }}
              className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-900/60 text-red-700 dark:text-red-400 hover:bg-red-500/10 disabled:opacity-50"
            >
              <MessageSquareWarning className="size-3.5" /> Request changes
            </button>
          </>
        )}
        {review && review.state !== 'pending' && (
          <span className={cn(
            'text-[11px] font-semibold px-2 py-1 rounded-md',
            review.state === 'approved'
              ? 'text-emerald-700 bg-emerald-500/15 dark:text-emerald-300'
              : 'text-red-700 bg-red-500/15 dark:text-red-300',
          )}>
            {review.state === 'approved' ? 'Approved' : 'Changes requested'}
          </span>
        )}
        <span className="ml-auto text-[10.5px] font-mono text-muted-foreground/70">
          {timeAgo(task.updatedAt || task.createdAt)}
        </span>
      </div>
    </div>
  );
}

function Section({ title, tint, tasks, onChanged }: { title: string; tint: string; tasks: A2ATask[]; onChanged: () => void }) {
  if (tasks.length === 0) return null;
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-2 px-0.5">
        <span className="size-2 rounded-full" style={{ background: tint }} />
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
        <span className="text-[11px] text-muted-foreground bg-muted border border-border rounded-full min-w-5 text-center px-1.5">{tasks.length}</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        {tasks.map((t) => <ReviewCard key={t.id} task={t} onChanged={onChanged} />)}
      </div>
    </div>
  );
}

/** Review Queue — "agents review each other" as a first-class screen: what's
 *  awaiting review, what's ready to be sent for review, and what was decided. */
export function ReviewView() {
  const { a2aTasks, refreshA2ATasks } = useWorkspace();
  const projectChannels = useProjectChannels();
  useEffect(() => { refreshA2ATasks(); }, [refreshA2ATasks]);

  const scoped = a2aTasks.filter((t) => inProjectChannels(projectChannels, t.channel));
  const pending = scoped.filter((t) => t.review?.state === 'pending');
  const decided = scoped.filter((t) => t.review && t.review.state !== 'pending');
  const ready = scoped.filter((t) => !t.review && t.delegator.startsWith('openagents:') &&
    (t.state === 'working' || t.state === 'completed'));

  const empty = pending.length === 0 && decided.length === 0 && ready.length === 0;

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="size-4 text-amber-500" />
          <h2 className="text-sm font-semibold">Review Queue</h2>
          <span className="text-xs text-muted-foreground">
            {pending.length} awaiting review · agents review each other
          </span>
        </div>
        <button
          onClick={refreshA2ATasks}
          className="p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-muted-foreground transition-colors"
        >
          <RefreshCw className="size-3.5" />
        </button>
      </div>

      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground gap-2">
          <Inbox className="size-8 opacity-30" />
          <p className="text-sm">Nothing to review yet</p>
          <p className="text-xs opacity-60">Delegate a task, then send the deliverable for peer review</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto p-4">
          <Section title="Awaiting review" tint="#f59e0b" tasks={pending} onChanged={refreshA2ATasks} />
          <Section title="Ready to send for review" tint="#3b82f6" tasks={ready} onChanged={refreshA2ATasks} />
          <Section title="Recently decided" tint="#22c55e" tasks={decided} onChanged={refreshA2ATasks} />
        </div>
      )}
    </div>
  );
}
