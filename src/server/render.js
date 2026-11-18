function renderBase() {
  const base = (process.env.tm_RENDER_URL || '').trim().replace(/\/$/, '');
  const secret = process.env.tm_SERVICE_SECRET || '';
  if (!base.startsWith('https://') || !secret) {
    const error = new Error('render is not configured');
    error.status = 503;
    throw error;
  }
  return { base, secret };
}

async function readResponse(response) {
  if (response.ok) return response.json();
  const error = new Error('render failed');
  error.status = response.status;
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === 'string') {
      error.detail = detail;
    } else if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
      // A structured detail carries a reason code the caller can explain.
      error.detail = detail.message;
      if (typeof detail.reason === 'string') error.reason = detail.reason;
    }
  } catch {
    // The status already describes the failure.
  }
  throw error;
}

export async function callRender(path, body) {
  const { base, secret } = renderBase();
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${secret}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify(body ?? {}),
    cache: 'no-store',
  });
  return readResponse(response);
}

export async function getRender(path) {
  const { base, secret } = renderBase();
  const response = await fetch(`${base}${path}`, {
    method: 'GET',
    headers: { authorization: `Bearer ${secret}` },
    cache: 'no-store',
  });
  return readResponse(response);
}
