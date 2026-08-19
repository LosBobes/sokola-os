import { NavLink } from "react-router-dom";
import { useSession } from "../auth/session";
import { PageHeader, ROLE_LABEL, overflowDestinations } from "../components/shell";
import { Button, Card } from "../components/ui";
import "./More.css";

/*
 * M1 "Više", the overflow destination every role's primary nav points at.
 *
 * Two jobs, in this order:
 *  1. Reach whatever the mobile tab bar left out. The bar holds four items
 *     plus this one, so on a phone Komunikacija / Događaji / Izveštaji live
 *     here and nowhere else , if this page did not list them they would be
 *     unreachable on the device most likely to be used on the floor.
 *  2. The account-actions catch-all: who you are, switching school/role,
 *     signing out, and where to get help.
 *
 * The header says "Nalog i podrška" rather than "Nalog i podešavanja" because
 * there are no settings behind it yet, and naming a screen after something it
 * does not have sends people looking for it.
 */

/** Where a school owner goes when something is wrong with SOKOLA OS itself. */
const SOKOLA_SUPPORT_EMAIL = "podrska@sokola.rs";

export function MorePage() {
  const { me, activeContext, chooseContext, signOut } = useSession();

  if (!me || !activeContext) return null;

  const roleLabel = ROLE_LABEL[activeContext.role_code];
  const otherContexts = me.contexts.filter(
    (c) => c.role_assignment_id !== activeContext.role_assignment_id,
  );
  const overflow = overflowDestinations(activeContext.role_code);

  /*
   * An owner IS the school's administrator. Telling them to "contact your
   * school's administrator" sends them to themselves, so they get the route
   * that actually exists for them: SOKOLA's own support.
   */
  const isOwner = activeContext.role_code === "OWNER";

  return (
    <div className="more-page">
      <PageHeader eyebrow="Nalog i podrška" title="Više" />

      {overflow.length > 0 ? (
        <Card
          eyebrow="Ostale stranice"
          title="Brzi pristup"
          subtitle="Stranice koje se ne vide u donjoj traci na telefonu."
          className="more-page__card"
        >
          <ul className="more-page__list">
            {overflow.map((d) => (
              <li key={d.to}>
                <NavLink
                  to={d.to}
                  className="more-page__row more-page__row--link"
                  data-cy={`more-nav-${d.to}`}
                >
                  <span className="more-page__row-org">{d.label}</span>
                  <span className="more-page__row-role">{d.hint}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card
        eyebrow="Nalog"
        title={me.display_name}
        subtitle={`${roleLabel} · ${activeContext.organization_name}`}
        className="more-page__card"
      >
        <div className="more-page__rows">
          <Button variant="secondary" onClick={signOut} data-cy="more-sign-out">
            Odjava
          </Button>
        </div>
      </Card>

      {me.contexts.length > 1 ? (
        <Card
          eyebrow="Kontekst"
          title="Škole i uloge"
          subtitle="Aktivna škola i uloga je označena. Izaberite drugu za prebacivanje."
          className="more-page__card"
        >
          <ul className="more-page__list">
            <li>
              <span className="more-page__row more-page__row--active" aria-current="true">
                <span className="more-page__row-org">{activeContext.organization_name}</span>
                <span className="more-page__row-role">{ROLE_LABEL[activeContext.role_code]}</span>
              </span>
            </li>
            {otherContexts.map((c) => (
              <li key={c.role_assignment_id}>
                <button
                  type="button"
                  className="more-page__row more-page__row--btn"
                  onClick={() => chooseContext(c.role_assignment_id)}
                  data-cy={`more-context-${c.role_assignment_id}`}
                >
                  <span className="more-page__row-org">{c.organization_name}</span>
                  <span className="more-page__row-role">{ROLE_LABEL[c.role_code]}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card eyebrow="Pomoć" title="Podrška" className="more-page__card">
        {isOwner ? (
          <p className="more-page__help" data-cy="more-support-owner">
            Za pitanja o korišćenju sistema ili prijavu problema pišite SOKOLA podršci na{" "}
            <a href={`mailto:${SOKOLA_SUPPORT_EMAIL}`}>{SOKOLA_SUPPORT_EMAIL}</a>.
          </p>
        ) : (
          <p className="more-page__help" data-cy="more-support-staff">
            Za pitanja o korišćenju sistema ili prijavu problema obratite se administratoru vaše
            škole.
          </p>
        )}
      </Card>
    </div>
  );
}
