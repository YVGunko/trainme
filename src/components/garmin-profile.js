'use client';

const SPORT_LABELS = {
  DEFAULT: 'Общие',
  RUNNING: 'Бег',
  CYCLING: 'Велосипед',
  SWIMMING: 'Плавание',
  LAP_SWIMMING: 'Плавание',
  STRENGTH_TRAINING: 'Силовые',
  YOGA: 'Йога',
  FITNESS_EQUIPMENT: 'Тренажёры',
};

export function GarminProfile({ garmin }) {
  const loaded = garmin != null;
  return (
    <details className="garmin-profile">
      <summary>
        <span className="garmin-summary">
          Профиль Garmin
          <span className="muted">{loaded ? 'загружен' : 'ещё не загружен'}</span>
        </span>
      </summary>
      <div className="garmin-body">
        {loaded ? <GarminFacts garmin={garmin} /> : <p>Синхронизация ещё не принесла профиль Garmin.</p>}
      </div>
    </details>
  );
}

function GarminFacts({ garmin }) {
  const facts = [
    birthFact(garmin.birth_date),
    measure(garmin.weight_kg, 'кг', 'Вес'),
    measure(garmin.height_cm, 'см', 'Рост'),
    measure(garmin.cycling_ftp, 'Вт', 'Вело-FTP'),
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
      <ZoneList title="Пульсовые зоны" zones={garmin.hr_zones} />
      <ZoneList title="Зоны мощности" zones={garmin.power_zones} />
      {garmin.recorded_at ? <p className="muted">Снимок {formatWhen(garmin.recorded_at)}</p> : null}
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
  return { label: 'Дата рождения', value };
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
  return bounds ? `${bounds}, до ${plainNumber(zone.ceiling)}` : `до ${plainNumber(zone.ceiling)}`;
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
  const mod10 = age % 10;
  const mod100 = age % 100;
  if (mod10 === 1 && mod100 !== 11) return `${age} год`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${age} года`;
  return `${age} лет`;
}

function shortDate(iso) {
  const [year, month, day] = iso.split('-');
  return `${day}.${month}.${year}`;
}

function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ru', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
