/**
 * MCP server wiring. Skeleton adapted from gilbarbara/agent-hub-mcp
 * (src/servers/mcp.ts): a low-level Server with ListTools / CallTool handlers,
 * tool results wrapped as a single JSON text block. The Initialize handler
 * injects usage instructions so the agent knows it can talk to teammates.
 */
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  InitializeRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import { A2AConfig } from './a2a.js';
import { createToolHandlers, TOOLS } from './tools.js';

export function createMcpServer(cfg: A2AConfig): Server {
  const server = new Server(
    { name: 'openagents-a2a-mcp', version: '0.1.0' },
    { capabilities: { tools: {} } },
  );

  const handlers = createToolHandlers(cfg);

  server.setRequestHandler(InitializeRequestSchema, async (request) => ({
    protocolVersion: request.params.protocolVersion,
    capabilities: { tools: {} },
    serverInfo: { name: 'openagents-a2a-mcp', version: '0.1.0' },
    instructions:
      `You are agent "${cfg.agent}" on a team. You can talk to your teammates directly:\n` +
      `• list_teammates — see who's on the team and their skills\n` +
      `• consult_teammate(coworker, question) — ask a teammate a question and use their answer\n` +
      `• delegate_to_teammate(coworker, task) — hand a whole task to the right specialist\n` +
      `• message_teammate(coworker, text) — a quick 1:1 note\n` +
      `• my_tasks — what teammates have asked you to do\n\n` +
      `Prefer consulting a specialist over guessing outside your expertise. ` +
      `Keep exchanges purposeful — ask a concrete question or hand off real work; don't send status chatter.`,
  }));

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const handler = handlers[name];
    if (!handler) {
      return { content: [{ type: 'text', text: JSON.stringify({ error: `Unknown tool: ${name}` }) }], isError: true };
    }
    try {
      const result = await handler((args ?? {}) as Record<string, unknown>);
      return { content: [{ type: 'text', text: JSON.stringify(result) }] };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Operation failed';
      // eslint-disable-next-line no-console
      console.error(`a2a-mcp: tool ${name} failed:`, error);
      return { content: [{ type: 'text', text: JSON.stringify({ error: message }) }], isError: true };
    }
  });

  return server;
}
