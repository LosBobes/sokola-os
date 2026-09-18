import { dateTimeInput, nextWeekday, onboard, tomorrow, uniq } from "../support/e2e";

const WEDNESDAY = 2; // Monday = 0, matching the weekday chips in Raspored.

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
    cy.get("[data-cy=session-start]").type(dateTimeInput(tomorrow(), 17));
    cy.get("[data-cy=session-save]").click();
    cy.get("[data-cy=session-row]").should("have.length.at.least", 1);

    // --- Journey 2: record attendance (exceptions only + version) ---
    // Attendance has exactly two marks, Prisutan and Odsutan; there is no
    // excused/unexcused follow-up question any more.
    cy.get("[data-cy=session-attendance]").first().click();
    cy.get("[data-cy=attendance-row]").should("have.length", 1);
    cy.get("[data-cy=attendance-row]").find("button[data-cy^=attendance-mark-absent-]").click();
    cy.get("[data-cy=attendance-rate]").contains("0%").should("exist");
    cy.get("[data-cy=attendance-save]").click();
    cy.contains("Sačuvano prisustvo").should("exist");
  });

  it("schedules a repeating slot and shows events on the same calendar", () => {
    onboard(`Klub ${uniq()}`);

    // A group to hang the recurrence on.
    const groupName = `Sreda ${uniq()}`;
    cy.get("[data-cy='nav-/ljudi']").click();
    cy.get("[data-cy=group-name]").type(groupName);
    cy.get("[data-cy=group-save]").click();

    // "Svake srede u 18:00": the rule and its occurrences are one action.
    cy.get("[data-cy='nav-/raspored']").click();
    cy.get("[data-cy=session-group]").select(groupName);
    cy.get("[data-cy=session-start]").type(dateTimeInput(nextWeekday(WEDNESDAY), 18));
    cy.get("[data-cy=session-repeats]").check();
    cy.get("[data-cy=session-weekday-2]").click();
    cy.get("[data-cy=session-weeks]").clear().type("3");
    cy.get("[data-cy=session-save]").click();
    cy.get("[data-cy=series-result]").should("exist");
    cy.get("[data-cy=session-row]").should("have.length.at.least", 3);

    // Editing an occurrence offers the three calendar scopes.
    cy.get("[data-cy=session-detail-open]").first().click();
    cy.get("[data-cy=session-edit-open]").click();
    cy.get("[data-cy=session-edit-scope]").should("exist");
    cy.get("[data-cy=session-edit-scope] option").should("have.length", 3);
  });
});
