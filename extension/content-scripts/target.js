/**
 * Target.com Content Script
 * Extracts product data from Target product pages (PDPs and PLPs)
 */

console.log('[Profit Capture] Target content script loaded');

// Configuration
const CONFIG = {
  backend_url: 'http://localhost:8000/api/v1/price-captures',
  debug: true,
};

// Generate or retrieve user ID
function getUserId() {
  let userId = localStorage.getItem('shoppingagent_user_id');
  if (!userId) {
    userId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
    localStorage.setItem('shoppingagent_user_id', userId);
  }
  return userId;
}

// Extract product data from Target product detail page (PDP)
function extractFromPDP() {
  try {
    // Target stores product data in __NEXT_DATA__ script tag
    const script = document.querySelector('script#__NEXT_DATA__');
    if (!script) return null;

    const data = JSON.parse(script.textContent);

    // Navigate the Next.js data structure to find product info
    const productData = data?.props?.pageProps?.initialState?.product?.productV2 || {};

    if (!productData.tcin) return null;

    // Extract fields
    const product = {
      user_id: getUserId(),
      platform: 'target',
      domain: 'target.com',
      product_id: productData.tcin,
      product_name: productData.title || 'Unknown Product',
      price: extractPrice(productData),
      store_location: extractStoreLocation(),
      page_type: 'PDP',
      search_query: null,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    if (CONFIG.debug) console.log('[Profit Capture] Extracted PDP:', product);

    return product;
  } catch (error) {
    if (CONFIG.debug) console.error('[Profit Capture] Error extracting PDP data:', error);
    return null;
  }
}

// Extract product data from Target search/category pages (PLPs)
function extractFromPLP() {
  try {
    const products = [];
    const foundTCINs = new Set(); // Track what we've already processed

    // Strategy 1: Look for product links directly
    const allProductLinks = document.querySelectorAll('a[href*="/p/"][href*=target]');
    if (CONFIG.debug) console.log(`[Profit Capture] Strategy 1: Found ${allProductLinks.length} product links`);

    // Strategy 2: Look for any link to a product page
    let cardContainers = document.querySelectorAll('[data-testid="product-card"]');
    if (cardContainers.length === 0) {
      cardContainers = document.querySelectorAll('article');
    }
    if (cardContainers.length === 0) {
      cardContainers = document.querySelectorAll('[class*="Card"][class*="product"], [class*="Product"][class*="Card"]');
    }

    if (CONFIG.debug) console.log(`[Profit Capture] Strategy 2: Found ${cardContainers.length} card containers`);

    // Process cards
    cardContainers.forEach((card) => {
      try {
        // Find product link within card
        const productLink = card.querySelector('a[href*="/p/"]') || card.closest('a[href*="/p/"]');
        if (!productLink) return;

        // Extract TCIN
        const tcin = productLink.href.match(/\/p\/(\d+)/)?.[1];
        if (!tcin || foundTCINs.has(tcin)) return;
        foundTCINs.add(tcin);

        // Extract name - try all text content from card
        let name = card.querySelector('[data-testid="product-title"]')?.textContent?.trim();
        if (!name) name = card.querySelector('h3, h2')?.textContent?.trim();
        if (!name) name = card.querySelector('a')?.getAttribute('title') || card.querySelector('a')?.textContent?.trim();
        if (!name) {
          // Get first meaningful text from card
          const textContent = card.textContent.trim();
          const lines = textContent.split('\n').filter(l => l.trim().length > 5 && l.trim().length < 100);
          if (lines.length > 0) name = lines[0].trim();
        }

        // Extract price - aggressive search
        let priceText;
        const priceSelectors = [
          '[data-testid="current-price"]',
          '[data-testid="product-price"]',
          '[class*="Price"]',
          'span:contains("$")'
        ];

        for (const selector of priceSelectors) {
          if (selector === 'span:contains("$")') {
            // Manual search for price
            const spans = Array.from(card.querySelectorAll('span'));
            const priceSpan = spans.find(s => s.textContent.match(/\$[\d.]+/));
            if (priceSpan) {
              priceText = priceSpan.textContent;
              break;
            }
          } else {
            const el = card.querySelector(selector);
            if (el) {
              priceText = el.textContent;
              break;
            }
          }
        }

        // Final fallback: search all text for price pattern
        if (!priceText) {
          const match = card.textContent.match(/\$[\d.]+/);
          if (match) priceText = match[0];
        }

        const price = parsePrice(priceText);

        if (!name || !price) {
          if (CONFIG.debug) console.log('[Profit Capture] Incomplete product - name:', !!name, 'price:', !!price);
          return;
        }

        const product = {
          user_id: getUserId(),
          platform: 'target',
          domain: 'target.com',
          product_id: tcin,
          product_name: name.substring(0, 200),
          price: price,
          store_location: extractStoreLocation(),
          page_type: 'PLP',
          search_query: extractSearchQuery(),
          url: window.location.href,
          timestamp: new Date().toISOString(),
        };

        products.push(product);
        if (CONFIG.debug) console.log('[Profit Capture] Captured:', product.product_name, '$' + product.price);
      } catch (e) {
        if (CONFIG.debug) console.log('[Profit Capture] Card error:', e.message);
      }
    });

    if (CONFIG.debug) console.log(`[Profit Capture] Total extracted from PLP: ${products.length}`);

    return products;
  } catch (error) {
    if (CONFIG.debug) console.error('[Profit Capture] PLP extraction error:', error);
    return [];
  }
}

// Helper: Extract price from price text
function parsePrice(priceText) {
  if (!priceText) return null;
  const match = priceText.match(/\$?([\d.]+)/);
  return match ? parseFloat(match[1]) : null;
}

// Helper: Extract store location from page
function extractStoreLocation() {
  // Target shows "Nearby stores" - look for location selector
  const storeInfo = document.querySelector('[data-testid="store-selector"]')?.textContent;
  if (storeInfo) {
    const match = storeInfo.match(/(\d{5})/);
    if (match) return match[1];
  }
  return null;
}

// Helper: Extract search query from URL
function extractSearchQuery() {
  const params = new URLSearchParams(window.location.search);
  return params.get('searchTerm') || null;
}

// Send product data to backend
async function sendToBackend(product) {
  try {
    const response = await fetch(CONFIG.backend_url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(product),
    });

    if (!response.ok) {
      console.error('[Profit Capture] Backend error:', response.statusText);
      return false;
    }

    if (CONFIG.debug) console.log('[Profit Capture] Product sent to backend');
    return true;
  } catch (error) {
    console.error('[Profit Capture] Error sending to backend:', error);
    return false;
  }
}

