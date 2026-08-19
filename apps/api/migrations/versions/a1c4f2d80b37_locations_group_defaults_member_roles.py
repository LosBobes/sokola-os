"""location kinds, session/event locations, group defaults, member roles,
payment slips

Revision ID: a1c4f2d80b37
Revises: 3b1e7c9a2d04
Create Date: 2026-08-19 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c4f2d80b37'
down_revision: str | None = '3b1e7c9a2d04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LOCATION_KIND = sa.Enum(
    'SPORTS_HALL', 'FIELD', 'KINDERGARTEN', 'SCHOOL', 'THEATRE', 'OUTDOOR',
    'ONLINE', 'OTHER',
    name='locationkind', native_enum=False, length=40,
)
_GROUP_MEMBER_ROLE = sa.Enum(
    'MEMBER', 'TRAINER', 'ASSISTANT', 'OTHER_STAFF',
    name='groupmemberrole', native_enum=False, length=40,
)
_ORG_MEMBER_TYPE = sa.Enum(
    'ATTENDEE', 'STAFF', 'GUARDIAN', 'CONTACT',
    name='orgmembertype', native_enum=False, length=40,
)


def upgrade() -> None:
    # --- Locations are the general concept, not just halls -----------------
    # Existing rows are classified OTHER, never SPORTS_HALL: the old model had
    # no kind, so guessing "hall" would invent a fact about someone's data.
    op.add_column(
        'structure_location',
        sa.Column(
            'kind', _LOCATION_KIND, nullable=False, server_default=sa.text("'OTHER'")
        ),
    )
    op.alter_column('structure_location', 'kind', server_default=None)

    # --- Where a session / series / event happens --------------------------
    for table in ('session', 'session_series', 'event'):
        op.add_column(table, sa.Column('location_id', sa.String(length=64), nullable=True))
        op.create_foreign_key(
            f'fk_{table}_location', table, 'structure_location',
            ['location_id'], ['id'], ondelete='SET NULL',
        )

    # --- Event: the rest of the "Događaji Light" fact set -------------------
    op.add_column('event', sa.Column('location_note', sa.String(length=400), nullable=True))
    op.add_column(
        'event', sa.Column('responsible_person_id', sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        'fk_event_responsible_person', 'event', 'person',
        ['responsible_person_id'], ['id'], ondelete='SET NULL',
    )
    op.add_column('event', sa.Column('description', sa.Text(), nullable=True))

    # --- The group is the default source for trainer + location ------------
    op.add_column(
        'group', sa.Column('default_trainer_person_id', sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        'fk_group_default_trainer', 'group', 'person',
        ['default_trainer_person_id'], ['id'], ondelete='SET NULL',
    )
    op.add_column(
        'group', sa.Column('default_location_id', sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        'fk_group_default_location', 'group', 'structure_location',
        ['default_location_id'], ['id'], ondelete='SET NULL',
    )
    # A group that already names a location keeps using it as the default for
    # new sessions, which is what that column meant in practice.
    op.execute(
        "UPDATE \"group\" SET default_location_id = location_id "
        "WHERE location_id IS NOT NULL"
    )

    # --- Participant vs. staff, inside a group -----------------------------
    # Backfill MEMBER: every pre-existing group membership was already being
    # rostered for attendance and billed, i.e. treated as a participant.
    op.add_column(
        'group_membership',
        sa.Column(
            'role', _GROUP_MEMBER_ROLE, nullable=False, server_default=sa.text("'MEMBER'")
        ),
    )
    op.alter_column('group_membership', 'role', server_default=None)

    # --- What a person is to the school ------------------------------------
    op.add_column(
        'organization_membership',
        sa.Column(
            'member_type', _ORG_MEMBER_TYPE, nullable=False,
            server_default=sa.text("'ATTENDEE'"),
        ),
    )
    # Anyone already holding an active staff-side role assignment is staff, not
    # a participant, so the "aktivni članovi" figure is correct from the first
    # request after deploy rather than after a manual cleanup pass. Guardians
    # are reclassified the same way from their PARENT role.
    op.execute(
        """
        UPDATE organization_membership AS m
        SET member_type = 'STAFF'
        WHERE EXISTS (
            SELECT 1 FROM role_assignment AS r
            WHERE r.person_id = m.person_id
              AND r.organization_id = m.organization_id
              AND r.status = 'ACTIVE'
              AND r.role_code IN ('OWNER', 'MANAGER', 'ADMIN', 'TRAINER')
        )
        """
    )
    op.execute(
        """
        UPDATE organization_membership AS m
        SET member_type = 'GUARDIAN'
        WHERE member_type = 'ATTENDEE'
          AND EXISTS (
            SELECT 1 FROM role_assignment AS r
            WHERE r.person_id = m.person_id
              AND r.organization_id = m.organization_id
              AND r.status = 'ACTIVE'
              AND r.role_code = 'PARENT'
        )
        """
    )
    op.alter_column('organization_membership', 'member_type', server_default=None)

    # --- Payment slip (uplatnica) with an NBS IPS QR ------------------------
    # Payee details live on the school; all nullable, a school without them
    # simply cannot produce a slip yet.
    op.add_column(
        'organization', sa.Column('bank_account_number', sa.String(length=30), nullable=True)
    )
    op.add_column('organization', sa.Column('address', sa.String(length=200), nullable=True))
    op.add_column('organization', sa.Column('city', sa.String(length=100), nullable=True))

    # A charge gains a due date and the "poziv na broj" printed on its slip.
    # Both stay NULL for existing charges: nobody set a deadline for them, and
    # backfilling one would retroactively mark historical charges overdue.
    op.add_column('charge', sa.Column('due_date', sa.Date(), nullable=True))
    op.add_column(
        'charge', sa.Column('payment_reference', sa.String(length=24), nullable=True)
    )
    op.create_index(
        'uq_charge_payment_reference', 'charge', ['organization_id', 'payment_reference'],
        unique=True, postgresql_where=sa.text('payment_reference IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_charge_payment_reference', table_name='charge',
        postgresql_where=sa.text('payment_reference IS NOT NULL'),
    )
    op.drop_column('charge', 'payment_reference')
    op.drop_column('charge', 'due_date')
    op.drop_column('organization', 'city')
    op.drop_column('organization', 'address')
    op.drop_column('organization', 'bank_account_number')

    op.drop_column('organization_membership', 'member_type')
    op.drop_column('group_membership', 'role')

    op.drop_constraint('fk_group_default_location', 'group', type_='foreignkey')
    op.drop_column('group', 'default_location_id')
    op.drop_constraint('fk_group_default_trainer', 'group', type_='foreignkey')
    op.drop_column('group', 'default_trainer_person_id')

    op.drop_column('event', 'description')
    op.drop_constraint('fk_event_responsible_person', 'event', type_='foreignkey')
    op.drop_column('event', 'responsible_person_id')
    op.drop_column('event', 'location_note')

    for table in ('event', 'session_series', 'session'):
        op.drop_constraint(f'fk_{table}_location', table, type_='foreignkey')
        op.drop_column(table, 'location_id')

    op.drop_column('structure_location', 'kind')
