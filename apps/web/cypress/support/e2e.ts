/// <reference types="cypress" />

/** Register a fresh manager + school and land in the shell. */
export function onboard(school: string): void {
  cy.visit("/");
  cy.get("[data-cy=go-register]").click();
  cy.get("[data-cy=given]").type("Menadžer");
  cy.get("[data-cy=family]").type("Test");
  cy.get("[data-cy=school]").type(school);
  cy.get("[data-cy=do-register]").click();
  cy.get("[data-cy=enter-school]", { timeout: 15000 }).click();
  cy.get("[data-cy=context-switcher]", { timeout: 15000 }).should("exist");
}

/** Unique-enough suffix so parallel/repeated runs don't collide on names. */
export function uniq(): string {
  return Math.random().toString(36).slice(2, 8);
}

/**
 * A value for a `datetime-local` input: exactly "YYYY-MM-DDTHH:mm", in local
 * time. Built from the local getters rather than `toISOString`, which would
 * shift the value by the runner's UTC offset.
 */
export function dateTimeInput(date: Date, hour: number, minute = 0): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(hour)}:${pad(minute)}`
  );
}

/**
 * The next date falling on `weekday` (Monday = 0 ... Sunday = 6), starting from
 * tomorrow.
 *
 * Schedule dates in these specs must be *relative*. Raspored lists a rolling
 * window that starts today, so a hardcoded calendar date silently leaves the
 * window once it passes and the session it created stops being listed. That is
 * a test rotting with the calendar, not a regression, and it is expensive to
 * diagnose from a bare "element never found".
 */
export function nextWeekday(weekday: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  while ((date.getDay() + 6) % 7 !== weekday) {
    date.setDate(date.getDate() + 1);
  }
  return date;
}

/** Tomorrow, which is always inside the window Raspored lists by default. */
export function tomorrow(): Date {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date;
}
