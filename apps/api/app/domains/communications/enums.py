from __future__ import annotations

import enum


class AnnouncementStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class AnnouncementTargetType(enum.StrEnum):
    ORGANIZATION = "ORGANIZATION"
    GROUP = "GROUP"
