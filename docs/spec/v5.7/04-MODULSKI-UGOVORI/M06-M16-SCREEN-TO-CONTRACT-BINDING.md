---
tip: screen-to-contract-binding
obim: M06-M16
status: SPEC_CANDIDATE
datum: 2026-09-15
exclude-from-programmer-candidate-until-complete: false
---

# M06–M16 — Screen-to-contract binding

Ovo je jedina aktivna putanja za M06–M16 screen binding. Sve veze su normativni UI ugovor, ali njihovo postojanje u stvarnom kodu ostaje `DESIGNED_COVERAGE/REPO_UNVERIFIED`.

## Kanonska pravila vezivanja

1. UI oznaka nije modul ID i ne menja vlasništvo entiteta.
2. Svaka korisnička mutacija mora se vezati za tačan command ID, permission, tenant/resource/subject guard, očekivanu verziju, idempotency i propisani success/error oblik.
3. Svaki query mora definisati tenant filtriranje pre count/sort/page i minimalnu PII projekciju.
4. Offline je default `DENY`; samo M11 attendance capture sme koristiti queue, uz `PENDING_SYNC|SYNCED|SYNC_FAILED` i serversku reautorizaciju.
5. Optimistic prikaz ne označava finansijsku, dokumentnu, pravnu ili drugu kritičnu mutaciju kao konačno uspešnu pre server receipt-a.
6. Neutralni runtime termini su `PARTICIPANT`, `ParticipantProfile`, `INSTRUCTOR` i M16 `origin_type=SCHOOL_ORGANIZED|EXTERNAL_ORGANIZER`.
7. M13 ručna komunikacija i M14 automatska notifikacija ostaju odvojene; izvorni moduli emituju outbox event i ne pozivaju M14 komandu.
8. PAYER prikaz je finance-only i ne otkriva child profil, prisustvo, dokument, zdravlje ili komunikaciju bez nezavisnog guardian prava.

## Stanje izrade

| Opseg | Status | Šta završava status |
|---|---|---|
| M06–M07 | `DESIGNED_COVERAGE/REPO_UNVERIFIED` | Veze su definisane ispod; repo contract/security testovi ih tek dokazuju. |
| M08–M12 | `DESIGNED_COVERAGE/REPO_UNVERIFIED` | Veze su definisane ispod; repo contract/security testovi ih tek dokazuju. |
| M13–M16 | `DESIGNED_COVERAGE/REPO_UNVERIFIED` | Veze su definisane ispod; repo contract/security testovi ih tek dokazuju. |

## M06–M16 obavezne funkcionalne veze

Nazivi površina su stabilne funkcionalne oznake, ne tvrdnja o ruti ili frameworku. `Online` znači da aktivna mreža i server receipt moraju postojati. `Offline attendance` znači jedini dozvoljeni M11 queue.

