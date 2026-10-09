from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, Session
from config import get_settings
from models import Base, PriceCapture, Partner, ChannelPartner
import os

# Initialize app
settings = get_settings()
app = FastAPI(
    title="ShoppingAgent API",
    version=settings.api_version,
    debug=settings.debug
)

# CORS middleware (allow requests from extension + frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Schemas ──────────────────────────────────────────────────────────────────

class PriceCaptureRequest(BaseModel):
    """Price capture data from browser extension."""

    user_id: UUID
    platform: str = Field(..., description="walmart, kroger, amazon, etc")
    domain: str = Field(..., description="walmart.com, ralphs.com, etc")
    product_id: str = Field(..., description="SKU/ASIN/TCIN")
    product_name: str
    price: float = Field(..., gt=0, description="Price in USD")
    store_location: Optional[str] = None
    page_type: str = Field(..., description="PDP or PLP")
    search_query: Optional[str] = None
    url: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "platform": "walmart",
                "domain": "walmart.com",
                "product_id": "WMT123456789",
                "product_name": "Great Value 2% Milk 1 Gallon",
                "price": 3.99,
                "store_location": "Denver, CO 80201",
                "page_type": "PDP",
                "search_query": None,
                "url": "https://walmart.com/product/...",
                "timestamp": "2026-04-21T14:30:00Z"
            }
        }


class PriceCaptureResponse(BaseModel):
    """Response after successful price capture."""

    id: UUID
    message: str
    status: str

    class Config:
        from_attributes = True


class PartnerCreate(BaseModel):
    """Create a new partner."""
    name: str = Field(..., description="Unique partner name")
    description: Optional[str] = None


class PartnerResponse(BaseModel):
    """Partner details."""
    id: UUID
    name: str
    enabled: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChannelToggleRequest(BaseModel):
    """Enable/disable a channel for a partner."""
    channel: str = Field(..., description="target, walmart, amazon, kroger, instacart, whole-foods, costco")
    enabled: bool


class ChannelPartnerResponse(BaseModel):
    """Channel status for a partner."""
    partner_id: UUID
    channel: str
    enabled: bool

    class Config:
        from_attributes = True


class ActiveChannelsResponse(BaseModel):
    """List of active channels for a partner."""
    partner_id: UUID
    active_channels: List[str]
    all_channels: List[str]


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/v1/price-captures", response_model=PriceCaptureResponse)
async def create_price_capture(
    capture: PriceCaptureRequest,
    db: Session = Depends(get_db)
):
    """
    Receive a price capture from the browser extension.

    The extension sends this data whenever a user views a product.
    Server-side governance: checks if user's partner allows this channel.
    """
    try:
        # Get user to check partner
        from models import User
        user = db.query(User).filter(User.id == capture.user_id).first()

        # If user has a partner, check if this channel is enabled
        if user and user.partner_id:
            partner = db.query(Partner).filter(Partner.id == user.partner_id).first()

            # Check if partner is enabled
            if partner and not partner.enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Partner {partner.name} is disabled"
                )

            # Check if this channel is enabled for the partner
            channel_partner = db.query(ChannelPartner).filter(
                ChannelPartner.partner_id == user.partner_id,
                ChannelPartner.channel == capture.platform
            ).first()

            if channel_partner and not channel_partner.enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Channel {capture.platform} is disabled for partner {partner.name}"
                )

        # Create and save price capture
        db_capture = PriceCapture(
            user_id=capture.user_id,
            platform=capture.platform,
            domain=capture.domain,
            product_id=capture.product_id,
            product_name=capture.product_name,
            price=capture.price,
            store_location=capture.store_location,
            page_type=capture.page_type,
            search_query=capture.search_query,
            url=capture.url,
            timestamp=capture.timestamp,
        )
        db.add(db_capture)
        db.commit()
        db.refresh(db_capture)

        return PriceCaptureResponse(
            id=db_capture.id,
            message=f"Price captured: {capture.product_name} @ {capture.platform}",
            status="success"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving price capture: {str(e)}"
        )


