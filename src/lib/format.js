export function activityWhen(startAt, offsetMin) {
  if (!startAt) return null;
  const date = startAt instanceof Date ? startAt : new Date(startAt);
  if (Number.isNaN(date.getTime())) return null;
  const offset = Number.isFinite(Number(offsetMin)) ? Number(offsetMin) : 0;
  const shifted = new Date(date.getTime() + offset * 60 * 1000);
  const iso = shifted.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
}

export function sportLabel(sport, subSport) {
  const sub = subSport && subSport !== 'generic' ? subSport : '';
  return [sport, sub].filter(Boolean).join(' / ');
}

export function fallbackTitle(row) {
  const garmin = typeof row.garmin_name === 'string' ? row.garmin_name.trim() : '';
  if (garmin) return garmin;
  return sportLabel(row.sport, row.sub_sport);
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function numberOrNull(value) {
  if (value == null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function formatDuration(seconds) {
  const value = numberOrNull(seconds);
  if (value == null) return '—';
  const total = Math.max(0, Math.round(value));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

export function formatDistance(meters) {
  const value = numberOrNull(meters);
  if (value == null) return '—';
  return `${(value / 1000).toFixed(2)} км`;
}

export function formatActivity(row) {
  const sport = sportLabel(row.sport, row.sub_sport) || '—';
  const fallback = fallbackTitle(row);
  const custom = cleanText(row.title);
  const description = cleanText(row.description);
  const local = cleanText(row.start_local);
  const when = local ? local.slice(0, 16) : activityWhen(row.start_at, row.timezone_offset_min);
  return {
    garminActivityId: String(row.garmin_activity_id),
    when: when || '—',
    whenSort: when || null,
    title: custom || fallback || '—',
    fallbackTitle: fallback || '',
    customTitle: custom,
    description,
    sport,
    duration: formatDuration(row.duration_sec),
    durationSec: numberOrNull(row.duration_sec),
    distance: formatDistance(row.distance_m),
    distanceM: numberOrNull(row.distance_m),
    parsed: Boolean(row.parsed),
  };
}
