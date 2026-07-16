import { onboard, uniq } from "../support/e2e";

describe("Manager: people, groups, schedule, attendance", () => {
  it("covers Journeys 8, 1 and 2 end-to-end", () => {
    onboard(`Klub ${uniq()}`);

    // --- Journey 8: create a provisional person + duplicate safety branch ---
    // (The owner is already a member, so we assert on the specific name.)
    cy.get("[data-cy='nav-/ljudi']").click();
    cy.get("[data-cy=person-given]").type("Petar");
    cy.get("[data-cy=person-family]").type("Petrović");
    cy.get("[data-cy=person-save]").click();
    cy.get("[data-cy=person-row]").filter(':contains("Petrović")').should("have.length", 1);

    // Same name again → possible-duplicate dialog → confirm with a reason.
    cy.get("[data-cy=person-given]").type("Petar");
    cy.get("[data-cy=person-family]").type("Petrović");
    cy.get("[data-cy=person-save]").click();
    cy.get("[data-cy=confirm-dialog]").should("be.visible");
    cy.get("[data-cy=dup-reason]").type("Blizanci");
    cy.get("[data-cy=confirm-dialog][open] [data-cy=confirm-yes]").click();
    cy.get("[data-cy=person-row]").filter(':contains("Petrović")').should("have.length", 2);

    // --- Group + member ---
    const groupName = `Pioniri ${uniq()}`;
    cy.get("[data-cy=group-name]").type(groupName);
    cy.get("[data-cy=group-save]").click();
    cy.get("[data-cy=group-item]").contains(groupName).should("exist");
    // Add the uniquely-named owner (two "Petar Petrović" now exist by design).
    cy.get("[data-cy=member-select]").first().select("Menadžer Test");
    cy.get("[data-cy=member-add]").first().click();
    cy.get("[data-cy=group-item]").contains("1 članova").should("exist");

    // --- Journey 1: create a one-off session (conflict preview then create) ---
    cy.get("[data-cy='nav-/raspored']").click();
    cy.get("[data-cy=session-group]").select(groupName);
    cy.get("[data-cy=session-start]").type("2026-09-01T17:00");
    cy.get("[data-cy=session-save]").click();
    cy.get("[data-cy=session-row]").should("have.length.at.least", 1);

    // --- Journey 2: record attendance (exceptions only + version) ---
    cy.get("[data-cy=session-attendance]").first().click();
    cy.get("[data-cy=attendance-row]").should("have.length", 1);
    cy.get("[data-cy=attendance-table] select").first().select("ABSENT");
    cy.get("[data-cy=attendance-save]").click();
    cy.contains("Sačuvano prisustvo").should("exist");
  });
});