@app.post("/api/v1/price-captures/batch")
async def create_price_captures_batch(
    captures: list[PriceCaptureRequest],
    db: Session = Depends(get_db)
):
    """
    Batch endpoint for sending multiple price captures at once.
    Server-side governance: filters captures based on partner permissions.
    """
    try:
        from models import User
        db_captures = []
        rejected_count = 0

        for c in captures:
            # Check user's partner permissions
            user = db.query(User).filter(User.id == c.user_id).first()
            should_capture = True

            if user and user.partner_id:
                partner = db.query(Partner).filter(Partner.id == user.partner_id).first()

                # Skip if partner disabled
                if partner and not partner.enabled:
                    rejected_count += 1
                    continue

                # Skip if channel disabled for partner
                channel_partner = db.query(ChannelPartner).filter(
                    ChannelPartner.partner_id == user.partner_id,
                    ChannelPartner.channel == c.platform
                ).first()

                if channel_partner and not channel_partner.enabled:
                    rejected_count += 1
                    continue

            # Add to batch if allowed
            db_captures.append(
                PriceCapture(
                    user_id=c.user_id,
                    platform=c.platform,
                    domain=c.domain,
                    product_id=c.product_id,
                    product_name=c.product_name,
                    price=c.price,
                    store_location=c.store_location,
                    page_type=c.page_type,
                    search_query=c.search_query,
                    url=c.url,
                    timestamp=c.timestamp,
                )
            )

        # Save allowed captures
        if db_captures:
            db.add_all(db_captures)
            db.commit()

        return {
            "status": "success",
            "message": f"Captured {len(db_captures)} price points",
            "count": len(db_captures),
            "rejected": rejected_count
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving price captures: {str(e)}"
        )


# ── Partner Management ───────────────────────────────────────────────────────

@app.post("/api/v1/partners", response_model=PartnerResponse)
async def create_partner(
    partner: PartnerCreate,
    db: Session = Depends(get_db)
):
    """Create a new partner."""
    try:
        db_partner = Partner(
            name=partner.name,
            description=partner.description,
            enabled=True
        )
        db.add(db_partner)
        db.commit()
        db.refresh(db_partner)
        return db_partner
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating partner: {str(e)}"
        )


@app.get("/api/v1/partners", response_model=List[PartnerResponse])
async def list_partners(db: Session = Depends(get_db)):
    """List all partners."""
    partners = db.query(Partner).all()
    return partners


@app.get("/api/v1/partners/{partner_id}", response_model=PartnerResponse)
async def get_partner(
    partner_id: UUID,
    db: Session = Depends(get_db)
):
    """Get partner details."""
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@app.patch("/api/v1/partners/{partner_id}")
async def update_partner(
    partner_id: UUID,
    enabled: bool,
    db: Session = Depends(get_db)
):
    """Enable/disable a partner."""
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    partner.enabled = enabled
    db.commit()
    return {"status": "updated", "partner_id": partner_id, "enabled": enabled}


@app.post("/api/v1/partners/{partner_id}/channels")
async def toggle_channel(
    partner_id: UUID,
    request: ChannelToggleRequest,
    db: Session = Depends(get_db)
):
    """Enable/disable a channel for a partner."""
    # Verify partner exists
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Check if mapping exists
    channel_partner = db.query(ChannelPartner).filter(
        ChannelPartner.partner_id == partner_id,
        ChannelPartner.channel == request.channel
    ).first()

    if channel_partner:
        # Update existing
        channel_partner.enabled = request.enabled
    else:
        # Create new
        channel_partner = ChannelPartner(
            partner_id=partner_id,
            channel=request.channel,
            enabled=request.enabled
        )
        db.add(channel_partner)

    db.commit()
    return {
        "status": "updated",
        "partner_id": partner_id,
        "channel": request.channel,
        "enabled": request.enabled
    }


