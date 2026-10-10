import { cookies } from 'next/headers';
import { LoginForm } from '@/components/login-form';
import { userFromToken } from '@/server/session';
import { listActivities } from '@/server/activities';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function HomePage() {
  const jar = await cookies();
  const token = jar.get('tm_session')?.value || '';
  let user = null;
  let sessionError = '';
  try {
    user = await userFromToken(token);
  } catch {
    console.error('session lookup failed');
    sessionError = 'Не удалось проверить вход';
  }

  if (!user) {
    return (
      <main>
        <h1>Тренировки</h1>
        <LoginForm notice={sessionError} />
      </main>
    );
  }

  let activities = [];
  let listError = '';
  try {
    activities = await listActivities();
  } catch {
    console.error('activity list failed');
    listError = 'Список не загрузился';
  }

  return (
    <main>
      <header className="top">
        <div>
          <h1>Тренировки</h1>
          <p className="muted">{user.username}</p>
        </div>
        <form action="/api/auth/logout" method="post">
          <button className="secondary" type="submit">
            Выйти
          </button>
        </form>
      </header>
      {listError ? <p className="error">{listError}</p> : null}
      {activities.length === 0 && !listError ? <p>Пока нет загруженных тренировок.</p> : null}
      {activities.length > 0 ? (
        <div className="table-wrap">
          <table>
            <caption>Дата есть только у уже разобранной тренировки. Название Garmin в базу не записывается.</caption>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Тип</th>
                <th>Длительность</th>
                <th>Дистанция</th>
                <th>Разбор</th>
              </tr>
            </thead>
            <tbody>
              {activities.map((activity) => (
                <tr key={activity.garminActivityId}>
                  <td>{activity.when}</td>
                  <td>{activity.sport}</td>
                  <td>{activity.duration}</td>
                  <td>{activity.distance}</td>
                  <td>{activity.parsed ? 'да' : 'нет'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </main>
  );
}
