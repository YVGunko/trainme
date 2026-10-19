'use client';

import { useState } from 'react';

export function DataTools() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [loadingPeriod, setLoadingPeriod] = useState(false);
  const [probeDate, setProbeDate] = useState('2026-10-14');
  const [probing, setProbing] = useState(false);

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
