'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity, RefreshCw, Brain, Terminal, MessageSquare, Send, AlertTriangle, Hash, X, CheckCircle2, ScrollText, Bell, ChevronDown, ChevronRight } from 'lucide-react';
import { workspaceApi } from '@/lib/api';
import { eventToMessage, type WorkspaceMessage, type Milestone } from '@/lib/types';
import { classifyActivity, type ActivityKind, type ActivityMeta } from '@/lib/agent-activity';
import { stripDelegationPlumbing } from '@/lib/a2a';
import { timeAgoShort } from '@/lib/helpers';
import { useWorkspace } from '@/lib/workspace-context';
import { useLayout } from '@/components/layout/layout-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { MarkdownContent } from '@/components/chat/markdown-content';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

const ICON: Record<ActivityKind, typeof Brain> = { thinking: Brain, tool: Terminal, message: MessageSquare, delegate: Send };

/** Timeline — the project's institutional memory.
 *  · Timeline: a "needs attention" strip (open loops) + a feed of decision
 *    milestones distilled from discussions (the gold: what was decided & why).
 *  · Activity: the per-agent flight-recorder (low-level steps), as a drill-down. */
export function TimelineView() {
  const { agents, teamActivity, a2aTasks } = useWorkspace();
  const { setViewMode } = useLayout();
  const agentNames = agents.map((a) => a.agentName);
  const [mode, setMode] = useState<'timeline' | 'activity'>('timeline');

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <ScrollText className="size-4 text-indigo-500 shrink-0" />
          <h2 className="text-sm font-semibold">Timeline</h2>
        </div>
        <div className="flex items-center rounded-lg border border-border p-0.5 text-[11px] shrink-0">
          {(['timeline', 'activity'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn('px-2.5 py-1 rounded-md transition-colors capitalize', mode === m ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:text-foreground')}
            >
              {m === 'timeline' ? '项目日记' : 'Activity'}
            </button>
          ))}
        </div>
      </div>
      {mode === 'timeline'
        ? <ProjectJournal a2aTasks={a2aTasks} agentNames={agentNames} onOpenTasks={() => setViewMode('tasks')} />
        : <ActivityLanes agents={agents} teamActivity={teamActivity} agentNames={agentNames} />}
    </div>
  );
}

// ── Timeline mode: needs-attention strip + decision-milestone feed ──────────

