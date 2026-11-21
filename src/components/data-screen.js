'use client';

import { useState } from 'react';
import { AthleteProfile } from '@/components/athlete-profile';
import { DataTools } from '@/components/data-tools';
import { WorkoutUpload } from '@/components/workout-upload';

const TABS = [
  { id: 'profile', label: 'Profile' },
  { id: 'fit', label: 'FIT' },
  { id: 'archive', label: 'Archive' },
];

export function DataScreen() {
  const [section, setSection] = useState('profile');

  return (
    <div className={`data-screen is-${section}`}>
      <section className="data-pane profile-pane" aria-label="Profile">
        <AthleteProfile />
      </section>
      <section className="data-pane fit-pane" aria-label="FIT">
        <WorkoutUpload />
      </section>
      <section className="data-pane archive-pane" aria-label="Archive">
        <DataTools />
      </section>
      <nav className="tabbar data-tabbar" aria-label="Data">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            aria-current={section === tab.id ? 'page' : undefined}
            onClick={() => setSection(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
