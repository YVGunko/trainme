export function activityWhen(startAt, offsetMin) {
  if (!startAt) return null;
  const date = startAt instanceof Date ? startAt : new Date(startAt);
  if (Number.isNaN(date.getTime())) return null;
  const offset = Number.isFinite(Number(offsetMin)) ? Number(offsetMin) : 0;
  const shifted = new Date(date.getTime() + offset * 60 * 1000);
  const iso = shifted.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
}

export function formatDuration(seconds) {
  if (seconds == null || seconds === '') return '—';
  const value = Number(seconds);
  if (!Number.isFinite(value)) return '—';
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
  if (meters == null || meters === '') return '—';
  const value = Number(meters);
  if (!Number.isFinite(value)) return '—';
  return `${(value / 1000).toFixed(2)} км`;
}

export function formatActivity(row) {
  const subSport = row.sub_sport && row.sub_sport !== 'generic' ? row.sub_sport : '';
  const sport = [row.sport, subSport].filter(Boolean).join(' / ') || '—';
  return {
    garminActivityId: String(row.garmin_activity_id),
    when: activityWhen(row.start_at, row.timezone_offset_min) || '—',
    sport,
    duration: formatDuration(row.duration_sec),
    distance: formatDistance(row.distance_m),
    parsed: Boolean(row.parsed),
  };
}
