import { clearSessionCookie } from '@/lib/auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request) {
  return new Response(null, {
    status: 303,
    headers: {
      Location: new URL('/', request.url).toString(),
      'Set-Cookie': clearSessionCookie(),
    },
  });
}
