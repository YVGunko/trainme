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
        setError(data.error || 'Download failed');
        return;
      }
      const result = data.result || {};
      const queued = Array.isArray(data.queue?.queued) ? data.queue.queued.length : 0;
      const failed = Array.isArray(data.queue?.failed) ? data.queue.failed.length : 0;
      const parseNote = [
        queued ? `Parsing queued: ${queued}.` : '',
        failed ? `Could not queue: ${failed}.` : '',
      ]
        .filter(Boolean)
        .join(' ');
      setMessage(
        `For ${result.start} – ${result.end}: ${result.downloaded_activity_count ?? 0} new files of ${result.activity_count ?? 0}. Days downloaded: ${result.downloaded_day_count ?? 0}. ${parseNote}`.trim()
      );
    } catch {
      setError('Download failed');
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
        setError(data.error || 'The Garmin check failed');
        return;
      }
      saveReport(probeDate, data.result);
      setMessage(`probe-unused-${probeDate}.json was saved to the browser downloads.`);
    } catch {
      setError('The Garmin check failed');
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
        setError(data.error || 'History was not loaded');
        return;
      }
      const result = data.result || {};
      setMessage(
        `History for ${result.start} – ${result.end}: stored ${result.stored_count ?? 0} activities of ${result.activity_count ?? 0}. ${result.history_total ?? 0} in the database.`,
      );
    } catch {
      setError('History was not loaded');
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
        setError(data.error || 'The context was not built');
        return;
      }
      setContext(data.result?.context || null);
      setCoverage(data.result?.coverage || null);
    } catch {
      setError('The context was not built');
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <section className="data-tools">
      <form className="toolbar" onSubmit={probeGarmin}>
        <label>
          Report day
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
          label={probing ? 'Requesting Garmin report' : 'Download Garmin report'}
          busy={probing}
        />
      </form>
      <form className="toolbar" onSubmit={loadPeriod}>
        <label>
          From
          <input type="date" value={start} onChange={(event) => setStart(event.target.value)} required />
        </label>
        <label>
          To
          <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} required />
        </label>
        <IconButton
          type="submit"
          icon="download"
          label={loadingPeriod ? 'Loading period' : 'Download'}
          busy={loadingPeriod}
        />
      </form>
      <div className="icon-row">
        <IconButton
          icon="download"
          variant="secondary"
          label={importing ? 'Loading history' : 'Load a year of history'}
          busy={importing}
          onClick={importYear}
        />
        <IconButton
          icon="eye"
          variant="secondary"
          label={previewing ? 'Building context' : 'Show the coach context'}
          busy={previewing}
          onClick={previewContext}
        />
      </div>
      {coverage ? (
        <p className="muted">
          Raw activities: {coverage.raw_activity_count} (last {coverage.raw_window_days} days).
          Weeks in the summary: {coverage.week_count}
          {coverage.weeks_first ? `, ${coverage.weeks_first} – ${coverage.weeks_last}` : ''}.
          Detailed days: {coverage.detail_day_count}. Wellness days: {coverage.wellness_day_count}.
          Profile: {coverage.profile_has_notes ? 'filled in' : 'empty'}.
        </p>
      ) : null}
      {context ? (
        <details>
          <summary>Context the model will receive</summary>
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
