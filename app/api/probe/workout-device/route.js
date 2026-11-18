import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const payload = {};
    const pushId = optionalId(body?.push_workout_id);
    const downloadId = optionalId(body?.download_workout_id);
    if (pushId === false || downloadId === false) {
      return Response.json({ ok: false, error: 'Номер тренировки должен быть положительным' }, { status: 400 });
    }
    if (pushId) payload.push_workout_id = pushId;
    if (downloadId) payload.download_workout_id = downloadId;
    const result = await callRender('/probe/workout-device', payload);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 400 || status === 503 ? status : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: renderMessage(status) }, { status: httpStatus });
  }
}

function optionalId(value) {
  if (value === undefined || value === null || value === '') return null;
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) return false;
  return number;
}

function renderMessage(status) {
  if (status === 400) return 'Номер тренировки должен быть положительным';
  if (status === 401) return 'Сервис проверки не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Сервис проверки не настроен';
  return 'Проверка устройств Garmin не удалась. Подождите минуту и повторите';
}
