# Profit Capture Backend

FastAPI backend for collecting and managing price data from the browser extension.

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Database

Copy `.env.example` to `.env` and update with your PostgreSQL connection string:

```bash
cp .env.example .env
```

**For local development:**
```
DATABASE_URL=postgresql://user:password@localhost:5432/profit_capture
```

**For Railway.app hosting:**
```
DATABASE_URL=postgresql://username:password@region.railway.app:5432/railway
```

### 3. Create Database

Make sure PostgreSQL is running, then the app will auto-create tables on first run.

## Running Locally

```bash
python main.py
```

Server runs at `http://localhost:8000`

API docs available at `http://localhost:8000/docs`

## API Endpoints

### Health Check
```
GET /health
```

### Single Price Capture
```
POST /api/v1/price-captures
```

Body:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "platform": "walmart",
  "domain": "walmart.com",
  "product_id": "WMT123456789",
  "product_name": "Great Value 2% Milk 1 Gallon",
  "price": 3.99,
  "store_location": "Denver, CO 80201",
  "page_type": "PDP",
  "search_query": null,
  "url": "https://walmart.com/product/...",
  "timestamp": "2026-04-21T14:30:00Z"
}
```

### Batch Price Captures (MVP for later)
```
POST /api/v1/price-captures/batch
```

Body:
```json
[
  { ...capture1... },
  { ...capture2... },
  { ...captureN... }
]
```

## Database Schema

### price_captures
- `id` (UUID) - Primary key
- `user_id` (UUID) - User who captured the price
- `platform` (string) - walmart, kroger, amazon, etc
- `domain` (string) - walmart.com, ralphs.com, etc
- `product_id` (string) - SKU/ASIN/TCIN
- `product_name` (text) - Full product name
- `price` (decimal) - Price in USD
- `store_location` (string, optional) - Physical store location
- `page_type` (string) - PDP or PLP
- `search_query` (string, optional) - Search query if from search
- `url` (string) - Source product URL
- `timestamp` (datetime) - When user saw it
- `created_at` (datetime) - When captured in DB

Indexes on: user_id + timestamp, platform + domain, product_id, created_at

### users
- `id` (UUID) - Primary key
- `email` (string) - Unique email
- `created_at` (datetime)
- `last_login` (datetime, optional)

## Next Steps

1. Deploy to Railway.app or similar
2. Update Cloudflare DNS to point to deployed backend
3. Update extension to send data to production API endpoint
4. Build conversation agent layer
5. Build frontend UI
