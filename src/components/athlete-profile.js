'use client';

import { useEffect, useState } from 'react';
import { GarminProfile } from '@/components/garmin-profile';
import { IconButton } from '@/components/icon-button';

const SPORTS = [
  { key: 'running', label: 'Бег' },
  { key: 'cycling', label: 'Велосипед' },
  { key: 'strength_training', label: 'Силовые' },
  { key: 'yoga', label: 'Йога' },
  { key: 'mobility', label: 'Мобилити' },
];

export function AthleteProfile() {
  const [notes, setNotes] = useState('');
  const [avoided, setAvoided] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [garmin, setGarmin] = useState(null);
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
        setGarmin(data.result?.garmin || null);
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

  return (
    <section className="data-tools">
      <form id="athlete-form" className="profile-form" onSubmit={save}>
        <div className="section-head">
          <h3>Профиль атлета</h3>
          <IconButton
            type="submit"
            icon="save"
            label={saving ? 'Сохранение профиля' : 'Сохранить профиль'}
            busy={saving}
            disabled={loading}
          />
        </div>
        <p className="muted">
          Постоянные особенности, которые тренер должен учитывать. Дневная заметка сюда не входит и модели не
          передаётся.
        </p>
        <label>
          Постоянные ограничения и особенности
          <textarea
            className="profile-notes"
            rows={8}
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
      </form>
      <GarminProfile garmin={garmin} />
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
