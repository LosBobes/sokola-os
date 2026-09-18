/*
 * Hand-authored view of the API response shapes the web app consumes. The full
 * machine-generated types live in schema.d.ts (npm run gen:api); these are the
 * curated subset the screens use.
 */

export type RoleCode = "OWNER" | "MANAGER" | "ADMIN" | "TRAINER" | "PARENT" | "STUDENT";

export interface Context {
  role_assignment_id: string;
  school_id: string;
  school_name: string;
  role_code: RoleCode;
  scope_type: string;
  scope_ref_id: string | null;
}

export interface Me {
  person_id: string;
  display_name: string;
  identity_status: string;
  contexts: Context[];
}

export interface School {
  id: string;
  name: string;
  slug: string | null;
  type: string;
  timezone: string;
}

/** What kind of place a location is. Activities are not only held in halls. */
export type LocationKind =
  | "SPORTS_HALL"
  | "FIELD"
  | "KINDERGARTEN"
  | "SCHOOL"
  | "THEATRE"
  | "OUTDOOR"
  | "ONLINE"
  | "OTHER";

export interface LocationSummary {
  id: string;
  name: string;
  kind: LocationKind;
  address?: string | null;
}

export interface TenantPublic {
  school_id: string;
  name: string;
  slug: string;
}

