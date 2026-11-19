import { callRender } from '@/server/render';

// Re-read the last few days of activity summaries, so the coach sees sessions
// that finished after the previous run. The import is keyed on the Garmin
// activity id, so repeating a window updates rows instead of duplicating them.
const WINDOW_DAYS = 10;

function isoDay(date) {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export async function refreshHistory(day, days = WINDOW_DAYS) {
  const end = new Date(`${day}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() - days);
  return callRender('/history', { start: isoDay(end), end: day });
}
