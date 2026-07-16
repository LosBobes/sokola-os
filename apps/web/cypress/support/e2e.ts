/// <reference types="cypress" />

/** Onboard a fresh manager + organization and wait for the app shell. */
export function onboard(school: string): void {
  cy.visit("/");
  cy.get("[data-cy=given]").type("Menadžer");
  cy.get("[data-cy=family]").type("Test");
  cy.get("[data-cy=school]").type(school);
  cy.get("[data-cy=onboard]").click();
  cy.get("[data-cy=context-switcher]", { timeout: 15000 }).should("exist");
}

/** Unique-enough suffix so parallel/repeated runs don't collide on names. */
export function uniq(): string {
  return Math.random().toString(36).slice(2, 8);
}
