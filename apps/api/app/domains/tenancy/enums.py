"""M03 tenancy enums.

`School` is the only operational security tenant (§1), so everything here is
about one school's access as a whole — never about one person's place in it,
which is M06's, nor about what they may do, which is M05's.
"""

from __future__ import annotations

import enum


class TenantInvalidationReason(enum.StrEnum):
    """§5.2 `last_invalidation_reason_code`, a closed `Code64` registry.

    Closed because this is what a security reviewer reads months later to answer
    "why did an entire school lose access on the 14th". Free text answers that
    with whatever the caller happened to be thinking.
    """

    SCHOOL_DEACTIVATED = "SCHOOL_DEACTIVATED"
    SCHOOL_REACTIVATED = "SCHOOL_REACTIVATED"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    OWNERSHIP_TRANSFERRED = "OWNERSHIP_TRANSFERRED"
    SUPPORT_ACCESS_REVOKED = "SUPPORT_ACCESS_REVOKED"
    PLATFORM_POLICY = "PLATFORM_POLICY"
    LEGAL_HOLD = "LEGAL_HOLD"


#: §15's outbox event for a tenant-wide invalidation. Tenant-scoped, so unlike
#: M01's account event it carries `school_id` — §11: "svaki tenant događaj ima
#: `tenant_id=school_id`; platform događaj koristi eksplicitni platform scope,
#: ne `null` po navici".
SCHOOL_ACCESS_INVALIDATED_EVENT = "tenancy.school_access_invalidated"
