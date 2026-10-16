'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ActivityBoard } from '@/components/activity-board';
import { DayPrompt } from '@/components/day-prompt';
import { WorkoutEditor } from '@/components/workout-editor';

export function ActivityScreen({ activities }) {
  const router = useRouter();
  const [panel, setPanel] = useState('');
  const editingId = panel && panel !== 'day' ? panel : '';

  function refresh() {
    router.refresh();
  }

  return (
    <>
      <DayPrompt open={panel === 'day'} onOpen={() => setPanel('day')} onClose={() => setPanel('')} />
      <ActivityBoard
        activities={activities}
        editingId={editingId}
        onEdit={setPanel}
        onRefresh={refresh}
      />
      {editingId ? (
        <WorkoutEditor activityId={editingId} onClose={() => setPanel('')} onSaved={refresh} />
      ) : null}
    </>
  );
}
