'use client';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Copy, Check, User, FileIcon, Download, Eye, WifiOff } from 'lucide-react';
import { toast } from 'sonner';
import { memo, useCallback, useMemo, useState } from 'react';
import { MESSAGE_TYPE, type WorkspaceMessage, type WorkspaceAgent, type A2ATask } from '@/lib/types';
import { messageKind, MessageKindBadge, KIND_META } from './message-kind';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { MarkdownContent } from './markdown-content';
import { workspaceApi } from '@/lib/api';
import { useLayout } from '@/components/layout/layout-context';
import { useWorkspace } from '@/lib/workspace-context';
import { colorFromName, roleTemplateByName } from '@/lib/role-templates';
import { taskRequestText, taskArtifactText, taskStatusMeta, stripDelegationPlumbing } from '@/lib/a2a';
import { CategoryChip } from '@/components/agents/role-library';

const TASK_PROGRESS: Record<string, number> = {
  submitted: 0.15, working: 0.6, 'input-required': 0.82,
  completed: 1, failed: 1, canceled: 1, rejected: 1,
};

/** Live A2A delegation card under a `delegate` chat message — shows the
 *  contractor working through the task right in the conversation. */
function DelegateTaskCard({ task, onJump }: { task: A2ATask; onJump: () => void }) {
  const who = task.contractorName;
  const c = colorFromName(who);
  const status = taskStatusMeta(task.state);
  const terminal = ['completed', 'failed', 'canceled', 'rejected'].includes(task.state);
  const artifact = taskArtifactText(task);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onJump}
      onKeyDown={(e) => { if (e.key === 'Enter') onJump(); }}
      style={{ borderLeftColor: c }}
      className="w-full mt-2 p-3 rounded-xl bg-background border border-border border-l-[3px] shadow-xs cursor-pointer transition-all hover:-translate-y-px hover:shadow-[0_4px_14px_-6px_rgba(20,20,40,0.14)]"
    >
      <div className="flex items-center gap-2.5">
        <AgentAvatar name={who} size={22} className="shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] font-semibold truncate">{taskRequestText(task)}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1.5">
            <span className="font-medium text-foreground/80 truncate">{who}</span>
            <span className="text-muted-foreground/50">·</span>
            <span className={cn('font-semibold inline-flex items-center gap-1 shrink-0', status.cls)}>
              {!terminal && <span className="size-1.5 rounded-full animate-pulse" style={{ background: status.dot }} />}
              {status.label}
            </span>
          </div>
        </div>
        <span className="text-[11.5px] font-semibold text-primary shrink-0">Board →</span>
      </div>
      {/* Progress bar — fills as the contractor drives the task */}
      <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${(TASK_PROGRESS[task.state] ?? 0.15) * 100}%`, background: status.dot }}
        />
      </div>
      {/* The contractor's deliverable, inline, once reported */}
      {artifact && (
        <p className="mt-2 text-[11px] leading-snug text-foreground/75 bg-muted/60 border border-border/50 rounded px-2 py-1.5 line-clamp-3 whitespace-pre-wrap">
          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">Result · </span>{artifact}
        </p>
      )}
    </div>
  );
}

interface Attachment {
  fileId: string;
  filename: string;
  contentType: string;
  url: string;
}

function humanColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return `hsl(${hash % 360} 55% 82%)`;
}

function isPreviewable(contentType: string, filename: string): boolean {
  if (contentType?.startsWith('image/')) return true;
  if (contentType === 'text/html' || /\.html?$/i.test(filename)) return true;
  if (contentType === 'text/markdown' || /\.mdx?$/i.test(filename)) return true;
  if (contentType?.startsWith('text/') || /\.(json|js|ts|tsx|jsx|py|rs|go|java|rb|sh|yaml|yml)$/i.test(filename)) return true;
  return false;
}

function Attachments({ items }: { items: Attachment[] }) {
  const { setViewMode } = useLayout();
  const { setSelectedFileId } = useWorkspace();

  const openPreview = useCallback((fileId: string) => {
    setSelectedFileId(fileId);
    setViewMode('files');
  }, [setSelectedFileId, setViewMode]);

  // Regenerate URLs from fileId to ensure they include current auth token
  const fixedItems = useMemo(() =>
    items.map((a) => ({ ...a, url: workspaceApi.getFileUrl(a.fileId) })),
    [items]
  );

  // After all hooks — safe to bail out (Rules of Hooks).
  if (!items || items.length === 0) return null;

  const images = fixedItems.filter((a) => a.contentType?.startsWith('image/'));
  const files = fixedItems.filter((a) => !a.contentType?.startsWith('image/'));

  return (
    <div className="mt-2 space-y-2">
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((img) => (
            <button
              key={img.fileId}
              type="button"
              onClick={() => openPreview(img.fileId)}
              className="block rounded-lg overflow-hidden border hover:shadow-md transition-shadow max-w-sm cursor-pointer text-left"
            >
              <img
                src={img.url}
                alt={img.filename}
                className="max-h-64 w-auto object-contain"
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((file) => {
            const previewable = isPreviewable(file.contentType, file.filename);
            return previewable ? (
              <button
                key={file.fileId}
                type="button"
                onClick={() => openPreview(file.fileId)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-muted hover:bg-muted/80 transition-colors text-sm cursor-pointer"
              >
                <Eye className="size-4 text-muted-foreground shrink-0" />
                <span className="truncate max-w-[200px]">{file.filename}</span>
              </button>
            ) : (
              <a
                key={file.fileId}
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-muted hover:bg-muted/80 transition-colors text-sm"
              >
                <FileIcon className="size-4 text-muted-foreground shrink-0" />
                <span className="truncate max-w-[200px]">{file.filename}</span>
                <Download className="size-3 text-muted-foreground shrink-0" />
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** When a message addressed agents that were offline, the router records them
 *  in `offline_skipped` so we can explain the silence instead of leaving the
 *  human wondering why no one replied. */
function OfflineSkippedNote({ names }: { names: string[] }) {
  if (!names.length) return null;
  const label = names.length === 1
    ? `${names[0]} is offline — didn't reply`
    : `${names.join(', ')} are offline — didn't reply`;
  return (
    <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-500">
      <WifiOff className="size-3 shrink-0" />
      <span>{label}</span>
    </div>
  );
}

