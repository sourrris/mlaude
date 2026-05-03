export interface Theme {
  color: {
    gold: string;
    amber: string;
    bronze: string;
    cornsilk: string;
    dim: string;
    label: string;
    ok: string;
    error: string;
    warn: string;
    prompt: string;
    statusBg: string;
    statusFg: string;
  };
  brand: {
    name: string;
    icon: string;
    prompt: string;
    welcome: string;
    subtitle: string;
    tool: string;
    assistant: string;
  };
}

export const THEME: Theme = {
  color: {
    gold: '#FFD700',
    amber: '#FFBF00',
    bronze: '#CD7F32',
    cornsilk: '#FFF8DC',
    dim: '#CC9B1F',
    label: '#DAA520',
    ok: '#4caf50',
    error: '#ef5350',
    warn: '#ffa726',
    prompt: '#FFF8DC',
    statusBg: '#1a1a2e',
    statusFg: '#C0C0C0',
  },
  brand: {
    name: 'mlaude',
    icon: '☠',
    prompt: '❯',
    welcome: 'Welcome to mlaude! Type your message or /help for commands.',
    subtitle: 'Powerful AI coding assistant',
    tool: '┊',
    assistant: 'mlaude',
  },
};
