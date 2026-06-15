/**
 * Role-template catalog for the "Add role" library (proposal module C).
 *
 * Source: VoltAgent/awesome-claude-code-subagents (~154 professional roles
 * across 10 categories). The role list lives in the auto-generated
 * `role-templates.data.ts` (regenerate with `scripts/gen-roles.py`, do not hand-edit);
 * categories, model badges and helpers are defined here.
 *
 * This is a frontend-only catalog — the OpenAgents backend models agents by
 * runtime `agentType`, not professional role. Joining a role is wired to a
 * launcher integration point (`agn create --path roles/<id> + connect`); each
 * role's persona is that subagent's markdown body (its CLAUDE.md).
 */

export interface RoleCategory {
  id: string;
  label: string;
  color: string;
}

export interface RoleModel {
  id: string;
  label: string;
  short: string;
  tint: string;
}

export interface RoleTemplate {
  id: string;
  name: string;
  cat: string;
  model: string;
  tagline: string;
  skills: string[];
  abilities: string[];
}

import { ROLE_TEMPLATES } from './role-templates.data';
export { ROLE_TEMPLATES };

// VoltAgent's 10 categories (dir-name slugs, minus the numeric prefix).
export const ROLE_CATEGORIES: Record<string, RoleCategory> = {
  'core-development': { id: 'core-development', label: 'Core Dev', color: '#6366F1' },
  'language-specialists': { id: 'language-specialists', label: 'Languages', color: '#0EA5E9' },
  'infrastructure': { id: 'infrastructure', label: 'Infrastructure', color: '#14B8A6' },
  'quality-security': { id: 'quality-security', label: 'Quality & Security', color: '#F43F5E' },
  'data-ai': { id: 'data-ai', label: 'Data / AI', color: '#10B981' },
  'developer-experience': { id: 'developer-experience', label: 'DevEx', color: '#8B5CF6' },
  'specialized-domains': { id: 'specialized-domains', label: 'Specialized', color: '#F59E0B' },
  'business-product': { id: 'business-product', label: 'Business', color: '#EC4899' },
  'meta-orchestration': { id: 'meta-orchestration', label: 'Orchestration', color: '#A855F7' },
  'research-analysis': { id: 'research-analysis', label: 'Research', color: '#06B6D4' },
};

// VoltAgent roles run on Claude tiers; cross-model badges kept for future sources.
export const ROLE_MODELS: Record<string, RoleModel> = {
  claude: { id: 'claude', label: 'Claude', short: 'claude', tint: '#D97757' },
  minimax: { id: 'minimax', label: 'MiniMax M2', short: 'minimax', tint: '#FF6B5A' },
  gpt: { id: 'gpt', label: 'GPT-4.1', short: 'gpt-4.1', tint: '#10A37F' },
  gemini: { id: 'gemini', label: 'Gemini 2.5', short: 'gemini', tint: '#4285F4' },
};

// A role's persona (its CLAUDE.md) is runtime-agnostic — the same role can run
// on any launcher runtime; the runtime is chosen when the role is added.
// `personaFidelity: 'full'` = the runtime injects the role's CLAUDE.md as-is
// (Claude Code reads it from the working dir). For others it depends on the
// launcher adapter; openclaw, for instance, doesn't inject CLAUDE.md today.
export interface AgentRuntime {
  id: string;
  label: string;
  hint: string;
  tint: string;
  personaFidelity: 'full' | 'partial';
}

export const RUNTIMES: AgentRuntime[] = [
  { id: 'claude', label: 'Claude', hint: 'Claude Code login · no API key', tint: '#D97757', personaFidelity: 'full' },
  { id: 'openclaw', label: 'OpenClaw', hint: 'Local MiniMax', tint: '#FF6B5A', personaFidelity: 'partial' },
  { id: 'codex', label: 'Codex', hint: 'GPT', tint: '#10A37F', personaFidelity: 'partial' },
  { id: 'gemini', label: 'Gemini', hint: 'Google', tint: '#4285F4', personaFidelity: 'partial' },
  { id: 'opencode', label: 'OpenCode', hint: 'Open-source coding agent', tint: '#8B5CF6', personaFidelity: 'partial' },
  { id: 'cursor', label: 'Cursor', hint: 'Cursor agent', tint: '#6366F1', personaFidelity: 'partial' },
  { id: 'kimi', label: 'Kimi', hint: 'Moonshot', tint: '#06B6D4', personaFidelity: 'partial' },
  { id: 'hermes', label: 'Hermes', hint: '', tint: '#10B981', personaFidelity: 'partial' },
];

export function runtimeById(id: string): AgentRuntime | undefined {
  return RUNTIMES.find((r) => r.id === id);
}

const TEMPLATES_BY_NAME = new Map(ROLE_TEMPLATES.map((r) => [r.name.toLowerCase(), r]));

/** Look up a role template by an agent's display name (case-insensitive). */
export function roleTemplateByName(name: string | null | undefined): RoleTemplate | undefined {
  if (!name) return undefined;
  return TEMPLATES_BY_NAME.get(name.toLowerCase());
}

/** Same beam palette as AgentAvatar — stable specialty color from any name. */
const OA_PALETTE = ['#6366F1', '#8B5CF6', '#06B6D4', '#10B981', '#F59E0B'];

export function colorFromName(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h << 5) - h + name.charCodeAt(i);
    h |= 0;
  }
  return OA_PALETTE[Math.abs(h) % OA_PALETTE.length];
}
