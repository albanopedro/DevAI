import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import AiTask from './AiTask.jsx';

const PREVIEW = {
  prepared_id: 'p1',
  task: 'docs',
  question: 'Send stats.py (~120 tokens) to OpenCode (free model) to document 2 names?',
  destination: 'OpenCode (free model)',
  leaves_machine: true,
  data_note: null,
  context: { file: { path: 'stats.py' } },
  characters: 480,
  tokens: 120,
  redacted_lines: 0,
};

const ANSWER = {
  task: 'docs',
  result: {
    docs: { file: 'stats.py' },
    ai: {
      model: 'fake-model',
      usage: { input_tokens: 5, output_tokens: 6 },
      proposal: { docs: [], notes: ['A note.'] },
      rejected: null,
      added: ['average'],
      dropped: [],
      diff: '--- a/stats.py\n+++ b/stats.py\n@@ -1 +1,2 @@\n def average(values):\n+    """Return the mean."""\n',
    },
  },
  apply: { outcome_id: 'o1', kind: 'write', files: ['stats.py'], blocked: null },
};

function fakeApi(overrides = {}) {
  return {
    prepare: vi.fn(async () => PREVIEW),
    send: vi.fn(async () => ANSWER),
    apply: vi.fn(async () => ({ applied: true, files: ['stats.py'], undo: 'git restore stats.py' })),
    ...overrides,
  };
}

function show(api, props = {}) {
  render(
    <AiTask api={api} projectId={0} request={{ task: 'docs', file: 'stats.py' }} label="Write docs with AI…" {...props} />,
  );
}

describe('AiTask', () => {
  test('nothing is sent before Send, nothing written before the confirmation', async () => {
    const api = fakeApi();
    const onApplied = vi.fn();
    show(api, { provider: 'ollama', onApplied });

    fireEvent.click(screen.getByText('Write docs with AI…'));
    await screen.findByText('Before anything is sent');
    expect(api.prepare).toHaveBeenCalledWith(0, { task: 'docs', file: 'stats.py', provider: 'ollama' });
    expect(screen.getByText(/Leaves this computer/)).toBeTruthy();
    expect(api.send).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('Send'));
    await screen.findByText('AI answer');
    expect(api.send).toHaveBeenCalledWith('p1');
    expect(screen.getByText(/Only documentation changed: checked/)).toBeTruthy();
    expect(api.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('Apply to stats.py…'));
    expect(screen.getByText(/Write these changes to stats.py\?/)).toBeTruthy();
    expect(api.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('Yes, write it'));
    await screen.findByText(/Nothing was committed/);
    expect(api.apply).toHaveBeenCalledWith('o1');
    expect(onApplied).toHaveBeenCalledWith({ applied: true, files: ['stats.py'], undo: 'git restore stats.py' });
  });

  test('Cancel sends nothing', async () => {
    const api = fakeApi();
    show(api);

    fireEvent.click(screen.getByText('Write docs with AI…'));
    fireEvent.click(await screen.findByText('Cancel'));

    expect(screen.queryByText('Before anything is sent')).toBeNull();
    expect(api.send).not.toHaveBeenCalled();
  });

  test('a blocked apply is disabled, with the reason', async () => {
    const blocked = { ...ANSWER, apply: { ...ANSWER.apply, blocked: 'stats.py has uncommitted changes' } };
    show(fakeApi({ send: vi.fn(async () => blocked) }));

    fireEvent.click(screen.getByText('Write docs with AI…'));
    fireEvent.click(await screen.findByText('Send'));

    expect((await screen.findByText('Apply')).disabled).toBe(true);
    expect(screen.getByText(/Can't apply now: stats.py has uncommitted changes/)).toBeTruthy();
  });

  test('errors are shown, and a failed send starts over', async () => {
    const api = fakeApi({ send: vi.fn(async () => Promise.reject(new Error('the free model is busy'))) });
    show(api);

    fireEvent.click(screen.getByText('Write docs with AI…'));
    fireEvent.click(await screen.findByText('Send'));

    expect(await screen.findByText('the free model is busy')).toBeTruthy();
    expect(screen.getByText('Write docs with AI…')).toBeTruthy();
  });

  test('a rejected answer says so and offers nothing to apply', async () => {
    const rejected = {
      task: 'docs',
      result: { ...ANSWER.result, ai: { ...ANSWER.result.ai, rejected: 'the docs contain */', diff: null } },
    };
    show(fakeApi({ send: vi.fn(async () => rejected) }));

    fireEvent.click(screen.getByText('Write docs with AI…'));
    fireEvent.click(await screen.findByText('Send'));

    expect(await screen.findByText(/Rejected by DevAI: the docs contain \*\//)).toBeTruthy();
    expect(screen.queryByText(/Apply to/)).toBeNull();
  });
});
