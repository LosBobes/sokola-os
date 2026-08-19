/*
 * Enum → Serbian label maps, in one place.
 *
 * These are the words a school reads. Several screens show the same enum (a
 * location's kind appears in Raspored, in Grupe and in the structure setup),
 * and letting each screen invent its own wording is how "sala" and "lokacija"
 * came to mean the same thing in different corners of the app.
 */

import type {
  EventType,
  GroupMemberRole,
  LocationKind,
  OrgMemberType,
  SessionStatus,
} from "../api/types";

/**
 * The kinds of place activities actually happen in. A hall is one of them, not
 * the category, which is why the filters read "Sve lokacije" and not "Sve sale".
 */
export const LOCATION_KIND_LABEL: Record<LocationKind, string> = {
  SPORTS_HALL: "sala / sportska hala",
  FIELD: "teren / balon",
  KINDERGARTEN: "vrtić",
  SCHOOL: "škola",
  THEATRE: "pozorište",
  OUTDOOR: "otvoreno",
  ONLINE: "online",
  OTHER: "drugo",
};

export const SESSION_STATUS_LABEL: Record<SessionStatus, string> = {
  SCHEDULED: "Zakazano",
  CANCELLED: "Otkazano",
  COMPLETED: "Završeno",
};

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  TRAINING_CAMP: "Kamp",
  PREPARATION: "Pripreme",
  COMPETITION: "Takmičenje",
  PERFORMANCE: "Nastup",
  WORKSHOP: "Radionica",
  SOCIAL: "Druženje",
  OTHER: "Ostalo",
};

/**
 * How a person is attached to a group. Only "polaznik" is rostered for
 * attendance and billed, everyone else is staff running the group.
 */
export const GROUP_MEMBER_ROLE_LABEL: Record<GroupMemberRole, string> = {
  MEMBER: "Polaznik",
  TRAINER: "Trener / nastavnik",
  ASSISTANT: "Asistent",
  OTHER_STAFF: "Drugo stručno lice",
};

/** What a person is to the school. Only ATTENDEE counts as an active member. */
export const ORG_MEMBER_TYPE_LABEL: Record<OrgMemberType, string> = {
  ATTENDEE: "Polaznik",
  STAFF: "Trener / osoblje",
  GUARDIAN: "Roditelj / staratelj",
  CONTACT: "Kontakt osoba",
};

/** The one-line explanation each member type gets where it is chosen. */
export const ORG_MEMBER_TYPE_HINT: Record<OrgMemberType, string> = {
  ATTENDEE: "Ulazi u evidenciju prisustva, obračun članarine i broj aktivnih članova.",
  STAFF: "Vodi grupe i termine. Ne plaća članarinu i ne broji se kao član.",
  GUARDIAN: "Prati svoje dete. Ne plaća članarinu za sebe i ne broji se kao član.",
  CONTACT: "Samo kontakt podatak, bez učešća u aktivnostima.",
};


/*
 * IANA timezone id → the city's name in Serbian.
 *
 * "Europe/Belgrade" is an identifier, not a thing to show a person: it is
 * English, it carries a slash, and the region half is noise. Only the zones a
 * school here would realistically pick are listed; anything else falls back to
 * the id's last segment with its underscores removed, which is still better
 * than printing the whole identifier.
 */
const TIMEZONE_CITY: Record<string, string> = {
  "Europe/Belgrade": "Beograd",
  "Europe/Zagreb": "Zagreb",
  "Europe/Sarajevo": "Sarajevo",
  "Europe/Podgorica": "Podgorica",
  "Europe/Skopje": "Skoplje",
  "Europe/Ljubljana": "Ljubljana",
  "Europe/Vienna": "Beč",
  "Europe/Budapest": "Budimpešta",
  "Europe/Berlin": "Berlin",
  "Europe/Zurich": "Cirih",
};

export function timezoneCity(timezone: string | null | undefined): string {
  if (!timezone) return "";
  return TIMEZONE_CITY[timezone] ?? (timezone.split("/").pop() ?? "").replace(/_/g, " ");
}
