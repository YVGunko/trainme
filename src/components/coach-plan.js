'use client';

import { useCallback, useEffect, useState } from 'react';
import { IconButton } from '@/components/icon-button';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function weekdayOf(iso) {
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? '' : WEEKDAYS[date.getUTCDay()];
}

function shortDate(iso) {
  const parts = iso.split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}` : iso;
}

export function CoachPlan() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sending, setSending] = useState({});
  const [sentDays, setSentDays] = useState({});
  const [sendErrors, setSendErrors] = useState({});
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/plan');
      const data = await response.json();
      if (!response.ok || !data.ok) {
        // No plan yet is not an error worth shouting about.
        if (data?.error && !/plan was not received/i.test(data.error)) setError(data.error);
        setPlan(null);
        return;
      }
      setPlan(data.result || null);
      setError('');
    } catch {
      setError('The plan did not load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function refresh(regenerate) {
    if (refreshing) return;
    setRefreshing(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/plan/refresh', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(regenerate ? { regenerate: true } : {}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'The coach could not revise the plan');
        return;
      }
      setPlan(data.result || null);
      setMessage(regenerate ? 'The coach built the plan again.' : 'The coach revised the plan.');
    } catch {
      setError('The coach could not revise the plan');
    } finally {
      setRefreshing(false);
    }
  }

  async function sendToGarmin(key, day, workout) {
    if (sending[key]) return;
    setSending((current) => ({ ...current, [key]: true }));
    setSendErrors((current) => ({ ...current, [key]: '' }));
    try {
      const response = await fetch('/api/workouts', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ workout, date: day.date }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setSendErrors((current) => ({ ...current, [key]: data.error || 'Not sent' }));
        return;
      }
      const result = data.result || {};
      setSentDays((current) => ({ ...current, [key]: `workout ${result.workout_id}` }));
    } catch {
      setSendErrors((current) => ({ ...current, [key]: 'Not sent' }));
    } finally {
      setSending((current) => ({ ...current, [key]: false }));
    }
  }

  if (loading) return <p className="muted">The plan is loading...</p>;

  return (
    <section className="data-tools">
      <div>
        <h2>Coach's plan</h2>
        {plan?.recommendation ? (
          <p className="muted">
            {plan.recommendation.summary} Confidence {Math.round((plan.recommendation.confidence || 0) * 100)}%.
          </p>
        ) : (
          <p className="muted">
            No plan yet. The schedule builds one twice a day, or build one now.
          </p>
        )}
      </div>

      <div className="icon-row">
        <IconButton
          icon="refresh"
          label={refreshing ? 'Revising plan' : 'Revise plan'}
          busy={refreshing}
          onClick={() => refresh(false)}
        />
        <IconButton
          icon="rebuild"
          variant="secondary"
          label="Build again"
          disabled={refreshing}
          onClick={() => refresh(true)}
        />
      </div>

      {plan?.recommendation?.reason ? (
        <details>
          <summary>Why</summary>
          <p className="muted">{plan.recommendation.reason}</p>
        </details>
      ) : null}

      {plan?.days?.length ? (
        <ol className="plan-days">
          {plan.days.map((day) => (
            <li key={day.date} className={day.kind === 'rest' ? 'plan-day is-rest' : 'plan-day'}>
              <div className="plan-day-head">
                <strong>
                  {weekdayOf(day.date)} {shortDate(day.date)}
                </strong>
                {day.kind === 'rest' ? <span className="muted">rest</span> : null}
              </div>
              {day.reason ? <p className="muted">{day.reason}</p> : null}
              {(day.workouts || []).map((workout, index) => {
                const key = `${day.date}-${index}`;
                const sent = sentDays[key];
                return (
                  <div key={key} className="plan-workout">
                    <div className="plan-workout-head">
                      <div>
                        <strong>{workout.name}</strong>
                        <span className="muted"> {workout.sport}</span>
                      </div>
                      {sent ? (
                        <span className="muted">sent ({sent})</span>
                      ) : (
                        <IconButton
                          icon="send"
                          variant="secondary"
                          label={sending[key] ? 'Sending to Garmin' : 'To Garmin'}
                          busy={Boolean(sending[key])}
                          onClick={() => sendToGarmin(key, day, workout)}
                        />
                      )}
                    </div>
                    {workout.description ? <p className="muted">{workout.description}</p> : null}
                    <ul className="sets">
                      {(workout.blocks || []).map((block, blockIndex) => (
                        <li key={blockIndex}>
                          {block.repeat ? <span className="muted">{block.repeat}× </span> : null}
                          {(block.steps || [])
                            .map((step) => describeStep(step))
                            .join(' · ')}
                        </li>
                      ))}
                    </ul>
                    {sendErrors[key] ? <p className="error">{sendErrors[key]}</p> : null}
                  </div>
                );
              })}
            </li>
          ))}
        </ol>
      ) : null}

      {plan?.unmatched_exercises?.length ? (
        <p className="muted">
          Missing from the Garmin catalogue and skipped: {plan.unmatched_exercises.join(', ')}.
        </p>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

function describeStep(step) {
  const end = step.end || {};
  const exercise = step.exercise ? ` ${step.exercise}` : '';
  const weight = step.weight_kg ? ` ${step.weight_kg} kg` : '';
  const kind = step.kind || '';
  return `${kind}${exercise}${weight} ${describeEnd(end)}`.replace(/\s+/g, ' ').trim();
}

function describeEnd(end) {
  if (end.type === 'time') {
    const seconds = Number(end.seconds) || 0;
    // A 30 second hold must not read as "0 min".
    const length = seconds < 60 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
    return length;
  }
  if (end.type === 'distance') {
    const metres = Number(end.meters) || 0;
    return metres < 1000 ? `${Math.round(metres)} m` : `${Math.round(metres / 100) / 10} km`;
  }
  if (end.type === 'reps') {
    return `${end.count || 0} reps`;
  }
  return end.type || '';
}
