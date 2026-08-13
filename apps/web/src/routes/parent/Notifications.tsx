import { PageHeader } from "../../components/shell";
import { EmptyState, SplitPane } from "../../components/ui";

/**
 * P06 Roditelj Obaveštenje, parent notification inbox.
 *
 * The in-app inbox backend (#15 Komunikacija) is not merged yet: the API only
 * exposes POST /communications/announcements (manager publish + preview),
 * with no GET endpoint a parent can read from. So this screen ships the
 * layout only, list area + detail placeholder, per-child/per-school scoping
 * to be wired the moment a read endpoint lands, and shows no fabricated
 * notifications in the meantime. The bottom tab bar is the shared
 * ProductShell nav (see components/shell.tsx); this route does not render
 * its own.
 */
export function ParentNotificationsPage() {
  return (
    <div>
      <PageHeader eyebrow="Poruke škole" title="Obaveštenja" />
      <SplitPane
        list={
          <div data-cy="notifications-list">
            <EmptyState>
              Trenutno nemate obaveštenja. Poruke škole će uskoro stizati direktno ovde, bez
              komentara, bez skrivenih primalaca.
            </EmptyState>
          </div>
        }
        detail={
          <div data-cy="notification-detail">
            <EmptyState>
              Prikaz obaveštenja dolazi uskoro, zajedno sa modulom za komunikaciju škole. Kada
              stigne, ovde ćete videti samo poruke koje se odnose na vaše dete i vašu školu.
            </EmptyState>
          </div>
        }
      />
    </div>
  );
}
