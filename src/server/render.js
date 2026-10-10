export async function callRender(path, body) {
  const base = (process.env.tm_RENDER_URL || '').trim().replace(/\/$/, '');
  const secret = process.env.tm_SERVICE_SECRET || '';
  if (!base.startsWith('https://') || !secret) {
    const error = new Error('render is not configured');
    error.status = 503;
    throw error;
  }
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${secret}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify(body ?? {}),
    cache: 'no-store',
  });
  if (!response.ok) {
    const error = new Error('render failed');
    error.status = response.status;
    throw error;
  }
  return response.json();
}
