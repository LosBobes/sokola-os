"""Guided onboarding enums (PRD 02 §24/§25, PRD 01 §13)."""

from __future__ import annotations

import enum


class OnboardingStep(enum.StrEnum):
    """A step of guided school setup, in the order a new owner walks them.

    ``SCHOOL_PROFILE`` is satisfied by ``POST /organizations`` itself (name/
    type/timezone are required at creation) so it is always complete.
    ``LOCATIONS``/``ROOMS``/``PROGRAMS`` are satisfied by using the structure
    domain's own create endpoints — onboarding does not duplicate them, it only
    reports whether at least one active row exists for the school (see
    ``app.domains.onboarding.service``). ``FIRST_INVITE`` is satisfied by
    sending any invitation (in practice, during onboarding, the co-owner invite
    — see ``app.domains.identity.policy.ensure_invitation_allowed_during_onboarding``).
    ``ACTIVATE`` is the terminal step: leaving "u pripremi".
    """

    SCHOOL_PROFILE = "SCHOOL_PROFILE"
    LOCATIONS = "LOCATIONS"
    ROOMS = "ROOMS"
    PROGRAMS = "PROGRAMS"
    FIRST_INVITE = "FIRST_INVITE"
    ACTIVATE = "ACTIVATE"
