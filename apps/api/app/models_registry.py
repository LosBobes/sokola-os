"""Single import surface for Alembic autogenerate.

Importing this module imports every ORM model so ``Base.metadata`` is complete.
Add each new domain's ``models`` module here as it is introduced.
"""

from __future__ import annotations

from app.common.base import Base  # noqa: F401

# Domain models, imported for their side effect of registering tables on
# Base.metadata. Appended increment by increment.
from app.domains.attendance import models as _attendance_models  # noqa: F401
from app.domains.authorization import models as _authorization_models  # noqa: F401
from app.domains.billing import models as _billing_models  # noqa: F401
from app.domains.communications import models as _communications_models  # noqa: F401
from app.domains.data_import import models as _data_import_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.events import models as _events_models  # noqa: F401
from app.domains.groups import models as _groups_models  # noqa: F401
from app.domains.identity import auth_models as _identity_auth_models  # noqa: F401
from app.domains.identity import models as _identity_models  # noqa: F401
from app.domains.onboarding import models as _onboarding_models  # noqa: F401
from app.domains.organization import models as _organization_models  # noqa: F401
from app.domains.payments import models as _payments_models  # noqa: F401
from app.domains.people import activity_profiles as _people_activity_profiles  # noqa: F401
from app.domains.people import models as _people_models  # noqa: F401
from app.domains.people import profile_models as _people_profile_models  # noqa: F401
from app.domains.privacy import models as _privacy_models  # noqa: F401
from app.domains.progress import models as _progress_models  # noqa: F401
from app.domains.scheduling import models as _scheduling_models  # noqa: F401
from app.domains.school import entitlement_models as _entitlement_models  # noqa: F401
from app.domains.school import models as _school_models  # noqa: F401
from app.domains.school import ownership_models as _ownership_models  # noqa: F401
from app.domains.structure import models as _structure_models  # noqa: F401
from app.domains.tenancy import models as _tenancy_models  # noqa: F401
from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.idempotency import models as _idempotency_models  # noqa: F401
from app.platform.inbox import models as _inbox_models  # noqa: F401
from app.platform.outbox import models as _outbox_models  # noqa: F401
from app.platform.rate_limit import models as _rate_limit_models  # noqa: F401

__all__ = ["Base"]
