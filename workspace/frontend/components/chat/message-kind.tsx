'use client';

import { Send, HelpCircle, ArrowLeftRight, Bell, ListChecks, Sparkles, Eye } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MESSAGE_TYPE, type WorkspaceMessage } from '@/lib/types';

/**
 * One visual vocabulary for message *kinds* shared across every surface (chat
 * stream, agent DMs, …) so a delegation, a consult, a direct message and a
 * nudge each read at a glance — same icon + accent colour everywhere.
 */
export type MsgKind = 'delegate' | 'consult' | 'direct' | 'nudge' | 'review' | 'plan' | 'thinking';

export const KIND_META: Record<MsgKind, { label: string; Icon: LucideIcon; cls: string; dot: string }> = {
  delegate: { label: 'delegate', Icon: Send, cls: 'text-indigo-600 bg-indigo-500/12 dark:text-indigo-300', dot: '#6366f1' },
  consult: { label: 'consult', Icon: HelpCircle, cls: 'text-amber-600 bg-amber-500/12 dark:text-amber-300', dot: '#f59e0b' },
  direct: { label: 'direct', Icon: ArrowLeftRight, cls: 'text-sky-600 bg-sky-500/12 dark:text-sky-300', dot: '#0ea5e9' },
  nudge: { label: 'nudge', Icon: Bell, cls: 'text-orange-600 bg-orange-500/12 dark:text-orange-300', dot: '#f97316' },
  review: { label: 'review', Icon: Eye, cls: 'text-violet-600 bg-violet-500/12 dark:text-violet-300', dot: '#8b5cf6' },
  plan: { label: 'plan', Icon: ListChecks, cls: 'text-emerald-600 bg-emerald-500/12 dark:text-emerald-300', dot: '#10b981' },
  thinking: { label: 'thinking', Icon: Sparkles, cls: 'text-zinc-500 bg-zinc-500/10 dark:text-zinc-400', dot: '#a1a1aa' },
};

/** Classify a chat message into a kind (or null = plain conversation). */
export function messageKind(m: WorkspaceMessage): MsgKind | null {
  const meta = (m.metadata || {}) as Record<string, unknown>;
  if (m.messageType === MESSAGE_TYPE.DELEGATE) return 'delegate';
  if (m.messageType === MESSAGE_TYPE.PEER) {
    const peer = meta.peer as { expectsReply?: boolean } | undefined;
    return peer?.expectsReply ? 'consult' : 'direct';
  }
  if (m.messageType === MESSAGE_TYPE.TODOS) return 'plan';
  if (m.messageType === MESSAGE_TYPE.THINKING) return 'thinking';
  if (meta.nudge) return 'nudge';
  if (meta.review) return 'review';
  return null;
}

/** A small icon+label chip identifying the message kind. */
export function MessageKindBadge({ kind, className }: { kind: MsgKind; className?: string }) {
  const { label, Icon, cls } = KIND_META[kind];
  return (
    <span className={cn('inline-flex items-center gap-1 text-[9.5px] font-bold px-1.5 py-0.5 rounded-full tracking-wide uppercase shrink-0', cls, className)}>
      <Icon className="size-2.5" />
      {label}
    </span>
  );
}
