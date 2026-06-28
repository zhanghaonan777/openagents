'use client';

/**
 * Per-project access tokens, kept in this browser keyed by workspace slug
 * (the projectId in the URL). This lets the URL stay clean — just `/<slug>` —
 * while the token is looked up locally, instead of pinning a `?token=` to every
 * link. One identity (this browser's stash) → many projects, selected by id.
 *
 * Account/bearer auth is the production path; this is the local/no-account mode.
 */
const STORE = 'oa_ws_tokens';

type Entry = { token?: string; name?: string };
export interface StashedWorkspace { slug: string; token?: string; name?: string }

function read(): Record<string, Entry> {
  if (typeof window === 'undefined') return {};
  let raw: Record<string, unknown> = {};
  try { raw = JSON.parse(localStorage.getItem(STORE) || '{}'); } catch { /* ignore */ }
  const out: Record<string, Entry> = {};
  // Normalise older entries that stored a bare token string.
  for (const [slug, v] of Object.entries(raw)) out[slug] = typeof v === 'string' ? { token: v } : (v as Entry);
  return out;
}

function write(m: Record<string, Entry>) {
  try { localStorage.setItem(STORE, JSON.stringify(m)); } catch { /* quota/availability */ }
}

/** Remember a workspace's token (and optionally its name) for later clean-URL access. */
export function stashWorkspace(slug: string, token?: string, name?: string) {
  if (typeof window === 'undefined' || !slug) return;
  const m = read();
  const prev = m[slug] || {};
  const next: Entry = { token: token ?? prev.token, name: name ?? prev.name };
  if (prev.token === next.token && prev.name === next.name) return;
  m[slug] = next;
  write(m);
}

/** The token this browser holds for a workspace slug, if any. */
export function readWorkspaceToken(slug: string): string | undefined {
  return read()[slug]?.token;
}

/** Every workspace this browser has a token for (for the switcher's local list). */
export function listStashedWorkspaces(): StashedWorkspace[] {
  return Object.entries(read()).map(([slug, v]) => ({ slug, token: v.token, name: v.name }));
}

/** Forget a workspace (e.g. after it's deleted). */
export function forgetWorkspace(slug: string) {
  const m = read();
  if (!(slug in m)) return;
  delete m[slug];
  write(m);
}
