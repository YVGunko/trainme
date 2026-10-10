import './globals.css';

export const metadata = {
  title: 'Тренировки',
  description: 'Загруженные и разобранные тренировки',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
