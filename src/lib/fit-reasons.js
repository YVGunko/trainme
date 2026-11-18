// Why a FIT file cannot be sent as a workout, and what about it was not kept.
// Each sentence names what the file actually is, because the user picked it by
// hand and needs to know whether to look for a different file or fix this one.
//
// Garmin Connect imports FIT activity files only. It has no workout import,
// so a FIT workout reaches Garmin as workout JSON, not as a file.
export const FIT_REASONS = {
  activity_file:
    'Это файл активности, а не тренировки. Garmin Connect не импортирует FIT-тренировки — только активности.',
  other_file: 'Это FIT другого типа, не тренировка.',
  no_workout_message: 'В файле нет сообщения тренировки.',
  unreadable: 'Файл повреждён или это не FIT.',
  empty: 'Файл пустой.',
  too_large: 'Файл больше 256 КБ.',
  missing: 'Файл не приложен.',
  bad_base64: 'Файл не удалось прочитать.',
};

export function fitReason(reason) {
  return FIT_REASONS[reason] || '';
}

function seconds(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  return `${rounded} с`;
}

function meters(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  return `${rounded} м`;
}

// The server reports warnings as codes plus the values behind them, so the
// sentence lives here and stays readable in Russian.
const WARNING_SENTENCES = {
  step_names_dropped: (w) => `Названия шагов не переносятся (${w.count}).`,
  notes_dropped: (w) => `Заметки к шагам не переносятся (${w.count}).`,
  short_steps: (w) =>
    `Похоже, в файле неверные единицы времени: ${w.count} шаг(ов) короче секунды, самый короткий ${seconds(w.smallest)}. Garmin примет это как тренировку на несколько секунд — проверьте файл.`,
  short_distance_steps: (w) =>
    `Похоже, в файле неверные единицы расстояния: ${w.count} шаг(ов) короче метра, самый короткий ${meters(w.smallest)}.`,
  short_workout: (w) =>
    `Вся тренировка длится ${seconds(w.total_seconds)}. Для плановой тренировки это почти наверняка ошибка в файле.`,
};

export function warningText(warning) {
  if (!warning || typeof warning.code !== 'string') return '';
  const render = WARNING_SENTENCES[warning.code];
  return render ? render(warning) : '';
}

// Warnings that mean the numbers themselves are suspect, not just lost text.
const NUMERIC_CODES = new Set(['short_steps', 'short_distance_steps', 'short_workout']);

export function hasNumericWarning(warnings) {
  return Array.isArray(warnings) && warnings.some((warning) => NUMERIC_CODES.has(warning?.code));
}

export function warningTexts(warnings) {
  if (!Array.isArray(warnings)) return [];
  return warnings.map(warningText).filter(Boolean);
}
