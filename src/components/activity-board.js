'use client';

import { useMemo, useState } from 'react';
import { filterActivities, sortActivities, sortLabel, toggleSort } from '@/lib/table';

const COLUMNS = [
  { id: 'when', label: 'Дата' },
  { id: 'title', label: 'Название' },
  { id: 'description', label: 'Описание' },
  { id: 'sport', label: 'Тип' },
  { id: 'duration', label: 'Длительность' },
  { id: 'distance', label: 'Дистанция' },
  { id: 'parsed', label: 'Разбор' },
];

export function ActivityBoard({ activities, onRefresh }) {
  const [query, setQuery] = useState('');
  const [sorting, setSorting] = useState([{ id: 'when', desc: true }]);
  const [drafts, setDrafts] = useState({});
  const [pendingId, setPendingId] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [loadingPeriod, setLoadingPeriod] = useState(false);

  const visible = useMemo(
    () => sortActivities(filterActivities(activities, query), sorting),
    [activities, query, sorting]
  );

  function draftValue(row, field, fallback) {
    const draft = drafts[row.garminActivityId];
    if (draft && Object.prototype.hasOwnProperty.call(draft, field)) return draft[field];
    return fallback;
  }

  function setDraft(id, field, value) {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], [field]: value },
    }));
  }

  async function saveField(row, field, value) {
    const shownTitle = row.title === '—' ? '' : row.title;
    const titleText = (field === 'title' ? value : draftValue(row, 'title', shownTitle)).trim();
    const descriptionText = (
      field === 'description' ? value : draftValue(row, 'description', row.description)
    ).trim();
    const title = !titleText || titleText === '—' || titleText === row.fallbackTitle ? null : titleText;
    const description = descriptionText || null;
    const storedTitle = row.customTitle || null;
    const storedDescription = row.description || null;
    if (title === storedTitle && description === storedDescription) return;

    setError('');
    try {
      const response = await fetch(`/api/activities/${row.garminActivityId}/note`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ title, description }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Не удалось сохранить');
        return;
      }
      setDrafts((current) => {
        const next = { ...current };
        delete next[row.garminActivityId];
        return next;
      });
      onRefresh();
    } catch {
      setError('Не удалось сохранить');
    }
  }

  async function parseActivity(row) {
    setPendingId(row.garminActivityId);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`/api/activities/${row.garminActivityId}/normalize`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Разбор не удался');
        return;
      }
      setMessage('Разбор записан');
      onRefresh();
    } catch {
      setError('Разбор не удался');
    } finally {
      setPendingId('');
    }
  }

  async function loadPeriod(event) {
    event.preventDefault();
    setLoadingPeriod(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/archive/period', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ start, end }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Загрузка не удалась');
        return;
      }
      const result = data.result || {};
      setMessage(
        `За период ${result.start} — ${result.end}: новых файлов ${result.downloaded_activity_count ?? 0} из ${result.activity_count ?? 0}. Дней скачано ${result.downloaded_day_count ?? 0}.`
      );
      onRefresh();
    } catch {
      setError('Загрузка не удалась');
    } finally {
      setLoadingPeriod(false);
    }
  }

  return (
    <section>
      <form className="toolbar" onSubmit={loadPeriod}>
        <label>
          С
          <input type="date" value={start} onChange={(event) => setStart(event.target.value)} required />
        </label>
        <label>
          По
          <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} required />
        </label>
        <button type="submit" disabled={loadingPeriod}>
          {loadingPeriod ? 'Загрузка...' : 'Загрузить'}
        </button>
      </form>
      <label className="search">
        Поиск по названию и описанию
        <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" />
      </label>
      <p className="muted" aria-live="polite">
        Сортировка: {sortLabel(sorting)}. Обычный щелчок выбирает одну колонку, Shift добавляет следующую.
      </p>
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {activities.length === 0 ? <p>Пока нет загруженных тренировок.</p> : null}
      {activities.length > 0 && visible.length === 0 ? <p>Ничего не найдено.</p> : null}
      {visible.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {COLUMNS.map((column) => {
                  const index = sorting.findIndex((item) => item.id === column.id);
                  const active = sorting[index];
                  return (
                    <th
                      key={column.id}
                      aria-sort={index === 0 ? (active.desc ? 'descending' : 'ascending') : undefined}
                    >
                      <button
                        className="sort-button"
                        type="button"
                        onClick={(event) =>
                          setSorting((current) => toggleSort(current, column.id, event.shiftKey))
                        }
                      >
                        {column.label}
                        {active ? ` ${active.desc ? '↓' : '↑'}${sorting.length > 1 ? index + 1 : ''}` : ''}
                      </button>
                    </th>
                  );
                })}
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.garminActivityId}>
                  <td>{row.when}</td>
                  <td>
                    <input
                      aria-label={`Название ${row.garminActivityId}`}
                      placeholder={row.fallbackTitle || '—'}
                      value={draftValue(row, 'title', row.title === '—' ? '' : row.title)}
                      onChange={(event) => setDraft(row.garminActivityId, 'title', event.target.value)}
                      onBlur={(event) => saveField(row, 'title', event.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`Описание ${row.garminActivityId}`}
                      value={draftValue(row, 'description', row.description)}
                      onChange={(event) =>
                        setDraft(row.garminActivityId, 'description', event.target.value)
                      }
                      onBlur={(event) => saveField(row, 'description', event.target.value)}
                    />
                  </td>
                  <td>{row.sport}</td>
                  <td>{row.duration}</td>
                  <td>{row.distance}</td>
                  <td>{row.parsed ? 'да' : 'нет'}</td>
                  <td>
                    <button
                      className="secondary"
                      type="button"
                      disabled={pendingId === row.garminActivityId}
                      onClick={() => parseActivity(row)}
                    >
                      {pendingId === row.garminActivityId ? 'Разбор...' : 'Разобрать'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
