---
tip: programmer-candidate-validation-evidence
status: DOCUMENTATION_VALIDATED_CODE_UNVERIFIED
scope: [M00-M21, M28]
datum: 2026-09-16
revizija: "1.0"
code-status: CODE_REPOSITORY_UNVERIFIED
---

# SOKOLA OS v5.7 — dokaz validacije dokumentacionog kandidata

## 1. Presuda i granica dokaza

**PRIHVAĆENO KAO DOKUMENTACIONI PROGRAMMER CANDIDATE.** U definisanom M00–M21 + M28 obuhvatu nije ostao detektovan dokumentacioni blocker, ciklična schema/read zavisnost, neusklađen QA brojač, polomljen interni link, duplikat aktivnog owner ugovora, nepoznat job/screen/permission ugovor niti aktivna kanonska kontradikcija obuhvaćena proverama ispod.

Ova presuda nije `IMPLEMENTED`, `CODE_COMPLETE`, production/pilot `GO` niti dokaz da postojeći brownfield repo već zadovoljava ugovore. Kod, šema, migracioni head, infrastruktura i izvršni testovi ostaju `CODE_REPOSITORY_UNVERIFIED` dok implementacioni agent ne popuni `CURRENT-CODE-BASELINE.md` dokazima iz stvarnog repozitorijuma.

## 2. Tačan obuhvat kandidata

| Stavka | Kanonski broj | Napomena |
|---|---:|---|
| Aktivni DCR-ovi | 6 | Samo odluke potrebne za ovaj kandidat. |
| M00 ugovori | 4 | Scope, arhitektura/zavisnosti, acceptance/predaja i katalog ekrana. |
| Aktivni module master ugovori | 22 | Tačno M01–M21 i M28; jedan master po modulu. |
| QA/traceability dokumenti | 22 | Jedan po aktivnom modulu. |
| Izvršni QA scenariji | 2.050 | Kontigvni ID-jevi bez duplikata i praznina unutar modula. |
| H0 UI površine | 42 | Tačno A01–A03, X01–X04, O01–O07, M01–M15, T01–T05 i P01–P08. |
| Published job definicije | 40 | 39 H0 + jedna M28 definicija, default-disabled. |
| Sadržajni Markdown dokumenti | 72 | Broj uključuje ovaj dokaz, ne uključuje transportni manifest. |
| Finalni Markdown fajlovi | 73 | 72 sadržajna dokumenta + `MANIFEST-SHA256.md`. |

M22–M27 i M29–M34 nisu implementacioni obuhvat ovog kandidata. M28 je H1 pre-pilot capability i ostaje `DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST`; ne ulazi neprimetno u H0 acceptance.

## 3. Deset završenih kontrolnih slojeva

| Sloj | Provereno | Deterministički rezultat |
|---:|---|---|
| 1 | Kanonski autoritet, owner granice, DCR/M00/module prioritet | Jedan aktivni owner za svaki entitet/komandu; nema paralelnog source of truth-a. |
| 2 | `schema-zavisnosti` i `read-portovi` kao odvojeni usmereni grafovi | Oba grafa su aciklična; svi target moduli postoje; owner consumer indeksi pokrivaju aktivne read/event potrošače. |
| 3 | Entiteti, conditional polja, FK/UNIQUE/CHECK očekivanja, novac i vreme | Exact decimal + ISO valuta, bez float/minor-unit mastera; UTC instant + IANA zona; tenant-safe relacije i immutable/append-only slojevi su eksplicitni. |
| 4 | M01/M03/M05/M07 guard pipeline, safe-404, child/PII i support pristup | Server-side fail-closed autorizacija je obavezna za request, job, cache, storage, export i realtime; UI nije security kontrola. |
| 5 | State machine, error katalog, command/query granice i API ishod | Dozvoljeni prelazi i terminalna stanja su zatvoreni; jedna greška nema različite HTTP mape; kritični write čeka server receipt. |
| 6 | Idempotency, expected version, DB lock redosled, concurrency i transaction atomicity | Retry ne pravi drugi poslovni efekat; partial write je zabranjen; paralelni i fault-injection scenariji postoje u QA. |
| 7 | Outbox/inbox, producer stream, dedupe, job lease/fencing i cleanup | Tačno 40 allow-listed job ključeva; stale worker ne objavljuje rezultat; PII/raw credential ne ulazi u događaj, log ili dead-letter. |
| 8 | Manager, coach/instructor i guardian/payer UX, 42 površine i „tri klika” | Quick flow ima eksplicitno početno stanje; pravna, finansijska i sigurnosna potvrda se ne preskače; jedna poslovna namera koristi jedan application endpoint. |
| 9 | QA sledljivost, brownfield klasifikacija, migracija, rollback/forward-recovery i handover | Svaki modul ima kontigvni acceptance skup; Markdown scenario nije proglašen izvršenim testom; repo dokaz je obavezan. |
| 10 | Sanitizacija transporta | Nema ličnih imena saradnika, tajni, privatne prepiske, istorijskih delta/recovery paketa, supersedovanih dokumenata ili lažne implementacione tvrdnje. |

