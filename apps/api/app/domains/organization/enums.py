from __future__ import annotations

import enum


class OrganizationStatus(enum.StrEnum):
    """M04 §5.1. ``ARCHIVED`` is terminal: an organization is not reactivated in
    this MVP, because reactivating one would silently re-open the commercial
    entitlements it once issued."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class OrganizationUpdateReason(enum.StrEnum):
    """§8.1.2, ORG-02. A closed registry: free text does not substitute."""

    LEGAL_NAME_CORRECTION = "LEGAL_NAME_CORRECTION"
    REGISTRY_DATA_CORRECTION = "REGISTRY_DATA_CORRECTION"
    ADMINISTRATIVE_CORRECTION = "ADMINISTRATIVE_CORRECTION"


class OrganizationArchiveReason(enum.StrEnum):
    """§8.1.2, ORG-03."""

    LEGAL_ENTITY_CLOSED = "LEGAL_ENTITY_CLOSED"
    CREATED_IN_ERROR = "CREATED_IN_ERROR"
    NO_LONGER_USED = "NO_LONGER_USED"


class OrganizationSchoolChangeReason(enum.StrEnum):
    """§2.3 ``change_reason_code``: why a school's organization link opened.

    ``INITIAL_PROVISIONING`` is written by the system on the first link and is
    not selectable; the rest are the §8.1.2 ORG-04 transfer reasons.
    """

    INITIAL_PROVISIONING = "INITIAL_PROVISIONING"
    LEGAL_OWNERSHIP_TRANSFER = "LEGAL_OWNERSHIP_TRANSFER"
    CORPORATE_RESTRUCTURE = "CORPORATE_RESTRUCTURE"
    CREATED_UNDER_WRONG_ORGANIZATION = "CREATED_UNDER_WRONG_ORGANIZATION"
