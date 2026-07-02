'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { X, Check, MessageSquareWarning, Eye, Ban, ArrowRight, Hash, Send, Reply, HelpCircle, Bell, ListTree, Plus, Trash2 } from 'lucide-react';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { MarkdownContent } from '@/components/chat/markdown-content';
import { useWorkspace } from '@/lib/workspace-context';
import { timeAgoShort as timeAgo } from '@/lib/helpers';
import { taskRequestText, taskArtifactText, taskStatusMeta } from '@/lib/a2a';
import { workspaceApi } from '@/lib/api';
import type { A2ATask, TaskReviewState } from '@/lib/types';

const REVIEW_TONE: Record<TaskReviewState, string> = {
  pending: 'text-amber-700 bg-amber-500/15 dark:text-amber-300',
  approved: 'text-emerald-700 bg-emerald-500/15 dark:text-emerald-300',
  changes_requested: 'text-red-700 bg-red-500/15 dark:text-red-300',
};
const REVIEW_LABEL: Record<TaskReviewState, string> = {
  pending: 'In review',
  approved: 'Approved',
  changes_requested: 'Changes requested',
};

function agentName(addr: string): string {
  return addr.includes(':') ? addr.split(':').slice(1).join(':') : addr;
}

// Friendly labels + a dot accent for the structured activity timeline.
const TASK_EVENT_LABEL: Record<string, string> = {
  task_created: 'Created',
  status_changed: 'Status',
  review_requested: 'Review requested',
  review_approved: 'Review approved',
  changes_requested: 'Changes requested',
  commented: 'Commented',
  dependency_added: 'Blocker added',
  dependency_removed: 'Blocker removed',
  reassigned: 'Reassigned',
  nudged: 'Nudged',
  clarification_requested: 'Needs input',
  clarification_resolved: 'Clarification resolved',
  subtask_created: 'Subtask added',
  deleted: 'Moved to trash',
  restored: 'Restored',
};
function eventDot(type: string): string {
  if (type === 'review_approved') return 'bg-emerald-500';
  if (type === 'changes_requested' || type === 'clarification_requested') return 'bg-amber-500';
  if (type === 'status_changed' || type === 'task_created') return 'bg-sky-500';
  return 'bg-border';
}

/** Full task detail slide-over: the request, the deliverable, the peer-review
 *  state + actions, and the status-history timeline (which the board never
 *  surfaces). Opened from a board/review card. */
