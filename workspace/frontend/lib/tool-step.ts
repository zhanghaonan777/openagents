// Shared parser for an agent's "intermediate step" messages (tool calls,
// thinking, status). Both the chat step list (components/chat/intermediate-steps)
// and the dense monitor tiles (components/monitor/monitor-tile) parse the same
// launcher/adapter markdown — this is the one definition they share.

export interface ParsedStep {
  type: 'thinking' | 'tool_call' | 'status' | 'compacting';
  tool?: string;        // raw tool name as emitted
  toolDisplay?: string; // cleaned (mcp prefixes stripped)
  args?: string;        // the tool args block, when present
  summary?: string;     // a one-line summary (file path / command / …)
  text?: string;        // thinking / status / compacting body
}

/** Strip MCP namespace prefixes from a tool name (mcp__server__tool → tool). */
export function cleanToolName(name: string): string {
  const mcpMatch = name.match(/^mcp__[^_]+__(.+)$/);
  if (mcpMatch) return mcpMatch[1];
  const mcpMatch2 = name.match(/^mcp_[^_]+--.+?__(.+)$/);
  if (mcpMatch2) return mcpMatch2[1];
  return name;
}

/** Best-effort one-line summary of a tool call from its serialized args. */
export function extractToolSummary(tool: string, args: string): string {
  const fileMatch = args.match(/'file_path':\s*'([^']+)'/);
  if (fileMatch && ['Write', 'Read', 'Edit'].includes(tool)) {
    return fileMatch[1];
  }
  const commandMatch = args.match(/'command':\s*'([^']+)'/);
  if (commandMatch && tool === 'Bash') {
    return commandMatch[1].slice(0, 80);
  }
  const statusMatch = args.match(/'status':\s*'([^']+)'/);
  if (statusMatch) return statusMatch[1];
  const contentMatch = args.match(/'content':\s*'([^']{0,60})/);
  if (contentMatch) {
    return contentMatch[1] + (contentMatch[1].length >= 60 ? '...' : '');
  }
  const patternMatch = args.match(/'pattern':\s*'([^']+)'/);
  if (patternMatch) return patternMatch[1];
  return args.length > 60 ? args.slice(0, 60) + '...' : args;
}

/** Parse one step message's content into a structured ParsedStep. */
export function parseToolStep(content: string): ParsedStep {
  // Thinking placeholder
  if (content === 'thinking...' || content.toLowerCase() === 'thinking') {
    return { type: 'thinking', text: content };
  }
  // Claude adapter: **Thinking:**\n{content}
  const thinkingMatch = content.match(/^\*\*Thinking:\*\*\n([\s\S]+)$/);
  if (thinkingMatch) {
    return { type: 'thinking', text: thinkingMatch[1].trim() };
  }
  // Claude adapter: **Using tool:** `ToolName` [optional ```args``` block]
  const toolMatch = content.match(/\*\*Using tool:\*\*\s*`([^`]+)`/);
  if (toolMatch) {
    const rawTool = toolMatch[1];
    const toolDisplay = cleanToolName(rawTool);
    const block = content.match(/```([\s\S]*?)```/);
    // With an args block, summarize from it; otherwise scan the whole content.
    const argsForSummary = block ? block[1].trim() : content;
    const summary = extractToolSummary(toolDisplay, argsForSummary);
    return { type: 'tool_call', tool: rawTool, toolDisplay, args: block ? block[1].trim() : undefined, summary };
  }
  // Codex adapter: **Running:** `command`
  const runMatch = content.match(/\*\*Running:\*\*\s*`([^`]+)`/);
  if (runMatch) {
    return { type: 'tool_call', tool: 'Bash', toolDisplay: 'Bash', summary: runMatch[1] };
  }
  // Codex adapter: **Editing:** `filename`
  const editMatch = content.match(/\*\*Editing:\*\*\s*`([^`]+)`/);
  if (editMatch) {
    return { type: 'tool_call', tool: 'Edit', toolDisplay: 'Edit', summary: editMatch[1] };
  }
  // Compaction / context management
  if (/compact/i.test(content)) {
    return { type: 'compacting', text: content };
  }
  // General status
  return { type: 'status', text: content };
}

/** Flat "Tool › summary" label for dense one-line views (monitor tiles). */
export function toolStepLabel(p: ParsedStep): string {
  if (p.type === 'tool_call') {
    return p.summary ? `${p.toolDisplay} › ${p.summary}` : (p.toolDisplay || '');
  }
  return (p.text || '').replace(/\n+/g, ' ').trim();
}
