'use client';

const SPORT_LABELS = {
  DEFAULT: 'General',
  RUNNING: 'Running',
  CYCLING: 'Cycling',
  SWIMMING: 'Swimming',
  LAP_SWIMMING: 'Swimming',
  STRENGTH_TRAINING: 'Strength',
  YOGA: 'Yoga',
  FITNESS_EQUIPMENT: 'Gym equipment',
};

export function GarminProfile({ garmin }) {
  const loaded = garmin != null;
  return (
    <details className="garmin-profile">
      <summary>
        <span className="garmin-summary">
          Garmin profile
          <span className="muted">{loaded ? 'loaded' : 'not loaded yet'}</span>
        </span>
      </summary>
      <div className="garmin-body">
        {loaded ? <GarminFacts garmin={garmin} /> : <p>Sync has not brought a Garmin profile yet.</p>}
      </div>
    </details>
  );
}

function GarminFacts({ garmin }) {
  const facts = [
    birthFact(garmin.birth_date),
    measure(garmin.weight_kg, 'kg', 'Weight'),
    measure(garmin.height_cm, 'cm', 'Height'),
    measure(garmin.cycling_ftp, 'W', 'Cycling FTP'),
  ].filter(Boolean);
  return (
    <>
      {facts.length > 0 ? (
        <dl className="garmin-facts">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <ZoneList title="Heart-rate zones" zones={garmin.hr_zones} />
      <ZoneList title="Power zones" zones={garmin.power_zones} />
      {garmin.recorded_at ? <p className="muted">Snapshot {formatWhen(garmin.recorded_at)}</p> : null}
    </>
  );
}

function ZoneList({ title, zones }) {
  if (!Array.isArray(zones) || zones.length === 0) return null;
  return (
    <div>
      <h4>{title}</h4>
      <ul className="garmin-zones">
        {zones.map((zone) => (
          <li key={zone.sport}>
            <span>{SPORT_LABELS[zone.sport] || zone.sport}</span>
            <span>{formatZone(zone)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function birthFact(iso) {
  if (!iso) return null;
  const age = ageYears(iso);
  const value = age == null ? shortDate(iso) : `${shortDate(iso)}, ${yearsLabel(age)}`;
  return { label: 'Date of birth', value };
}

function measure(value, unit, label) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const rounded = Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return { label, value: `${text} ${unit}` };
}

function formatZone(zone) {
  const floors = Array.isArray(zone.floors) ? zone.floors.map(plainNumber).filter(Boolean) : [];
  const bounds = floors.join('–');
  if (zone.ceiling == null) return bounds;
  return bounds ? `${bounds}, up to ${plainNumber(zone.ceiling)}` : `up to ${plainNumber(zone.ceiling)}`;
}

function plainNumber(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '';
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function ageYears(iso, now = new Date()) {
  const [year, month, day] = iso.split('-').map(Number);
  if (!year || !month || !day) return null;
  let age = now.getFullYear() - year;
  const beforeBirthday = now.getMonth() + 1 < month || (now.getMonth() + 1 === month && now.getDate() < day);
  if (beforeBirthday) age -= 1;
  return age >= 0 ? age : null;
}

function yearsLabel(age) {
  return age === 1 ? '1 year' : `${age} years`;
}

function shortDate(iso) {
  const [year, month, day] = iso.split('-');
  return `${day}/${month}/${year}`;
}

function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
