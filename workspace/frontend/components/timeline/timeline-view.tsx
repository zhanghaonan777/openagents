'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity, RefreshCw, Brain, Terminal, MessageSquare, Send, AlertTriangle, Hash, X } from 'lucide-react';
import { workspaceApi } from '@/lib/api';
import { eventToMessage, type WorkspaceMessage } from '@/lib/types';
import { classifyActivity, type ActivityKind, type ActivityMeta } from '@/lib/agent-activity';
import { stripDelegationPlumbing } from '@/lib/a2a';
import { timeAgoShort } from '@/lib/helpers';
import { useWorkspace } from '@/lib/workspace-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { MarkdownContent } from '@/components/chat/markdown-content';
import { cn } from '@/lib/utils';

const ICON: Record<ActivityKind, typeof Brain> = { thinking: Brain, tool: Terminal, message: MessageSquare, delegate: Send };

interface Step { m: WorkspaceMessage; meta: ActivityMeta }

/** Multi-agent flight-recorder: one horizontal lane per agent, recent steps as
 *  typed chips (oldest→newest), parallel work visible across lanes, failures
 *  highlighted with a "failures only" filter, click a chip to drill in. */
export function TimelineView() {
  const { agents, teamActivity } = useWorkspace();
  const agentNames = agents.map((a) => a.agentName);
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
    for (const m of [...events].reverse()) {   // ascending (oldest → newest)
      if (m.senderType !== 'agent' || m.messageType === 'join') continue;
      const c = (m.content || '').trim();
      if (!c || c === 'thinking...') continue;  // drop the launcher placeholder
      (byAgent[m.senderName] ??= []).push({ m, meta: classifyActivity(m) });
    }
    // Stable order by name so lanes don't jump around on each poll; "working"
    // is conveyed by the pulse dot, not by position.
    return Object.entries(byAgent)
      .map(([name, list]) => ({ name, list: list.slice(-40) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [events]);

  const failureCount = lanes.reduce((n, l) => n + l.list.filter((s) => s.meta.failure).length, 0);
  const workingCount = lanes.filter((l) => teamActivity[l.name]?.working).length;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Activity className="size-4 text-indigo-500 shrink-0" />
          <h2 className="text-sm font-semibold">Activity Timeline</h2>
          <span className="text-xs text-muted-foreground truncate">{workingCount} working · {lanes.length} agents</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setFailuresOnly((v) => !v)}
            className={cn(
              'text-[11px] px-2 py-1 rounded-md border inline-flex items-center gap-1 transition-colors',
              failuresOnly ? 'bg-red-500/10 border-red-300 dark:border-red-900/50 text-red-600 dark:text-red-400' : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            <AlertTriangle className="size-3" /> Failures only{failureCount > 0 && <span className="font-semibold"> ({failureCount})</span>}
          </button>
          {loading && <RefreshCw className="size-3.5 text-muted-foreground animate-spin" />}
        </div>
      </div>

      {/* Lanes */}
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
                    <button
                      key={s.m.messageId}
                      onClick={() => setSelected(s.m)}
                      title={s.meta.detail.slice(0, 100)}
                      className={cn(
                        'shrink-0 inline-flex items-center gap-1 px-1.5 py-1 rounded text-[10px] font-medium max-w-[150px] transition-transform hover:-translate-y-px',
                        s.meta.failure ? 'text-red-600 bg-red-500/12 dark:text-red-400' : s.meta.chip,
                        selected?.messageId === s.m.messageId && 'ring-1 ring-primary',
                        isLast && working && 'animate-pulse',
                      )}
                    >
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

      {/* Drill-in detail */}
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
              <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground shrink-0" title="Close">
                <X className="size-3.5" />
              </button>
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
    </div>
  );
}
