---
modul-id: M20
tip: normativni-import-schema
status: SPEC_CANDIDATE
schema-key: SOKOLA_CHILD_GUARDIAN_ENROLLMENT
schema-version: 1
import-namespace-key: CHILD_GUARDIAN_ENROLLMENT_V1
formats: [CSV, XLSX]
datum: 2026-09-09
---

# M20 — Zvanični import schema v1

## 1. Obuhvat i autoritet

Ovaj dokument je jedini H0 ugovor kolona za `CHILD_GUARDIAN_ENROLLMENT` import. Jedan data red predstavlja jednu atomsku nameru: kreirati ili dokazivo povezati dete i jednog staratelja, aktivirati verifikovanu guardian vezu i primarni kontakt, pa kreirati jedan enrollment u već postojeću grupu. Red ne kreira UserAccount, pozivnicu, program, grupu, lokaciju, finansijski zapis, dokument ili zdravstveni podatak.

CSV i XLSX moraju proizvesti isti kanonski payload i `candidate_hash`. Zvanični template ima tačno 16 obaveznih kolona ispod na pozicijama 1–16 i tim redosledom. Ulaz mora imati svih 16; opciona source kolona sme postojati samo posle kolone 16, mora imati jedinstven header i ovlašćeni actor je eksplicitno mapira na `IGNORE` nakon što je sistem klasifikuje kao neosetljivu. Dodatna kolona ne ulazi u canonical payload/hash. Kolona sa zdravljem, nacionalnim ID-em, finansijama, dokumentom, slobodnom beleškom ili nepoznatom/binarno nečitljivom vrednošću ne može se ignorisanjem provući: ceo fajl dobija `IMPORT_SCHEMA_UNSUPPORTED`.

## 2. Tačan header i polja

| # | Header / target key | Tip i granica | Obavezno | Kanonsko pravilo |
|---:|---|---|---:|---|
| 1 | `import_row_key` | ASCII/Unicode text 1..128 | DA | Osetljiv ulazni school-local stabilan logical-row key; NFKC + outer trim; case-sensitive; bez control/BiDi/zero-width/soft-hyphen znakova. Posle parsera se čuva samo envelope-encrypted i kao tenant-keyed domain-separated HMAC digest; nema plaintext DB/index/log/event polja. |
| 2 | `child_external_reference` | text 1..64 | DA | Stabilna school-local referenca deteta; puni M06 `SchoolPersonProfile.local_person_code`; NFKC + outer trim, case-sensitive; exact candidate basis, nikad globalni identitet. |
| 3 | `child_first_name` | Unicode text 1..100 | DA | NFKC + outer trim + internal whitespace collapse; originalni case/pismo se čuvaju; bez HTML/control/BiDi/zero-width. |
| 4 | `child_last_name` | Unicode text 1..100 | DA | Isto kao `child_first_name`. |
| 5 | `child_birth_date` | LocalDate | NE | CSV: isključivo `YYYY-MM-DD`; XLSX: ISO tekst ili prava date ćelija bez formule, konvertovana bez timezone-a; nema locale guessing-a. Prazno znači nepoznato. |
| 6 | `guardian_external_reference` | text 1..64 | DA | Stabilna school-local referenca odrasle osobe i puni M06 `SchoolPersonProfile.local_person_code`; ista normalizacija i case pravilo kao child reference. |
| 7 | `guardian_first_name` | Unicode text 1..100 | DA | Kao child name; nije auto-link ključ. |
| 8 | `guardian_last_name` | Unicode text 1..100 | DA | Kao child name; nije auto-link ključ. |
| 9 | `guardian_email` | email text 3..254 | NE | NFKC + outer trim; validacija syntax-a; čuva se enkriptovano kao M06 kontakt kandidat. Nikad auth/identity/auto-link ključ i ne šalje poziv. |
| 10 | `guardian_phone` | E.164 text | NE | `+` i 8..15 cifara posle normalizacije; enkriptovan M06 kontakt kandidat; nije auto-link ključ. |
| 11 | `guardian_relationship_kind` | enum | DA | Tačno `PARENT`, `LEGAL_GUARDIAN`, `AUTHORIZED_CAREGIVER` ili `OTHER_VERIFIED`. |
| 12 | `guardian_is_primary_contact` | boolean | DA | Schema v1 prihvata isključivo `TRUE`; CSV literal `TRUE`, XLSX boolean TRUE. Jedan importovani staratelj je primarni kontakt tog reda. |
| 13 | `program_code` | English ASCII `Code64` | DA | Exact M08 `Program.code` iste škole; NFKC+outer trim, bez case promene ili fuzzy match-a; program mora biti ACTIVE. |
| 14 | `group_code` | English ASCII `Code64` | DA | Exact M09 `Group.code` iste škole; mora pripadati navedenom programu i biti ACTIVE. |
| 15 | `enrollment_starts_on` | LocalDate | DA | Kao datum; poslovni datum škole. |
| 16 | `enrollment_ends_on` | LocalDate | NE | Prazno = otvoren kraj; kada postoji mora biti strogo posle `enrollment_starts_on`. |

Empty string posle outer trim-a se tretira kao null samo za opciono polje. Za required polje je `IMPORT_ROW_INVALID`. Literal `NULL`, `N/A`, `-` i lokalizovane varijante nisu null i odbijaju se ako ne zadovolje tip. Header-i su English ASCII i case-sensitive; BOM je dozvoljen samo pre prvog CSV header-a.

## 3. Format ugovor

### 3.1 CSV