export interface AuthConfig {
  google_enabled: boolean;
  password_enabled: boolean;
  dev_auth_enabled: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type PersonIdentityStatus = "PROVISIONAL" | "CLAIMED" | "VERIFIED" | "MERGED" | "ARCHIVED";

/**
 * What a person is to the school. Only ATTENDEE counts as an active member,
 * which is why the roster screens ask for it rather than defaulting silently.
 */
export type OrgMemberType = "ATTENDEE" | "STAFF" | "GUARDIAN" | "CONTACT";

export interface PersonSummary {
  id: string;
  display_name: string;
  identity_status: PersonIdentityStatus;
  member_type: OrgMemberType;
}

export interface Person {
  id: string;
  given_name: string;
  family_name: string;
  display_name: string;
  identity_status: PersonIdentityStatus;
}

export type PersonResponse = Person;

export interface Group {
  id: string;
  name: string;
  capacity_mode: "UNLIMITED" | "LIMITED";
  capacity: number | null;
  program_id?: string | null;
  location_id?: string | null;
  base_monthly_price?: string | null;
  /** Copied onto a new session for this group; overridable per occurrence. */
  default_trainer_person_id?: string | null;
  default_location_id?: string | null;
}

/** In what capacity a person is attached to a group. */
export type GroupMemberRole = "MEMBER" | "TRAINER" | "ASSISTANT" | "OTHER_STAFF";

export interface GroupMember {
  membership_id: string;
  person_id: string;
  display_name: string;
  role?: GroupMemberRole;
}

/* --- Membership (increment #6, merged to main) ------------------------ */

export type MembershipStatus = "ACTIVE" | "SUSPENDED" | "ENDED";

export interface MembershipResponse {
  id: string;
  person_id: string;
  status: MembershipStatus;
  local_member_code: string | null;
  admin_note: string | null;
}

/* --- Guardians ---------------------------------------------------------- */

export type GuardianRelationshipType = "PARENT" | "LEGAL_GUARDIAN" | "OTHER";
export type GuardianAccessStatus = "ACTIVE" | "SUSPENDED" | "REVOKED";

export interface GuardianContactResponse {
  guardian_person_id: string;
  display_name: string;
  relationship_type: GuardianRelationshipType;
  is_primary_contact: boolean;
  access_status: GuardianAccessStatus;
}

export type SessionStatus = "SCHEDULED" | "CANCELLED" | "COMPLETED";

export type SessionCancellationReasonCode =
  | "WEATHER"
  | "TRAINER_UNAVAILABLE"
  | "HOLIDAY"
  | "LOW_ATTENDANCE"
  | "OTHER";

export type SessionChangeReasonCode = "TIME_CHANGE" | "LOCATION_CHANGE" | "TRAINER_CHANGE" | "OTHER";

/** Calendar-style edit scope for a session that belongs to a series. */
export type SessionEditScope = "SINGLE" | "THIS_AND_FUTURE" | "ALL_FUTURE";

export interface SessionSummary {
  id: string;
  group_id: string;
  title: string | null;
  starts_at: string;
  ends_at: string;
  status: SessionStatus;
  trainer_person_id?: string | null;
  location_id?: string | null;
  series_id?: string | null;
  cancellation_reason?: SessionCancellationReasonCode | null;
}

export type SessionSeriesFrequency = "WEEKLY" | "BIWEEKLY" | "MONTHLY";

/** POST /schedule/series body: a recurrence rule ("svake srede u 18:00"). */
export interface SessionSeriesCreate {
  group_id: string;
  trainer_person_id?: string | null;
  location_id?: string | null;
  title: string;
  frequency?: SessionSeriesFrequency;
  /** 0 = Monday .. 6 = Sunday, matching the API's date.weekday(). */
  weekdays: number[];
  start_date: string;
  local_time: string;
  duration_minutes: number;
}

export interface SessionSeriesSummary {
  id: string;
  group_id: string;
  trainer_person_id: string | null;
  location_id: string | null;
  title: string;
  frequency: SessionSeriesFrequency;
  weekdays: number[];
  start_date: string;
  timezone: string;
  local_time: string;
  duration_minutes: number;
}

export interface SeriesGenerateResult {
  series_id: string;
  created_count: number;
  skipped_existing: number;
  skipped_conflicts: { starts_at: string; reason: string }[];
  horizon_start: string;
  horizon_end: string;
}

/** PATCH /schedule/sessions/{id} body. Any field left undefined is unchanged. */
export interface SessionEdit {
  local_time?: string | null;
  duration_minutes?: number | null;
  title?: string | null;
  trainer_person_id?: string | null;
  location_id?: string | null;
  reason: SessionChangeReasonCode;
  scope: SessionEditScope;
}

/** POST /schedule/sessions/{id}/cancel body. */
export interface SessionCancel {
  reason: SessionCancellationReasonCode;
  note?: string | null;
}

export interface ConflictCheck {
  has_conflict: boolean;
  conflicts: SessionSummary[];
}

export type AttendanceStatus = "PRESENT" | "ABSENT" | "EXCUSED" | "LATE";

export interface AttendanceEntry {
  person_id: string;
  display_name: string;
  status: AttendanceStatus;
}

export interface AttendanceSheet {
  session_id: string;
  attendance_version: number;
  entries: AttendanceEntry[];
}

export interface SaveAttendanceResponse {
  session_id: string;
  attendance_version: number;
  present: number;
  absent: number;
  excused: number;
  late: number;
}

export interface BillingPreviewItem {
  person_id: string;
  display_name: string;
  amount: string;
}

export interface BillingPreview {
  preview_hash: string;
  currency: string;
  total: string;
  items: BillingPreviewItem[];
}

export interface BillingRun {
  id: string;
  description: string;
  period_label: string;
  currency: string;
  total: string;
  charge_count: number;
}

export type ChargeStatus = "OPEN" | "PARTIALLY_PAID" | "PAID" | "CANCELLED";

export interface Charge {
  id: string;
  person_id: string;
  description: string;
  currency: string;
  amount_due: string;
  amount_paid: string;
  /** ISO date. Null when nobody set a deadline for this charge. */
  due_date?: string | null;
  payment_reference?: string | null;
  status: ChargeStatus;
}

/**
 * Payment-slip data for one charge, including the NBS IPS QR payload.
 *
 * Scanning the QR only pre-fills the payer's banking app. It does not move
 * money and it does not tell SOKOLA OS anything: the charge stays open until
 * the school checks its account and records the payment by hand.
 */
export interface PaymentSlip {
  charge_id: string;
  payee_name: string;
  payee_address: string | null;
  payee_city: string | null;
  account_number: string;
  payer_name: string;
  currency: string;
  amount: string;
  purpose: string;
  payment_code: string;
  reference_number: string;
  due_date: string | null;
  ips_qr_payload: string;
}

export interface Payment {
  id: string;
  charge_id: string;
  amount: string;
  currency: string;
  method: string;
  status: string;
  charge_status: ChargeStatus;
  charge_amount_due: string;
  charge_amount_paid: string;
}

export type EventType =
  | "TRAINING_CAMP"
  | "PREPARATION"
  | "COMPETITION"
  | "PERFORMANCE"
  | "WORKSHOP"
  | "SOCIAL"
  | "OTHER";

export type EventStatus = "DRAFT" | "PUBLISHED" | "CANCELLED" | "COMPLETED";

export interface EventItem {
  id: string;
  title: string;
  type: EventType;
  category: string;
  status: EventStatus;
  starts_at: string;
  ends_at?: string | null;
  location_id?: string | null;
  /** Free-text detail one structured location cannot hold (multi-venue camps). */
  location_note?: string | null;
  responsible_person_id?: string | null;
  description?: string | null;
  capacity_mode: "UNLIMITED" | "LIMITED";
  capacity: number | null;
}

export interface Registration {
  registration_id: string;
  child_person_id: string;
  display_name: string;
  status: "REGISTERED" | "CANCELLED";
}

export interface AnnouncementPreview {
  recipient_count: number;
  snapshot_hash: string;
}

export interface Announcement {
  id: string;
  title: string;
  status: string;
  recipient_count: number;
}


/**
 * GET /reports/overview , the school's health right now.
 *
 * `active_member_count` is the authoritative "Aktivni članovi" figure: active
 * ATTENDEE memberships only, so owners, trainers, guardians and contacts are
 * excluded. Screens must read it from here rather than counting /people.
 */
export interface OverviewReport {
  period_start: string;
  period_end: string;
  currency: string;
  active_member_count: number;
  billed_total: string;
  collected_total: string;
  outstanding_debt_total: string;
  attendance_window_days: number;
  attendance_recorded_count: number;
  attendance_present_count: number;
  attendance_rate: number;
}
