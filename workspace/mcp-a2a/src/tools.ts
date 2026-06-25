/**
 * The "talk to a teammate" tool surface. Tool naming and descriptions follow
 * CrewAI's proven delegation tools (Ask question / Delegate work to coworker),
 * which map cleanly onto the two agent-to-agent patterns:
 *   - consult  = agent-as-tool   (ask a specific question, get an answer back)
 *   - delegate = handoff         (hand a whole task to a specialist)
 * plus a lightweight DM and a "what's assigned to me" check. Every handler is a
 * thin wrapper over the A2A gateway (see a2a.ts).
 */
import type { Tool } from '@modelcontextprotocol/sdk/types.js';

import {
  A2AConfig,
  artifactText,
  consult,
  createTask,
  listAgents,
  listMyTasks,
  sendPeerMessage,
} from './a2a.js';

const TERMINAL = new Set(['completed', 'failed', 'canceled', 'rejected']);

export const TOOLS: Tool[] = [
  {
    name: 'list_teammates',
    description:
      'List the other agents on your team you can talk to, with their roles and declared skills. Call this first to discover who to consult or delegate to.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'consult_teammate',
    description:
      'Ask a specific question to a teammate and get their answer back, so you can keep working with the result. Use when you need information or a focused check from a colleague — not to hand off the whole task. Blocks briefly for the reply.',
    inputSchema: {
      type: 'object',
      properties: {
        coworker: { type: 'string', description: 'The teammate to ask (agent name from list_teammates).' },
        question: { type: 'string', description: 'The specific question you need answered.' },
        context: { type: 'string', description: 'Optional background to frame the question.' },
      },
      required: ['coworker', 'question'],
    },
  },
  {
    name: 'delegate_to_teammate',
    description:
      'Hand a whole task to a teammate with the right expertise. Use when the work belongs to someone else; control passes to them and the task is tracked on the board. Returns immediately with a task id (fire-and-forget).',
    inputSchema: {
      type: 'object',
      properties: {
        coworker: { type: 'string', description: 'The teammate to delegate to (agent name).' },
        task: { type: 'string', description: 'The work to be done.' },
        context: { type: 'string', description: 'Optional background or constraints.' },
      },
      required: ['coworker', 'task'],
    },
  },
  {
    name: 'message_teammate',
    description:
      'Send a short direct message to a teammate in your private 1:1 thread (no task, no board). Use for a quick heads-up or note.',
    inputSchema: {
      type: 'object',
      properties: {
        coworker: { type: 'string', description: 'The teammate to message (agent name).' },
        text: { type: 'string', description: 'The message.' },
      },
      required: ['coworker', 'text'],
    },
  },
  {
    name: 'my_tasks',
    description: 'List the open tasks currently assigned to you (delegated by teammates or humans).',
    inputSchema: { type: 'object', properties: {} },
  },
];

type Args = Record<string, unknown>;
const str = (v: unknown) => (typeof v === 'string' ? v.trim() : '');

export function createToolHandlers(cfg: A2AConfig): Record<string, (a: Args) => Promise<unknown>> {
  return {
    async list_teammates() {
      const { agents } = await listAgents(cfg);
      return {
        teammates: agents
          .filter((a) => a.name !== cfg.agent)
          .map((a) => ({
            name: a.name,
            role: a.description || undefined,
            skills: (a.skills || []).map((s) => s.name),
          })),
      };
    },

    async consult_teammate(a) {
      const coworker = str(a.coworker);
      const question = str(a.question);
      const context = str(a.context);
      if (!coworker || !question) throw new Error('Invalid input: coworker and question are required');
      // Use the dedicated /consult endpoint, which blocks for the teammate's
      // *reply message* (these agents answer in chat, not by completing a task).
      const q = context ? `${question}\n\nContext: ${context}` : question;
      return consult(cfg, { to: coworker, question: q, wait: 75 });
    },

    async delegate_to_teammate(a) {
      const coworker = str(a.coworker);
      const work = str(a.task);
      const context = str(a.context);
      if (!coworker || !work) throw new Error('Invalid input: coworker and task are required');
      const text = context ? `${work}\n\nContext: ${context}` : work;
      const task = await createTask(cfg, { contractor: coworker, text, wait: 0 });
      return { delegated: true, to: coworker, taskId: task.id, state: task.state };
    },

    async message_teammate(a) {
      const coworker = str(a.coworker);
      const text = str(a.text);
      if (!coworker || !text) throw new Error('Invalid input: coworker and text are required');
      const r = await sendPeerMessage(cfg, { to: coworker, text });
      return { delivered: true, to: coworker, thread: r.channel };
    },

    async my_tasks() {
      const { tasks } = await listMyTasks(cfg);
      return {
        tasks: tasks
          .filter((t) => !TERMINAL.has(t.state))
          .map((t) => ({ id: t.id, from: t.delegator, state: t.state, request: artifactText(t) ?? undefined })),
      };
    },
  };
}