export function TaskDetail({ task, onClose, onChanged }: { task: A2ATask; onClose: () => void; onChanged: () => void }) {
  const { currentUser, a2aTasks, agents } = useWorkspace();
  const otherAgents = agents.filter((a) => a.agentName !== task.contractorName);
  const clarification = task.clarification || null;
  const blockers = task.blockedBy || [];
  const reqOf = (id: string) => {
    const t = a2aTasks.find((x) => x.id === id);
    return t ? taskRequestText(t) : id.slice(0, 8);
  };
  const addableBlockers = a2aTasks.filter((t) => t.id !== task.id && !blockers.includes(t.id));
  const meta = taskStatusMeta(task.state);
  const artifact = taskArtifactText(task);
  const review = task.review || null;
  const comments = task.comments || [];
  const terminal = ['completed', 'failed', 'canceled', 'rejected'].includes(task.state);
  const canRequestReview = !review && task.delegator.startsWith('openagents:') &&
    (task.state === 'working' || task.state === 'completed');
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const agentNames = a2aTasks.map((t) => t.contractorName);
  const replyTarget = replyTo ? comments.find((c) => c.id === replyTo) : null;
  const commentById = (id?: string | null) => (id ? comments.find((c) => c.id === id) : null);

  // Subtask fan-out: this task's children (and how many are done).
  const isSubtask = !!task.parentId;
  const children = a2aTasks.filter((t) => t.parentId === task.id && !t.deleted);
  const childDone = children.filter((c) => c.state === 'completed').length;
  const events = task.events && task.events.length > 0 ? task.events : null;
  const [subContractor, setSubContractor] = useState('');
  const [subText, setSubText] = useState('');

  async function addSubtask() {
    const text = subText.trim();
    const contractor = subContractor || otherAgents[0]?.agentName;
    if (!text || !contractor) return;
    setSubText('');
    setSubContractor('');
    await act(() => workspaceApi.createA2ASubtask(task.id, {
      // Stable identity — matches createA2ATask in workspace-context (human:<id>).
      source: `human:${currentUser.id}`,
      contractor,
      text,
    }));
  }

  async function sendComment() {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    const rt = replyTo;
    setReplyTo(null);
    await act(() => workspaceApi.addA2AComment(task.id, {
      // Stable identity — matches createA2ATask in workspace-context (human:<id>).
      author: `human:${currentUser.id}`,
      text,
      replyTo: rt || undefined,
    }));
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); onChanged(); } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[1px]" onClick={onClose} />
      <div className="relative w-full max-w-md h-full bg-background border-l border-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="shrink-0 px-4 py-3 border-b border-border flex items-center gap-2">
          <AgentAvatar name={task.contractorName} size={24} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="truncate">{agentName(task.delegator)}</span>
              <ArrowRight className="size-3 shrink-0" />
              <span className="font-medium text-foreground truncate">{task.contractorName}</span>
            </div>
          </div>
          <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded shrink-0', meta.cls)} style={{ background: `${meta.dot}1f` }}>
            {meta.label}
          </span>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground shrink-0" title="Close">
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {/* Clarification — task is waiting on a human answer */}
          {clarification && (
            <div className="rounded-lg border border-amber-300 dark:border-amber-900/60 bg-amber-500/10 px-3 py-2">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 mb-0.5">
                <HelpCircle className="size-3.5" /> Needs your input
              </div>
              <p className="text-[12.5px] text-foreground/90">{clarification.question}</p>
              <button
                disabled={busy}
                onClick={() => { const answer = window.prompt(clarification.question || 'Your answer:') || undefined; if (answer) act(() => workspaceApi.setA2AClarification(task.id, { action: 'resolve', answer })); }}
                className="mt-1.5 inline-flex items-center gap-1 text-[12px] font-semibold px-2.5 py-1 rounded-md bg-amber-500/90 text-white hover:bg-amber-500 disabled:opacity-50"
              >
                <Check className="size-3.5" /> Respond
              </button>
            </div>
          )}

          {/* Assignment — who's on it, reassign, nudge */}
          <section>
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Assignment</h4>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1.5 text-[12.5px]">
                <AgentAvatar name={task.contractorName} size={18} /> <span className="font-medium">{task.contractorName}</span>
              </span>
              {!terminal && otherAgents.length > 0 && (
                <select
                  value=""
                  disabled={busy}
                  onChange={(e) => { const c = e.target.value; if (c) act(() => workspaceApi.reassignA2ATask(task.id, { contractor: c })); }}
                  className="h-7 text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none"
                  title="Reassign to another agent"
                >
                  <option value="">Reassign…</option>
                  {otherAgents.map((a) => <option key={a.agentName} value={a.agentName}>{a.agentName}</option>)}
                </select>
              )}
              {!terminal && (
                <button
                  disabled={busy}
                  onClick={() => act(() => workspaceApi.nudgeA2ATask(task.id))}
                  className="h-7 inline-flex items-center gap-1 text-[12px] font-medium px-2 rounded-md border border-border hover:bg-muted disabled:opacity-50"
                  title="Poke the agent to continue"
                >
                  <Bell className="size-3" /> Nudge
                </button>
              )}
            </div>
          </section>

          {/* Request */}
          <section>
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Request</h4>
            <p className="text-[13px] leading-relaxed text-foreground/90 whitespace-pre-wrap">{taskRequestText(task)}</p>
          </section>

          {/* Subtasks — fan this work out to other agents */}
          {!isSubtask && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center justify-between">
                <span className="inline-flex items-center gap-1"><ListTree className="size-3" /> Subtasks</span>
                {children.length > 0 && <span className="font-mono text-muted-foreground/60">{childDone}/{children.length} done</span>}
              </h4>
              {children.length > 0 && (
                <ul className="space-y-1 mb-2">
                  {children.map((c) => {
                    const m = taskStatusMeta(c.state);
                    return (
                      <li key={c.id} className="flex items-center gap-1.5 text-[12px]">
                        <AgentAvatar name={c.contractorName} size={16} className="shrink-0" />
                        <span className="truncate flex-1">{taskRequestText(c)}</span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0" style={{ color: m.dot, background: `${m.dot}1f` }}>{m.label}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
              {!terminal && otherAgents.length > 0 ? (
                <div className="flex items-center gap-1.5">
                  <select
                    value={subContractor}
                    disabled={busy}
                    onChange={(e) => setSubContractor(e.target.value)}
                    className="h-7 text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none shrink-0 max-w-[35%]"
                    title="Assign the subtask to"
                  >
                    <option value="">{otherAgents[0]?.agentName}</option>
                    {otherAgents.map((a) => <option key={a.agentName} value={a.agentName}>{a.agentName}</option>)}
                  </select>
                  <input
                    value={subText}
                    disabled={busy}
                    onChange={(e) => setSubText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addSubtask(); } }}
                    placeholder="Break off a subtask…"
                    className="flex-1 min-w-0 h-7 text-[12px] rounded-md bg-muted/50 border border-border px-2 outline-none focus:ring-1 focus:ring-primary/40"
                  />
                  <button
                    disabled={busy || !subText.trim()}
                    onClick={addSubtask}
                    className="shrink-0 inline-flex items-center justify-center size-7 rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90"
                    title="Add subtask"
                  >
                    <Plus className="size-3.5" />
                  </button>
                </div>
              ) : children.length === 0 ? (
                <p className="text-[12px] text-muted-foreground/70">No subtasks.</p>
              ) : null}
            </section>
          )}

          {/* Deliverable */}
          {artifact && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Deliverable</h4>
              <div className="text-[12.5px] leading-snug text-foreground/85 bg-muted/60 border border-border/60 rounded-lg px-3 py-2 whitespace-pre-wrap">
                {artifact}
              </div>
            </section>
          )}

          {/* Review */}
          {(review || canRequestReview || review === null) && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Review</h4>
              {review ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={cn('text-[11px] font-semibold px-2 py-0.5 rounded', REVIEW_TONE[review.state])}>
                      {REVIEW_LABEL[review.state]}
                    </span>
                    {review.reviewer && <span className="text-[12px] text-muted-foreground">reviewer <span className="text-foreground font-medium">{review.reviewer}</span></span>}
                  </div>
                  {review.comment && (
                    <p className="text-[12px] italic text-muted-foreground border-l-2 border-border pl-2">“{review.comment}”</p>
                  )}
                  {review.state === 'pending' && (
                    <div className="flex items-center gap-2 pt-0.5">
                      <button disabled={busy} onClick={() => act(() => workspaceApi.approveA2AReview(task.id))}
                        className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-emerald-500/90 text-white hover:bg-emerald-500 disabled:opacity-50">
                        <Check className="size-3.5" /> Approve
                      </button>
                      <button disabled={busy} onClick={() => { const comment = window.prompt('What changes are needed?'); if (comment === null) return; act(() => workspaceApi.requestA2AReviewChanges(task.id, { comment: comment || undefined })); }}
                        className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-900/60 text-red-700 dark:text-red-400 hover:bg-red-500/10 disabled:opacity-50">
                        <MessageSquareWarning className="size-3.5" /> Request changes
                      </button>
                    </div>
                  )}
                </div>
              ) : canRequestReview ? (
                <div className="flex items-center gap-2 flex-wrap">
                  <button disabled={busy} onClick={() => act(() => workspaceApi.requestA2AReview(task.id))}
                    className="inline-flex items-center gap-1.5 text-[12px] font-medium px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-50">
                    <Eye className="size-3.5" /> Request review
                  </button>
                  {otherAgents.length > 0 && (
                    <select
                      value=""
                      disabled={busy}
                      onChange={(e) => { const r = e.target.value; if (r) act(() => workspaceApi.requestA2AReview(task.id, { reviewer: r })); }}
                      className="h-[30px] text-[12px] rounded-lg bg-muted/50 border border-border px-1.5 outline-none"
                      title="Request review from a specific agent"
                    >
                      <option value="">…from a specific agent</option>
                      {otherAgents.map((a) => <option key={a.agentName} value={a.agentName}>{a.agentName}</option>)}
                    </select>
                  )}
                </div>
              ) : (
                <p className="text-[12px] text-muted-foreground">Not yet ready for review.</p>
              )}
            </section>
          )}

          {/* Activity — structured, typed timeline (status, reviews, comments, …) */}
          {events ? (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">Activity</h4>
              <ol className="relative border-l border-border ml-1.5 space-y-3">
                {events.map((e, i) => {
                  const label = TASK_EVENT_LABEL[e.type] || e.type.replace(/_/g, ' ');
                  const isStatus = e.type === 'status_changed';
                  const subline = !isStatus && e.detail ? e.detail : null;
                  return (
                    <li key={i} className="ml-3.5">
                      <span className={cn('absolute -left-[5px] mt-1 size-2 rounded-full', eventDot(e.type))} />
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="text-[11.5px] font-semibold text-foreground/80">
                          {label}{isStatus && e.detail ? <span className="text-foreground/60"> → {e.detail}</span> : null}
                        </span>
                        {e.actor && <span className="text-[10.5px] text-muted-foreground">{e.actor}</span>}
                        {e.at && <span className="text-[10px] font-mono text-muted-foreground/60">{timeAgo(e.at)}</span>}
                      </div>
                      {subline && <p className="text-[12px] leading-snug text-foreground/75 mt-0.5 whitespace-pre-wrap">{subline}</p>}
                    </li>
                  );
                })}
              </ol>
            </section>
          ) : task.history && task.history.length > 0 ? (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">History</h4>
              <ol className="relative border-l border-border ml-1.5 space-y-3">
                {task.history.map((h, i) => {
                  const text = (h.parts || []).map((p) => p.text).filter(Boolean).join(' ');
                  return (
                    <li key={i} className="ml-3.5">
                      <span className="absolute -left-[5px] mt-1 size-2 rounded-full bg-border" />
                      <div className="flex items-baseline gap-2">
                        <span className="text-[10.5px] font-semibold text-foreground/70 capitalize">{h.role || 'event'}</span>
                        {h.timestamp && <span className="text-[10px] font-mono text-muted-foreground/60">{timeAgo(h.timestamp)}</span>}
                      </div>
                      {text && <p className="text-[12px] leading-snug text-foreground/85 mt-0.5 whitespace-pre-wrap">{text}</p>}
                    </li>
                  );
                })}
              </ol>
            </section>
          ) : null}

          {/* Dependencies */}
          <section>
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Blocked by</h4>
            {blockers.length === 0 ? (
              <p className="text-[12px] text-muted-foreground/70 mb-1.5">Nothing — this task is unblocked.</p>
            ) : (
              <ul className="space-y-1 mb-1.5">
                {blockers.map((id) => (
                  <li key={id} className="flex items-center gap-1.5 text-[12px]">
                    <span className="size-1.5 rounded-full bg-amber-500 shrink-0" />
                    <span className="truncate flex-1">{reqOf(id)}</span>
                    <button
                      disabled={busy}
                      onClick={() => act(() => workspaceApi.editA2ADependency(task.id, { blockedBy: id, action: 'remove' }))}
                      className="text-muted-foreground hover:text-red-500 shrink-0"
                      title="Remove blocker"
                    >
                      <X className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {addableBlockers.length > 0 && (
              <select
                value=""
                disabled={busy}
                onChange={(e) => { const id = e.target.value; if (id) act(() => workspaceApi.editA2ADependency(task.id, { blockedBy: id, action: 'add' })); }}
                className="h-7 w-full text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none"
              >
                <option value="">+ Add a blocker…</option>
                {addableBlockers.map((t) => (
                  <option key={t.id} value={t.id}>{taskRequestText(t).slice(0, 60)}</option>
                ))}
              </select>
            )}
          </section>

          {/* Comments thread */}
          <section>
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              Comments{comments.length > 0 && <span className="ml-1 text-muted-foreground/60">{comments.length}</span>}
            </h4>
            {comments.length === 0 ? (
              <p className="text-[12px] text-muted-foreground/70">No comments yet.</p>
            ) : (
              <ul className="space-y-2.5">
                {comments.map((c) => {
                  const parent = commentById(c.replyTo);
                  return (
                    <li key={c.id} className="flex gap-2 group">
                      <AgentAvatar name={c.author} size={20} className="mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-[12px] font-semibold truncate">{c.author}</span>
                          <span className="text-[10px] font-mono text-muted-foreground/60">{timeAgo(c.createdAt)}</span>
                          <button
                            onClick={() => setReplyTo(c.id)}
                            className="ml-auto opacity-0 group-hover:opacity-100 inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground transition-opacity"
                            title="Reply"
                          >
                            <Reply className="size-2.5" /> Reply
                          </button>
                        </div>
                        {parent && (
                          <div className="mt-0.5 mb-1 pl-2 border-l-2 border-border text-[11px] text-muted-foreground truncate">
                            <span className="font-medium">{parent.author}</span>: {parent.text}
                          </div>
                        )}
                        <div className="text-[12.5px] leading-snug text-foreground/85">
                          <MarkdownContent content={c.text} agentNames={agentNames} />
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        {/* Comment composer */}
        <div className="shrink-0 border-t border-border px-3 py-2">
          {replyTarget && (
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted/50 rounded-md px-2 py-1">
              <Reply className="size-3 shrink-0" />
              <span className="truncate">Replying to <span className="font-medium text-foreground">{replyTarget.author}</span>: {replyTarget.text}</span>
              <button onClick={() => setReplyTo(null)} className="ml-auto shrink-0 hover:text-foreground" title="Cancel reply"><X className="size-3" /></button>
            </div>
          )}
          <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sendComment(); } }}
            rows={1}
            placeholder="Add a comment…  (⌘↵ to send)"
            className="flex-1 resize-none bg-muted/50 border border-border rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-1 focus:ring-primary/40 max-h-24"
          />
          <button
            disabled={busy || !draft.trim()}
            onClick={sendComment}
            className="shrink-0 inline-flex items-center justify-center size-8 rounded-lg bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90"
            title="Send comment"
          >
            <Send className="size-4" />
          </button>
          </div>
        </div>

        {/* Footer meta + cancel */}
        <div className="shrink-0 border-t border-border px-4 py-2.5 flex items-center gap-3 text-[11px] text-muted-foreground">
          {task.channel && (
            <span className="inline-flex items-center gap-0.5 min-w-0 truncate"><Hash className="size-3 shrink-0" /><span className="truncate">{task.channel}</span></span>
          )}
          <span className="font-mono shrink-0">{timeAgo(task.createdAt)}</span>
          <div className="ml-auto flex items-center gap-3">
            {!terminal && (
              <button disabled={busy} onClick={() => act(() => workspaceApi.cancelA2ATask(task.id))}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-red-600 dark:text-red-400 hover:underline disabled:opacity-50">
                <Ban className="size-3" /> Cancel
              </button>
            )}
            <button disabled={busy} onClick={() => act(async () => { await workspaceApi.softDeleteA2ATask(task.id); onClose(); })}
              className="inline-flex items-center gap-1 text-[11px] font-medium hover:text-foreground hover:underline disabled:opacity-50"
              title="Move to recycle bin">
              <Trash2 className="size-3" /> Trash
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
