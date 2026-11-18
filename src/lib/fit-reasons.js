// Why a FIT file cannot be sent as a workout. Each sentence names what the
// file actually is, because the user picked it by hand and needs to know
// whether to look for a different file or fix this one.
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
