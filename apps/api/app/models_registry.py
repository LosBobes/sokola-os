"""Single import surface for Alembic autogenerate.

Importing this module imports every ORM model so ``Base.metadata`` is complete.
Add each new domain's ``models`` module here as it is introduced.
"""

from __future__ import annotations

from app.common.base import Base  # noqa: F401
from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.idempotency import models as _idempotency_models  # noqa: F401

# Platform + domain models are imported for their side effect of registering
# tables on Base.metadata. They are appended increment by increment.
from app.platform.outbox import models as _outbox_models  # noqa: F401

__all__ = ["Base"]
