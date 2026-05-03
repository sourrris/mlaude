import { describe, expect, it } from 'vitest';
import { applyGatewayEvent } from '../src/state.js';
describe('applyGatewayEvent', () => {
    it('appends message deltas into a single assistant entry', () => {
        const start = [];
        const afterOne = applyGatewayEvent(start, {
            method: 'message.delta',
            params: { delta: 'hel', role: 'assistant' },
        });
        const afterTwo = applyGatewayEvent(afterOne, {
            method: 'message.delta',
            params: { delta: 'lo', role: 'assistant' },
        });
        expect(afterTwo).toEqual([{ kind: 'message', role: 'assistant', content: 'hello' }]);
    });
    it('records tool completion as a transcript entry', () => {
        const transcript = applyGatewayEvent([], {
            method: 'tool.complete',
            params: { name: 'terminal', result: 'ok' },
        });
        expect(transcript).toEqual([
            { kind: 'tool', name: 'terminal', status: 'complete', arguments: '', content: 'ok' },
        ]);
    });
    it('merges tool start and completion into one entry', () => {
        const running = applyGatewayEvent([], {
            method: 'tool.start',
            params: { name: 'terminal', arguments: { cmd: 'pwd' } },
        });
        const completed = applyGatewayEvent(running, {
            method: 'tool.complete',
            params: { name: 'terminal', result: '/tmp/project' },
        });
        expect(completed).toEqual([
            {
                kind: 'tool',
                name: 'terminal',
                status: 'complete',
                arguments: '{"cmd":"pwd"}',
                content: '/tmp/project',
            },
        ]);
    });
});
