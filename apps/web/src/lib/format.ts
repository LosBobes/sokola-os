/*
 * Date, time and period formatting, in one place.
 *
 * Serbian dates are written DD.MM.YYYY. Reading "08.14.2026" or "8/14/2026" in
 * a Serbian school's app costs the reader a beat every single time and is
 * genuinely ambiguous for the first twelve days of a month, so no screen
 * formats a date by hand or leans on a locale the browser might not have.
 * `sr-Latn` is requested where a month or weekday NAME is wanted, but the
 * numeric forms below are assembled explicitly so they cannot drift.
 */

const MONTHS_NOMINATIVE = [
  "januar",
  "februar",
  "mart",
  "april",
  "maj",
  "jun",
  "jul",
  "avgust",
  "septembar",
  "oktobar",
  "novembar",
  "decembar",
] as const;

const WEEKDAYS_LONG = [
  "nedelja",
  "ponedeljak",
  "utorak",
  "sreda",
  "četvrtak",
  "petak",
  "subota",
] as const;

const WEEKDAYS_SHORT = ["NED", "PON", "UTO", "SRE", "ČET", "PET", "SUB"] as const;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function toDate(value: Date | string): Date {
  return value instanceof Date ? value : new Date(value);
}

/** `14.08.2026`. The canonical date format across the app. */
export function formatDate(value: Date | string): string {
  const d = toDate(value);
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}.`;
}

/** `14.08.` , a date inside a context that already establishes the year. */
export function formatDayMonth(value: Date | string): string {
  const d = toDate(value);
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`;
}

/** `18:00`. 24-hour, always two digits. */
export function formatTime(value: Date | string): string {
  const d = toDate(value);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** `14.08.2026. 18:00`. */
export function formatDateTime(value: Date | string): string {
  return `${formatDate(value)} ${formatTime(value)}`;
}

/** `sreda, 14.08.2026.` , the long form a day view heads itself with. */
export function formatWeekdayDate(value: Date | string): string {
  const d = toDate(value);
  return `${WEEKDAYS_LONG[d.getDay()] ?? ""}, ${formatDate(d)}`;
}

/** `SRE` , the column head in a week grid. */
export function formatWeekdayShort(value: Date | string): string {
  return WEEKDAYS_SHORT[toDate(value).getDay()] ?? "";
}

/** `avgust 2026`. */
export function formatMonthYear(value: Date | string): string {
  const d = toDate(value);
  return `${MONTHS_NOMINATIVE[d.getMonth()] ?? ""} ${d.getFullYear()}`;
}

/**
 * A stored billing period turned into something a person reads.
 *
 * Periods are stored machine-sortable (`2026-08`), which is right for the
 * database and wrong for a screen. A label that is not in that shape is a
 * free-text period the school typed ("Jesenja sezona") and is shown verbatim.
 */
export function formatPeriodLabel(periodLabel: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(periodLabel.trim());
  if (!match) return periodLabel;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return periodLabel;
  return `${MONTHS_NOMINATIVE[month - 1]} ${year}`;
}

/** The `YYYY-MM` label for a date, the format billing periods are stored in. */
export function toPeriodLabel(value: Date | string): string {
  const d = toDate(value);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

/**
 * `14.08.2026. – 20.08.2026.`, collapsed where the two ends share a month or a
 * year, e.g. `14 – 20. avgust 2026`.
 */
export function formatDateRange(from: Date | string, toInclusive: Date | string): string {
  const start = toDate(from);
  const end = toDate(toInclusive);
  const sameYear = start.getFullYear() === end.getFullYear();
  const sameMonth = sameYear && start.getMonth() === end.getMonth();
  if (sameMonth) {
    return `${start.getDate()}. – ${end.getDate()}. ${MONTHS_NOMINATIVE[end.getMonth()]} ${end.getFullYear()}.`;
  }
  if (sameYear) {
    return `${formatDayMonth(start)} – ${formatDate(end)}`;
  }
  return `${formatDate(start)} – ${formatDate(end)}`;
}

/**
 * Whether a due date has actually passed.
 *
 * "Dospelo" is a claim about time, not about a charge's status: an unpaid
 * charge whose due date is next week is outstanding, not overdue. Anything
 * calling a charge overdue must go through here and must print the date
 * alongside the word.
 */
export function isPastDue(dueDate: string | null | undefined): boolean {
  if (!dueDate) return false;
  const due = new Date(`${dueDate}T23:59:59`);
  return due.getTime() < Date.now();
}
