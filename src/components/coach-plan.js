'use client';

import { useCallback, useEffect, useState } from 'react';

const WEEKDAYS = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

function weekdayOf(iso) {
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? '' : WEEKDAYS[date.getUTCDay()];
}

function shortDate(iso) {
  const parts = iso.split('-');
  return parts.length === 3 ? `${parts[2]}.${parts[1]}` : iso;
}

export function CoachPlan() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/plan');
      const data = await response.json();
      if (!response.ok || !data.ok) {
        // No plan yet is not an error worth shouting about.
        if (data?.error && !/План не получен/.test(data.error)) setError(data.error);
        setPlan(null);
        return;
      }
      setPlan(data.result || null);
      setError('');
    } catch {
      setError('План не загрузился');
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
        setError(data.error || 'Тренер не смог пересчитать план');
        return;
      }
      setPlan(data.result || null);
      setMessage(regenerate ? 'Тренер построил план заново.' : 'Тренер пересмотрел план.');
    } catch {
      setError('Тренер не смог пересчитать план');
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) return <p className="muted">План загружается...</p>;

  return (
    <section className="data-tools">
      <div>
        <h2>План тренера</h2>
        {plan?.recommendation ? (
          <p className="muted">
            {plan.recommendation.summary} Уверенность {Math.round((plan.recommendation.confidence || 0) * 100)}%.
          </p>
        ) : (
          <p className="muted">
            Плана пока нет. Крон строит его дважды в день, либо постройте сейчас.
          </p>
        )}
      </div>

      <div className="toolbar">
        <button type="button" disabled={refreshing} onClick={() => refresh(false)}>
          {refreshing ? 'Пересчёт...' : 'Пересмотреть план'}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={refreshing}
          onClick={() => refresh(true)}
        >
          Построить заново
        </button>
      </div>

      {plan?.recommendation?.reason ? (
        <details>
          <summary>Почему так</summary>
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
                {day.kind === 'rest' ? <span className="muted">отдых</span> : null}
              </div>
              {day.reason ? <p className="muted">{day.reason}</p> : null}
              {(day.workouts || []).map((workout, index) => (
                <div key={`${day.date}-${index}`} className="plan-workout">
                  <strong>{workout.name}</strong>
                  <span className="muted"> {workout.sport}</span>
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
                </div>
              ))}
            </li>
          ))}
        </ol>
      ) : null}

      {plan?.unmatched_exercises?.length ? (
        <p className="muted">
          Не нашлись в каталоге Garmin и пропущены: {plan.unmatched_exercises.join(', ')}.
        </p>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

function describeStep(step) {
  const end = step.end || {};
  const length =
    end.type === 'time'
      ? `${Math.round((end.seconds || 0) / 60)} мин`
      : end.type === 'distance'
        ? `${Math.round((end.meters || 0) / 100) / 10} км`
        : `${end.count || 0} повт`;
  const exercise = step.exercise ? `${step.exercise} ` : '';
  const weight = step.weight_kg ? ` ${step.weight_kg} кг` : '';
  return `${step.kind || ''} ${exercise}${length}${weight}`.replace(/\s+/g, ' ').trim();
}
