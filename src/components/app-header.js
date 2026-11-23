export function AppHeader({ username, section = 'home' }) {
  const onData = section === 'data';
  return (
    <header className="top">
      <div>
        <h1>{onData ? 'Data' : 'Training'}</h1>
        <p className="muted">{username}</p>
      </div>
      <div className="top-actions">
        <a className="secondary" href={onData ? '/' : '/data'}>
          {onData ? 'Home' : 'Data'}
        </a>
        <form action="/api/auth/logout" method="post">
          <button className="secondary" type="submit">
            Sign out
          </button>
        </form>
      </div>
    </header>
  );
}
