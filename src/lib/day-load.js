// One archive request for the open day, then one read of that day.
// The card does not poll. The archive writes daily_metrics before it responds.
export function dayLoadVisible(garmin) {
  return garmin === null;
}

export async function requestDayLoad(date, fetchImpl = globalThis.fetch) {
  const archiveResponse = await fetchImpl('/api/archive/period', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ start: date, end: date }),
  });
  const archive = await archiveResponse.json();
  if (!archiveResponse.ok || !archive.ok) {
    return { ok: false, error: archive.error || 'Could not load this day.' };
  }

  const dayResponse = await fetchImpl(`/api/days/${date}`);
  const day = await dayResponse.json();
  if (!dayResponse.ok || !day.ok) {
    return { ok: false, error: day.error || 'Could not load this day.' };
  }
  return { ok: true, garmin: day.garmin, wellness: day.wellness };
}
