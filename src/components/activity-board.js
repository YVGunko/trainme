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

export function ActivityBoard({ activities, editingId, onEdit }) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [sorting, setSorting] = useState([{ id: 'when', desc: true }]);

  const visible = useMemo(
    () => sortActivities(filterActivities(activities, query), sorting),
    [activities, query, sorting]
  );
  const view = useMemo(() => pageOf(visible, page), [visible, page]);

  return (
    <section>
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
      <p className="muted sort-note" aria-live="polite">
        Сортировка: {sortLabel(sorting)}. Обычный щелчок выбирает одну колонку, Shift добавляет следующую.
      </p>
      {activities.length === 0 ? <p>Пока нет загруженных тренировок.</p> : null}
      {activities.length > 0 && visible.length === 0 ? <p>Ничего не найдено.</p> : null}
      {visible.length > 0 ? (
        <>
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
          <ul className="activity-cards">
            {view.rows.map((row) => (
              <li key={row.garminActivityId}>
                <button
                  className={editingId === row.garminActivityId ? 'activity-card is-selected' : 'activity-card'}
                  type="button"
                  onClick={() => onEdit(row.garminActivityId)}
                >
                  <span className="activity-when">{row.when}</span>
                  <span className="activity-title">{row.title}</span>
                  <span className="activity-meta">
                    {row.sport} · {row.duration}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
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