// Send multiple products to backend (batch)
async function sendBatchToBackend(products) {
  if (products.length === 0) return;

  try {
    const response = await fetch(`${CONFIG.backend_url}/batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(products),
    });

    if (!response.ok) {
      console.error('[Profit Capture] Batch backend error:', response.statusText);
      return false;
    }

    if (CONFIG.debug) console.log(`[Profit Capture] Batch of ${products.length} products sent`);
    return true;
  } catch (error) {
    console.error('[Profit Capture] Error sending batch to backend:', error);
    return false;
  }
}

// Detect page type and extract accordingly
async function capturePageData() {
  // Check if it's a PDP (product detail page)
  const pdpProduct = extractFromPDP();
  if (pdpProduct) {
    await sendToBackend(pdpProduct);
    return;
  }

  // Check if it's a PLP (product listing page)
  const plpProducts = extractFromPLP();
  if (plpProducts.length > 0) {
    await sendBatchToBackend(plpProducts);
    return;
  }

  if (CONFIG.debug) console.log('[Profit Capture] No products detected on page');
}

// Run on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', capturePageData);
} else {
  capturePageData();
}

// Also run when page is updated (infinite scroll, etc)
const observer = new MutationObserver(() => {
  capturePageData();
});

observer.observe(document.body, {
  childList: true,
  subtree: true,
});
