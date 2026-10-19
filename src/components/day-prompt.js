'use client';

import { useCallback, useEffect, useState } from 'react';
import { dayNeedsCheckIn, localCalendarDate } from '@/lib/wellness';

export function DayPrompt({ onOpen, refreshKey = 0 }) {
  const [needs, setNeeds] = useState(false);
  const [checked, setChecked] = useState(false);
  const [checkError, setCheckError] = useState('');

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
    refresh(localCalendarDate());
  }, [refresh, refreshKey]);

  return (
    <>
      {checked && needs ? (
        <section className="day-prompt" role="status">
          <p>Today's check-in is not filled in.</p>
          <button type="button" onClick={onOpen}>
            Today
          </button>
        </section>
      ) : null}
      {checkError ? <p className="error">{checkError}</p> : null}
    </>
  );
}
