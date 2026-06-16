// Classify one of an agent's session events (a WorkspaceMessage) into a typed,
// labelled, coloured activity step. Shared by the agent profile panel's session
// timeline and the multi-agent flight-recorder timeline.
import { MESSAGE_TYPE, type WorkspaceMessage } from './types';

export type ActivityKind = 'tool' | 'thinking' | 'delegate' | 'message';

export interface ActivityMeta {
  key: ActivityKind;
  label: string;   // short label: tool name / "Thinking" / "Message" / "Delegate"
  detail: string;  // the body/detail text
  dot: string;     // colour hex (lane dots / progress)
  chip: string;    // tailwind text+bg classes for a chip/badge
  failure: boolean;
}

// Heuristic: does this step look like a failure/error? (kept tight to avoid
// flagging prose that merely mentions "errors").
const FAIL_RE = /(✗|❌|\b(failed|error|errored|exception|denied|rejected)\b|interrupted)/i;

export function classifyActivity(m: WorkspaceMessage): ActivityMeta {
  const content = m.content || '';
  const failure = FAIL_RE.test(content);
  if (m.messageType === MESSAGE_TYPE.THINKING) {
    return { key: 'thinking', label: 'Thinking', detail: content, dot: '#8b5cf6', chip: 'text-violet-700 bg-violet-500/12 dark:text-violet-300', failure: false };
  }
  if (m.messageType === MESSAGE_TYPE.DELEGATE) {
    return { key: 'delegate', label: 'Delegate', detail: content, dot: '#6366f1', chip: 'text-indigo-700 bg-indigo-500/12 dark:text-indigo-300', failure };
  }
  if (m.messageType === MESSAGE_TYPE.STATUS) {
    // Launcher tool lines are "Bash › <detail>".
    const i = content.indexOf('›');
    const tool = i > 0 ? content.slice(0, i).trim() : 'Tool';
    const detail = i > 0 ? content.slice(i + 1).trim() : content;
    return { key: 'tool', label: tool || 'Tool', detail, dot: '#f59e0b', chip: 'text-amber-700 bg-amber-500/14 dark:text-amber-300', failure };
  }
  return { key: 'message', label: 'Message', detail: content, dot: '#0ea5e9', chip: 'text-sky-700 bg-sky-500/12 dark:text-sky-300', failure };
}
