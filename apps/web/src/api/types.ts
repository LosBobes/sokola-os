/*
 * Hand-authored view of the API response shapes the web app consumes. The full
 * machine-generated types live in schema.d.ts (npm run gen:api); these are the
 * curated subset the screens use.
 */

export type RoleCode = "OWNER" | "MANAGER" | "ADMIN" | "TRAINER" | "PARENT" | "STUDENT";

export interface Context {
  role_assignment_id: string;
  organization_id: string;
  organization_name: string;
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

export interface Organization {
  id: string;
  name: string;
  slug: string | null;
  type: string;
  timezone: string;
}

export interface LocationSummary {
  id: string;
  name: string;
}

export interface TenantPublic {
  organization_id: string;
  name: string;
  slug: string;
}

export interface AuthConfig {
  google_enabled: boolean;
  dev_auth_enabled: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type PersonIdentityStatus = "PROVISIONAL" | "CLAIMED" | "VERIFIED" | "MERGED" | "ARCHIVED";

export interface PersonSummary {
  id: string;
  display_name: string;
  identity_status: PersonIdentityStatus;
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
}

export interface GroupMember {
  membership_id: string;
  person_id: string;
  display_name: string;
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
  series_id?: string | null;
  cancellation_reason?: SessionCancellationReasonCode | null;
}

/** PATCH /schedule/sessions/{id} body. Any field left undefined is unchanged. */
export interface SessionEdit {
  local_time?: string | null;
  duration_minutes?: number | null;
  title?: string | null;
  trainer_person_id?: string | null;
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
  amount_minor: number;
}

export interface BillingPreview {
  preview_hash: string;
  currency: string;
  total_minor: number;
  items: BillingPreviewItem[];
}

export interface BillingRun {
  id: string;
  description: string;
  period_label: string;
  currency: string;
  total_minor: number;
  charge_count: number;
}

export type ChargeStatus = "OPEN" | "PARTIALLY_PAID" | "PAID" | "CANCELLED";

export interface Charge {
  id: string;
  person_id: string;
  description: string;
  currency: string;
  amount_due_minor: number;
  amount_paid_minor: number;
  status: ChargeStatus;
}

export interface Payment {
  id: string;
  charge_id: string;
  amount_minor: number;
  currency: string;
  method: string;
  status: string;
  charge_status: ChargeStatus;
  charge_amount_due_minor: number;
  charge_amount_paid_minor: number;
}

export interface EventItem {
  id: string;
  title: string;
  type: string;
  category: string;
  status: string;
  starts_at: string;
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
