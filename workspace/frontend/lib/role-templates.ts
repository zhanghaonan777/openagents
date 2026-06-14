/**
 * Role-template catalog for the "Add role" library (proposal module C).
 *
 * This is a frontend-only catalog — the OpenAgents backend models agents by
 * runtime `agentType` (claude/codex/…), not by professional role. Joining a
 * role is wired to a launcher integration point (`agn create … + connect`);
 * see the onAddRole handler in components/layout/wrapper.tsx.
 *
 * Avatars reuse the same boring-avatars "beam" palette as AgentAvatar so a
 * joined role's live avatar matches its card.
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

export const ROLE_CATEGORIES: Record<string, RoleCategory> = {
  product: { id: 'product', label: 'Product', color: '#6366F1' },
  eng: { id: 'eng', label: 'Engineering', color: '#0EA5E9' },
  design: { id: 'design', label: 'Design', color: '#8B5CF6' },
  data: { id: 'data', label: 'Data / AI', color: '#10B981' },
  security: { id: 'security', label: 'Security', color: '#F43F5E' },
  quality: { id: 'quality', label: 'Quality', color: '#F59E0B' },
  growth: { id: 'growth', label: 'Growth', color: '#EC4899' },
};

export const ROLE_MODELS: Record<string, RoleModel> = {
  claude: { id: 'claude', label: 'Claude Sonnet', short: 'claude', tint: '#D97757' },
  minimax: { id: 'minimax', label: 'MiniMax M2', short: 'minimax', tint: '#FF6B5A' },
  gpt: { id: 'gpt', label: 'GPT-4.1', short: 'gpt-4.1', tint: '#10A37F' },
  gemini: { id: 'gemini', label: 'Gemini 2.5', short: 'gemini', tint: '#4285F4' },
};

export const ROLE_TEMPLATES: RoleTemplate[] = [
  {
    id: 'product-manager', name: 'Product Manager', cat: 'product', model: 'claude',
    tagline: 'Turns fuzzy requests into a shippable roadmap.',
    skills: ['Discovery', 'Roadmapping', 'Prioritization', 'PRDs', 'Stakeholders'],
    abilities: ['Breaks user stories into assignable task cards', 'Coordinates schedules and dependencies across roles', 'Makes data-driven prioritization calls'],
  },
  {
    id: 'frontend-engineer', name: 'Frontend Engineer', cat: 'eng', model: 'claude',
    tagline: 'Pixel-faithful React / Next.js implementation.',
    skills: ['React 19', 'Next.js', 'Tailwind', 'Motion', 'A11y'],
    abilities: ['Builds components from design specs and wires state', 'Polishes interactions and responsive layout', 'Fixes styling and accessibility defects'],
  },
  {
    id: 'backend-engineer', name: 'Backend Engineer', cat: 'eng', model: 'gpt',
    tagline: 'Draws systems as service boundaries that ship.',
    skills: ['System Design', 'APIs', 'Databases', 'Concurrency', 'Observability'],
    abilities: ['Designs service boundaries and data models', 'Reviews API contracts and performance', 'Debugs distributed-system failures'],
  },
  {
    id: 'fullstack-engineer', name: 'Fullstack Engineer', cat: 'eng', model: 'claude',
    tagline: 'Takes a demo end-to-end, solo.',
    skills: ['TypeScript', 'Node', 'Prototyping', 'Deploy', 'Scaffolding'],
    abilities: ['Stands up end-to-end prototypes from scratch', 'Connects front and back ends', 'Ships a demoable build fast'],
  },
  {
    id: 'devops-engineer', name: 'DevOps Engineer', cat: 'eng', model: 'gpt',
    tagline: 'Pipelines, containers, observability — end to end.',
    skills: ['Docker', 'CI/CD', 'K8s', 'Monitoring', 'Alerting'],
    abilities: ['Orchestrates containers and deploy pipelines', 'Sets up monitoring and alerts', 'Triages production incidents'],
  },
  {
    id: 'ui-designer', name: 'UI Designer', cat: 'design', model: 'claude',
    tagline: 'Weaves tokens and grids into interfaces with taste.',
    skills: ['Design Systems', 'Grids', 'Color', 'Components', 'Specs'],
    abilities: ['Defines design tokens and component specs', 'Produces high-fidelity interface mockups', 'Audits visual consistency'],
  },
  {
    id: 'ux-researcher', name: 'UX Researcher', cat: 'design', model: 'gemini',
    tagline: 'Hears what users won’t say out loud.',
    skills: ['Interviews', 'Usability', 'Journeys', 'IA'],
    abilities: ['Designs and analyzes usability tests', 'Maps user journeys and pain points', 'Turns insight into design direction'],
  },
  {
    id: 'data-analyst', name: 'Data Analyst', cat: 'data', model: 'minimax',
    tagline: 'Refines raw logs into decisions.',
    skills: ['SQL', 'Metrics', 'Dashboards', 'A/B Tests'],
    abilities: ['Builds metric systems and dashboards', 'Designs and reads A/B experiments', 'Finds growth openings in the data'],
  },
  {
    id: 'ml-engineer', name: 'ML Engineer', cat: 'data', model: 'gpt',
    tagline: 'Tames paper models into production services.',
    skills: ['Training', 'Eval', 'RAG', 'Inference', 'MLOps'],
    abilities: ['Builds training and eval pipelines', 'Optimizes inference latency and cost', 'Ships RAG and retrieval augmentation'],
  },
  {
    id: 'security-auditor', name: 'Security Auditor', cat: 'security', model: 'claude',
    tagline: 'Thinks through the worst case before you ship.',
    skills: ['Threat Modeling', 'Code Audit', 'OWASP', 'Secrets', 'Compliance'],
    abilities: ['Audits code and dependencies for risk', 'Models attack surface and threats', 'Returns an actionable hardening checklist'],
  },
  {
    id: 'pentester', name: 'Penetration Tester', cat: 'security', model: 'minimax',
    tagline: 'Thinks like an attacker, finds the gaps first.',
    skills: ['Pentest', 'Repro', 'Reporting', 'Social Eng'],
    abilities: ['Simulates attack paths to find holes', 'Reproduces and verifies security defects', 'Produces a remediable pentest report'],
  },
  {
    id: 'qa-engineer', name: 'QA Engineer', cat: 'quality', model: 'gemini',
    tagline: 'Seals off the edge cases, one by one.',
    skills: ['Test Cases', 'Automation', 'Regression', 'Bug Tracking'],
    abilities: ['Designs full-coverage test cases', 'Builds automated regression', 'Locates and reproduces defects'],
  },
  {
    id: 'code-reviewer', name: 'Code Reviewer', cat: 'quality', model: 'claude',
    tagline: 'Holds the quality line before merge.',
    skills: ['Review', 'Refactor', 'Standards', 'Perf', 'Maintainability'],
    abilities: ['Reviews PRs with concrete suggestions', 'Spots smells and refactor points', 'Unifies team code standards'],
  },
  {
    id: 'growth-engineer', name: 'Growth Engineer', cat: 'growth', model: 'minimax',
    tagline: 'Finds the lever to pull at every funnel step.',
    skills: ['Experiments', 'Funnels', 'Retention', 'Tracking'],
    abilities: ['Designs growth experiments and funnels', 'Analyzes retention and conversion', 'Finds levers worth scaling'],
  },
  {
    id: 'technical-writer', name: 'Technical Writer', cat: 'growth', model: 'claude',
    tagline: 'Makes the product make sense in one line.',
    skills: ['Docs', 'UX Copy', 'Release Notes', 'i18n'],
    abilities: ['Polishes interface and brand copy', 'Writes release notes and announcements', 'Unifies product voice and terms'],
  },
  {
    id: 'mobile-engineer', name: 'Mobile Engineer', cat: 'eng', model: 'gpt',
    tagline: 'iOS and Android, both surefooted.',
    skills: ['Swift', 'Kotlin', 'Cross-platform', 'Offline', 'Push'],
    abilities: ['Builds native experiences on both platforms', 'Handles offline and sync', 'Optimizes startup and smoothness'],
  },
];

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
