'use client';

import { useState } from 'react';
import { FIT_REASONS } from '@/lib/fit-reasons';

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
        setError(data.error || 'Список устройств не получен');
        return;
      }
      setDevices(Array.isArray(data.result?.devices) ? data.result.devices : []);
    } catch {
      setError('Список устройств не получен');
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
        setError(data.error || 'Проверка устройств не удалась');
        return;
      }
      saveReport('workout-device', data.result);
      const chosen = Object.entries(data.result?.sport_device || {})
        .map(([sport, entry]) => `${sport} → ${entry.payload?.device_id ?? entry.error}`)
        .join(', ');
      setMessage(`Отчёт сохранён в загрузки браузера. ${chosen}`);
    } catch {
      setError('Проверка устройств не удалась');
    } finally {
      setProbing(false);
    }
  }

  async function send(event) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (!file) {
      setError('Выберите файл FIT');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError('Файл больше 256 КБ');
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
        setError(FIT_REASONS[data?.reason] || data.error || 'Загрузка не удалась');
        return;
      }
      const result = data.result || {};
      const parts = [
        result.stored ? `Шаблон ${result.workout_id} создан` : `Шаблон ${result.workout_id} уже был загружен`,
        result.date ? `поставлен на ${result.date}` : '',
        result.pushed ? `отправлен на устройство ${result.device_id}` : '',
        Array.isArray(result.warnings) ? result.warnings.join('; ') : '',
      ];
      setMessage(parts.filter(Boolean).join(', '));
    } catch {
      setError('Загрузка не удалась');
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="data-tools">
      <div>
        <h3>Тренировка из файла FIT</h3>
        <p className="muted">Файл проходит проверку перед отправкой в Garmin.</p>
      </div>
      <form className="toolbar" onSubmit={send}>
        <label>
          Файл FIT
          <input
            type="file"
            accept=".fit,application/octet-stream"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Дата
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label>
          Устройство
          <select
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
            onFocus={loadDevices}
          >
            <option value="">{loadingDevices ? 'Загрузка...' : 'По виду тренировки'}</option>
            {devices.map((device) => (
              <option key={device.device_id} value={device.device_id}>
                {device.name || device.device_id}
                {device.primary ? ' (основное)' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={push} onChange={(event) => setPush(event.target.checked)} />
          Отправить на устройство
        </label>
        <button type="submit" disabled={sending}>
          {sending ? 'Отправка...' : 'Загрузить FIT'}
        </button>
      </form>
      <div>
        <h3>Устройства Garmin</h3>
        <p className="muted">
          Пустой номер читает устройства и выбор по виду спорта. Номер тренировки ещё и разбирает FIT от Garmin.
        </p>
      </div>
      <form className="toolbar" onSubmit={probe}>
        <label>
          Номер тренировки
          <input
            value={probeId}
            onChange={(event) => setProbeId(event.target.value)}
            placeholder="Пусто — только чтение"
          />
        </label>
        <button type="submit" disabled={probing}>
          {probing ? 'Запрос...' : 'Проверить устройства'}
        </button>
      </form>
      {message ? <p className="muted">{message}</p> : null}
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
