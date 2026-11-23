'use client';

import { useState } from 'react';
import { FIT_REASONS, hasNumericWarning, warningTexts } from '@/lib/fit-reasons';
import { IconButton } from '@/components/icon-button';

const MAX_FILE_BYTES = 256 * 1024;

export function WorkoutUpload() {
  const [file, setFile] = useState(null);
  const [date, setDate] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [push, setPush] = useState(false);
  const [devices, setDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [sending, setSending] = useState(false);
  const [probeId, setProbeId] = useState('');
  const [probing, setProbing] = useState(false);
  const [warnings, setWarnings] = useState([]);
  const [warningIsNumeric, setWarningIsNumeric] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function loadDevices() {
    if (loadingDevices || devices.length > 0) return;
    setLoadingDevices(true);
    setError('');
    try {
      const response = await fetch('/api/workouts/devices', { method: 'POST' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'The device list was not received');
        return;
      }
      setDevices(Array.isArray(data.result?.devices) ? data.result.devices : []);
    } catch {
      setError('The device list was not received');
    } finally {
      setLoadingDevices(false);
    }
  }

  async function probe(event) {
    event.preventDefault();
    setProbing(true);
    setError('');
    setMessage('');
    try {
      const body = {};
      const id = Number(probeId);
      if (Number.isInteger(id) && id > 0) body.download_workout_id = id;
      const response = await fetch('/api/probe/workout-device', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'The device check failed');
        return;
      }
      saveReport('workout-device', data.result);
      const chosen = Object.entries(data.result?.sport_device || {})
        .map(([sport, entry]) => `${sport} → ${entry.payload?.device_id ?? entry.error}`)
        .join(', ');
      setMessage(`The report was saved to the browser downloads. ${chosen}`);
    } catch {
      setError('The device check failed');
    } finally {
      setProbing(false);
    }
  }

  async function send(event) {
    event.preventDefault();
    setError('');
    setMessage('');
    setWarnings([]);
    setWarningIsNumeric(false);
    if (!file) {
      setError('Choose a FIT file');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError('The file is larger than 256 KB');
      return;
    }
    setSending(true);
    try {
      const content = await readBase64(file);
      const body = { content_base64: content, push };
      if (date) body.date = date;
      if (deviceId) body.device_id = Number(deviceId);
      const response = await fetch('/api/workouts/fit', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(FIT_REASONS[data?.reason] || data.error || 'Upload failed');
        return;
      }
      const result = data.result || {};
      const parts = [
        result.stored ? `Workout ${result.workout_id} created` : `Workout ${result.workout_id} was already uploaded`,
        result.date ? `scheduled for ${result.date}` : '',
        result.pushed ? `sent to device ${result.device_id}` : '',
      ];
      setMessage(parts.filter(Boolean).join(', '));
      // The file's own problems are shown apart from the result, because the
      // workout is already in Garmin and the numbers may need a second look.
      setWarnings(warningTexts(result.warnings));
      setWarningIsNumeric(hasNumericWarning(result.warnings));
    } catch {
      setError('Upload failed');
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="data-tools">
      <div>
        <h3>Workout from a FIT file</h3>
        <p className="muted">The file is checked before it is sent to Garmin.</p>
      </div>
      <form className="toolbar" onSubmit={send}>
        <label>
          FIT file
          <input
            type="file"
            accept=".fit,application/octet-stream"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Date
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label>
          Device
          <select
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
            onFocus={loadDevices}
          >
            <option value="">{loadingDevices ? 'Loading...' : 'By workout type'}</option>
            {devices.map((device) => (
              <option key={device.device_id} value={device.device_id}>
                {device.name || device.device_id}
                {device.primary ? ' (primary)' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={push} onChange={(event) => setPush(event.target.checked)} />
          Send to the device
        </label>
        <IconButton
          type="submit"
          icon="upload"
          label={sending ? 'Sending FIT' : 'Upload FIT'}
          busy={sending}
        />
      </form>
      <div>
        <h3>Garmin devices</h3>
        <p className="muted">
          An empty id reads the devices and the choice by sport. A workout id also parses the FIT from Garmin.
        </p>
      </div>
      <form className="toolbar" onSubmit={probe}>
        <label>
          Workout id
          <input
            value={probeId}
            onChange={(event) => setProbeId(event.target.value)}
            placeholder="Empty — read only"
          />
        </label>
        <IconButton
          type="submit"
          icon="search"
          label={probing ? 'Checking devices' : 'Check devices'}
          busy={probing}
        />
      </form>
      {message ? <p className="muted">{message}</p> : null}
      {warnings.length > 0 ? (
        <div className={warningIsNumeric ? 'error' : 'muted'}>
          {warnings.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

function saveReport(name, report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `probe-${name}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('read failed'));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const comma = result.indexOf(',');
      resolve(comma === -1 ? '' : result.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}
