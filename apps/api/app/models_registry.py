"""Single import surface for Alembic autogenerate.

Importing this module imports every ORM model so ``Base.metadata`` is complete.
Add each new domain's ``models`` module here as it is introduced.
"""

from __future__ import annotations

from app.common.base import Base  # noqa: F401

# Domain models — imported for their side effect of registering tables on
# Base.metadata. Appended increment by increment.
from app.domains.groups import models as _groups_models  # noqa: F401
from app.domains.identity import models as _identity_models  # noqa: F401
from app.domains.organization import models as _organization_models  # noqa: F401
from app.domains.people import models as _people_models  # noqa: F401
from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.idempotency import models as _idempotency_models  # noqa: F401
from app.platform.outbox import models as _outbox_models  # noqa: F401

__all__ = ["Base"]
