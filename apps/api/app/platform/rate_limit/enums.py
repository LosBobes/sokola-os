"""Rate-limit scopes (M01 §6 AUTH-01, §10).

Each scope is a separate budget. They are separate on purpose: exhausting the
per-IP login budget must not also exhaust the per-device one, or a shared
office NAT would lock out everyone behind it the moment one person fat-fingers
a password.
"""

from __future__ import annotations

import enum


class RateLimitScope(enum.StrEnum):
    #: §6 AUTH-01: 5 login starts per IP per 10 minutes.
    LOGIN_START_IP = "LOGIN_START_IP"
    #: §6 AUTH-01: 10 per browser/device signal per 24 hours. Slower and
    #: longer, because a device is a much better proxy for "one person trying
    #: repeatedly" than an address shared by a building.
    LOGIN_START_DEVICE = "LOGIN_START_DEVICE"
    #: §10: 20 callback failures per IP per 10 minutes.
    CALLBACK_FAILURE_IP = "CALLBACK_FAILURE_IP"
    #: §10's brute-force limit on the local password adapter. Not in AUTH-01's
    #: list because AUTH-01 is about starting a provider flow; a password POST
    #: *is* the attempt, so it needs its own budget.
    PASSWORD_FAILURE_IP = "PASSWORD_FAILURE_IP"
