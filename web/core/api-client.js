export class ApiRequestError extends Error {
  constructor(
    message,
    { status = 0, code = 'request_failed', category = 'unexpected', retryable = false, payload = null } = {},
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.category = category;
    this.retryable = retryable;
    this.payload = payload;
  }
}

export function apiErrorMessage(payload, fallback = 'The request could not be completed.') {
  if (typeof payload?.error?.message === 'string' && payload.error.message) return payload.error.message;
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc.filter((value) => value !== 'body').join(' → ') : '';
        return `${field ? `${field}: ` : ''}${item?.msg || 'Invalid value'}`;
      })
      .join(' · ');
  }
  if (detail && typeof detail === 'object') return detail.message || fallback;
  return fallback;
}

export async function apiResponseJson(response, fallback = 'The request could not be completed.') {
  const payload = await response.json().catch(() => ({}));
  if (response.ok) return payload;
  throw new ApiRequestError(apiErrorMessage(payload, fallback), {
    status: Number(response.status || 0),
    code: payload?.error?.code,
    category: payload?.error?.category,
    retryable: Boolean(payload?.error?.retryable),
    payload,
  });
}

export async function apiRequest(url, options = {}, { fetchImpl = fetch, fallback } = {}) {
  return apiResponseJson(await fetchImpl(url, options), fallback);
}

export function createApiClient({ fetchImpl = (...args) => fetch(...args) } = {}) {
  const raw = (url, options = {}) => fetchImpl(url, options);
  const request = async (url, options = {}, fallback) => apiResponseJson(await raw(url, options), fallback);
  const json = (method, url, body, options = {}, fallback) =>
    request(
      url,
      {
        ...options,
        method,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      },
      fallback,
    );
  return Object.freeze({
    raw,
    request,
    errorMessage: apiErrorMessage,
    get: (url, options, fallback) => request(url, options, fallback),
    post: (url, body, options, fallback) => json('POST', url, body, options, fallback),
    put: (url, body, options, fallback) => json('PUT', url, body, options, fallback),
    patch: (url, body, options, fallback) => json('PATCH', url, body, options, fallback),
    delete: (url, options, fallback) => request(url, { ...options, method: 'DELETE' }, fallback),
  });
}
