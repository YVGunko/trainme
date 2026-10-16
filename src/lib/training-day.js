// The athlete's calendar is UTC+3. Vercel cron runs in UTC.
export const TRAINING_UTC_OFFSET_MINUTES = 3 * 60;

export function trainingCalendarDate(now = new Date(), offsetMinutes = TRAINING_UTC_OFFSET_MINUTES) {
  const shifted = new Date(now.getTime() + offsetMinutes * 60 * 1000);
  const year = shifted.getUTCFullYear();
  const month = String(shifted.getUTCMonth() + 1).padStart(2, '0');
  const day = String(shifted.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
