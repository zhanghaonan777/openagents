// Shared A2A task helpers — one definition for the request text, the result
// artifact text, and the state→label/color mapping, so the Tasks board, the
// chat delegate card, and the agent profile panel can never drift apart again.
import type { A2ATask, A2ATaskState } from './types';

/** The human-readable request that kicked off a task (its first user message). */
export function taskRequestText(t: A2ATask): string {
  const hist = t.history || [];
  const m = hist.find((h) => h.role === 'user' && h.parts?.[0]?.text) || hist.find((h) => h.parts?.[0]?.text);
  return m?.parts?.[0]?.text || '(task)';
}

/** The contractor's deliverable — all artifact text parts joined. */
export function taskArtifactText(t: A2ATask): string {
  return (t.artifacts || [])
    .flatMap((a) => (a.parts || []).map((p) => p.text || ''))
    .join('\n')
    .trim();
}

/** Canonical state → { label, text-color class, dot hex } for badges/cards. */
export function taskStatusMeta(s: A2ATaskState): { label: string; cls: string; dot: string } {
  if (s === 'working') return { label: 'In Progress', cls: 'text-blue-600 dark:text-blue-400', dot: '#3b82f6' };
  if (s === 'input-required') return { label: 'Review', cls: 'text-amber-600 dark:text-amber-400', dot: '#f59e0b' };
  if (s === 'completed') return { label: 'Done', cls: 'text-emerald-600 dark:text-emerald-400', dot: '#22c55e' };
  if (s === 'failed' || s === 'rejected') return { label: s === 'failed' ? 'Failed' : 'Rejected', cls: 'text-red-600 dark:text-red-400', dot: '#ef4444' };
  if (s === 'canceled') return { label: 'Canceled', cls: 'text-muted-foreground', dot: '#a1a1aa' };
  return { label: 'To Do', cls: 'text-muted-foreground', dot: '#a1a1aa' };
}

// A delegation kick-off embeds an internal contractor instruction prefixed with
// this marker; the backend produces it (DELEGATION_MARKER in routers/a2a.py) and
// the chat + activity views strip it from human-facing display. Cross-stack
// contract — keep in sync with the backend constant.
const DELEGATION_SPLIT = /\n*\[A2A delegation/;

/** Hide the internal A2A kick-off plumbing from displayed message content. */
export function stripDelegationPlumbing(content: string): string {
  return (content || '').split(DELEGATION_SPLIT)[0].trimEnd();
}