interface ChatMessageProps {
  message: WorkspaceMessage;
  agents?: WorkspaceAgent[];
}

export const ChatMessage = memo(function ChatMessage({ message, agents = [] }: ChatMessageProps) {
  const { currentUser, a2aTasks } = useWorkspace();
  const { setViewMode, setFlashTaskId } = useLayout();
  const isHuman = message.senderType === 'human' || message.senderType === 'user';
  const isSystem = message.messageType === MESSAGE_TYPE.STATUS;
  const isJoin = message.messageType === MESSAGE_TYPE.JOIN;
  const isDelegate = message.messageType === MESSAGE_TYPE.DELEGATE;
  const kind = messageKind(message);
  const [copied, setCopied] = useState(false);

  // A delegate kick-off embeds an internal "[A2A delegation · task …]" instruction
  // the contractor agent reads to drive the task — hide that plumbing from humans
  // (the structured task card below already shows what matters).
  const displayContent = stripDelegationPlumbing(message.content);

  const agentNames = agents.map((a) => a.agentName);
  const agent = agents.find((a) => a.agentName === message.senderName);
  const rawAttachments = (message.metadata?.attachments as Record<string, unknown>[]) || [];
  const attachments: Attachment[] = rawAttachments.map((a) => ({
    fileId: (a.fileId || a.file_id || '') as string,
    filename: (a.filename || '') as string,
    contentType: (a.contentType || a.content_type || '') as string,
    url: '',
  }));

  const timestamp = message.createdAt
    ? new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy');
    }
  };

  // ── "X joined the workspace" system line ──
  if (isJoin) {
    const role = roleTemplateByName(message.senderName);
    return (
      <div className="flex justify-center py-2">
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-muted border border-border rounded-full pl-1.5 pr-3 py-1">
          <AgentAvatar name={message.senderName} size={18} />
          <strong className="text-foreground font-semibold">{message.senderName}</strong> joined the workspace
          {role && <CategoryChip cat={role.cat} />}
        </span>
      </div>
    );
  }

  // Status messages — subtle inline
  if (isSystem) {
    const isQueued = message.content.includes('queued');
    return (
      <div className="flex justify-center py-1">
        <span className={cn(
          'text-xs italic',
          isQueued
            ? 'text-blue-500 dark:text-blue-400'
            : 'text-muted-foreground'
        )}>
          {message.senderName}: {message.content}
        </span>
      </div>
    );
  }

  // ── Human message — Slack style ──
  if (isHuman) {
    const isCurrentUser = !!message.senderId && message.senderId === currentUser.id;
    const displayName = isCurrentUser
      ? 'You'
      : (message.senderName && message.senderName !== 'user' ? message.senderName : 'User');
    const seed = message.senderId || message.senderName || 'human';

    return (
      <div className="py-1.5">
        <div className="flex items-start gap-2">
          <div
            className="size-9 rounded-lg shrink-0 flex items-center justify-center mt-0.5"
            style={{ backgroundColor: humanColor(seed) }}
          >
            <User className="size-4 text-zinc-700" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-[15px] font-bold text-foreground">{displayName}</span>
              {timestamp && (
                <span className="text-xs text-muted-foreground">{timestamp}</span>
              )}
            </div>
            <div className="text-sm leading-relaxed mt-0.5">
              <MarkdownContent content={message.content} agentNames={agentNames} />
              <Attachments items={attachments} />
              <OfflineSkippedNote names={(message.metadata?.offline_skipped as string[]) || []} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Agent message — Slack style ──
  return (
    <div className="py-1.5">
      <div className="flex items-start gap-2">
        <AgentAvatar name={message.senderName} size={36} square className="mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-bold text-foreground truncate">
              {message.senderName}
            </span>
            {agent && (
              <span className={cn(
                'text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0',
                agent.role === 'master'
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                  : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400'
              )}>
                {agent.role}
              </span>
            )}
            {kind && <MessageKindBadge kind={kind} />}
            {timestamp && (
              <span className="text-xs text-muted-foreground">{timestamp}</span>
            )}
          </div>
          <div
            className={cn('text-sm leading-relaxed mt-0.5', kind && 'border-l-2 pl-2.5')}
            style={kind ? { borderColor: KIND_META[kind].dot } : undefined}
          >
            <MarkdownContent content={displayContent} agentNames={agentNames} />
            <Attachments items={attachments} />

            {/* Delegate → linked task card (jumps to the board) */}
            {isDelegate && (() => {
              const taskId = message.metadata?.taskId as string | undefined;
              const task = taskId ? a2aTasks.find((t) => t.id === taskId) : undefined;
              return task ? (
                <DelegateTaskCard
                  task={task}
                  onJump={() => { setViewMode('tasks'); setFlashTaskId(task.id); }}
                />
              ) : null;
            })()}

            {/* Copy button */}
            <div className="flex items-center gap-1 mt-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-1.5 text-xs text-muted-foreground hover:text-foreground gap-1"
                onClick={handleCopy}
              >
                {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});
