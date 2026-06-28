import { describe, it, expect, beforeEach } from 'vitest';
import { stashWorkspace, readWorkspaceToken, listStashedWorkspaces, forgetWorkspace } from './ws-tokens';

// Minimal localStorage + window so the (window-guarded) helpers run in node.
beforeEach(() => {
  const store: Record<string, string> = {};
  (globalThis as { window?: unknown }).window = {};
  (globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  };
});

describe('ws-tokens', () => {
  it('stashes and reads a per-project token', () => {
    stashWorkspace('abc', 'tok-1', 'Acme');
    expect(readWorkspaceToken('abc')).toBe('tok-1');
    expect(readWorkspaceToken('nope')).toBeUndefined();
  });

  it('lists stashed workspaces (with name) and forgets one', () => {
    stashWorkspace('a', 't1', 'A');
    stashWorkspace('b', 't2');
    expect(listStashedWorkspaces().map((w) => w.slug).sort()).toEqual(['a', 'b']);
    expect(listStashedWorkspaces().find((w) => w.slug === 'a')?.name).toBe('A');
    forgetWorkspace('a');
    expect(readWorkspaceToken('a')).toBeUndefined();
    expect(listStashedWorkspaces().map((w) => w.slug)).toEqual(['b']);
  });

  it('normalises legacy bare-string entries to {token}', () => {
    (globalThis as { localStorage: Storage }).localStorage.setItem('oa_ws_tokens', JSON.stringify({ old: 'rawtoken' }));
    expect(readWorkspaceToken('old')).toBe('rawtoken');
  });

  it('keeps the name when re-stashing with only a token', () => {
    stashWorkspace('x', 'tok', 'Named');
    stashWorkspace('x', 'tok2');
    expect(listStashedWorkspaces().find((w) => w.slug === 'x')?.name).toBe('Named');
    expect(readWorkspaceToken('x')).toBe('tok2');
  });
});
