// Turn a Render failure into a status and a sentence the athlete can act on.
//
// The distinction that matters: a 404 means the Python service is running an
// older build that has no such route yet, so waiting fixes it. A 502 means the
// service ran and failed, so waiting fixes nothing and the cause has to be
// shown. Collapsing both into "wait a minute" hides a real bug.
const MESSAGES = {
  400: () => 'Check the values you entered',
  401: () => 'The service rejected the secret',
  404: () =>
    'The service has not updated after the last deploy: that method is not there yet. Wait a few minutes and try again',
  429: () => 'Garmin limited the requests. Wait and try again',
  503: () => 'The service is not configured: no access to the database or to Garmin',
};

export function renderFailure(error, fallback) {
  const status = typeof error?.status === 'number' ? error.status : 0;
  const detail = typeof error?.detail === 'string' ? error.detail.trim() : '';

  if (status === 502 && detail) {
    // Carry the failure name through: it is the only clue without server logs.
    return { status: 502, error: `The service answered with an error: ${detail}` };
  }
  const sentence = MESSAGES[status];
  if (sentence) {
    return { status: status === 404 ? 502 : status, error: sentence() };
  }
  if (status === 0) {
    return { status: 502, error: 'The service did not answer. Check that it is running' };
  }
  return { status: 502, error: fallback };
}
