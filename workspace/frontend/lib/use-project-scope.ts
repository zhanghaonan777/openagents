'use client';

import { useMemo } from 'react';
import { useLayout } from '@/components/layout/layout-context';
import { useWorkspace } from '@/lib/workspace-context';

/**
 * The set of channel names filed under the active project, or `null` when no
 * project is active ("All projects" — no filtering).
 *
 * Project-scoped panels (Tasks/Review/Files/…) derive an item's project from the
 * channel it lives in, via the thread→project link (`channels.project_id`). An
 * item whose channel isn't filed under any project (e.g. a direct agent
 * delegation with no project thread) maps to no project, so it surfaces only in
 * the org-wide "All projects" view — never misattributed to a specific project.
 *
 * Returning `null` (rather than an empty set) is the "show everything" signal so
 * callers can write `!channels || channels.has(name)`.
 */
export function useProjectChannels(): Set<string> | null {
  const { currentProjectId } = useLayout();
  const { sessions } = useWorkspace();
  return useMemo(() => {
    if (!currentProjectId) return null;
    return new Set(
      sessions.filter((s) => s.projectId === currentProjectId).map((s) => s.sessionId),
    );
  }, [currentProjectId, sessions]);
}

/** Predicate for a project-scoped item, keyed by the channel it lives in.
 *  `null`/`undefined` channel → only visible in the org-wide view. */
export function inProjectChannels(channels: Set<string> | null, channel: string | null | undefined): boolean {
  if (!channels) return true;            // All projects → no filter
  return channel != null && channels.has(channel);
}
