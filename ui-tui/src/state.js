const assistantRole = role => role ?? 'assistant';

const pushAssistantMessage = (transcript, content, role = 'assistant') => {
  const next = [...transcript];
  const last = next[next.length - 1];

  if (last && last.kind === 'message' && last.role === assistantRole(role)) {
    last.content = content;
    return next;
  }

  next.push({ kind: 'message', role: assistantRole(role), content });
  return next;
};

const findOpenTool = (transcript, name) => {
  for (let index = transcript.length - 1; index >= 0; index -= 1) {
    const entry = transcript[index];

    if (entry?.kind === 'tool' && entry.name === name && entry.status === 'running') {
      return entry;
    }
  }

  return null;
};

export function applyGatewayEvent(transcript, event) {
  const next = [...transcript];

  switch (event.method) {
    case 'message.delta': {
      const delta = String(event.params?.delta ?? '');
      const role = assistantRole(event.params?.role);
      const last = next[next.length - 1];

      if (last && last.kind === 'message' && last.role === role) {
        last.content += delta;
        return next;
      }

      next.push({ kind: 'message', role, content: delta });
      return next;
    }

    case 'message.complete':
      return pushAssistantMessage(
        next,
        String(event.params?.content ?? ''),
        assistantRole(event.params?.role),
      );

    case 'reasoning.delta': {
      const delta = String(event.params?.delta ?? '');
      const last = next[next.length - 1];

      if (last && last.kind === 'reasoning') {
        last.content += delta;
        return next;
      }

      next.push({ kind: 'reasoning', content: delta });
      return next;
    }

    case 'reasoning.available': {
      const content = String(event.params?.content ?? event.params?.text ?? '');
      const last = next[next.length - 1];

      if (last && last.kind === 'reasoning') {
        last.content = content;
        return next;
      }

      next.push({ kind: 'reasoning', content });
      return next;
    }

    case 'tool.start': {
      const name = String(event.params?.name ?? 'tool');
      const args = event.params?.arguments;
      const preview =
        args && typeof args === 'object' ? JSON.stringify(args).slice(0, 120) : String(args ?? '');

      next.push({ kind: 'tool', name, status: 'running', arguments: preview, content: '' });
      return next;
    }

    case 'tool.complete': {
      const name = String(event.params?.name ?? 'tool');
      const content = String(event.params?.result ?? '');
      const existing = findOpenTool(next, name);

      if (existing) {
        existing.status = 'complete';
        existing.content = content;
        return next;
      }

      next.push({
        kind: 'tool',
        name,
        status: 'complete',
        arguments: '',
        content,
      });
      return next;
    }

    case 'status.update':
    default:
      return next;
  }
}
