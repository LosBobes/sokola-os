import { onboard, uniq } from "../support/e2e";

function setupGroupWithMember(groupName: string): void {
  cy.get("[data-cy='nav-/ljudi']").click();
  cy.get("[data-cy=person-given]").type("Mila");
  cy.get("[data-cy=person-family]").type("Jovanović");
  cy.get("[data-cy=person-save]").click();
  cy.get("[data-cy=group-name]").type(groupName);
  cy.get("[data-cy=group-save]").click();
  cy.get("[data-cy=member-select]").first().select("Mila Jovanović");
  cy.get("[data-cy=member-add]").first().click();
  cy.get("[data-cy=group-item]").contains("1 članova").should("exist");
}

describe("Manager: finance and communications", () => {
  it("covers Journeys 5, 6 and 7 end-to-end", () => {
    onboard(`Klub ${uniq()}`);
    const groupName = `Grupa ${uniq()}`;
    setupGroupWithMember(groupName);

    // --- Journey 5: post a billing run (preview → confirm → post) ---
    cy.get("[data-cy='nav-/finansije']").click();
    cy.get("[data-cy=billing-group]").select(groupName);
    cy.get("[data-cy=billing-amount]").clear().type("3000");
    cy.get("[data-cy=billing-preview]").click();
    cy.get("[data-cy=billing-preview-summary]").contains("1").should("exist");
    cy.get("[data-cy=confirm-dialog][open] [data-cy=confirm-yes]").click();
    cy.get("[data-cy=charge-row]").should("have.length", 1);

    // --- Journey 6: record a payment (partial) ---
    cy.get("[data-cy=charge-pay]").first().click();
    cy.get("[data-cy=pay-amount]").clear().type("1000");
    cy.get("[data-cy=confirm-dialog][open] [data-cy=confirm-yes]").click();
    cy.get("[data-cy=charge-row]").contains("Delimično plaćeno").should("exist");

    // --- Journey 7: publish an announcement (preview snapshot → publish) ---
    cy.get("[data-cy='nav-/komunikacija']").click();
    cy.get("[data-cy=ann-new]").click();
    cy.get("[data-cy=ann-group]").select(groupName);
    cy.get("[data-cy=ann-title]").type("Trening otkazan");
    cy.get("[data-cy=ann-body]").type("Sutrašnji trening je otkazan.");
    cy.get("[data-cy=ann-preview]").click();
    cy.get("[data-cy=ann-preview-summary]").contains("1").should("exist");
    cy.get("[data-cy=confirm-dialog][open] [data-cy=confirm-yes]").click();
    cy.contains("je objavljena za 1 primalaca").should("exist");
  });
});
