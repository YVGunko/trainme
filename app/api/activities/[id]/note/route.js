import { requireUser } from '@/server/session';
import { saveActivityNote } from '@/server/meta';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function cleanText(value, maxLength) {
  if (value == null) return null;
  if (typeof value !== 'string') {
    const error = new Error('invalid');
    error.status = 400;
    throw error;
  }
  const text = value.trim();
  if (!text) return null;
  if (text.length > maxLength) {
    const error = new Error('too long');
    error.status = 400;
    throw error;
  }
  return text;
}

export async function POST(request, { params }) {
  try {
    await requireUser(request);
    const { id } = await params;
    if (!/^\d+$/.test(id)) {
      return Response.json({ ok: false, error: 'Тренировка не найдена' }, { status: 404 });
    }
    const body = await request.json();
    const title = cleanText(body?.title, 200);
    const description = cleanText(body?.description, 4000);
    await saveActivityNote(id, title, description);
    return Response.json({ ok: true });
  } catch (error) {
    const status = error?.status === 401 ? 401 : error?.status === 400 ? 400 : 500;
    const message =
      status === 401 ? 'Нужно войти' : status === 400 ? 'Текст слишком длинный' : 'Не удалось сохранить';
    if (status === 500) console.error('note save failed');
    return Response.json({ ok: false, error: message }, { status });
  }
}
