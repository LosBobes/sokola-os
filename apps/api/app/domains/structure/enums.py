from __future__ import annotations

import enum


class LocationKind(enum.StrEnum):
    """What kind of place a :class:`app.domains.structure.models.Location` is.

    Activities do not only happen in a hall, so the model deliberately carries
    the general concept *location* (lokacija) and lets this enum describe the
    specific kind. Renaming the UI filter from "sale" to "lokacije" without
    this would have left the data model unable to express a session held in a
    kindergarten, a theatre, outdoors or online.

    ``OTHER`` is the fallback for anything not listed and the default for rows
    created before the column existed, so an unclassified location is never
    silently mislabelled as a hall.
    """

    SPORTS_HALL = "SPORTS_HALL"
    FIELD = "FIELD"
    KINDERGARTEN = "KINDERGARTEN"
    SCHOOL = "SCHOOL"
    THEATRE = "THEATRE"
    OUTDOOR = "OUTDOOR"
    ONLINE = "ONLINE"
    OTHER = "OTHER"
