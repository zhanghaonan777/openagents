/**
 * Thin HTTP client for the OpenAgents A2A gateway (workspace/backend
 * app/routers/a2a.py). The MCP tools are pure wrappers over these calls — no
 * local state, no duplicated protocol logic. Backed by the same endpoints the
 * web UI uses.
 */

export interface A2AConfig {
  baseUrl: string;
  network: string; // workspace id
  token: string; // workspace token
  agent: string; // the agent this server speaks for ("me")
}

/** Read config from the environment; throw a clear error if a required var is missing. */
export function loadConfig(): A2AConfig {
  const network = process.env.A2A_NETWORK;
  const token = process.env.A2A_TOKEN;
  const agent = process.env.A2A_AGENT;
  const baseUrl = process.env.A2A_BASE_URL ?? 'http://localhost:8000';
  const missing = [
    ['A2A_NETWORK', network],
    ['A2A_TOKEN', token],
    ['A2A_AGENT', agent],
  ].filter(([, v]) => !v).map(([k]) => k);
  if (missing.length) {
    throw new Error(`Missing required env: ${missing.join(', ')}`);
  }
  return { baseUrl, network: network!, token: token!, agent: agent! };
}

export const selfAddress = (cfg: A2AConfig) => `openagents:${cfg.agent}`;

interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

async function request<T>(cfg: A2AConfig, method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${cfg.baseUrl}${path}`, {
    method,
    headers: {
      'X-Workspace-Token': cfg.token,
      'Content-Type': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json: ApiEnvelope<T>;
  try {
    json = (await res.json()) as ApiEnvelope<T>;
  } catch {
    throw new Error(`A2A ${method} ${path} → non-JSON response (HTTP ${res.status})`);
  }
  if (json.code !== 0) {
    throw new Error(json.message || `A2A ${method} ${path} failed (HTTP ${res.status})`);
  }
  return json.data;
}

// ── Shapes (only the fields the tools use) ──
export interface AgentCard {
  name: string;
  description?: string;
  skills?: { id: string; name: string; description?: string }[];
}
export interface A2ATask {
  id: string;
  state: string;
  contractorName: string;
  delegator: string;
  channel: string | null;
  artifacts: { parts: { text?: string }[] }[];
  createdAt: string | null;
}

const enc = encodeURIComponent;

export function listAgents(cfg: A2AConfig): Promise<{ agents: AgentCard[] }> {
  return request(cfg, 'GET', `/v1/a2a/agents?network=${enc(cfg.network)}`);
}

export function createTask(
  cfg: A2AConfig,
  p: { contractor: string; text: string; wait?: number },
): Promise<A2ATask> {
  return request(cfg, 'POST', '/v1/a2a/tasks', {
    network: cfg.network,
    source: selfAddress(cfg),
    contractor: p.contractor,
    text: p.text,
    wait: p.wait ?? 0,
  });
}

export function sendPeerMessage(
  cfg: A2AConfig,
  p: { to: string; text: string; expectsReply?: boolean },
): Promise<{ channel: string; from: string; to: string }> {
  return request(cfg, 'POST', '/v1/a2a/messages', {
    network: cfg.network,
    source: selfAddress(cfg),
    to: p.to,
    text: p.text,
    expects_reply: !!p.expectsReply,
  });
}

export function listMyTasks(cfg: A2AConfig): Promise<{ tasks: A2ATask[] }> {
  return request(cfg, 'GET', `/v1/a2a/tasks?network=${enc(cfg.network)}&contractor=${enc(cfg.agent)}`);
}

/** The contractor's reported result (first artifact's text), if any. */
export function artifactText(task: A2ATask): string | null {
  for (const a of task.artifacts || []) {
    for (const part of a.parts || []) {
      if (part.text) return part.text;
    }
  }
  return null;
}
