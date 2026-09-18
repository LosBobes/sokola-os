---
tip: programmer-entrypoint
status: PROGRAMMER_CANDIDATE
scope: [M00-M21, M28]
code-status: CODE_REPOSITORY_UNVERIFIED
datum: 2026-09-16
---

# SOKOLA OS v5.7 — start za programera

Ovo je samostalan normativni paket za repo-first implementaciju. Dokumentacioni ugovori su spremni za mapiranje na postojeći kod; paket ne tvrdi da su kod, migracije, infrastruktura ili testovi već završeni. Tu činjenicu utvrđuje implementacioni agent u stvarnom repozitorijumu i upisuje u `CURRENT-CODE-BASELINE.md`.

## 1. Obuhvat

- H0/MVP: M00–M21, uključujući Events Light, CSV/XLSX import, tri dashboard/workspace toka, PWA osnovu i platformske operativne ugovore.
- H1 pre-pilot: M28 mySOKOLA Basic, zaseban acceptance, `DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST`.
- M22–M27 i M29–M34: nisu deo ove implementacione predaje osim rezervisanih, fail-closed arhitektonskih granica navedenih u M00/DCR-u.
- Stvarni repo je brownfield autoritet za stack i fizičku organizaciju, ali ne sme menjati ovde zaključano poslovno ponašanje.

## 2. Obavezni redosled čitanja

1. `00-CLAUDE-CODE-IZVRSI.md` i `CURRENT-CODE-BASELINE.md`.
2. Svi aktivni DCR-ovi u `00-DCR-AKTIVNI-v5.7`; DCR-20260907-01 revizija 2.3 razrešava konfliktni zajednički ugovor.
3. Četiri M00 dokumenta: scope, arhitektura/zavisnosti, izrada/acceptance/predaja i tačan katalog 42 H0 UI površine.
4. M01–M07 master+QA, uključujući oba M05 permission registra.
5. M08–M16 master+QA, cross-module traceability i screen-to-contract binding.
6. M17–M21 master+QA/integration dokumenta, M20 import schema v1 i M21 job catalog v1.
7. M28 master, QA, screen/command mapu i integration mapu.
8. `05-VALIDACIJA/DOCUMENTATION-VALIDATION-EVIDENCE.md`, zatim `MANIFEST-SHA256.md` radi provere granice dokaza i integriteta transporta.

QA tabele su obavezni test zahtevi, ne unapred proglašeni rezultati. `SPEC_CANDIDATE` na modulu označava normativnu specifikaciju; `IMPLEMENTED` se sme tvrditi samo uz repo commit, migration head i stvarno izvršene testove.

## 3. Autoritet kada se tekstovi dodiruju

1. aktivni DCR za eksplicitno supersedovanu odluku;
2. M00 za zajednički ugovor i granice;
3. owner modul za entitet, lifecycle, komandu i poslovnu grešku;
4. M05 za permission/policy binding;
5. M03 za tenant context/izolaciju;
6. M07 ili drugi owner za subject guard;
7. M21 za transport, audit/job/operativnu semantiku;
8. M19/M28 samo za UI composition i presentation, nikad kao novi business master.

Neslaganje sa stvarnim repoom nije dozvola za tihu promenu kanona. Evidentira se kao `CHALLENGE_NOT_APPLIED` sa tačnim dokazom i nastavlja se sve nezavisno.

## 4. Nezaobilazne granice

- Jedna škola je jedan H0 security tenant; Organization, lokacija, hala ili prikazni workspace nisu authorization domen.
- `Person`, `UserAccount`, school membership, role, guardian relation i payer relation ostaju odvojeni autoriteti. Dete nema nalog u H0/M28 Basic.
- Pristup je invite-only; email/telefon nikad nisu automatski identity/person/guardian linking ključ.
- SaaS naplata SOKOLA proizvoda prema klijentu pripada M04. Školske obaveze/uplate pripadaju M12. Budući venue-rental/event-only proizvodi koriste odvojene product/workspace/authorization ugovore i ne aktiviraju skrivenu naplatu.
- M11 attendance je jedini H0 offline business write. Privatni mySOKOLA podaci, finansije, dokumenti, consent i event registracije zahtevaju mrežu i server receipt.
- M28 nema novi child/finance/document/event master, nema cross-school privatnu agregaciju i ostaje OFF bez entitlement+pilot+flag+permission+basis guardova.
- Nema big-bang rewrite-a, paralelnog auth/tenant/RBAC/finance sistema, lažnog PASS-a, ličnih podataka u telemetry-ju ili tajni u paketu.

## 5. Završni dokaz programera

Implementaciona predaja mora sadržati: popunjen repo baseline; klasifikaciju `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT|VERIFY_IN_REPO`; promenjene fajlove; migracije i rollback/forward-recovery; stvarne komande i exit kodove; passed/failed/skipped rezultate; tenant/security/PII dokaz; otvorene `CHALLENGE_NOT_APPLIED` stavke. Očekivani format je detaljno propisan u M21 handover checklist-i.
