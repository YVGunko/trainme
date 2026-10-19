'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ActivityBoard } from '@/components/activity-board';
import { DayCard } from '@/components/day-card';
import { DayPrompt } from '@/components/day-prompt';
import { WorkoutEditor } from '@/components/workout-editor';

// Phone layout is CSS width <= 640px (iPhone 16 portrait is 393). Landscape is wider and uses the desktop arrangement.
// Phone sections are Today and Activities. Archive import and the Garmin report live on /data, not here.
export function ActivityScreen({ activities }) {
  const router = useRouter();
  const [section, setSection] = useState('today');
  const [editingId, setEditingId] = useState('');
  const [checkInVersion, setCheckInVersion] = useState(0);

  function refresh() {
    router.refresh();
  }

  return (
    <div className={section === 'today' ? 'shell is-today' : 'shell is-activities'}>
      <section className="day-card today-pane">
        <DayCard onSaved={() => setCheckInVersion((version) => version + 1)} />
      </section>
      <section className="activities-pane" aria-label="Activities">
        <div className="phone-only">
          <DayPrompt refreshKey={checkInVersion} onOpen={() => setSection('today')} />
        </div>
        <ActivityBoard activities={activities} editingId={editingId} onEdit={setEditingId} />
      </section>
      <nav className="tabbar" aria-label="Sections">
        <button type="button" aria-current={section === 'today' ? 'page' : undefined} onClick={() => setSection('today')}>
          Today
        </button>
        <button
          type="button"
          aria-current={section === 'activities' ? 'page' : undefined}
          onClick={() => setSection('activities')}
        >
          Activities
        </button>
      </nav>
      {editingId ? (
        <WorkoutEditor activityId={editingId} onClose={() => setEditingId('')} onSaved={refresh} />
      ) : null}
    </div>
  );
}
