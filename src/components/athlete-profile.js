'use client';

import { useEffect, useState } from 'react';

const SPORTS = [
  { key: 'running', label: 'Бег' },
  { key: 'cycling', label: 'Велосипед' },
  { key: 'strength_training', label: 'Силовые' },
  { key: 'yoga', label: 'Йога' },
  { key: 'mobility', label: 'Мобилити' },
];

function isoDay(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function AthleteProfile() {
  const [notes, setNotes] = useState('');
  const [avoided, setAvoided] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await fetch('/api/profile');
        const data = await response.json();
        if (!active) return;
        if (!response.ok || !data.ok) {
          setError(data.error || 'Профиль не загружен');
          return;
        }
        setNotes(data.result?.notes || '');
        setAvoided(Array.isArray(data.result?.avoided_sports) ? data.result.avoided_sports : []);
      } catch {
        if (active) setError('Профиль не загружен');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  function toggleSport(key) {
    setAvoided((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  }

  async function save(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ notes: notes.trim() || null, avoided_sports: avoided }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Профиль не сохранён');
        return;
      }
      setMessage('Профиль сохранён.');
    } catch {
      setError('Профиль не сохранён');
    } finally {
      setSaving(false);
    }
  }

  async function importYear() {
    if (importing) return;
    setImporting(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/history', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ start: isoDay(-365), end: isoDay(0) }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'История не загружена');
        return;
      }
      const result = data.result || {};
      setMessage(
        `История за ${result.start} — ${result.end}: сохранено ${result.stored_count ?? 0} тренировок из ${result.activity_count ?? 0}. Всего в базе ${result.history_total ?? 0}.`,
      );
    } catch {
      setError('История не загружена');
    } finally {
      setImporting(false);
    }
  }

  return (
    <section className="data-tools">
      <div>
        <h3>Профиль атлета</h3>
        <p className="muted">
          Постоянные особенности, которые тренер должен учитывать. Дневная заметка сюда не входит и модели не
          передаётся.
        </p>
      </div>
      <form onSubmit={save}>
        <label>
          Постоянные ограничения и особенности
          <textarea
            value={notes}
            maxLength={4000}
            disabled={loading || saving}
            placeholder="Например: периодически тянет заднюю поверхность левого бедра, нужна эксцентрика. Резкие спринты переношу плохо."
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        <fieldset className="score" disabled={loading || saving}>
          <legend>Исключить виды спорта</legend>
          <div className="choices">
            {SPORTS.map((sport) => (
              <button
                key={sport.key}
                type="button"
                aria-pressed={avoided.includes(sport.key)}
                onClick={() => toggleSport(sport.key)}
              >
                {sport.label}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="toolbar">
          <button type="submit" disabled={loading || saving}>
            {saving ? 'Сохранение...' : 'Сохранить профиль'}
          </button>
          <button type="button" className="secondary" disabled={importing} onClick={importYear}>
            {importing ? 'Загрузка...' : 'Загрузить историю за год'}
          </button>
        </div>
      </form>
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