- encoding je UTF-8, sa opcionim jednim BOM-om;
- line ending može biti LF ili CRLF i normalizuje se u LF pre canonical content HMAC-a;
- delimiter je jedan od comma, semicolon ili tab i mora biti isti u celom fajlu; parser proba sva tri nad punim header redom po quoting pravilima i tačno jedan kandidat mora proizvesti 16 obaveznih header-a na pozicijama 1–16 plus eventualne jedinstvene dodatne header-e posle njih; nula ili više od jednog validnog kandidata daje `IMPORT_SCHEMA_UNSUPPORTED` bez nagađanja;
- RFC 4180 quoting semantika važi za comma/semicolon, a tab format koristi isto double-quote escaping pravilo;
- header je tačno jedan red; blank data redovi se odbacuju pre `row_count`, ali red sa delimiterima i praznim required vrednostima nije blank;
- formula-like tekst koji počinje `=`, `-` ili `@` je nevalidan za Code/date/boolean/email/phone. Vodeći `+` je za phone dozvoljen isključivo ako cela normalizovana vrednost odgovara E.164 obrascu `^\+[1-9][0-9]{7,14}$`; za sva druga polja ostaje formula-risk pravilo. Svaka vrednost koja bi pri CSV/rejected-report izvozu mogla biti protumačena kao formula bezbedno se prefiksuje apostrofom, uključujući validan prikaz telefona, bez menjanja internog kanonskog payload-a.

### 3.2 XLSX

- tačno jedan vidljiv worksheet naziva `SOKOLA_IMPORT`;
- nema hidden/very-hidden sheet-a, macro/VBA, formule, named external reference-a, external link-a, embedded object-a, pivot cache-a, data connection-a ili password zaštite;
- red 1 je header, redovi 2..5001 su podaci; nema merged cell-a;
- parser prihvata string, boolean i date/numeric cell samo prema ciljnom tipu; nikad ne koristi cached result formule;
- workbook `date1904` zastavica se poštuje pri pretvaranju prave date ćelije, a rezultat mora biti validan LocalDate; Excel pseudo-datum `1900-02-29`, serijski broj koji zavisi od pogrešnog 1900 leap-year modela i datum čije poreklo/epoch nije jednoznačno dokazano se odbijaju. Vreme u date-time ćeliji mora biti 00:00:00, inače red je nevalidan.

## 4. Kanonski payload i hash

Kanonski payload je JSON objekat sa tačno 16 key-eva abecednim redom, UTF-8, bez insignificant whitespace-a. Opcione prazne vrednosti su JSON `null`; datumi su ISO string, boolean je JSON boolean, ostalo string. Brojevi redova, file name, format, worksheet metadata i ciphertext nonce ne ulaze u payload.

`candidate_hash = HMAC-SHA-256(tenant_import_key[key_version], "SOKOLA-M20-CANDIDATE-V1\n" || lower(school_uuid) || "\n" || schema_key || ":" || schema_version || "\n" || canonical_json_utf8)`.

Čuva se i `candidate_hash_key_version`; sirovi SHA-256 nad imenima, datumom rođenja ili drugim niskoentropijskim PII je zabranjen zbog offline dictionary napada. HMAC ključ je tenant-isolated, nije exportovan/logovan i stara verzija ostaje dostupna samo kroz rok potreban za validaciju postojećeg business receipt-a. Pri poređenju sa postojećim receipt-om novi payload se hashira njegovom zabeleženom key verzijom; rotacija ne pretvara identičan red u konflikt niti dozvoljava cross-tenant poređenje. CSV i XLSX fixture sa istim logičkim vrednostima u istoj školi/schema/key verziji moraju dati byte-identičan canonical JSON i isti hash; isti payload druge škole mora dati različit hash.

## 5. Duplicate i owner semantika

1. `child_external_reference` i `guardian_external_reference` mapiraju se tačno na M06 `SchoolPersonProfile.local_person_code` i prvo se traže isključivo unutar aktivne škole. Email, telefon i imena ne potvrđuju target.
2. Ako exact referenca ne postoji, M06 kreira Person + odgovarajući SchoolMembership/profile u istoj row transakciji. Ako postoji jedan exact target i imena/datum nisu u konfliktu, koristi se LINKED putanja; razlika se ne koristi kao tihi update.
3. Više targeta, possible match ili konflikt field-a daje `RESOLUTION_REQUIRED`; school actor bira dokazivi target ili ispravlja izvorni red. M20 ne merge-uje Person.
4. Confirmation uključuje izjavu `GUARDIAN_RELATION_VERIFIED_BY_SCHOOL` sa actorom, vremenom i policy version `M20_IMPORT_V1`. Bez nje nema execute-a.
5. M07 u istoj transakciji kreira ACTIVE `GuardianChildLink`, jedan `RelationshipVerificationRecord.verification_method=MIGRATION_VERIFIED` i ACTIVE `PrimaryGuardianContactDesignation`. Ako već postoji ACTIVE primary za isti guardian-child link, koristi se postojeći designation; ako pripada drugom linku, red se blokira. Nema tihog supersede-a.
6. M09 kreira DRAFT pa ACTIVE enrollment kroz svoje tranzicione ugovore samo ako nema preklapajućeg upisa i capacity pravila prolaze. Import nema capacity override.
7. Actor mora imati `school.import.execute`, `school.people.manage`, `school.memberships.manage`, `school.guardians.manage`, `school.guardians.primary_contact.manage` i `school.groups.enrollments.manage`; nedostajući owner permission blokira ceo execute pre prvog reda.

## 6. Verzija i kompatibilnost

Schema v1 se nikad ne menja nakon publish-a. Nova/izmenjena kolona, enum, normalizacija, requiredness ili hash algoritam zahteva schema v2 i novi template hash. Parser mora eksplicitno odbiti nepoznatu buduću verziju; ne radi best-effort mapiranje. Retired schema može samo prikazati istorijski batch i receipt; novi upload nije dozvoljen.
