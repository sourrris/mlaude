import { spawn } from 'node:child_process';
import path from 'node:path';
import { createInterface } from 'node:readline';

const DEFAULT_TIMEOUT_MS = 120_000;

export class GatewayClient {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
    this.eventHandlers = new Set();

    const python = process.env.MLAUDE_PYTHON || 'python3';
    const pythonPath = [process.env.MLAUDE_PYTHON_SRC_ROOT, process.env.PYTHONPATH]
      .filter(Boolean)
      .join(path.delimiter);
    const env = { ...process.env, PYTHONPATH: pythonPath };

    this.child = spawn(python, ['-m', 'mlaude.tui_gateway.entry'], {
      cwd: process.env.MLAUDE_CWD || process.cwd(),
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const rl = createInterface({ input: this.child.stdout });
    rl.on('line', line => this.handleLine(line));

    this.child.stderr.on('data', chunk => {
      this.emit({
        jsonrpc: '2.0',
        method: 'gateway.stderr',
        params: { message: chunk.toString('utf8').trim() },
      });
    });

    this.child.on('exit', code => {
      for (const [, pending] of this.pending) {
        clearTimeout(pending.timeout);
        pending.reject(new Error(`gateway exited (${code ?? 'unknown'})`));
      }
      this.pending.clear();
      this.emit({
        jsonrpc: '2.0',
        method: 'gateway.stderr',
        params: { message: `gateway exited (${code ?? 'unknown'})` },
      });
    });
  }

  onEvent(handler) {
    this.eventHandlers.add(handler);
    return () => {
      this.eventHandlers.delete(handler);
    };
  }

  emit(event) {
    for (const handler of this.eventHandlers) {
      handler(event);
    }
  }

  handleLine(line) {
    let message;

    try {
      message = JSON.parse(line);
    } catch (error) {
      this.emit({
        jsonrpc: '2.0',
        method: 'gateway.stderr',
        params: { message: `invalid gateway json: ${String(error)}` },
      });
      return;
    }

    if ('id' in message) {
      const pending = this.pending.get(message.id);

      if (!pending) {
        return;
      }

      this.pending.delete(message.id);
      clearTimeout(pending.timeout);

      if (message.error) {
        pending.reject(new Error(message.error.message));
        return;
      }

      pending.resolve(message.result);
      return;
    }

    this.emit(message);
  }

  request(method, params = {}) {
    const id = this.nextId++;
    const payload = { jsonrpc: '2.0', id, method, params };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timeout: ${method}`));
      }, DEFAULT_TIMEOUT_MS);

      this.pending.set(id, { resolve, reject, timeout });
      this.child.stdin.write(JSON.stringify(payload) + '\n');
    });
  }

  close() {
    this.child.kill();
  }
}
