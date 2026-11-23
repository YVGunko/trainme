'use client';

import { useEffect, useState } from 'react';
import { EnglishCheck } from '@/components/english-check';
import { GarminProfile } from '@/components/garmin-profile';
import { IconButton } from '@/components/icon-button';

const SPORTS = [
  { key: 'running', label: 'Running' },
  { key: 'cycling', label: 'Cycling' },
  { key: 'strength_training', label: 'Strength' },
  { key: 'yoga', label: 'Yoga' },
  { key: 'mobility', label: 'Mobility' },
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
          setError(data.error || 'The profile did not load');
          return;
        }
        setNotes(data.result?.notes || '');
        setAvoided(Array.isArray(data.result?.avoided_sports) ? data.result.avoided_sports : []);
        setGarmin(data.result?.garmin || null);
      } catch {
        if (active) setError('The profile did not load');
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
        setError(data.error || 'The profile was not saved');
        return;
      }
      setMessage('Profile saved.');
    } catch {
      setError('The profile was not saved');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="data-tools">
      <form id="athlete-form" className="profile-form" onSubmit={save}>
        <div className="section-head">
          <h3>Athlete profile</h3>
          <IconButton
            type="submit"
            icon="save"
            label={saving ? 'Saving profile' : 'Save profile'}
            busy={saving}
            disabled={loading}
          />
        </div>
        <p className="muted">
          Standing points the coach should follow. The daily note stays on the day and is not sent as this profile.
        </p>
        <EnglishCheck
          text={notes}
          placement="inline"
          label="Standing limits and notes"
          fieldId="profile-notes"
          onApply={setNotes}
        >
          <textarea
            id="profile-notes"
            className="profile-notes"
            rows={8}
            value={notes}
            maxLength={4000}
            disabled={loading || saving}
            placeholder="For example: the back of the left thigh tightens from time to time and needs eccentric work. I tolerate sharp sprints poorly."
            onChange={(event) => setNotes(event.target.value)}
          />
        </EnglishCheck>
        <fieldset className="score" disabled={loading || saving}>
          <legend>Exclude sports</legend>
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
