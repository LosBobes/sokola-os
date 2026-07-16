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
