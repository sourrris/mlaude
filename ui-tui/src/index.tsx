import { render } from 'ink';
import React from 'react';

import { App } from './app.js';

if (!process.stdin.isTTY || !process.stdout.isTTY) {
  console.error('mlaude-tui: no TTY');
  process.exit(1);
}

render(<App />, { exitOnCtrlC: false });
