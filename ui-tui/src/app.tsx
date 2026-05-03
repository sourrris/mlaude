import { spawnSync } from 'node:child_process';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Text, useApp, useInput } from 'ink';

import { artWidth, hero, HERO_WIDTH, logo, LOGO_WIDTH } from './banner.js';
import { GatewayClient } from './gateway-client.js';
import { applyGatewayEvent } from './state.js';
import { THEME } from './theme.js';

const STATUS_COLOR = (busy: boolean, detail: string) => {
  if (detail.startsWith('error')) {
    return THEME.color.error;
  }
  if (busy) {
    return THEME.color.warn;
  }
  return THEME.color.dim;
};

const truncate = (value: string, max = 240) =>
  value.length > max ? `${value.slice(0, Math.max(0, max - 1))}…` : value;

const plainTextLines = (text: string) => (text ? text.split('\n') : ['']);

const compactJson = (value: unknown, max = 120) => {
  if (value === null || value === undefined) {
    return '';
  }

  try {
    return truncate(JSON.stringify(value), max);
  } catch {
    return truncate(String(value), max);
  }
};

const buildRule = (label: string, cols: number) => {
  const safeCols = Math.max(32, cols);
  const prefix = `  ${label}  `;
  const fill = Math.max(8, safeCols - prefix.length);
  return `${prefix}${'─'.repeat(fill)}`;
};

const buildCenteredRule = (label: string, cols: number) => {
  const safeCols = Math.max(32, cols);
  const capped = truncate(label, Math.max(10, safeCols - 8));
  const available = Math.max(4, safeCols - capped.length - 2);
  const left = Math.max(2, Math.floor(available / 2));
  const right = Math.max(2, available - left);
  return `${'─'.repeat(left)} ${capped} ${'─'.repeat(right)}`;
};

const formatStatus = (status: Record<string, unknown>) => {
  const parts = [
    status.busy ? 'busy' : 'idle',
    status.detail ? String(status.detail) : '',
    status.provider_label ? String(status.provider_label) : '',
    status.model ? String(status.model) : '',
    status.session_tokens ? `session ${Number(status.session_tokens).toLocaleString()}` : '',
  ].filter(Boolean);

  return parts.join(' | ') || 'idle';
};

const apiCallLabel = (count: number) => `${count} API call${count === 1 ? '' : 's'}`;

const copyToClipboard = (text: string) => {
  if (!text) {
    return false;
  }

  const candidates =
    process.platform === 'darwin'
      ? [['pbcopy']]
      : process.platform === 'win32'
        ? [['clip']]
        : [['wl-copy'], ['xclip', '-selection', 'clipboard']];

  for (const [command, ...args] of candidates) {
    const result = spawnSync(command, args, { input: text, encoding: 'utf8' });

    if (result.status === 0) {
      return true;
    }
  }

  return false;
};

function ArtLines({ lines }: { lines: Array<[string, string]> }) {
  return (
    <Box flexDirection="column">
      {lines.map(([color, text], index) => (
        <Text color={color} key={index}>
          {text}
        </Text>
      ))}
    </Box>
  );
}