@app.get("/api/v1/partners/{partner_id}/channels", response_model=ActiveChannelsResponse)
async def get_active_channels(
    partner_id: UUID,
    db: Session = Depends(get_db)
):
    """Get active channels for a partner."""
    # Verify partner exists
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Get channel statuses
    channel_partners = db.query(ChannelPartner).filter(
        ChannelPartner.partner_id == partner_id
    ).all()

    all_channels = ["target", "walmart", "amazon", "kroger", "instacart", "whole-foods", "costco"]
    active_channels = [cp.channel for cp in channel_partners if cp.enabled]

    # For channels not explicitly mapped, assume enabled (backward compatibility)
    implicit_active = [c for c in all_channels if c not in [cp.channel for cp in channel_partners]]
    active_channels.extend(implicit_active)

    return ActiveChannelsResponse(
        partner_id=partner_id,
        active_channels=active_channels,
        all_channels=all_channels
    )


# ── Price Capture Retrieval ─────────────────────────────────────────────────

@app.get("/api/v1/price-captures")
async def list_price_captures(
    limit: int = 100,
    skip: int = 0,
    product_name: Optional[str] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retrieve all captured prices with optional filtering.

    Query params:
    - limit: max results (default 100)
    - skip: offset for pagination (default 0)
    - product_name: filter by product name (partial match)
    - platform: filter by platform (exact match)
    """
    query = db.query(PriceCapture)

    if product_name:
        query = query.filter(PriceCapture.product_name.ilike(f"%{product_name}%"))

    if platform:
        query = query.filter(PriceCapture.platform == platform)

    # Order by timestamp descending (newest first)
    query = query.order_by(desc(PriceCapture.timestamp))

    total = query.count()
    captures = query.offset(skip).limit(limit).all()

    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "platform": c.platform,
            "domain": c.domain,
            "product_id": c.product_id,
            "product_name": c.product_name,
            "price": float(c.price),
            "store_location": c.store_location,
            "page_type": c.page_type,
            "search_query": c.search_query,
            "url": c.url,
            "timestamp": c.timestamp.isoformat(),
            "created_at": c.created_at.isoformat(),
        }
        for c in captures
    ]


@app.get("/dashboard")
async def serve_dashboard():
    """Serve the dashboard HTML."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Dashboard not found")


# ── Historical Data Import ──────────────────────────────────────────────────

@app.post("/api/v1/import/historical")
async def import_historical_data(
    user_id: str = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Endpoint for importing historical order data from user uploads.

    Accepts multipart form data with:
    - user_id: UUID of the user
    - files: One or more files (CSV, images, JSON exports, etc.)

    MVP: Accepts files and acknowledges receipt. Actual parsing queued for async processing.
    """
    try:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required"
            )

        # Verify/create user
        from models import User
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid user_id format"
            )

        user = db.query(User).filter(User.id == user_uuid).first()
        if not user:
            # For MVP, auto-create user if they don't exist
            try:
                user = User(id=user_uuid, email=f"user-{user_id}@shoppingagent.local")
                db.add(user)
                db.commit()
            except Exception as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not create user: {str(e)}"
                )

        # Validate file types
        allowed_types = {
            'text/csv',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'image/jpeg',
            'image/png',
            'application/pdf',
            'application/json'
        }

        total_files = len(files)
        valid_files = []

        for file in files:
            # Basic validation
            if file.content_type not in allowed_types:
                continue  # Skip unsupported files
            valid_files.append(file.filename)

        # MVP: Return success acknowledgment
        # In production, would:
        # 1. Save files to storage
        # 2. Queue async parsing job
        # 3. Return job tracking ID
        return {
            "status": "queued",
            "message": f"Received {len(valid_files)} file(s) for processing",
            "imported_count": 0,
            "skipped_count": total_files - len(valid_files),
            "user_id": str(user_uuid),
            "files_received": len(valid_files)
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing import: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
