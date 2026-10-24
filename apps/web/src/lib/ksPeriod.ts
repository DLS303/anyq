/** Last calendar month, used as the default act period. */

function iso(day: Date) {
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

export function lastMonth(today = new Date()) {
  const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const end = new Date(today.getFullYear(), today.getMonth(), 0);
  const periodTo = iso(end);
  return { period_from: iso(start), period_to: periodTo, act_date: periodTo };
}