| Površina | Query/komanda | Permission + guard | UX/offline ugovor |
|---|---|---|---|
| Ljudi i school membership | List/Get/Create/Update Person profile; Create/Activate/Suspend/Terminate SchoolMembership | `school.people.basic.view`, `school.people.manage`, `school.memberships.manage`; field-level i last-owner guard | Online write; Person nije nalog ni rola; list filter pre count/page; child minimum po subjectu. |
| Participant/staff profil | Get/Update neutralni ParticipantProfile/StaffProfile; safety reveal samo kada je dozvoljen | `school.people.basic.view`, `school.participant.safety.view`, odgovarajući manage ključ; assignment/purpose guard | Neutralna terminologija; safety read posebno auditovan i nikad u generic cache/search-u. |
| Porodica i staratelji | List/Get Family/links; request/approve/reject/revoke guardian; set primary contact | `school.families.view`, `school.families.manage`, `school.guardians.view`, `school.guardians.manage`, `school.guardians.primary_contact.manage`; current M06 types, M07 subject i distinct-approver guard | Online; email/ime nije identity/link dokaz; jedan guardian ne menja odluku drugog. |
| Platioci | List/Get/request/approve/revoke payer; set primary payer | `school.payers.view`, `school.payers.manage`, `school.payers.primary.manage`; finance-only M07 basis | Online; payer link ne daje profil, raspored, prisustvo, dokument ili komunikaciju. |
| Struktura škole | List/Get Branch, Program, Location, Space; create/update/lifecycle | `school.structure.view`, `school.structure.manage`; School tenant | Online; archive blocker se prikazuje bez tihog cascade-a. |
| Online lokacija | Set/Rotate/Revoke/Get access za konkretan occurrence/event | `school.online_access.view`, `school.online_access.manage`; step-up za manage + occurrence/event subject | URI nikad u list/search; online only. |
| Zauzeće prostora | Confirm/Cancel manual hold; conflict detail samo svoje škole | `school.occupancy.manage`; source/resource guard | Online; 409 prikazuje konflikt bez child/other-tenant podatka. |
| Grupe | List/Get/Create/Update/Activate/Deactivate/Archive Group | `school.groups.view`, `school.groups.manage` | Online; price/schedule nije Group polje. |
| Upisi | As-of roster; Create/Activate/Suspend/Resume/Terminate/Transfer | `school.groups.enrollments.view`, `school.groups.enrollments.manage`; participant/assignment guard | Online; capacity/transfer server-confirmed, bez hidden waitlist-a. |
| Osoblje grupe | List as-of, Assign/End | `school.groups.staff_assignments.manage` | Online; assignment ne prikazuje niti menja RBAC. |
| Kalendar | Calendar range/Get occurrence | `school.schedule.view`; assigned Group ili linked child scope | Read može cache uz authorization version; range/page limit. |
| Uređivanje rasporeda | Create/Activate/Pause/Resume/End Series; edit/cancel/reactivate occurrence | `school.schedule.manage` | Online; eksplicitan scope THIS/THIS_AND_FUTURE/ENTIRE; hard conflict nema override. |
| Današnje prisustvo | GetTodayAttendanceLaunch/Open session | `school.attendance.view/record`; active staff assignment | Jedan click sa home površine; server roster je UNRECORDED. |
| Evidencija prisustva | Proposed all-present, mark exceptions, summary, Confirm/Correct | `school.attendance.record`; roster/record version guard | Najviše 2 osnovne interakcije bez izuzetka/3 sa jednim; explicit confirm; offline queue dozvoljen. |
| Sync problemi | Pregled PENDING/SYNCED/SYNC_FAILED, conflict compare, explicit retry | isti M11 subject + novi lease/base | Nema last-write-wins; logout/revoke/switch briše lokalne child podatke. |
| Cenovnik | List/Get/Create/Publish/Retire FeeRuleVersion | `finance.view`, `finance.fee_rules.manage` | Online; objavljena cena/valuta/uslovi vidljivi pre obaveze. |
| Obračun | PrepareBillingRun preview / ConfirmBillingRun | `finance.billing.preview/confirm` | Preview jasno „nije knjiženo“; confirm online, stale hash all-or-nothing. |
| Obaveze | List/Get/Cancel; payer/guardian projection | `finance.view`, `finance.obligations.manage`; M07 payer subject | Iznos nikad optimistic PAID; drugi payer/account skriven. |
| Uplate | Payment instruction, cash/bank record, reconciliation resolve | granularni `finance.payments.*` | IPS QR je instrukcija; PAID tek server-confirmed payment/allocation. |
| Porodični kredit | Balance/history, Apply, admin Correct | `finance.view`, `finance.credit.apply/correct`; FamilyBillingAccount guard | Auto-apply default OFF; ledger se ne prepisuje. |
| Refund review | Open/Decide/ConfirmExternal | `finance.refund_reviews.decide`, `finance.refunds.confirm_external` | Payer vidi neutralan status; refund nikad automatski. |
| Ručna komunikacija | Draft/Edit/Preview/Publish/Withdraw/Correct; inbox/read | `school.communications.compose`, `school.communications.publish`, `school.communications.withdraw`, `school.communications.view`, `school.communications.delivery_view`; audience + current subject guard | Online; preview hash mora biti svež; email je generički signal bez sadržaja/priloga. |
| Sistemske notifikacije | Notification list/read; staff Attention list/resolve | `school.notifications.view_own`, `school.notifications.mark_read_own`, `school.notification_delivery.view`, `school.attention.view`, `school.attention.resolve`; recipient/current basis | Online; izvorni modul samo outbox; attendance nema mapping; push default OFF. |
| Dokumenti | List/Get/Upload/Publish/Download/Accept/Decline | `school.documents.view`, `school.documents.manage`, `school.documents.publish`, `school.documents.download`, `school.documents.accept`; typed access + current subject + one-time ticket | Online; nema javnog URL-a/offline fajla; upload nije AVAILABLE pre validacije i scan-a. |
| Događaji Light | List/Get/Create/Publish/Cancel/Register/Attendance | `school.events.view`, `school.events.manage`, `school.events.publish`, `school.events.register_child`, `school.events.registration_manage`, `school.events.attendance_record`, `school.events.attendance_correct`; origin-specific state/subject/capacity guard | Online; fee create/cancel spaja neutralni M16+M12 coordinator; whole-event cancel odmah aktivira finance barrier; EVENT dokument validira M15; nema implicitne reaktivacije. |

