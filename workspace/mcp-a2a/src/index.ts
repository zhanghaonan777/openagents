#!/usr/bin/env node
/**
 * Stdio entrypoint. One instance runs per agent, parameterized by env
 * (A2A_AGENT identifies "me"). Pattern follows agent-hub-mcp/src/index.ts.
 */
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

import { loadConfig } from './a2a.js';
import { createMcpServer } from './server.js';

async function main() {
  const cfg = loadConfig();
  const server = createMcpServer(cfg);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // eslint-disable-next-line no-console
  console.error(`openagents-a2a-mcp ready — speaking for "${cfg.agent}" @ ${cfg.baseUrl}`);
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Failed to start a2a-mcp:', error);
  process.exit(1);
});
