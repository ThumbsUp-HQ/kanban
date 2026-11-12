"""Rate limit models: rate_limit_buckets."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class RateLimitBucket(Base):
    """Sliding-window rate limit counter bucket."""

    __tablename__ = "rate_limit_buckets"

    policy: Mapped[str] = mapped_column(String, primary_key=True)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
