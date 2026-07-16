import { uniq } from "../support/e2e";

describe("Tenant-first auth", () => {
  it("registers a school, then logs in via school code + access code", () => {
    const school = `Klub ${uniq()}`;

    // --- Register a new school (separate from logging in) ---
    cy.visit("/");
    cy.get("[data-cy=go-register]").click();
    cy.get("[data-cy=given]").type("Vlasnik");
    cy.get("[data-cy=family]").type("Test");
    cy.get("[data-cy=school]").type(school);
    cy.get("[data-cy=do-register]").click();

    // The tenant code + access code are shown once.
    cy.get("[data-cy=registered]").should("exist");
    cy.get("[data-cy=school-code]")
      .invoke("text")
      .then((slug) => {
        cy.get("[data-cy=access-id]")
          .invoke("text")
          .then((accessId) => {
            cy.get("[data-cy=enter-school]").click();
            cy.get("[data-cy=context-switcher]").should("exist");

            // --- Sign out, then log in tenant-first ---
            cy.get("[data-cy=sign-out]").click();
            cy.get("[data-cy=go-login]").click();
            cy.get("[data-cy=tenant-code]").type(slug.trim());
            cy.get("[data-cy=tenant-continue]").click();

            // Routed to that school's login, which names the tenant.
            cy.contains(`Prijava — ${school}`).should("exist");
            cy.get("[data-cy=access-code]").type(accessId.trim());
            cy.get("[data-cy=do-login]").click();
            cy.get("[data-cy=context-switcher]").should("exist");
          });
      });
  });

  it("rejects a login for someone with no role in that school", () => {
    const school = `Klub ${uniq()}`;
    // Owner registers school A.
    cy.visit("/");
    cy.get("[data-cy=go-register]").click();
    cy.get("[data-cy=given]").type("Vlasnik");
    cy.get("[data-cy=family]").type("A");
    cy.get("[data-cy=school]").type(school);
    cy.get("[data-cy=do-register]").click();
    cy.get("[data-cy=school-code]")
      .invoke("text")
      .then((slug) => {
        cy.get("[data-cy=enter-school]").click();
        cy.get("[data-cy=sign-out]").click();

        // A stranger tries to enter that school with an unknown access code.
        cy.get("[data-cy=go-login]").click();
        cy.get("[data-cy=tenant-code]").type(slug.trim());
        cy.get("[data-cy=tenant-continue]").click();
        cy.get("[data-cy=access-code]").type("per_nepostoji");
        cy.get("[data-cy=do-login]").click();
        cy.get("[data-cy=login-error]").should("exist");
      });
  });
});