Svaka greška koristi namespaced kod vlasničkog modula. Safe 404 se prikazuje kao neutralno „nije dostupno“, bez otkrivanja da objekat/dete/uplata postoji. UI ne prevodi `PENDING_SYNC` u „sačuvano“ niti payment instruction u „plaćeno“.

## Ključni tokovi i granica od tri primarne interakcije

„Tri klika” znači najviše tri primarne korisničke interakcije od odgovarajuće početne površine do serveru poslate namere; unos teksta, izbor iz više stvarno potrebnih stavki, step-up autentifikacija i rešavanje greške ne prikrivaju se radi veštačkog brojanja. Bezbednosna potvrda se ne uklanja da bi se ispunio cilj.

| Tok | Maksimalni standardni put | Backend ugovor koji sprečava frontend orkestraciju |
|---|---|---|
| Današnje prisustvo | Otvori današnji termin → označi izuzetak ako postoji → potvrdi; bez izuzetka dve interakcije | `GetTodayAttendanceLaunch` + jedan atomski `ConfirmAttendance`; frontend ne šalje N per-person komandi. |
| Prijava/otkazivanje deteta na događaj | Otvori događaj → izaberi dete samo kada ih ima više → potvrdi nameru | Jedan application endpoint poziva M16 owner port ili neutralni M16+M12 coordinator za naplativ događaj; frontend nikad uzastopno orkestrira registraciju/status pa finansiju. |
| Pregled finansija | Otvori Finansije → izaberi dete/porodični račun samo kada postoji više dozvoljenih obuhvata → otvori obavezu | Jedan subject-scoped summary query vraća saldo, dospele obaveze i dozvoljene sledeće akcije; detalj ne zahteva klijentsko spajanje nezaštićenih M07/M12 odgovora. |
| Objavljivanje pripremljene poruke | Otvori sačuvani nacrt → proveri recipient preview → potvrdi objavu | `PreviewRecipients` vraća hash, a jedan `PublishCommunication` atomski materijalizuje snapshot, delivery redove, audit, outbox i receipt. Pisanje sadržaja nije deo navigacionog brojača. |

Acceptance: automatizovani UI/contract test meri ove standardne putanje; mrežni poziv za konačnu poslovnu mutaciju je jedan, osim transparentnog step-up izazova. Test pada ako frontend radi per-row attendance upise, direktan M16→M12 lanac, klijentsko spajanje nefiltriranih finansijskih podataka ili publish bez svežeg recipient hash-a.

Pre programerske predaje svaka aktivna UI akcija mora imati tačno jednu normativnu backend vezu ili oznaku `UI_ONLY_NO_BUSINESS_MUTATION`; svaka javna business komanda mora imati najmanje jednu dozvoljenu površinu ili oznaku `INTERNAL_ONLY`. Nema siročadi i nema izmišljene tvrdnje da ekran već postoji u repou.
