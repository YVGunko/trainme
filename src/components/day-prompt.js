'use client';

import { useCallback, useEffect, useState } from 'react';
import { DayCard } from '@/components/day-card';
import { Drawer } from '@/components/drawer';
import { dayNeedsCheckIn, localCalendarDate } from '@/lib/wellness';

export function DayPrompt({ open, onOpen, onClose }) {
  const [today, setToday] = useState('');
  const [needs, setNeeds] = useState(false);
  const [checked, setChecked] = useState(false);
  const [checkError, setCheckError] = useState('');
  const [dirty, setDirty] = useState(false);

  const refresh = useCallback(async (day) => {
    try {
      const response = await fetch(`/api/days/${day}`);
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setCheckError(data.error || 'Could not check today.');
        return;
      }
      setCheckError('');
      setNeeds(dayNeedsCheckIn(data.wellness));
      setChecked(true);
    } catch {
      setCheckError('Could not check today.');
    }
  }, []);

  useEffect(() => {
    const day = localCalendarDate();
    setToday(day);
    refresh(day);
  }, [refresh]);

  function requestClose() {
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    setDirty(false);
    onClose();
  }

  return (
    <>
      {checked && needs ? (
        <section className="day-prompt" role="status">
          <p>Today's check-in is not filled in.</p>
          <button type="button" onClick={onOpen}>
            Fill in today
          </button>
        </section>
      ) : null}
      {checked && !needs ? (
        <p className="day-link">
          <button className="secondary" type="button" onClick={onOpen}>
            Today
          </button>
        </p>
      ) : null}
      {checkError ? <p className="error">{checkError}</p> : null}
      {open ? (
        <Drawer title="Day" onClose={requestClose}>
          <DayCard
            onDirtyChange={setDirty}
            onSaved={(date, wellness) => {
              if (date === today) setNeeds(dayNeedsCheckIn(wellness));
            }}
          />
        </Drawer>
      ) : null}
    </>
  );
}