function ProjectJournal({ a2aTasks, agentNames, onOpenTasks }: {
  a2aTasks: ReturnType<typeof useWorkspace>['a2aTasks'];
  agentNames: string[];
  onOpenTasks: () => void;
}) {
  const { sessions, currentSessionId, currentUser } = useWorkspace();
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  const refresh = () => workspaceApi.listTimeline().then((r) => setMilestones(r.milestones)).catch(() => {});
  useEffect(() => {
    let alive = true;
    const tick = () => workspaceApi.listTimeline().then((r) => { if (alive) setMilestones(r.milestones); }).catch(() => {});
    tick();
    const id = setInterval(tick, 8000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Capture the currently-open thread's conclusion as a decision milestone.
  const current = sessions.find((s) => s.sessionId === currentSessionId && !s.sessionId.startsWith('dm-'));
  async function capture() {
    if (!current || capturing) return;
    setCapturing(true);
    try {
      await workspaceApi.captureMilestone(current.sessionId, `human:${currentUser?.name || currentUser?.id || 'you'}`);
      await refresh();
      toast.success(`已归档「${current.title}」的结论`);
    } catch (e) {
      toast.error(`归档失败:${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setCapturing(false);
    }
  }

  // Open loops that want a human — the "needs attention" strip.
  const attention = useMemo(() => {
    const items: { key: string; tone: string; label: string; who: string }[] = [];
    for (const t of a2aTasks) {
      if (t.deleted) continue;
      if (t.review?.state === 'pending') items.push({ key: t.id + ':r', tone: 'amber', label: '待 review', who: t.contractorName });
      else if (t.review?.state === 'changes_requested') items.push({ key: t.id + ':c', tone: 'amber', label: '需修改', who: t.contractorName });
      if (t.clarification) items.push({ key: t.id + ':q', tone: 'blue', label: '待澄清', who: t.contractorName });
      if (t.state === 'failed' || t.state === 'rejected') items.push({ key: t.id + ':f', tone: 'red', label: t.state, who: t.contractorName });
    }
    return items;
  }, [a2aTasks]);

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Needs attention */}
      {attention.length > 0 && (
        <button onClick={onOpenTasks} className="w-full text-left px-4 py-2.5 border-b border-border bg-amber-50/60 dark:bg-amber-900/15 hover:bg-amber-50 dark:hover:bg-amber-900/25 transition-colors">
          <div className="flex items-center gap-2 flex-wrap">
            <Bell className="size-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
            <span className="text-[12px] font-medium text-amber-800 dark:text-amber-300">待你处理 ({attention.length})</span>
            {attention.slice(0, 6).map((a) => (
              <span key={a.key} className={cn('text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                a.tone === 'red' ? 'bg-red-500/15 text-red-600 dark:text-red-400' : a.tone === 'blue' ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400' : 'bg-amber-500/20 text-amber-700 dark:text-amber-300')}>
                {a.label} · {a.who}
              </span>
            ))}
          </div>
        </button>
      )}

      {/* Capture: distill the currently-open thread's conclusion into a milestone */}
      {current && (
        <div className="px-4 py-2 border-b border-border flex items-center gap-2">
          <button onClick={capture} disabled={capturing}
            className="inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 transition-colors">
            <ScrollText className="size-3.5" />
            {capturing ? '归档中…' : '归档结论'}
          </button>
          <span className="text-[11px] text-muted-foreground truncate">从「{current.title}」蒸馏一条决策里程碑</span>
        </div>
      )}

      {/* Decision-milestone feed */}
      {milestones.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground px-6 text-center">
          <ScrollText className="size-8 opacity-30" />
          <p className="text-sm">还没有里程碑</p>
          <p className="text-xs max-w-xs">在某个讨论收敛后,用「归档结论」把决定记下来 —— 它会作为决策里程碑出现在这里。</p>
        </div>
      ) : (
        <ol className="px-4 py-3 space-y-2">
          {milestones.map((m) => {
            const open = expanded === m.id;
            return (
              <li key={m.id} className="rounded-xl border border-border bg-background overflow-hidden">
                <button onClick={() => setExpanded(open ? null : m.id)} className="w-full text-left px-3.5 py-3 flex gap-3 hover:bg-muted/40 transition-colors">
                  <CheckCircle2 className="size-4 text-emerald-500 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wide font-semibold text-emerald-600 dark:text-emerald-400">{m.kind}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{timeAgoShort(m.createdAt)}</span>
                    </div>
                    <div className="text-[13.5px] font-semibold mt-0.5 truncate">{m.title}</div>
                    {m.summary && <p className={cn('text-[12px] text-muted-foreground mt-0.5', !open && 'line-clamp-2')}>{m.summary}</p>}
                    <div className="flex items-center gap-1.5 mt-1.5">
                      <div className="flex -space-x-1.5">
                        {m.participants.slice(0, 4).map((p) => (
                          <div key={p} className="ring-2 ring-background rounded-full"><AgentAvatar name={p} size={16} /></div>
                        ))}
                      </div>
                      <span className="text-[10px] text-muted-foreground">{m.participants.length} 人</span>
                      <span className="ml-auto text-muted-foreground">{open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}</span>
                    </div>
                  </div>
                </button>
                {open && m.detail && (
                  <div className="px-3.5 pb-3 pt-1 border-t border-border/60 text-[12.5px] leading-relaxed">
                    <MarkdownContent content={m.detail} agentNames={agentNames} />
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

// ── Activity mode: per-agent flight recorder (the original view) ────────────

interface Step { m: WorkspaceMessage; meta: ActivityMeta }

function ActivityLanes({ agents, teamActivity, agentNames }: {
  agents: ReturnType<typeof useWorkspace>['agents'];
  teamActivity: ReturnType<typeof useWorkspace>['teamActivity'];
  agentNames: string[];
}) {
  const [events, setEvents] = useState<WorkspaceMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [failuresOnly, setFailuresOnly] = useState(false);
  const [selected, setSelected] = useState<WorkspaceMessage | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = (spinner: boolean) => {
      if (spinner) setLoading(true);
      workspaceApi.pollEvents({ type: 'workspace.message', sort: 'desc', limit: 150 })
        .then((r) => { if (alive) setEvents(r.events.map(eventToMessage)); })
        .catch(() => {})
        .finally(() => { if (alive) setLoading(false); });
    };
    tick(true);
    const id = setInterval(() => tick(false), 4000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const lanes = useMemo(() => {
    const byAgent: Record<string, Step[]> = {};
    for (const m of [...events].reverse()) {
      if (m.senderType !== 'agent' || m.messageType === 'join') continue;
      const c = (m.content || '').trim();
      if (!c || c === 'thinking...') continue;
      (byAgent[m.senderName] ??= []).push({ m, meta: classifyActivity(m) });
    }
    return Object.entries(byAgent)
      .map(([name, list]) => ({ name, list: list.slice(-40) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [events]);

  const failureCount = lanes.reduce((n, l) => n + l.list.filter((s) => s.meta.failure).length, 0);
  const workingCount = lanes.filter((l) => teamActivity[l.name]?.working).length;

  return (
    <>
      <div className="shrink-0 px-4 py-2 border-b border-border flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground truncate"><Activity className="size-3 inline -mt-0.5 mr-1" />{workingCount} working · {lanes.length} agents</span>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setFailuresOnly((v) => !v)} className={cn('text-[11px] px-2 py-1 rounded-md border inline-flex items-center gap-1 transition-colors', failuresOnly ? 'bg-red-500/10 border-red-300 dark:border-red-900/50 text-red-600 dark:text-red-400' : 'border-border text-muted-foreground hover:text-foreground')}>
            <AlertTriangle className="size-3" /> Failures only{failureCount > 0 && <span className="font-semibold"> ({failureCount})</span>}
          </button>
          {loading && <RefreshCw className="size-3.5 text-muted-foreground animate-spin" />}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {lanes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
            <Activity className="size-8 opacity-30" />
            <p className="text-sm">No agent activity yet</p>
          </div>
        ) : lanes.map((lane) => {
          const working = !!teamActivity[lane.name]?.working;
          const shown = failuresOnly ? lane.list.filter((s) => s.meta.failure) : lane.list;
          if (failuresOnly && shown.length === 0) return null;
          return (
            <div key={lane.name} className="flex items-stretch border-b border-border/60">
              <div className="w-[150px] shrink-0 px-3 py-2.5 flex items-center gap-2 border-r border-border/60 bg-muted/20">
                <AgentAvatar name={lane.name} size={20} className="shrink-0" />
                <span className="text-[12px] font-medium truncate flex-1">{lane.name}</span>
                {working && <span className="size-1.5 rounded-full bg-blue-500 animate-pulse shrink-0" />}
              </div>
              <div className="flex-1 min-w-0 overflow-x-auto px-2 py-2 flex items-center gap-1">
                {shown.map((s, i) => {
                  const Icon = ICON[s.meta.key];
                  const isLast = i === shown.length - 1;
                  return (
                    <button key={s.m.messageId} onClick={() => setSelected(s.m)} title={s.meta.detail.slice(0, 100)}
                      className={cn('shrink-0 inline-flex items-center gap-1 px-1.5 py-1 rounded text-[10px] font-medium max-w-[150px] transition-transform hover:-translate-y-px',
                        s.meta.failure ? 'text-red-600 bg-red-500/12 dark:text-red-400' : s.meta.chip,
                        selected?.messageId === s.m.messageId && 'ring-1 ring-primary',
                        isLast && working && 'animate-pulse')}>
                      {s.meta.failure ? <AlertTriangle className="size-2.5 shrink-0" /> : <Icon className="size-2.5 shrink-0" />}
                      <span className="truncate">{s.meta.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {selected && (() => {
        const meta = classifyActivity(selected);
        const text = stripDelegationPlumbing(selected.content);
        return (
          <div className="shrink-0 border-t border-border bg-muted/20 max-h-[42%] flex flex-col">
            <div className="px-4 py-2 flex items-center gap-2 border-b border-border/60 shrink-0">
              <AgentAvatar name={selected.senderName} size={18} />
              <span className="text-xs font-semibold truncate">{selected.senderName}</span>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0', meta.chip)}>{meta.label}</span>
              {selected.sessionId && (
                <span className="text-[10px] text-muted-foreground inline-flex items-center gap-0.5 min-w-0 truncate">
                  <Hash className="size-2.5 shrink-0" /><span className="truncate">{selected.sessionId}</span>
                </span>
              )}
              <span className="text-[10px] text-muted-foreground ml-auto font-mono shrink-0">{timeAgoShort(selected.createdAt)}</span>
              <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground shrink-0" title="Close"><X className="size-3.5" /></button>
            </div>
            <div className="px-4 py-3 overflow-y-auto">
              {meta.key === 'tool' || meta.key === 'thinking' ? (
                <pre className="whitespace-pre-wrap break-all font-mono text-[11.5px] leading-snug text-foreground/80">{meta.detail || '…'}</pre>
              ) : (
                <div className="text-[12.5px] leading-relaxed"><MarkdownContent content={text || '…'} agentNames={agentNames} /></div>
              )}
            </div>
          </div>
        );
      })()}
    </>
  );
}
