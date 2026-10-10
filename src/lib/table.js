export function filterActivities(rows, query) {
  const needle = String(query || '').trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) => {
    const title = row.title === '—' ? '' : row.title;
    return `${title}\n${row.description || ''}`.toLowerCase().includes(needle);
  });
}

export function toggleSort(current, id, multi) {
  const initialDesc = id === 'when';
  if (multi) {
    const existing = current.find((item) => item.id === id);
    if (!existing) return [...current, { id, desc: initialDesc }];
    return current.map((item) => (item.id === id ? { ...item, desc: !item.desc } : item));
  }
  if (current.length === 1 && current[0].id === id) {
    return [{ id, desc: !current[0].desc }];
  }
  return [{ id, desc: initialDesc }];
}

export function sortActivities(rows, sorting) {
  const keys = sorting.length ? sorting : [{ id: 'when', desc: true }];
  return [...rows].sort((left, right) => {
    for (const key of keys) {
      const result = compareRows(left, right, key);
      if (result !== 0) return result;
    }
    return String(left.garminActivityId).localeCompare(String(right.garminActivityId));
  });
}

export function sortLabel(sorting) {
  const names = {
    when: 'дата',
    title: 'название',
    description: 'описание',
    sport: 'тип',
    duration: 'длительность',
    distance: 'дистанция',
    parsed: 'разбор',
  };
  return sorting
    .map((item, index) => {
      const name = names[item.id] || item.id;
      const direction = item.desc ? 'по убыванию' : 'по возрастанию';
      return sorting.length > 1 ? `${index + 1}. ${name} ${direction}` : `${name} ${direction}`;
    })
    .join(', ');
}

function compareRows(left, right, key) {
  if (key.id === 'when') return compareMissingLast(left.whenSort, right.whenSort, key.desc);
  if (key.id === 'duration') return compareMissingLast(left.durationSec, right.durationSec, key.desc);
  if (key.id === 'distance') return compareMissingLast(left.distanceM, right.distanceM, key.desc);
  if (key.id === 'parsed') return compareMissingLast(left.parsed ? 1 : 0, right.parsed ? 1 : 0, key.desc);
  return compareMissingLast(textValue(left[key.id]), textValue(right[key.id]), key.desc);
}

function textValue(value) {
  if (value == null || value === '' || value === '—') return null;
  return String(value).toLowerCase();
}

function compareMissingLast(left, right, desc) {
  if (left == null || right == null) {
    if (left == null && right == null) return 0;
    return left == null ? 1 : -1;
  }
  let result = 0;
  if (typeof left === 'number' && typeof right === 'number') result = left - right;
  else if (left < right) result = -1;
  else if (left > right) result = 1;
  return desc ? -result : result;
}
