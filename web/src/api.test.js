import { describe, expect, test, vi } from 'vitest';
import { ApiError, createApi, readToken } from './api.js';

function memoryStorage() {
  const items = new Map();
  return { getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value) };
}

describe('readToken', () => {
  test('takes the token from the address, keeps it, and removes it from the address', () => {
    const storage = memoryStorage();
    const history = { replaceState: vi.fn() };
    const location = { search: '?token=abc&tab=docs', pathname: '/', hash: '#x' };

    expect(readToken(location, storage, history)).toBe('abc');
    expect(storage.getItem('devai-token')).toBe('abc');
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/?tab=docs#x');
  });

  test('after a reload, the token comes from this tab', () => {
    const storage = memoryStorage();
    storage.setItem('devai-token', 'kept');
    const history = { replaceState: vi.fn() };

    expect(readToken({ search: '', pathname: '/', hash: '' }, storage, history)).toBe('kept');
    expect(history.replaceState).not.toHaveBeenCalled();
  });

  test('no token anywhere', () => {
    expect(readToken({ search: '', pathname: '/', hash: '' }, memoryStorage(), {})).toBeNull();
  });
});

describe('createApi', () => {
  function respond(status, body) {
    return vi.fn(async () => ({ ok: status < 400, status, json: async () => body }));
  }

  test('every call carries the token', async () => {
    const fetch = respond(200, [{ id: 0 }]);

    await createApi('secret', fetch).projects();

    expect(fetch).toHaveBeenCalledWith('/api/projects', {
      method: 'GET',
      headers: { 'X-DevAI-Token': 'secret' },
      body: undefined,
    });
  });

  test('a prepare sends JSON; apply sends only the id', async () => {
    const fetch = respond(200, {});
    const api = createApi('secret', fetch);

    await api.prepare(1, { task: 'docs', file: 'a.py' });
    await api.apply('id/with?odd');

    expect(fetch.mock.calls[0][0]).toBe('/api/projects/1/ai');
    expect(fetch.mock.calls[0][1].body).toBe('{"task":"docs","file":"a.py"}');
    expect(fetch.mock.calls[1][0]).toBe('/api/outcomes/id%2Fwith%3Fodd/apply');
    expect(fetch.mock.calls[1][1].body).toBeUndefined();
  });

  test('errors carry the API message', async () => {
    const api = createApi('secret', respond(409, { detail: 'stats.py changed' }));

    await expect(api.projects()).rejects.toEqual(new ApiError(409, 'stats.py changed'));
  });

  test('validation errors are joined', async () => {
    const detail = [{ msg: 'field required' }, { msg: 'not a string' }];
    const api = createApi('secret', respond(422, { detail }));

    await expect(api.projects()).rejects.toThrow('field required; not a string');
  });
});
