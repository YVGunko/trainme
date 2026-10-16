'use client';

import { useMemo, useState } from 'react';
import { filterActivities, pageNumbers, pageOf, sortActivities, sortLabel, toggleSort } from '@/lib/table';

const COLUMNS = [
  { id: 'when', label: 'Дата' },
  { id: 'title', label: 'Название' },
  { id: 'description', label: 'Описание' },
  { id: 'sport', label: 'Тип' },
  { id: 'duration', label: 'Длительность' },
  { id: 'distance', label: 'Дистанция' },
  { id: 'parsed', label: 'Разбор' },
];

export function ActivityBoard({ activities, editingId, onEdit, onRefresh }) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [sorting, setSorting] = useState([{ id: 'when', desc: true }]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [loadingPeriod, setLoadingPeriod] = useState(false);
  const [probeDate, setProbeDate] = useState('2026-10-14');
  const [probing, setProbing] = useState(false);

  const visible = useMemo(
    () => sortActivities(filterActivities(activities, query), sorting),
    [activities, query, sorting]
  );
  const view = useMemo(() => pageOf(visible, page), [visible, page]);

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
      const queued = Array.isArray(data.queue?.queued) ? data.queue.queued.length : 0;
      const failed = Array.isArray(data.queue?.failed) ? data.queue.failed.length : 0;
      const parseNote = [
        queued ? `Разбор поставлен в очередь: ${queued}.` : '',
        failed ? `Не удалось поставить в очередь: ${failed}.` : '',
      ]
        .filter(Boolean)
        .join(' ');
      setMessage(
        `За период ${result.start} — ${result.end}: новых файлов ${result.downloaded_activity_count ?? 0} из ${result.activity_count ?? 0}. Дней скачано ${result.downloaded_day_count ?? 0}. ${parseNote}`.trim()
      );
      onRefresh();
    } catch {
      setError('Загрузка не удалась');
    } finally {
      setLoadingPeriod(false);
    }
  }

  async function probeGarmin(event) {
    event.preventDefault();
    setProbing(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/probe/unused-garmin', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ date: probeDate }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Проверка Garmin не удалась');
        return;
      }
      saveReport(probeDate, data.result);
      setMessage(`Файл probe-unused-${probeDate}.json сохранён в загрузки браузера.`);
    } catch {
      setError('Проверка Garmin не удалась');
    } finally {
      setProbing(false);
    }
  }

  return (
    <section>
      <form className="toolbar" onSubmit={probeGarmin}>
        <label>
          День отчёта
          <input
            type="date"
            value={probeDate}
            onChange={(event) => setProbeDate(event.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={probing}>
          {probing ? 'Запрос...' : 'Снять отчёт Garmin'}
        </button>
      </form>
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
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
          type="search"
        />
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
                        onClick={(event) => {
                          setSorting((current) => toggleSort(current, column.id, event.shiftKey));
                          setPage(1);
                        }}
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
              {view.rows.map((row) => (
                <tr
                  key={row.garminActivityId}
                  className={editingId === row.garminActivityId ? 'is-selected' : undefined}
                >
                  <td>{row.when}</td>
                  <td>{row.title}</td>
                  <td>{row.description || '—'}</td>
                  <td>{row.sport}</td>
                  <td>{row.duration}</td>
                  <td>{row.distance}</td>
                  <td>{row.parsed ? 'да' : 'нет'}</td>
                  <td>
                    <button className="secondary" type="button" onClick={() => onEdit(row.garminActivityId)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {view.pageCount > 1 ? (
        <nav className="pager" aria-label="Pages">
          <p className="muted">
            {view.from}–{view.to} of {view.total}
          </p>
          <div className="pager-controls">
            <button
              className="secondary"
              type="button"
              disabled={view.page === 1}
              onClick={() => setPage(view.page - 1)}
            >
              Previous
            </button>
            {pageNumbers(view.page, view.pageCount).map((item, index) =>
              item === '…' ? (
                <span key={`gap-${index}`} className="pager-gap">
                  …
                </span>
              ) : (
                <button
                  key={item}
                  type="button"
                  className={item === view.page ? undefined : 'secondary'}
                  aria-current={item === view.page ? 'page' : undefined}
                  onClick={() => setPage(item)}
                >
                  {item}
                </button>
              )
            )}
            <button
              className="secondary"
              type="button"
              disabled={view.page === view.pageCount}
              onClick={() => setPage(view.page + 1)}
            >
              Next
            </button>
          </div>
        </nav>
      ) : null}
    </section>
  );
}

function saveReport(day, report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `probe-unused-${day}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
