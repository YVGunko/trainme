'use client';

import { useRouter } from 'next/navigation';
import { ActivityBoard } from '@/components/activity-board';

export function ActivityScreen({ activities }) {
  const router = useRouter();
  return <ActivityBoard activities={activities} onRefresh={() => router.refresh()} />;
}
