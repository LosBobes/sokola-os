from __future__ import annotations

import enum


class EventType(enum.StrEnum):
    TRAINING_CAMP = "TRAINING_CAMP"
    COMPETITION = "COMPETITION"
    WORKSHOP = "WORKSHOP"
    SOCIAL = "SOCIAL"
    OTHER = "OTHER"


class EventCategory(enum.StrEnum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class EventStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class EventCapacityMode(enum.StrEnum):
    UNLIMITED = "UNLIMITED"
    LIMITED = "LIMITED"


class RegistrationStatus(enum.StrEnum):
    REGISTERED = "REGISTERED"
    CANCELLED = "CANCELLED"


class CancellationReasonCode(enum.StrEnum):
    PARENT_REQUEST = "PARENT_REQUEST"
    ORGANIZER = "ORGANIZER"
    OTHER = "OTHER"
