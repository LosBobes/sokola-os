---
tip: qa-traceability
modul-id: M07
status: SPEC_CANDIDATE
revizija: "1.1"
datum: 2026-09-08
obavezni-scenariji: 52
---

# M07 — QA i traceability

Svi testovi koriste dve škole, kontrolisani clock i deterministične UUID-e. Svaki deny proverava nepromenjenu bazu, bez success audita/outbox-a i bez PII u telemetry-ju.

| ID | Scenario | Očekivano | Trag |
|---|---|---|---|
| `M07-QA-001` | CreateFamily u A. | Jedan ACTIVE red, version 1, receipt/audit/outbox. | §2.1, §7 |
| `M07-QA-002` | Actor A čita Family B poznatim ID-em. | 404 `M07_NOT_FOUND_SAFE`; isti response kao unknown. | §4, §6 |
| `M07-QA-003` | Ista Person je adult član dve Family u A. | Dozvoljeno; nema implicitnog deljenja podataka. | §2.2, §3.2 |
| `M07-QA-004` | Dete je dependent u dve porodice razvedenih roditelja. | Obe veze dozvoljene; svaka porodica vidi samo svoj scope. | §2.2, §3.2 |
| `M07-QA-005` | Dupli ACTIVE FamilyMembership istog prirodnog ključa. | 409 `M07_FAMILY_MEMBERSHIP_EXISTS`. | §2.2, §6 |
| `M07-QA-006` | End FamilyMembership bez reason/date. | 422; nema izmene. | §5.2 |
| `M07-QA-007` | Archive prazne Family. | ARCHIVED; terminalno. | §5.1 |
| `M07-QA-008` | Archive Family sa aktivnim članom/linkom/M12 obavezom. | 409 `M07_FAMILY_ARCHIVE_BLOCKED`; ništa nije zatvoreno. | §3.13, §6 |
| `M07-QA-009` | M12 blocker port nedostupan. | 503 `M07_DEPENDENCY_UNAVAILABLE`; fail-closed. | §3.13, §6 |
| `M07-QA-010` | Request guardian link sa validnim GUARDIAN/PARTICIPANT membership-ima. | PENDING_VERIFICATION; nema pristupa detetu. | §2.3, §5.3 |
| `M07-QA-011` | Guardian i child su ista Person. | 422 `M07_VALIDATION_FAILED`. | §2.3 |
| `M07-QA-012` | Guardian ima STAFF, ne GUARDIAN membership. | 422 `M07_MEMBERSHIP_TYPE_MISMATCH`. | §2.3, §6 |
| `M07-QA-013` | Child pripada B, context A. | 404 safe; nema linka. | §4 |
| `M07-QA-014` | Drugi open isti guardian-child prirodni ključ. | 409 `M07_RELATIONSHIP_EXISTS`. | §2.3 |
| `M07-QA-015` | Guardian sam potvrđuje svoju pending vezu. | 403 `M07_SELF_VERIFICATION_FORBIDDEN`. | §3.6 |
| `M07-QA-016` | School approver aktivira bez verification method/policy. | 422 `M07_RELATIONSHIP_VERIFICATION_REQUIRED`. | §2.4, §6 |
| `M07-QA-017` | School approver validno aktivira. | Link ACTIVE i tačno jedan immutable verification record u jednoj transakciji. | §2.3-2.4, §5.3 |
| `M07-QA-018` | Dva approver-a paralelno aktiviraju isti version. | Jedan uspe; drugi 409 `M07_STALE_VERSION`; jedan dokaz. | §3.1, §7 |
| `M07-QA-019` | Verification insert pada posle status update-a. | Cela transakcija rollback; link ostaje pending. | §3.5, §7 |
| `M07-QA-020` | Reject pending link bez reason-a. | 422; ostaje pending. | §5.3 |
| `M07-QA-021` | Re-activate REJECTED/REVOKED link. | 409 `M07_RELATIONSHIP_INVALID_TRANSITION`; nova provera koristi novi ID. | §5.3 |
| `M07-QA-022` | Dete ima tri ACTIVE guardian linka. | Dozvoljeno; prava se računaju odvojeno. | §3.3 |
| `M07-QA-023` | Postavi primarnog guardian-a. | Jedan ACTIVE designation; link ostaje ACTIVE. | §2.6, §5.4 |
| `M07-QA-024` | Paralelno postavljanje dva primarna. | Jedan konačni ACTIVE; drugi 409 `M07_PRIMARY_CONFLICT`. | §3.1, §7 |
| `M07-QA-025` | Zameni primarnog guardian-a. | Stari SUPERSEDED + novi ACTIVE atomski. | §5.4 |
| `M07-QA-026` | Primarni guardian link se opoziva. | Link i designation REVOKED u istoj transakciji; primarni može biti nula. | §3.10 |
| `M07-QA-027` | Primarni kontakt traži širi permission od drugog guardian-a. | Denied kao i drugi; primarnost nije authorization. | §3.8 |
| `M07-QA-028` | Guardian A čita kontakt guardian-a B. | 404 safe, osim posebno dozvoljenog school workflow-a koji vraća bezbednu projekciju. | §3.1, §4 |
| `M07-QA-029` | Request payer link za adult CONTACT membership + PARTICIPANT child u istoj Family. | PENDING_VERIFICATION; nema finansijskog prava pre activation-a. | §2.5 |
| `M07-QA-030` | Payer nije guardian, ali ima ACTIVE CONTACT membership. | Posle zasebne provere ACTIVE payer je dozvoljen; nastaje tipiziran immutable verification record. | §2.4–2.5, §3.7 |
| `M07-QA-031` | Payer i child nisu u istoj Family, bez sponsor dokaza. | 422 `M07_PAYER_BASIS_INVALID`. | §2.5, §6 |
| `M07-QA-032` | Sponsor verifier potvrdi eksternog payer-a. | ACTIVE `SPONSOR_VERIFIED`; nema guardian link-a. | §2.5 |
| `M07-QA-033` | Dete ima dva ACTIVE payer linka. | Dozvoljeno; M07 ne dodeljuje procente. | §3.3, §3.9 |
| `M07-QA-034` | Designate primary payer na pending/revoked link. | 409 `M07_PRIMARY_LINK_NOT_ACTIVE`. | §5.4, §6 |
| `M07-QA-035` | Replace primary payer. | Jedan ACTIVE; istorijski stari SUPERSEDED. | §5.4 |
| `M07-QA-036` | Payer-only actor čita child attendance/profile/document. | 404 `M07_NOT_FOUND_SAFE`; nema metadata/count hint-a. | §3.7, §4 |
| `M07-QA-037` | Payer-only actor poziva dozvoljenu M12 finansijsku projekciju. | M07 resolver vraća active payer link + `FINANCE_ONLY`; M12 radi svoj guard. | §7.2 |
| `M07-QA-038` | M06 guardian/child membership postane TERMINATED, consumer kasni. | Request-time resolver odmah vraća NOT_FOUND; stale access ne prolazi. | §3.12 |
| `M07-QA-039` | Revoke commit, novi request koristi stale cache. | 404 safe; autoritativna version provera. | §3.11, §4 |
| `M07-QA-040` | High-risk write počne pre revoke-a, commit posle. | 409 `M07_CONCURRENT_AUTHORIZATION_CHANGE`; nema business upisa. | §3.11 |
| `M07-QA-041` | Isti idempotency key+payload za activation retry. | Isti rezultat; jedan proof/audit/outbox. | §7 |
| `M07-QA-042` | Isti key, drugi relationship kind. | 409 `M07_IDEMPOTENCY_KEY_REUSED`. | §7 |
| `M07-QA-043` | Event/outbox se dostavi tri puta. | Consumer dedupe; M14 notifikacija najviše jednom po event/user/channel politici. | §7.3 |
| `M07-QA-044` | Log/audit/event skeniranje nakon svih tokova. | Nema imena, email-a, telefona, evidence sadržaja ili child payload-a; samo opaque ID/code/version. | §4, §7.3 |
| `M07-QA-045` | Klijent offline pokuša create/revoke/designate. | Operacija nije queued niti lokalno finalizovana; zahteva online server receipt. | §4, §8.9 |
| `M07-QA-046` | PAY-02 pokuša ACTIVE bez `RelationshipVerificationRecord` ili zapis pokazuje guardian link. | 422 `M07_RELATIONSHIP_VERIFICATION_REQUIRED`; payer link ostaje pending. | §2.4–2.5, §5.3 |
| `M07-QA-047` | PAY-02 validno aktivira payer vezu. | Payer link ACTIVE i tačno jedan `link_kind=PAYER_CHILD` immutable verification record u istoj transakciji. | §2.4–2.5, §5.3, §7 |
| `M07-QA-048` | Family/guardian/payer red škole A referencira membership škole B ili istog school ID-a ali druge Person. | Triple composite FK odbija direktan DB upis; API daje safe 404; nema relation/family existence hint-a. | §2.2–2.5, §4 |
| `M07-QA-049` | Payer ima samo STAFF membership, bez CONTACT/GUARDIAN membership-a. | 422 `M07_MEMBERSHIP_TYPE_MISMATCH`; nema pending link-a. | §2.5, §6 |
| `M07-QA-050` | Payer-ov CONTACT/GUARDIAN membership ili detetov PARTICIPANT membership koji referencira payer link postane TERMINATED dok consumer kasni. | Request-time payer resolver odmah daje NOT_FOUND; M05 PAYER grant je neefektivan; consumer zatvara link idempotentno. | §3.11–3.12, §4, §7.2 |
| `M07-QA-051` | Isti PAY-02 `request_id` i payload retry posle timeout-a, zatim isti key sa drugim verification method-om. | Prvi retry vraća isti ACTIVE rezultat i jedan dokaz; drugačiji payload daje 409 `M07_IDEMPOTENCY_KEY_REUSED`. | §7 |
| `M07-QA-052` | PAY-02 i PAY-04 paralelno koriste istu link version. | Tačno jedan commit; ako PAY-04 pobedi finalno je REVOKED bez activation dokaza, a ako PAY-02 pobedi finalno je ACTIVE sa tačno jednim dokazom; loser dobija 409 `M07_STALE_VERSION`. | §5.3, §7 |

## Seed podaci

- School A/B; dve Family u A; dete prisutno u obe; guardian G1/G2 i payer P bez guardian veze.
- Guardian/payer linkovi u svim statusima; dva candidate primarna; cross-tenant poznati ID-jevi.
- M06 membership ACTIVE/SUSPENDED/TERMINATED i M12 dependency adapter ready/unavailable.

## Izvršni minimum

Tagovi: `m07-unit`, `m07-db-constraints`, `m07-api`, `m07-tenant-negative`, `m07-subject-negative`, `m07-family-privacy`, `m07-payer-isolation`, `m07-idempotency`, `m07-concurrency`, `m07-outbox`, `m07-migration`. Pokrenuto 52, prošlo 52, preskočeno 0.
