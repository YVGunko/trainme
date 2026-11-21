'use client';

import { useState } from 'react';
import { IconButton } from '@/components/icon-button';

function isoDay(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function DataTools() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [loadingPeriod, setLoadingPeriod] = useState(false);
  const [probeDate, setProbeDate] = useState('2026-10-14');
  const [probing, setProbing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [context, setContext] = useState(null);
  const [coverage, setCoverage] = useState(null);

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

  async function previewContext() {
    if (previewing) return;
    setPreviewing(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch('/api/context');
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Контекст не собран');
        return;
      }
      setContext(data.result?.context || null);
      setCoverage(data.result?.coverage || null);
    } catch {
      setError('Контекст не собран');
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <section className="data-tools">
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
        <IconButton
          type="submit"
          icon="download"
          label={probing ? 'Запрос отчёта Garmin' : 'Снять отчёт Garmin'}
          busy={probing}
        />
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
        <IconButton
          type="submit"
          icon="download"
          label={loadingPeriod ? 'Загрузка периода' : 'Загрузить'}
          busy={loadingPeriod}
        />
      </form>
      <div className="icon-row">
        <IconButton
          icon="download"
          variant="secondary"
          label={importing ? 'Загрузка истории' : 'Загрузить историю за год'}
          busy={importing}
          onClick={importYear}
        />
        <IconButton
          icon="eye"
          variant="secondary"
          label={previewing ? 'Сбор контекста' : 'Показать контекст тренера'}
          busy={previewing}
          onClick={previewContext}
        />
      </div>
      {coverage ? (
        <p className="muted">
          Сырых тренировок: {coverage.raw_activity_count} (последние {coverage.raw_window_days} дней).
          Недель в сводке: {coverage.week_count}
          {coverage.weeks_first ? `, ${coverage.weeks_first} — ${coverage.weeks_last}` : ''}.
          Детальных дней: {coverage.detail_day_count}. Дней wellness: {coverage.wellness_day_count}.
          Профиль: {coverage.profile_has_notes ? 'заполнен' : 'пуст'}.
        </p>
      ) : null}
      {context ? (
        <details>
          <summary>Контекст, который получит модель</summary>
          <pre className="context-preview">{JSON.stringify(context, null, 2)}</pre>
        </details>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
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
