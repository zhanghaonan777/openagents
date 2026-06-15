'use client';

import { cn } from '@/lib/utils';
import { timeAgo } from '@/lib/helpers';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import {
  Activity,
  Brain,
  CheckCircle2,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  Star,
  Terminal,
  User,
  Wrench,
  Eye,
} from 'lucide-react';
import type { WorkspaceAgent, WorkspaceMessage, WorkspaceSession } from '@/lib/types';
import { parseToolStep, toolStepLabel, type ParsedStep } from '@/lib/tool-step';
import type { TileData } from './monitor-grid';

interface MonitorTileProps {
  session: WorkspaceSession;
  tileData: TileData | undefined;
  isActive: boolean;
  isCompleted: boolean;
  agents: WorkspaceAgent[];
  onClick: () => void;
  /** Keyboard shortcut number (1-6) shown as a badge on the tile. */
  shortcutKey?: number;
}

// ── Parsing (mirrors intermediate-steps.tsx patterns) ──

// Dense one-line step for the monitor tile — delegates parsing to the shared
// parser, then flattens to a label (CSS truncates it in the tile).
function parseStep(msg: WorkspaceMessage): { type: ParsedStep['type']; label: string } {
  // A thinking message whose body isn't the **Thinking:** form still shows its text.
  if (
    msg.messageType === 'thinking' &&
    !/^\*\*Thinking:\*\*/.test(msg.content) &&
    msg.content !== 'thinking...' &&
    msg.content.toLowerCase() !== 'thinking'
  ) {
    return { type: 'thinking', label: msg.content };
  }
  const p = parseToolStep(msg.content);
  if (p.type === 'compacting') return { type: 'compacting', label: 'Vibing...' };
  return { type: p.type, label: toolStepLabel(p) };
}

const STEP_ICONS: Record<string, typeof Wrench> = {
  thinking: Brain,
  tool_call: Wrench,
  status: Activity,
  compacting: RefreshCw,
};

// Map common tool names to specific icons
function getToolIcon(label: string): typeof Wrench {
  if (/^(Read|Edit|Write|Pencil)\b/.test(label)) return label.startsWith('Read') ? Eye : Pencil;
  if (/^Bash\b/.test(label)) return Terminal;
  if (/^(Glob|Grep|Search)\b/.test(label)) return Search;
  return Wrench;
}

// ── Helpers ──

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*/g, '')
    .replace(/`{1,3}/g, '')
    .replace(/```[\s\S]*?```/g, '[code]')
    .replace(/\n+/g, ' ')
    .trim();
}

// ── Tile Component ──

export function MonitorTile({ session, tileData, isActive, isCompleted, agents, onClick, shortcutKey }: MonitorTileProps) {
  const participants = session.participants || [];
  const sessionAgents = agents.filter((a) => participants.includes(a.agentName));

  const activityMs = session.lastEventAt;
  const displayTime = activityMs
    ? timeAgo(new Date(activityMs).toISOString())
    : session.createdAt ? timeAgo(session.createdAt) : '';

  const lastUser = tileData?.lastUserMessage;
  const lastAgent = tileData?.lastAgentMessage;
  const recentSteps = tileData?.recentSteps || [];
  const agentIsWorking = lastAgent && (lastAgent.messageType === 'status' || lastAgent.messageType === 'thinking');

  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-col text-left border border-input rounded-xl bg-background shadow-xs cursor-pointer p-3 overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md',
        isActive && 'thread-wip',
        isCompleted && 'bg-amber-50 dark:bg-amber-900/20 ring-1 ring-amber-200/60 dark:ring-amber-700/40 animate-[glow_2s_ease-in-out_infinite]',
      )}
    >
      {/* Header: avatars + title + time */}
      <div className="flex items-center gap-2 mb-2 shrink-0">
        <div className="flex -space-x-1.5 shrink-0">
          {sessionAgents.slice(0, 3).map((agent) => (
            <div key={agent.agentName} className="border-2 border-background rounded-full">
              <AgentAvatar name={agent.agentName} size={18} />
            </div>
          ))}
        </div>
        {session.starred && <Star className="size-3 text-amber-400 fill-amber-400 shrink-0" />}
        <span className="text-xs font-medium text-foreground truncate flex-1 min-w-0">
          {session.title || 'Untitled'}
        </span>
        {isCompleted ? (
          <CheckCircle2 className="size-3.5 shrink-0 text-amber-500" />
        ) : (
          <span className="text-[10px] text-muted-foreground shrink-0">{displayTime}</span>
        )}
        {shortcutKey && (
          <kbd className="size-4 flex items-center justify-center rounded text-[9px] font-mono font-medium bg-muted text-muted-foreground border border-input shrink-0">
            {shortcutKey}
          </kbd>
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {/* Last user message (fall back to session title if not found in recent events) */}
        {lastUser || session.title ? (
          <div className="flex gap-1.5 items-start shrink-0 mb-1.5">
            <User className="size-3 shrink-0 text-muted-foreground mt-0.5" />
            <p className="text-xs text-foreground line-clamp-2">
              {lastUser
                ? truncate(stripMarkdown(lastUser.content), 150)
                : truncate(session.title!, 150)}
            </p>
          </div>
        ) : !lastAgent && recentSteps.length === 0 ? (
          <p className="text-xs text-muted-foreground/50">No messages yet</p>
        ) : null}

        {/* Agent section: intermediate steps (working) or final response (done) */}
        {agentIsWorking && recentSteps.length > 0 ? (
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col justify-end">
            {/* Show steps from bottom up, newest at bottom — reversed to fill from bottom */}
            <div className="overflow-hidden space-y-0.5">
              {[...recentSteps].reverse().map((step) => {
                const parsed = parseStep(step);
                const Icon = parsed.type === 'tool_call' ? getToolIcon(parsed.label) : STEP_ICONS[parsed.type];
                return (
                  <div key={step.messageId} className="flex items-center gap-1.5 min-w-0">
                    <Icon className={cn(
                      'size-3 shrink-0',
                      parsed.type === 'thinking' && 'text-amber-500',
                      parsed.type === 'tool_call' && 'text-blue-500',
                      parsed.type === 'status' && 'text-emerald-500',
                      parsed.type === 'compacting' && 'text-violet-500 animate-spin',
                    )} />
                    <span className={cn(
                      'text-[11px] truncate min-w-0 text-muted-foreground',
                      parsed.type === 'thinking' && 'italic',
                      parsed.type === 'compacting' && 'italic text-violet-500/80',
                    )}>
                      {parsed.label}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Activity dots */}
            <div className="shrink-0 mt-0.5">
              <Loader2 className="size-3 text-muted-foreground/50 animate-spin" />
            </div>
          </div>
        ) : lastAgent ? (
          <div className="flex gap-1.5 items-start flex-1 min-h-0">
            <AgentAvatar name={lastAgent.senderName} size={14} className="mt-0.5" />
            <p className="text-xs text-foreground line-clamp-3 min-w-0">
              {truncate(stripMarkdown(lastAgent.content), 200)}
            </p>
          </div>
        ) : null}
      </div>
    </button>
  );
}
