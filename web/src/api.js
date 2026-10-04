/** The local DevAI API. Every call carries the token `devai serve` printed. */

const TOKEN_KEY = 'devai-token';

/**
 * Take the token from the address once, keep it for this tab only, and remove
 * it from the address bar (so it doesn't stay in the history or a screenshot).
 */
export function readToken(
  location = window.location,
  storage = window.sessionStorage,
  history = window.history,
) {
  const params = new URLSearchParams(location.search);
  const fromAddress = params.get('token');
  if (fromAddress) {
    storage.setItem(TOKEN_KEY, fromAddress);
    params.delete('token');
    const rest = params.toString();
    history.replaceState(null, '', location.pathname + (rest ? `?${rest}` : '') + location.hash);
    return fromAddress;
  }
  return storage.getItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** FastAPI's "detail": a message, or a list of validation problems. */
function describe(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ');
  return '';
}

export function createApi(token, fetchImpl = (...args) => fetch(...args)) {
  async function call(method, path, body) {
    const headers = { 'X-DevAI-Token': token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetchImpl(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new ApiError(response.status, describe(data.detail) || `HTTP ${response.status}`);
    }
    return data;
  }

  return {
    projects: () => call('GET', '/api/projects'),
    view: (projectId, view) => call('GET', `/api/projects/${projectId}/${view}`),
    github: (projectId) => call('GET', `/api/projects/${projectId}/github`),
    pull: (projectId, number) => call('GET', `/api/projects/${projectId}/github/pulls/${number}`),
    prepare: (projectId, request) => call('POST', `/api/projects/${projectId}/ai`, request),
    send: (preparedId) => call('POST', `/api/prepared/${encodeURIComponent(preparedId)}/send`),
    apply: (outcomeId) => call('POST', `/api/outcomes/${encodeURIComponent(outcomeId)}/apply`),
  };
}
