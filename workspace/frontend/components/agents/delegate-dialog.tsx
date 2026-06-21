'use client';

import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { AgentAvatar } from '@/components/agents/agent-avatar';
import { workspaceApi } from '@/lib/api';
import type { WorkspaceAgent, A2AAgentSkill } from '@/lib/types';

/**
 * Delegate a structured A2A task to an agent. The delegation creates a real
 * A2A Task (lifecycle: submitted → working → … → completed) plus a kick-off
 * @-mention so the contractor's runtime starts working.
 */
export function DelegateDialog({
  open,
  onOpenChange,
  agents,
  onDelegate,
  defaultContractor,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: WorkspaceAgent[];
  onDelegate: (contractor: string, text: string, skillId?: string) => Promise<void>;
  defaultContractor?: string;
}) {
  const [contractor, setContractor] = useState('');
  const [text, setText] = useState('');
  const [skillId, setSkillId] = useState<string | undefined>(undefined);
  const [skillsByAgent, setSkillsByAgent] = useState<Record<string, A2AAgentSkill[]>>({});
  const [busy, setBusy] = useState(false);

  // On open, preselect the requested contractor (per-member "Assign task"), else
  // re-validate the current pick and fall back to the first agent.
  useEffect(() => {
    if (!open) return;
    if (defaultContractor && agents.some((a) => a.agentName === defaultContractor)) {
      setContractor(defaultContractor);
    } else if (agents.length > 0 && !agents.some((a) => a.agentName === contractor)) {
      setContractor(agents[0].agentName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultContractor]);

  // Reset the draft when the dialog closes so a cancelled task doesn't leak
  // its text into the next delegation.
  useEffect(() => {
    if (!open) {
      setText('');
      setSkillId(undefined);
    }
  }, [open]);

  // Load declared A2A skills (Agent Cards) so the user can target one.
  useEffect(() => {
    if (!open) return;
    let alive = true;
    workspaceApi
      .listA2AAgentCards()
      .then((r) => {
        if (!alive) return;
        const map: Record<string, A2AAgentSkill[]> = {};
        for (const c of r.agents) map[c.name] = c.skills || [];
        setSkillsByAgent(map);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [open]);

  // Reset the chosen skill when switching contractor.
  useEffect(() => { setSkillId(undefined); }, [contractor]);

  const contractorSkills = skillsByAgent[contractor] || [];

  const submit = async () => {
    const t = text.trim();
    if (!t || !contractor || busy) return;
    setBusy(true);
    try {
      await onDelegate(contractor, t, skillId);
      setText('');
      setSkillId(undefined);
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md gap-0 p-0 overflow-hidden rounded-2xl">
        <div className="px-5 pt-5 pb-3">
          <DialogTitle className="text-[17px] font-bold tracking-tight">Delegate a task</DialogTitle>
          <DialogDescription className="mt-1 text-[12.5px]">
            Creates an A2A task with a real lifecycle and assigns it to an agent.
          </DialogDescription>
        </div>

        <div className="px-5 pb-5 flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Contractor</label>
            <div className="flex flex-wrap gap-1.5">
              {agents.map((a) => (
                <button
                  key={a.agentName}
                  type="button"
                  onClick={() => setContractor(a.agentName)}
                  className={
                    'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12.5px] transition-colors ' +
                    (contractor === a.agentName
                      ? 'border-primary bg-primary/[0.08] text-foreground font-semibold'
                      : 'border-input text-muted-foreground hover:bg-muted')
                  }
                >
                  <AgentAvatar name={a.agentName} size={18} />
                  {a.agentName}
                </button>
              ))}
              {agents.length === 0 && (
                <span className="text-[12.5px] text-muted-foreground">No agents in this workspace yet.</span>
              )}
            </div>
          </div>

          {contractorSkills.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Skill (optional)</label>
              <div className="flex flex-wrap gap-1.5">
                {contractorSkills.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSkillId((cur) => (cur === s.id ? undefined : s.id))}
                    title={s.description}
                    className={
                      'rounded-lg border px-2.5 py-1 text-[12px] transition-colors ' +
                      (skillId === s.id
                        ? 'border-indigo-500 bg-indigo-500/[0.08] text-foreground font-semibold'
                        : 'border-input text-muted-foreground hover:bg-muted')
                    }
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Task</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit();
              }}
              rows={3}
              autoFocus
              placeholder="Describe what the agent should do…"
              className="w-full resize-none rounded-xl border border-input bg-background px-3 py-2.5 text-[13.5px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded-lg px-3 py-2 text-[13px] font-medium text-muted-foreground hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!text.trim() || !contractor || busy}
              className="rounded-lg bg-primary px-4 py-2 text-[13px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-default transition-colors"
            >
              {busy ? 'Delegating…' : 'Delegate'}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
