from sqlalchemy import Column, String, Numeric, DateTime, Text, Index, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator
import uuid
from datetime import datetime

Base = declarative_base()


# UUID type that works with both SQLite and PostgreSQL
class GUID(TypeDecorator):
    """Platform-independent GUID type for SQLite and PostgreSQL."""
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value) if dialect.name != 'postgresql' else value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value) if not isinstance(value, uuid.UUID) else value


class PriceCapture(Base):
    """Raw price capture data from extension."""

    __tablename__ = "price_captures"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # walmart, kroger, amazon, etc
    domain = Column(String(100), nullable=False)   # walmart.com, ralphs.com, etc
    product_id = Column(String(100), nullable=False)  # SKU/ASIN/TCIN
    product_name = Column(Text, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    store_location = Column(String(200), nullable=True)  # Optional
    page_type = Column(String(20), nullable=False)  # PDP or PLP
    search_query = Column(String(500), nullable=True)  # Optional
    url = Column(String(2000), nullable=False)
    timestamp = Column(DateTime, nullable=False)  # When user saw it
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_platform_domain', 'platform', 'domain'),
        Index('idx_product_id', 'product_id'),
        Index('idx_created_at', 'created_at'),
    )


class User(Base):
    """User profiles and preferences."""

    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    partner_id = Column(GUID(), ForeignKey('partners.id'), nullable=True, index=True)  # Which partner this user belongs to
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class Partner(Base):
    """Partners/retailers that can have channels enabled/disabled."""

    __tablename__ = "partners"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "affiliate-a", "costco-partner"
    enabled = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChannelPartner(Base):
    """Maps which channels (platforms) are enabled for each partner."""

    __tablename__ = "channel_partners"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    partner_id = Column(GUID(), ForeignKey('partners.id'), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # target, walmart, amazon, kroger, instacart, whole-foods, costco
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one entry per partner-channel combo
    __table_args__ = (
        Index('idx_partner_channel', 'partner_id', 'channel', unique=True),
    )
