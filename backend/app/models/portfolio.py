import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..core.database import Base


class Portfolio(Base):
    """Saved simulation result — one per user submission they chose to keep."""

    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(120), nullable=False)
    risk_tier = Column(String(20), nullable=False)
    amount = Column(Numeric, nullable=False)
    horizon_years = Column(Numeric, nullable=False)
    monthly_contribution = Column(Numeric, nullable=False, default=0)
    extra_fee = Column(Numeric, nullable=False, default=0)
    goal = Column(Numeric, nullable=True)
    purpose = Column(String(20), nullable=True)  # retirement|house|education|general

    # Full simulation result stored as JSON blob
    result_json = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="portfolios")
