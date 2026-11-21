const ICONS = {
  save: 'M5 4h10l4 4v12H5V4z M8 4v5h7 M8 20v-6h8v6',
  download: 'M12 4v11 M7 11l5 5 5-5 M5 20h14',
  upload: 'M12 16V5 M7 9l5-5 5 5 M5 20h14',
  refresh: 'M20 12a8 8 0 1 1-2.2-5.5 M20 4v5h-5',
  rebuild: 'M4 8h11 M12 5l3 3-3 3 M20 16H9 M12 13l-3 3 3 3',
  send: 'M4 12 L20 4 L14 20 L11 13 Z',
  eye: 'M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M16.5 16.5 L20 20',
  parse: 'M7 5h7l3 3v11H7V5z M14 5v4h4 M9 12h6 M9 16h4',
};

export function IconButton({
  icon,
  label,
  variant = 'primary',
  type = 'button',
  className = '',
  busy = false,
  disabled = false,
  ...props
}) {
  const classes = ['icon-button', variant === 'secondary' ? 'secondary' : '', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      type={type}
      className={classes}
      aria-label={label}
      title={label}
      aria-busy={busy || undefined}
      disabled={disabled || busy}
      {...props}
    >
      <Icon name={icon} />
    </button>
  );
}

function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round">
      <path d={ICONS[name]} />
    </svg>
  );
}
