'use client';

import { useEffect, useRef, useState } from 'react';
import {
  emptyWellnessForm,
  formFromWellness,
  garminLines,
  localCalendarDate,
  SCORE_FIELDS,
  SCORE_LABELS,
  SCORE_WORDS,
  splitGarminLines,
} from '@/lib/wellness';

export function DayCard({ onSaved }) {
  const [date, setDate] = useState('');
  const [loadedDate, setLoadedDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [garmin, setGarmin] = useState(undefined);
  const [form, setForm] = useState(emptyWellnessForm);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [showAll, setShowAll] = useState(false);
  const dateRef = useRef('');

  useEffect(() => {
    setDate(localCalendarDate());
  }, []);

  useEffect(() => {
    dateRef.current = date;
    if (!date) return undefined;
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError('');
    setMessage('');
    setLoadedDate('');
    setGarmin(undefined);
    setForm(emptyWellnessForm());

    async function load() {
      try {
        const response = await fetch(`/api/days/${date}`, { signal: controller.signal });
        const data = await response.json();
        if (!active) return;
        if (!response.ok || !data.ok) {
          setError(data.error || 'Could not load this day.');
          return;
        }
        const nextForm = formFromWellness(data.wellness);
      setGarmin(data.garmin);
      setForm(nextForm);
      setLoadedDate(date);
      } catch (loadError) {
        if (!active || loadError?.name === 'AbortError') return;
        setError('Could not load this day.');
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [date]);

  function setScore(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    const savedDate = date;
    if (!savedDate || loadedDate !== savedDate || saving) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`/api/days/${savedDate}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await response.json();
      if (dateRef.current !== savedDate) return;
      if (!response.ok || !data.ok) {
        setError(data.error || 'Could not save.');
        return;
      }
      const nextForm = formFromWellness(data.wellness);
      setGarmin(data.garmin);
      setForm(nextForm);
      setMessage(data.wellness ? 'Saved.' : 'Cleared.');
      onSaved?.(savedDate, data.wellness);
    } catch {
      if (dateRef.current !== savedDate) return;
      setError('Could not save.');
    } finally {
      setSaving(false);
    }
  }

  const ready = Boolean(date) && loadedDate === date && !loading;
  const lines = garminLines(garmin);
  const { summary, rest } = splitGarminLines(lines);
  const restOpen = showAll || summary.length === 0;

  return (
    <form className="editor-form" onSubmit={onSubmit}>
      <div className="day-scroll">
        <label>
          Date
          <input
            type="date"
            value={date}
            onChange={(event) => {
              setShowAll(false);
              setDate(event.target.value);
            }}
            required
          />
        </label>
        <div>
          <h3>Garmin</h3>
          {!date ? <p className="muted">Choose a date.</p> : null}
          {date && loading ? <p className="muted">Loading...</p> : null}
          {date && !loading && !error && garmin === null ? <p>This day is not loaded.</p> : null}
          {date && !loading && !error && garmin && lines.length === 0 ? (
            <p>No Garmin metrics for this day.</p>
          ) : null}
          {date && !loading && !error && lines.length > 0 ? (
            <>
              <MetricList lines={lines} className="metrics metrics-all" />
              {summary.length > 0 ? <MetricList lines={summary} className="metrics metrics-summary" /> : null}
              {rest.length > 0 ? (
                <>
                  {summary.length > 0 ? (
                    <button
                      className="secondary metrics-toggle"
                      type="button"
                      aria-expanded={showAll}
                      onClick={() => setShowAll((current) => !current)}
                    >
                      {showAll ? 'Hide metrics' : 'All metrics'}
                    </button>
                  ) : null}
                  <MetricList lines={rest} className={restOpen ? 'metrics metrics-rest is-open' : 'metrics metrics-rest'} />
                </>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="wellness">
          <h3>Wellness</h3>
          {SCORE_FIELDS.map((field) => (
            <fieldset key={field} className="score" disabled={!ready || saving}>
              <legend>{SCORE_LABELS[field]}</legend>
              <div className="choices">
                {SCORE_WORDS[field].map((word, index) => {
                  const value = index + 1;
                  const selected = form[field] === value;
                  return (
                    <button
                      key={word}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setScore(field, selected ? null : value)}
                    >
                      {word}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <label>
            Note
            <textarea
              value={form.note}
              maxLength={4000}
              disabled={!ready || saving}
              onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
            />
          </label>
        </div>
      </div>
      <div className="day-actions">
        <button type="submit" disabled={!ready || saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        {message ? <p className="muted">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
      </div>
    </form>
  );
}

function MetricList({ lines, className }) {
  return (
    <dl className={className}>
      {lines.map((line) => (
        <div key={line.key}>
          <dt>{line.label}</dt>
          <dd>{line.value}</dd>
        </div>
      ))}
    </dl>
  );
}
