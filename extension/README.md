# Profit Capture Browser Extension

Chrome extension for collecting grocery prices as users browse major online retailers.

## Current Status

**MVP Prototype** - Extracts prices from Target.com (PDP + PLP)

Planned support for 24 domains across 8 retailers (Walmart, Amazon, Kroger, Albertsons, Instacart, Publix, etc.)

## Architecture

```
Content Scripts (per domain)
├── target.js - Extract from Target
├── walmart.js - (TODO)
├── amazon.js - (TODO)
└── ... more domains

Background Service Worker
├── Receive messages from content scripts
├── Queue prices for batching
├── Send batches to backend API

Popup UI
├── Show collection status
├── Link to dashboard
└── Settings
```

## How It Works

1. **Content Script** (target.js)
   - Runs on Target.com product pages
   - Extracts product name, price, SKU, location, page type
   - Detects PDPs (single products) and PLPs (search/category pages)
   - Sends data to background worker

2. **Background Service Worker** (background.js)
   - Queues price data from all content scripts
   - Batches data for efficiency (MVP: sends individual, later: batches)
   - Posts to backend API at `http://localhost:8000/api/v1/price-captures`

3. **Popup** (popup.html/js)
   - Shows number of prices captured
   - Displays user ID
   - Links to dashboard

## Installation (Local Development)

1. **Load Extension in Chrome**
   - Open Chrome → Settings → Extensions
   - Enable "Developer mode" (toggle, top right)
   - Click "Load unpacked"
   - Select this `extension/` folder

2. **Start Backend**
   ```bash
   cd ../backend
   python main.py
   ```
   Backend runs at `http://localhost:8000`

3. **Test**
   - Navigate to target.com
   - View a product or search
   - Check extension popup - should show "Prices Captured"
   - Check backend console - should log received prices

## Data Captured

Per product:
- `platform` - "target"
- `domain` - "target.com"
- `product_id` - TCIN (Target internal SKU)
- `product_name` - Full product name
- `price` - USD price
- `store_location` - ZIP/region if available
- `page_type` - "PDP" (single) or "PLP" (listing)
- `search_query` - Search term if from search
- `url` - Source page URL
- `timestamp` - When captured
- `user_id` - Extension user ID

## Files

- `manifest.json` - Extension config + permissions
- `content-scripts/target.js` - Target.com price extraction
- `background.js` - Service worker for queuing/batching
- `popup.html/js/css` - Extension popup UI
- `README.md` - This file

## Next Steps

1. Test with live Target site
2. Add content scripts for other domains (Walmart, Amazon, Kroger, etc.)
3. Implement real batching (currently MVP sends individually)
4. Build frontend dashboard
5. Build conversational agent layer

## Debugging

Enable debug logging:
- In `content-scripts/target.js`: `CONFIG.debug = true`
- In `background.js`: `CONFIG.debug = true`
- Open Chrome DevTools → Extensions tab → check "Developer mode" output