function StartupPanel({
  cols,
  cwd,
  model,
  provider,
  sessionId,
}: {
  cols: number;
  cwd: string;
  model: string;
  provider: string;
  sessionId: string;
}) {
  const logoLines = logo();
  const heroLines = hero();
  const wide = cols >= 110;
  const leftWidth = Math.min((artWidth(heroLines) || HERO_WIDTH) + 4, Math.floor(cols * 0.38));

  return (
    <Box flexDirection="column" marginBottom={1} marginTop={1}>
      {cols >= LOGO_WIDTH ? (
        <ArtLines lines={logoLines} />
      ) : (
        <Text bold color={THEME.color.gold}>
          {THEME.brand.icon} MLAUDE
        </Text>
      )}

      <Text color={THEME.color.dim}>
        {THEME.brand.icon} {THEME.brand.subtitle}
      </Text>

      <Box borderColor={THEME.color.bronze} borderStyle="round" flexDirection="column" marginTop={1} paddingX={1}>
        {wide ? (
          <Box>
            <Box flexDirection="column" marginRight={2} width={leftWidth}>
              <ArtLines lines={heroLines} />
            </Box>

            <Box flexDirection="column" flexGrow={1}>
              <Text bold color={THEME.color.gold}>
                {THEME.brand.name}
              </Text>
              <Text color={THEME.color.dim} wrap="truncate-end">
                {provider || 'Provider auto-detect'}
              </Text>
              <Text color={THEME.color.cornsilk} wrap="truncate-end">
                {model}
              </Text>
              <Text color={THEME.color.dim} wrap="truncate-end">
                {cwd}
              </Text>
              <Text color={THEME.color.dim} wrap="truncate-end">
                Session: {sessionId || 'pending'}
              </Text>
              <Text> </Text>
              <Text color={THEME.color.cornsilk}>/help for commands</Text>
            </Box>
          </Box>
        ) : (
          <Box flexDirection="column">
            <Text bold color={THEME.color.gold}>
              {THEME.brand.name}
            </Text>
            <Text color={THEME.color.dim} wrap="truncate-end">
              {provider || 'Provider auto-detect'}
            </Text>
            <Text color={THEME.color.cornsilk} wrap="truncate-end">
              {model}
            </Text>
            <Text color={THEME.color.dim} wrap="truncate-end">
              {cwd}
            </Text>
            <Text color={THEME.color.dim} wrap="truncate-end">
              Session: {sessionId || 'pending'}
            </Text>
            <Text color={THEME.color.cornsilk}>/help for commands</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
}

function AssistantMessage({ cols, content }: { cols: number; content: string }) {
  return (
    <Box flexDirection="column" marginBottom={1} marginTop={1}>
      <Text color={THEME.color.amber}>{buildRule(`${THEME.brand.icon} ${THEME.brand.assistant}`, cols)}</Text>
      <Box borderColor={THEME.color.amber} borderStyle="round" flexDirection="column" paddingX={1}>
        {plainTextLines(content).map((line, index) => (
          <Text color={THEME.color.cornsilk} key={index} wrap="wrap">
            {line || ' '}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <Box marginTop={1}>
      <Text bold color={THEME.color.label}>
        {THEME.brand.prompt}{' '}
      </Text>
      <Text color={THEME.color.cornsilk} wrap="wrap">
        {content}
      </Text>
    </Box>
  );
}

function ReasoningBlock({ content }: { content: string }) {
  return (
    <Box flexDirection="column" marginLeft={2} marginTop={1}>
      <Text color={THEME.color.dim}>{THEME.brand.tool} thinking</Text>
      {plainTextLines(content).slice(0, 8).map((line, index) => (
        <Text color={THEME.color.dim} dimColor key={index} wrap="wrap">
          │ {line || ' '}
        </Text>
      ))}
    </Box>
  );
}

function ToolBlock({ cols, entry }: { cols: number; entry: any }) {
  const summary = entry.arguments ? ` ${entry.arguments}` : '';
  const title =
    entry.status === 'running'
      ? `${THEME.brand.tool} ${entry.name}${summary}`
      : `${THEME.brand.tool} ${entry.name} complete`;

  return (
    <Box flexDirection="column" marginLeft={2} marginTop={1}>
      <Text color={entry.status === 'running' ? THEME.color.amber : THEME.color.dim} wrap="wrap">
        {title}
      </Text>
      {entry.content ? (
        <Box borderColor={THEME.color.dim} borderStyle="round" flexDirection="column" marginLeft={2} paddingX={1}>
          {plainTextLines(truncate(entry.content, Math.max(80, cols * 4))).slice(0, 6).map((line, index) => (
            <Text color={THEME.color.dim} key={index} wrap="wrap">
              {line || ' '}
            </Text>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

function PanelBlock({ title, body }: { title: string; body: string }) {
  return (
    <Box borderColor={THEME.color.bronze} borderStyle="round" flexDirection="column" marginTop={1} paddingX={1}>
      <Text bold color={THEME.color.gold}>
        {title}
      </Text>
      {plainTextLines(body).map((line, index) => (
        <Text color={THEME.color.cornsilk} key={index} wrap="wrap">
          {line || ' '}
        </Text>
      ))}
    </Box>
  );
}

function NoticeBlock({ body, level }: { body: string; level: string }) {
  const color =
    level === 'error'
      ? THEME.color.error
      : level === 'warn'
        ? THEME.color.warn
        : level === 'metric'
          ? THEME.color.dim
          : THEME.color.ok;

  return (
    <Text color={color} dimColor={level === 'metric'} wrap="wrap">
      {level === 'metric' ? `(${body})` : `• ${body}`}
    </Text>
  );
}

function renderEntry(entry: any, index: number, cols: number) {
  if (entry.kind === 'message') {
    return entry.role === 'user' ? (
      <UserMessage content={entry.content} key={index} />
    ) : (
      <AssistantMessage cols={cols} content={entry.content} key={index} />
    );
  }

  if (entry.kind === 'reasoning') {
    return <ReasoningBlock content={entry.content} key={index} />;
  }

  if (entry.kind === 'tool') {
    return <ToolBlock cols={cols} entry={entry} key={index} />;
  }

  if (entry.kind === 'panel') {
    return <PanelBlock body={entry.body} key={index} title={entry.title} />;
  }

  return <NoticeBlock body={entry.body} key={index} level={entry.level || 'info'} />;
}

export function App() {
  const { exit } = useApp();
  const [client] = useState(() => new GatewayClient());
  const [catalog, setCatalog] = useState({ commands: [] as Array<any> });
  const [transcript, setTranscript] = useState<any[]>([]);
  const [status, setStatus] = useState<Record<string, unknown>>({ detail: 'starting…', busy: true });
  const [sessionId, setSessionId] = useState('');
  const [input, setInput] = useState('');
  const [approval, setApproval] = useState<null | { toolName: string }>(null);
  const pendingTurn = useRef(false);
  const cols = process.stdout.columns ?? 100;

  useEffect(() => {
    process.stdout.write('\u001b[?1049h');
    return () => {
      process.stdout.write('\u001b[?1049l');
      client.close();
    };
  }, [client]);

  useEffect(() => {
    const unsubscribe = client.onEvent(event => {
      if (event.method === 'gateway.ready') {
        const resumeId = process.env.MLAUDE_TUI_RESUME || '';
        const method = resumeId ? 'session.resume' : 'session.new';

        client
          .request(method, resumeId ? { session_id: resumeId } : {})
          .then((session: any) => {
            setSessionId(String(session.session_id || ''));
            setTranscript(session.transcript || []);
          })
          .catch((error: Error) => {
            setTranscript([{ kind: 'notice', level: 'error', body: error.message }]);
          });

        client.request('slash.catalog').then(setCatalog).catch(() => undefined);
        return;
      }

      if (event.method === 'status.update') {
        const params = event.params || {};
        setStatus(params);
        if (params.session_id) {
          setSessionId(String(params.session_id));
        }
        if (pendingTurn.current && !params.busy) {
          const iterations = Number(params.iterations || 0);
          if (iterations > 0) {
            setTranscript(current => [
              ...current,
              { kind: 'notice', level: 'metric', body: apiCallLabel(iterations) },
            ]);
          }
          pendingTurn.current = false;
        }
        return;
      }

      if (event.method === 'approval.request') {
        setApproval({ toolName: String(event.params?.tool_name || 'tool') });
        return;
      }

      if (event.method === 'gateway.stderr') {
        const message = String(event.params?.message || '').trim();
        if (!message) {
          return;
        }
        setTranscript(current => [...current, { kind: 'notice', level: 'error', body: message }]);
        pendingTurn.current = false;
        return;
      }

      if (
        event.method === 'message.delta' ||
        event.method === 'message.complete' ||
        event.method === 'reasoning.delta' ||
        event.method === 'reasoning.available' ||
        event.method === 'tool.start' ||
        event.method === 'tool.complete'
      ) {
        setTranscript(current => applyGatewayEvent(current, event));
      }
    });

    return unsubscribe;
  }, [client]);

  const completion = useMemo(() => {
    if (!input.startsWith('/')) {
      return '';
    }

    const prefix = input.slice(1).toLowerCase();
    const match = catalog.commands.find((command: any) => command.name.startsWith(prefix));
    return match ? `/${match.name}` : '';
  }, [catalog.commands, input]);

  async function sendTurn(text: string) {
    const result: any = await client.request('session.send', { text });
    if (!result?.accepted) {
      setTranscript(current => [
        ...current,
        { kind: 'notice', level: 'warn', body: result?.reason || 'request rejected' },
      ]);
      pendingTurn.current = false;
    }
  }

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    if (trimmed.startsWith('/')) {
      const result: any = await client.request('slash.exec', { text: trimmed });

      if (result.kind === 'panel') {
        setTranscript(current => [
          ...current,
          { kind: 'panel', title: String(result.title || ''), body: String(result.body || '') },
        ]);
        return;
      }

      if (result.kind === 'notice') {
        setTranscript(current => [
          ...current,
          { kind: 'notice', level: String(result.level || 'info'), body: String(result.body || '') },
        ]);
        return;
      }

      if (result.kind === 'session') {
        setSessionId(String(result.session_id || sessionId));
        const next = [...(result.transcript || [])];
        if (result.body) {
          next.push({ kind: 'notice', level: 'info', body: String(result.body) });
        }
        setTranscript(next);
        return;
      }

      if (result.kind === 'send') {
        const retryText = String(result.text || '');
        setTranscript(current => [...current, { kind: 'message', role: 'user', content: retryText }]);
        pendingTurn.current = true;
        await sendTurn(retryText);
        return;
      }

      if (result.kind === 'copy') {
        const copied = copyToClipboard(String(result.text || ''));
        setTranscript(current => [
          ...current,
          {
            kind: 'notice',
            level: copied ? 'info' : 'warn',
            body: copied ? 'Copied last response to clipboard.' : 'Clipboard command unavailable.',
          },
        ]);
        return;
      }

      if (result.kind === 'quit') {
        exit();
      }

      return;
    }

    setTranscript(current => [...current, { kind: 'message', role: 'user', content: trimmed }]);
    pendingTurn.current = true;
    await sendTurn(trimmed);
  }

  useInput((value, key) => {
    if (approval) {
      if (value.toLowerCase() === 'y') {
        client.request('approval.respond', { approve: true }).finally(() => setApproval(null));
      } else if (value.toLowerCase() === 'n') {
        client.request('approval.respond', { approve: false }).finally(() => setApproval(null));
      }
      return;
    }

    if (key.ctrl && value === 'c') {
      if (Boolean(status.busy)) {
        client.request('session.interrupt').catch(() => undefined);
        return;
      }
      exit();
      return;
    }

    if (key.return) {
      const pending = input;
      setInput('');
      submit(pending).catch((error: Error) => {
        pendingTurn.current = false;
        setTranscript(current => [...current, { kind: 'notice', level: 'error', body: error.message }]);
      });
      return;
    }

    if (key.tab && completion) {
      setInput(`${completion} `);
      return;
    }

    if (key.backspace || key.delete) {
      setInput(current => current.slice(0, -1));
      return;
    }

    if (key.escape) {
      if (Boolean(status.busy)) {
        client.request('session.interrupt').catch(() => undefined);
      } else {
        setInput('');
      }
      return;
    }

    if (value) {
      setInput(current => current + value);
    }
  });

  const statusLine = formatStatus(status);
  const transcriptWindow = transcript.slice(-80);
  const detailText = String(status.detail || '');
  const providerText = String(status.provider_label || status.provider || 'Provider pending');
  const modelText = String(status.model || process.env.MLAUDE_DEFAULT_CHAT_MODEL || '');

  return (
    <Box flexDirection="column">
      <Text color={STATUS_COLOR(Boolean(status.busy), detailText)}>
        {buildCenteredRule(statusLine, cols)}
      </Text>

      <Text color={THEME.color.statusFg}>{THEME.brand.welcome}</Text>

      {transcript.length === 0 ? (
        <StartupPanel
          cols={cols}
          cwd={process.env.MLAUDE_CWD || process.cwd()}
          model={modelText}
          provider={providerText}
          sessionId={sessionId}
        />
      ) : null}

      <Box flexDirection="column" marginTop={transcript.length === 0 ? 0 : 1}>
        {transcriptWindow.map((entry, index) => renderEntry(entry, index, cols))}
      </Box>

      <Box marginTop={1}>
        <Text bold color={THEME.color.label}>
          {THEME.brand.prompt}{' '}
        </Text>
        <Text color={THEME.color.prompt}>{input || ' '}</Text>
      </Box>

      {completion && input.startsWith('/') ? (
        <Text color={THEME.color.dim}>tab completes: {completion}</Text>
      ) : null}

      {approval ? (
        <Box borderColor={THEME.color.warn} borderStyle="round" flexDirection="column" marginTop={1} paddingX={1}>
          <Text color={THEME.color.warn}>Approval required for {approval.toolName}</Text>
          <Text color={THEME.color.cornsilk}>Press y to approve or n to deny.</Text>
        </Box>
      ) : null}
    </Box>
  );
}
