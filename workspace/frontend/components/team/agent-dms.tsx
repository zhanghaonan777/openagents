'use client';

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { MessagesSquare, Send, ArrowRight, ChevronRight, RefreshCw, HelpCircle } from 'lucide-react';
import { useWorkspace } from '@/lib/workspace-context';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { MessageKindBadge, BUBBLE_ME, BUBBLE_OTHER } from '@/components/chat/message-kind';
import { timeAgoShort as timeAgo } from '@/lib/helpers';
import { workspaceApi } from '@/lib/api';
import type { PeerThread, PeerMessage } from '@/lib/types';

/** Agent↔agent direct messaging (the A2A peer lane): seed a private side
 *  conversation between two agents and watch them go back and forth, off the
 *  main channel. A message triggers the recipient via the normal routing. */
export function AgentDms() {
  const { agents } = useWorkspace();
  const [threads, setThreads] = useState<PeerThread[]>([]);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [text, setText] = useState('');
  const [consult, setConsult] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Record<string, PeerMessage[]>>({});

  const load = useCallback(async () => {
    try { setThreads((await workspaceApi.listA2APeerThreads()).threads); } catch { /* best-effort */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Seed sensible default sender/recipient once the roster loads.
  useEffect(() => {
    if (!from && agents[0]) setFrom(agents[0].agentName);
    if (!to && agents.find((a) => a.agentName !== agents[0]?.agentName)) {
      setTo(agents.find((a) => a.agentName !== from)?.agentName || '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]);

  async function loadThread(channel: string) {
    try {
      const r = await workspaceApi.getA2APeerThread(channel);
      setMsgs((m) => ({ ...m, [channel]: r.messages }));
    } catch { /* best-effort */ }
  }

  async function toggle(channel: string) {
    if (open === channel) { setOpen(null); return; }
    setOpen(channel);
    await loadThread(channel);
  }

  const recipient = to && to !== from ? to : agents.find((a) => a.agentName !== from)?.agentName || '';

  async function send() {
    const t = text.trim();
    if (!t || !from || !recipient || busy) return;
    setBusy(true);
    try {
      const r = await workspaceApi.sendA2APeerMessage({ source: from, to: recipient, text: t, expectsReply: consult });
      setText('');
      await load();
      setOpen(r.channel);
      await loadThread(r.channel);
    } finally { setBusy(false); }
  }

  return (
    <section>
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
        <MessagesSquare className="size-3" /> Direct messages
        <span className="font-normal normal-case tracking-normal text-muted-foreground/60">agent ↔ agent</span>
        <button onClick={load} className="ml-auto text-muted-foreground hover:text-foreground" title="Refresh"><RefreshCw className="size-3" /></button>
      </h3>

      {/* Composer — seed a private A→B conversation */}
      <div className="flex items-center gap-1.5 mb-2.5 flex-wrap">
        <select
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          className="h-7 text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none max-w-[30%]"
          title="From agent"
        >
          {agents.map((a) => <option key={a.agentName} value={a.agentName}>{a.agentName}</option>)}
        </select>
        <ArrowRight className="size-3.5 text-muted-foreground shrink-0" />
        <select
          value={recipient}
          onChange={(e) => setTo(e.target.value)}
          className="h-7 text-[12px] rounded-md bg-muted/50 border border-border px-1.5 outline-none max-w-[30%]"
          title="To agent"
        >
          {agents.filter((a) => a.agentName !== from).map((a) => <option key={a.agentName} value={a.agentName}>{a.agentName}</option>)}
        </select>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } }}
          placeholder={consult ? 'Ask a question…' : 'Send a direct message…'}
          className="flex-1 min-w-[120px] h-7 text-[12px] rounded-md bg-muted/50 border border-border px-2 outline-none focus:ring-1 focus:ring-primary/40"
        />
        <button
          type="button"
          onClick={() => setConsult((v) => !v)}
          className={cn(
            'shrink-0 inline-flex items-center gap-1 h-7 px-2 rounded-md border text-[11px] font-medium transition-colors',
            consult ? 'border-amber-400/60 bg-amber-500/12 text-amber-700 dark:text-amber-300' : 'border-border text-muted-foreground hover:bg-muted',
          )}
          title="Consult: ask a question and expect a reply"
        >
          <HelpCircle className="size-3.5" /> Consult
        </button>
        <button
          onClick={send}
          disabled={busy || !text.trim() || !from || !recipient}
          className="shrink-0 inline-flex items-center justify-center size-7 rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90"
          title="Send"
        >
          <Send className="size-3.5" />
        </button>
      </div>

      {/* Threads */}
      {threads.length === 0 ? (
        <p className="text-[12.5px] text-muted-foreground/70">No direct conversations yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {threads.map((t) => {
            const expanded = open === t.channel;
            const list = msgs[t.channel] || [];
            return (
              <li key={t.channel} className="bg-background border border-border rounded-lg overflow-hidden">
                <button onClick={() => toggle(t.channel)} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/40 transition-colors text-left">
                  <ChevronRight className={cn('size-3.5 shrink-0 text-muted-foreground transition-transform', expanded && 'rotate-90')} />
                  <span className="inline-flex items-center -space-x-1 shrink-0">
                    {t.participants.map((p) => <AgentAvatar key={p} name={p} size={18} className="ring-1 ring-background rounded-full" />)}
                  </span>
                  <span className="text-[12px] font-medium shrink-0">{t.participants.join(' ↔ ')}</span>
                  {t.lastText && <span className="text-[11.5px] text-muted-foreground truncate flex-1 min-w-0">{t.lastFrom}: {t.lastText}</span>}
                  {t.lastAt && <span className="text-[10px] font-mono text-muted-foreground/60 shrink-0">{timeAgo(new Date(t.lastAt))}</span>}
                </button>
                {expanded && (
                  <div className="px-3 pb-2.5 pt-2 space-y-2.5 border-t border-border/60 bg-muted/20">
                    {list.length === 0 ? (
                      <p className="text-[11.5px] text-muted-foreground/60 pt-1">No messages.</p>
                    ) : list.map((m) => {
                      const right = m.from === t.participants[1];
                      return (
                        <div key={m.id} className={cn('flex gap-1.5 items-start', right && 'flex-row-reverse')}>
                          <AgentAvatar name={m.from} size={20} className="shrink-0 mt-0.5" />
                          <div className={cn('flex flex-col max-w-[78%]', right ? 'items-end' : 'items-start')}>
                            <div className="flex items-center gap-1 mb-0.5 px-0.5">
                              <span className="text-[10px] text-muted-foreground/70">{m.from}</span>
                              {m.consult && <MessageKindBadge kind="consult" />}
                              <span className="text-[9px] font-mono text-muted-foreground/50">{timeAgo(new Date(m.at))}</span>
                            </div>
                            <div className={cn(
                              'px-2.5 py-1.5 text-[12px] leading-snug whitespace-pre-wrap break-words rounded-xl',
                              right ? cn(BUBBLE_ME, 'rounded-tr-sm') : cn(BUBBLE_OTHER, 'rounded-tl-sm'),
                            )}>{m.text}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