## 4. Posebno zaključane visokorizične tačke

- M04 komercijalni obračun koristi exact decimal. Popust ima eksplicitan target i zatvorenu formulu; hash ugovornog override-a nije sam izvršna cena. Agreement transition job je platform coordinator sa agreement shard-om, uskom system capability i fencing dokazom.
- M12 svaki `ConfirmBillingRun` zahteva svež step-up bez tenant praga. Svaka ručna korekcija porodičnog kredita zahteva drugog ovlašćenog aktera i jednokratno, hash-bound odobrenje; step-up vreme dolazi samo iz server-side M01 context-a.
- M18 ne prikazuje pretpostavljen broj: obavezni source gap daje `PARTIAL` ili `UNAVAILABLE`; recorded/effective cutoff, source versions, M11/M16 razdvajanje i finansijski slojevi ostaju dokazivi.
- M20 issue report nastaje asinhrono, iz stabilnog source hash-a, u privatnom encrypted objektu. Promenjen source završava report kao terminalni FAILED bez objekta; download je kratkotrajan i ponovo autorizovan po range-u.
- M21 katalog ima tačno 40 definicija, uključujući M04 agreement transition i M20 issue-report generator. M28 job je jedini default-disabled H1 red.
- M28 koristi postojeće P01–P08 površine i owner portove; ne postaje child, finance, document, consent ili event master i ne daje cross-school private response.

## 5. Rezultat automatizovane dokumentacione validacije

Strukturna validacija je završena sa `pass=true` i nulom nalaza u svim kategorijama:

- UTF-8 decode i zabranjeni control/BiDi/zero-width/soft-hyphen znakovi;
- YAML frontmatter;
- duplicate headings;
- duplicate ili nekontigvni QA ID-jevi;
- polomljeni i dvosmisleni interni linkovi;
- Markdown tabele;
- mešani latinično-ćirilični runtime tokeni;
- lična imena saradnika.

Semantička validacija je završena sa `pass=true` i nulom nalaza u svim kategorijama:

- tačan skup module master/QA dokumenata;
- schema/read dependency ciklusi i consumer indeksi;
- job katalog, permission registry, error katalog i screen katalog;
- kvalitet izvršnih QA scenarija;
- kanonske invarijante M04, M08–M21 i M28;
- sanitizacija programmer candidate-a.

Transportni SHA-256 manifest se generiše tek posle finalizacije svih sadržajnih fajlova. Integritet ZIP-a se zatim proverava ekstrakcijom u čist direktorijum, ponovnim pokretanjem oba validaciona sloja i poređenjem svakog payload hash-a sa manifestom.

## 6. Obavezna implementaciona verifikacija

Dokumentacioni PASS postaje implementacioni dokaz samo ako stvarni repo isporuči sve sledeće:

1. popunjen baseline sa commit SHA i migration head-om;
2. `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT|VERIFY_IN_REPO` mapu sa putanjama;
3. backward-safe migracije, reconciliation i rollback ili forward-recovery;
4. stvarne build/lint/typecheck/test komande sa exit kodovima;
5. svih primenljivih 2.050 scenarija kao izvršne testove ili jednoznačno mapirane test case-ove bez preskočenog CRITICAL testa;
6. cross-tenant, child-data, concurrency, idempotency, storage, event/job, backup/restore i browser/PWA dokaz;
7. listu eventualnih `CHALLENGE_NOT_APPLIED` nalaza bez tihog menjanja kanona.

Do tada je jedina ispravna oznaka: `DOCUMENTATION_VALIDATED_CODE_UNVERIFIED`.
