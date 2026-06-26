import { describe, it, expect } from 'vitest';
import { cleanToolName, extractToolSummary } from '@/lib/tool-step';
import {
  stripDelegationPlumbing,
  taskRequestText,
  taskArtifactText,
  taskStatusMeta,
} from '@/lib/a2a';
import type { A2ATask, A2ATaskState } from '@/lib/types';

describe('cleanToolName', () => {
  it('strips a simple mcp__server__tool prefix', () => {
    expect(cleanToolName('mcp__github__create_issue')).toBe('create_issue');
  });

  // Regression: server names can contain single underscores; the old
  // /^mcp__[^_]+__/ stopped at the first one and never stripped.
  it('strips when the server name contains underscores', () => {
    expect(cleanToolName('mcp__plugin_claude-mem_mcp-search__search')).toBe('search');
  });

  it('passes non-mcp names through unchanged', () => {
    expect(cleanToolName('Bash')).toBe('Bash');
    expect(cleanToolName('Read')).toBe('Read');
  });
});

describe('extractToolSummary', () => {
  it('returns a string for typical tool args', () => {
    const s = extractToolSummary('Bash', JSON.stringify({ command: 'ls -la' }));
    expect(typeof s).toBe('string');
  });
});

describe('stripDelegationPlumbing', () => {
  it('removes the delegation marker and everything after it', () => {
    const raw = 'Build the login form\n\n[A2A delegation taskId=abc]\ninternal contractor instruction';
    expect(stripDelegationPlumbing(raw)).toBe('Build the login form');
  });

  it('leaves plain content untouched', () => {
    expect(stripDelegationPlumbing('just a normal message')).toBe('just a normal message');
  });

  it('handles empty input', () => {
    expect(stripDelegationPlumbing('')).toBe('');
  });
});

describe('taskRequestText / taskArtifactText', () => {
  const task = {
    history: [{ role: 'user', parts: [{ text: 'Build the login form' }] }],
    artifacts: [{ parts: [{ text: 'done: form.tsx' }] }],
  } as unknown as A2ATask;

  it('reads the first user message as the request', () => {
    expect(taskRequestText(task)).toBe('Build the login form');
  });

  it('falls back to "(task)" when there is no history', () => {
    expect(taskRequestText({ history: [] } as unknown as A2ATask)).toBe('(task)');
  });

  it('joins artifact text parts', () => {
    expect(taskArtifactText(task)).toBe('done: form.tsx');
  });
});

describe('taskStatusMeta', () => {
  it('maps known states to human labels', () => {
    expect(taskStatusMeta('working').label).toBe('In Progress');
    expect(taskStatusMeta('completed').label).toBe('Done');
    expect(taskStatusMeta('failed').label).toBe('Failed');
    expect(taskStatusMeta('rejected').label).toBe('Rejected');
  });

  it('defaults unknown/initial states to "To Do"', () => {
    expect(taskStatusMeta('submitted' as A2ATaskState).label).toBe('To Do');
  });
});
