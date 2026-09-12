import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String(64), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Profile
    date_of_birth = Column(Date, nullable=False)
    citizenship_attested = Column(Boolean, nullable=False)   # self-attestation; not KYC
    monthly_income = Column(Numeric, nullable=True)

    # Account state
    is_active = Column(Boolean, nullable=False, default=True)
    # Guest accounts are ephemeral demo sessions: no real credentials, data
    # labelled as sample throughout the UI, isolated like any other user.
    is_guest = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    portfolios = relationship(
        "Portfolio", back_populates="user", cascade="all, delete-orphan"
    )
    scenarios = relationship(
        "Scenario", back_populates="user", cascade="all, delete-orphan"
    )
