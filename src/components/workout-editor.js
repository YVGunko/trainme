'use client';

import { useEffect, useState } from 'react';
import { describeActivity } from '@/lib/activity-record';
import { Drawer } from '@/components/drawer';

export function WorkoutEditor({ activityId, onClose, onSaved }) {
  const [record, setRecord] = useState(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [savedTitle, setSavedTitle] = useState('');
  const [savedDescription, setSavedDescription] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError('');
    setMessage('');
    async function load() {
      try {
        const response = await fetch(`/api/activities/${activityId}`, { signal: controller.signal });
        const data = await response.json();
        if (!active) return;
        if (!response.ok || !data.ok) {
          setError(data.error || 'Could not load this workout.');
          setRecord(null);
          return;
        }
        applyRecord(data.record);
      } catch (loadError) {
        if (!active || loadError?.name === 'AbortError') return;
        setError('Could not load this workout.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [activityId]);

  function applyRecord(next) {
    const nextTitle = next.title || '';
    const nextDescription = next.description || '';
    setRecord(next);
    setTitle(nextTitle);
    setDescription(nextDescription);
    setSavedTitle(nextTitle);
    setSavedDescription(nextDescription);
  }

  function requestClose() {
    const dirty = title !== savedTitle || description !== savedDescription;
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    onClose();
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (saving || loading) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`/api/activities/${activityId}/note`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          title: title.trim() || null,
          description: description.trim() || null,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Could not save.');
        return;
      }
      const nextTitle = title.trim();
      const nextDescription = description.trim();
      setTitle(nextTitle);
      setDescription(nextDescription);
      setSavedTitle(nextTitle);
      setSavedDescription(nextDescription);
      setMessage('Saved.');
      onSaved();
    } catch {
      setError('Could not save.');
    } finally {
      setSaving(false);
    }
  }

  async function parseWorkout() {
    if (parsing || loading) return;
    setParsing(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`/api/activities/${activityId}/normalize`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setError(data.error || 'Could not parse this workout.');
        return;
      }
      const reload = await fetch(`/api/activities/${activityId}`);
      const next = await reload.json();
      if (!reload.ok || !next.ok) {
        setError(next.error || 'Could not load this workout.');
        return;
      }
      const typedTitle = title;
      const typedDescription = description;
      applyRecord(next.record);
      setTitle(typedTitle);
      setDescription(typedDescription);
      setMessage('Parsed.');
      onSaved();
    } catch {
      setError('Could not parse this workout.');
    } finally {
      setParsing(false);
    }
  }

  const view = record ? describeActivity(record) : { facts: [], sets: [] };
  const heading = title.trim() || record?.garminName || 'Workout';

  return (
    <Drawer
      title={heading}
      onClose={requestClose}
      footer={
        <div className="drawer-actions">
          <button className="secondary" type="button" onClick={parseWorkout} disabled={loading || parsing || saving}>
            {parsing ? 'Parsing...' : 'Parse'}
          </button>
          <button type="submit" form="workout-form" disabled={loading || saving || parsing || !record}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      }
    >
      {loading ? <p className="muted">Loading...</p> : null}
      {!loading && error && !record ? <p className="error">{error}</p> : null}
      {record ? (
        <form id="workout-form" className="editor-form" onSubmit={onSubmit}>
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} />
          </label>
          <label>
            Description
            <textarea
              value={description}
              maxLength={4000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <div>
            <h3>Garmin</h3>
            {!record.parsed ? <p>Garmin details appear after Parse.</p> : null}
            {view.facts.length > 0 ? (
              <dl className="metrics">
                {view.facts.map((fact, index) => (
                  <div key={`${fact.label}-${index}`}>
                    <dt>{fact.label}</dt>
                    <dd>{fact.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </div>
          {view.sets.length > 0 ? (
            <div>
              <h3>Sets</h3>
              <ul className="sets">
                {view.sets.map((line, index) => (
                  <li key={`${index}-${line}`}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {message ? <p className="muted">{message}</p> : null}
          {error && record ? <p className="error">{error}</p> : null}
        </form>
      ) : null}
    </Drawer>
  );
}
