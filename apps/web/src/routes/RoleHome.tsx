import { Link } from "react-router-dom";
import { useSession } from "../auth/session";
import { PageHeader } from "../components/shell";
import { ManagerHome } from "./manager/ManagerHome";
import { TrainerHome } from "./trainer/TrainerHome";

/** Each role lands on its own home with one dominant next action. */
export function RoleHome() {
  const { activeContext } = useSession();
  const role = activeContext?.role_code ?? "STUDENT";
  const org = activeContext?.organization_name ?? "";

  if (role === "PARENT") {
    return (
      <div>
        <PageHeader title={`Dobrodošli · ${org}`} />
        <div className="card">
          <p>Šta je sledeće za vaše dete?</p>
          <Link className="btn btn--primary" to="/dogadjaji" data-cy="home-events">
            Pogledaj događaje
          </Link>
        </div>
      </div>
    );
  }

  if (role === "TRAINER") return <TrainerHome />;

  if (role === "OWNER" || role === "MANAGER" || role === "ADMIN") return <ManagerHome />;

  // STUDENT (and any other role without a dedicated home yet).
  return (
    <div>
      <PageHeader title={`Danas · ${org}`} />
      <div className="card" style={{ display: "grid", gap: "var(--space-3)" }}>
        <p>Brze radnje:</p>
        <Link className="btn btn--secondary" to="/ljudi" data-cy="home-people">
          Ljudi i grupe
        </Link>
        <Link className="btn btn--secondary" to="/raspored" data-cy="home-schedule">
          Raspored
        </Link>
        <Link className="btn btn--secondary" to="/finansije" data-cy="home-money">
          Finansije
        </Link>
      </div>
    </div>
  );
}
