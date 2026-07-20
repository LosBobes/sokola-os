import { PageHeader } from "../../components/shell";
import {
  Button,
  Card,
  EmptyState,
  FilterBar,
  FilterChip,
  StatusBadge,
  TableContainer,
} from "../../components/ui";

/*
 * M11 · Dokumenti (#31).
 *
 * The documents domain has no backend yet — GET /documents (and friends)
 * do not exist in schema.d.ts (tracked separately as #11). Rather than
 * fabricate data or invent an endpoint shape, this screen ships the route,
 * the page chrome, and the layout structure from the design
 * (09_M11_Dokumenti.png: header + upload action, filter row, a
 * name/type/owner/date/visibility list, and a detail pane) with every
 * interactive piece disabled and explained as "uskoro". When #11 lands,
 * this file is the one place to swap the stubs for real `useAsync` calls —
 * no other route or shared component needs to change.
 */

const COLUMNS = ["Naziv", "Tip", "Vlasnik", "Datum", "Vidljivost", "Stanje"];

export function DocumentsPage() {
  return (
    <div>
      <PageHeader
        title="Dokumenti"
        action={
          <Button
            disabled
            title="Uskoro — dodavanje dokumenata dolazi kada modul dokumenata bude spreman (#11)"
            data-cy="doc-upload"
          >
            Dodaj dokument
          </Button>
        }
      />
      <p style={{ color: "var(--text-secondary)", marginTop: 0, marginBottom: "var(--space-4)" }}>
        Dokumenti škole i članova, dostupni samo ovlašćenim korisnicima.{" "}
        <StatusBadge tone="info">Uskoro</StatusBadge>
      </p>

      <FilterBar>
        <div className="field" style={{ margin: 0, minWidth: 220 }}>
          <input
            type="search"
            placeholder="Pretražite naziv ili vlasnika"
            aria-label="Pretražite naziv ili vlasnika"
            disabled
            data-cy="doc-search"
          />
        </div>
        <FilterChip caret disabled title="Uskoro — filter po vlasniku dolazi sa modulom dokumenata (#11)" style={{ opacity: 0.55 }}>
          Vlasnik
        </FilterChip>
        <FilterChip caret disabled title="Uskoro — filter po grupi dolazi sa modulom dokumenata (#11)" style={{ opacity: 0.55 }}>
          Grupa
        </FilterChip>
        <FilterChip caret disabled title="Uskoro — filter po tipu dolazi sa modulom dokumenata (#11)" style={{ opacity: 0.55 }}>
          Tip
        </FilterChip>
        <FilterChip caret disabled title="Uskoro — filter po stanju dolazi sa modulom dokumenata (#11)" style={{ opacity: 0.55 }}>
          Stanje
        </FilterChip>
        <FilterChip caret disabled title="Uskoro — filter po vidljivosti dolazi sa modulom dokumenata (#11)" style={{ opacity: 0.55 }}>
          Vidljivost
        </FilterChip>
      </FilterBar>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--space-4)", alignItems: "start" }}>
        <Card flat>
          <TableContainer>
            <table className="data" data-cy="doc-list">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                  <th aria-label="Radnja" />
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td colSpan={COLUMNS.length + 1}>
                    <EmptyState>
                      Dokumenti uskoro stižu. Ovaj modul (arhiva saglasnosti, ugovora, rasporeda i drugih fajlova
                      škole i članova) čeka backend #11 — kada bude spreman, lista, filteri i akcije za
                      pregled/preuzimanje se popunjavaju ovde bez izmene drugih ekrana.
                    </EmptyState>
                  </td>
                </tr>
              </tbody>
            </table>
          </TableContainer>
          <p
            style={{
              margin: "var(--space-3) 0 0",
              color: "var(--text-secondary)",
              fontSize: "var(--text-sm)",
            }}
          >
            Planirano: PDF, JPG i PNG, uz proveru pre dostupnosti — dolazi sa modulom dokumenata.
          </p>
        </Card>

        <Card title="Detalj dokumenta" flat>
          <EmptyState>Izaberite dokument sa liste da vidite detalje.</EmptyState>
        </Card>
      </div>
    </div>
  );
}
