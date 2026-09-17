"""Ownership persistence services; callers own the transaction.

These helpers validate references, not caller permissions. Legacy API routes
explicitly use the local organization until organization-aware authorization
is implemented. A login identity never implies a membership or client role.
"""

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from api.db import (
    AdvisorClientAssignmentRecord,
    ClientRecord,
    MembershipRole,
    OrganizationMembershipRecord,
    OrganizationRecord,
    ProfileRecord,
    UserRecord,
)

LOCAL_ORGANIZATION_ID = "local"
LOCAL_ORGANIZATION_NAME = "Local workspace"


def ensure_local_organization(session: Session) -> OrganizationRecord:
    """Concurrency-safe, idempotent local workspace creation."""
    session.execute(
        insert(OrganizationRecord)
        .values(id=LOCAL_ORGANIZATION_ID, name=LOCAL_ORGANIZATION_NAME)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return session.get(OrganizationRecord, LOCAL_ORGANIZATION_ID)


def create_organization(session: Session, name: str) -> OrganizationRecord:
    if not name.strip():
        raise ValueError("Organization name is required")
    organization = OrganizationRecord(name=name.strip())
    session.add(organization)
    session.flush()
    return organization


def _require_organization(session: Session, organization_id: str) -> None:
    if session.get(OrganizationRecord, organization_id) is None:
        raise ValueError("Organization not found")


def _require_user(session: Session, user_id: str) -> None:
    if session.get(UserRecord, user_id) is None:
        raise ValueError("User not found")


def set_membership(
    session: Session, organization_id: str, user_id: str, role: MembershipRole
) -> OrganizationMembershipRecord:
    role = MembershipRole(role)
    _require_organization(session, organization_id)
    _require_user(session, user_id)
    membership = session.exec(
        select(OrganizationMembershipRecord).where(
            OrganizationMembershipRecord.organization_id == organization_id,
            OrganizationMembershipRecord.user_id == user_id,
        )
    ).first()
    if membership is None:
        membership = OrganizationMembershipRecord(
            organization_id=organization_id, user_id=user_id, role=role
        )
    else:
        membership.role = role
    session.add(membership)
    session.flush()
    return membership


def create_client(
    session: Session, organization_id: str, *, user_id: str | None = None
) -> ClientRecord:
    _require_organization(session, organization_id)
    if user_id is not None:
        _require_user(session, user_id)
    client = ClientRecord(organization_id=organization_id, user_id=user_id)
    session.add(client)
    session.flush()
    return client


def attach_profile(
    session: Session, client_id: str, profile: ProfileRecord
) -> ProfileRecord:
    """Attach a new profile to a client that has no profile yet."""
    if session.get(ClientRecord, client_id) is None:
        raise ValueError("Client not found")
    if profile.id is not None or profile.client_id is not None:
        raise ValueError("Profile is already attached")
    if (
        session.exec(
            select(ProfileRecord.id).where(ProfileRecord.client_id == client_id)
        ).first()
        is not None
    ):
        raise ValueError("Client already has a profile")
    profile.client_id = client_id
    session.add(profile)
    session.flush()
    return profile


def create_local_profile(session: Session, profile: ProfileRecord) -> ProfileRecord:
    organization = ensure_local_organization(session)
    client = create_client(session, organization.id)
    return attach_profile(session, client.id, profile)


def get_profile_owner(session: Session, profile_id: int) -> ClientRecord:
    """Resolve the unique client and its organization ID from a profile ID."""
    client = session.exec(
        select(ClientRecord)
        .join(ProfileRecord, ProfileRecord.client_id == ClientRecord.id)
        .where(ProfileRecord.id == profile_id)
    ).first()
    if client is None:
        raise ValueError("Profile not found")
    return client


def local_profile_keys(
    session: Session, organization_id: str = LOCAL_ORGANIZATION_ID
) -> set[tuple[str, str]]:
    """Scope legacy import deduplication to its destination organization."""
    return set(
        session.exec(
            select(ProfileRecord.name, ProfileRecord.created_at)
            .join(ClientRecord, ProfileRecord.client_id == ClientRecord.id)
            .where(ClientRecord.organization_id == organization_id)
        ).all()
    )


def create_scoped_profile(
    session: Session,
    profile: ProfileRecord,
    organization_id: str,
    *,
    advisor_user_id: str | None = None,
) -> ProfileRecord:
    client = create_client(session, organization_id)
    if advisor_user_id is not None:
        membership = session.exec(
            select(OrganizationMembershipRecord).where(
                OrganizationMembershipRecord.organization_id == organization_id,
                OrganizationMembershipRecord.user_id == advisor_user_id,
                OrganizationMembershipRecord.role == MembershipRole.ADVISOR,
            )
        ).first()
        if membership is None:
            raise ValueError("Advisor membership required")
        session.add(
            AdvisorClientAssignmentRecord(
                organization_id=organization_id,
                advisor_user_id=advisor_user_id,
                client_id=client.id,
            )
        )
    return attach_profile(session, client.id, profile)


DEMO_ORGANIZATION_ID = "demo"


def ensure_demo_organization(session: Session) -> OrganizationRecord:
    session.execute(
        insert(OrganizationRecord)
        .values(id=DEMO_ORGANIZATION_ID, name="Demo workspace")
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return session.get(OrganizationRecord, DEMO_ORGANIZATION_ID)
