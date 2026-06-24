/**
 * Wiring check: run each tool handler against a live backend (no MCP client
 * needed). Usage:
 *   A2A_NETWORK=.. A2A_TOKEN=.. A2A_AGENT=alice node dist/smoke.js [coworker]
 */
import { loadConfig } from './a2a.js';
import { createToolHandlers } from './tools.js';

async function main() {
  const cfg = loadConfig();
  const h = createToolHandlers(cfg);
  const log = (label: string, v: unknown) => console.log(`\n## ${label}\n` + JSON.stringify(v, null, 2));

  const mates = (await h.list_teammates({})) as { teammates: { name: string }[] };
  log('list_teammates', mates);

  const coworker = process.argv[2] || mates.teammates[0]?.name;
  if (!coworker) {
    console.log('\n(no teammates to talk to)');
    return;
  }

  log('message_teammate', await h.message_teammate({ coworker, text: 'smoke: quick hello' }));
  log('delegate_to_teammate', await h.delegate_to_teammate({ coworker, task: 'smoke: write a unit test' }));
  log('consult_teammate', await h.consult_teammate({ coworker, question: 'smoke: which DB did we pick?' }));
  log('my_tasks', await h.my_tasks({}));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
