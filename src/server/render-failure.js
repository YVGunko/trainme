// Turn a Render failure into a status and a sentence the athlete can act on.
//
// The distinction that matters: a 404 means the Python service is running an
// older build that has no such route yet, so waiting fixes it. A 502 means the
// service ran and failed, so waiting fixes nothing and the cause has to be
// shown. Collapsing both into "wait a minute" hides a real bug.
const MESSAGES = {
  400: () => 'Проверьте введённые данные',
  401: () => 'Сервис не принял секрет',
  404: () =>
    'Сервис ещё не обновился после последнего деплоя: такого метода в нём пока нет. Подождите несколько минут и повторите',
  429: () => 'Garmin ограничил запросы. Подождите и повторите',
  503: () => 'Сервис не настроен: нет доступа к базе или к Garmin',
};

export function renderFailure(error, fallback) {
  const status = typeof error?.status === 'number' ? error.status : 0;
  const detail = typeof error?.detail === 'string' ? error.detail.trim() : '';

  if (status === 502 && detail) {
    // Carry the failure name through: it is the only clue without server logs.
    return { status: 502, error: `Сервис ответил ошибкой: ${detail}` };
  }
  const sentence = MESSAGES[status];
  if (sentence) {
    return { status: status === 404 ? 502 : status, error: sentence() };
  }
  if (status === 0) {
    return { status: 502, error: 'Сервис не ответил. Проверьте, что он запущен' };
  }
  return { status: 502, error: fallback };
}
