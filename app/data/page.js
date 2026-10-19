import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { AppHeader } from '@/components/app-header';
import { DataTools } from '@/components/data-tools';
import { userFromToken } from '@/server/session';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function DataPage() {
  const jar = await cookies();
  const token = jar.get('tm_session')?.value || '';
  let user = null;
  try {
    user = await userFromToken(token);
  } catch {
    console.error('session lookup failed');
  }
  if (!user) redirect('/');

  return (
    <main>
      <AppHeader username={user.username} section="data" />
      <DataTools />
    </main>
  );
}
