import { useSession } from "../auth/session";
import { PageHeader, ROLE_LABEL } from "../components/shell";
import { Button, Card } from "../components/ui";
import "./More.css";

/*
 * M1 "Više" — the overflow destination every role's primary nav already
 * points at (sidebar/tab-bar). Since NAV in shell.tsx already surfaces every
 * role's operational screens as top-level links, there's nothing left to
 * "overflow" here — so this page is the account-actions catch-all: who you
 * are, switching school/role, signing out, and where to get help.
 */
export function MorePage() {
  const { me, activeContext, chooseContext, signOut } = useSession();

  if (!me || !activeContext) return null;

  const roleLabel = ROLE_LABEL[activeContext.role_code];
  const otherContexts = me.contexts.filter(
    (c) => c.role_assignment_id !== activeContext.role_assignment_id,
  );

  return (
    <div className="more-page">
      <PageHeader title="Više" />

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
          subtitle="Aktivna škola i uloga je označena — izaberite drugu za prebacivanje."
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
        <p className="more-page__help">
          Za pitanja o korišćenju sistema ili prijavu problema obratite se administratoru vaše
          škole.
        </p>
      </Card>
    </div>
  );
}
