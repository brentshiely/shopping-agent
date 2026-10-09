/**
 * Instacart.com Content Script
 * Extracts product data from Instacart product pages (PDPs and PLPs)
 * Note: Instacart aggregates from multiple retailers, tracks both Instacart ID and store
 */

console.log('[ShoppingAgent] Instacart content script loaded');

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

// Extract product data from Instacart product detail page (PDP)
function extractFromPDP() {
  try {
    // Instacart stores product data in data attributes
    const productTitle = document.querySelector('[data-testid="product-title"]') ||
                        document.querySelector('h1');
    const titleText = productTitle?.textContent?.trim();

    if (!titleText) return null;

    const priceElement = document.querySelector('[data-testid="product-price"]') ||
                        document.querySelector('[class*="Price"]');

    const productId = extractProductId();
    if (!productId) return null;

    // Get the current store/retailer
    const retailer = extractRetailer();

    const product = {
      user_id: getUserId(),
      platform: 'instacart',
      domain: 'instacart.com',
      product_id: productId,
      product_name: titleText,
      price: parsePrice(priceElement?.textContent),
      store_location: retailer, // In Instacart, this is the store/retailer
      page_type: 'PDP',
      search_query: null,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    if (CONFIG.debug) console.log('[ShoppingAgent] Extracted Instacart PDP:', product);

    return product;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Instacart PDP data:', error);
    return null;
  }
}

// Extract product data from Instacart search/category pages (PLPs)
function extractFromPLP() {
  try {
    const products = [];

    // Instacart uses role="button" on product items in search
    const productCards = document.querySelectorAll('[data-testid="product-item"]') ||
                        document.querySelectorAll('[class*="Product__Wrapper"]');

    productCards.forEach((card) => {
      try {
        // Extract title
        const titleElement = card.querySelector('[data-testid="product-title"]') ||
                            card.querySelector('[class*="Title"]');
        const title = titleElement?.textContent?.trim();

        // Extract product ID
        const productId = card.getAttribute('data-product-id') ||
                         extractIdFromCard(card);

        // Extract price
        const priceElement = card.querySelector('[data-testid="product-price"]') ||
                            card.querySelector('[class*="Price"]');
        const price = parsePrice(priceElement?.textContent);

        if (!title || !productId || !price) return;

        const product = {
          user_id: getUserId(),
          platform: 'instacart',
          domain: 'instacart.com',
          product_id: productId,
          product_name: title,
          price: price,
          store_location: extractRetailer(), // Current store
          page_type: 'PLP',
          search_query: extractSearchQuery(),
          url: window.location.href,
          timestamp: new Date().toISOString(),
        };

        products.push(product);
      } catch (e) {
        // Skip individual card errors
      }
    });

    if (CONFIG.debug) console.log(`[ShoppingAgent] Extracted ${products.length} products from Instacart PLP`);

    return products;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Instacart PLP data:', error);
    return [];
  }
}

// Helper: Extract product ID
function extractProductId() {
  const match = window.location.href.match(/products\/(\d+)/);
  if (match) return match[1];

  const idElement = document.querySelector('[data-product-id]');
  return idElement?.getAttribute('data-product-id');
}

// Helper: Extract ID from product card
function extractIdFromCard(card) {
  const link = card.querySelector('a[href*="/products/"]');
  const match = link?.href?.match(/\/products\/(\d+)/);
  return match ? match[1] : null;
}

// Helper: Extract current retailer/store
function extractRetailer() {
  // Instacart shows the selected store/retailer
  const storeElement = document.querySelector('[data-testid="selected-retailer"]') ||
                      document.querySelector('[class*="StoreName"]');
  return storeElement?.textContent?.trim() || 'Instacart';
}

// Helper: Extract price from price text
function parsePrice(priceText) {
  if (!priceText) return null;
  const match = priceText.match(/\$?([\d.]+)/);
  return match ? parseFloat(match[1]) : null;
}

// Helper: Extract search query from URL
function extractSearchQuery() {
  const params = new URLSearchParams(window.location.search);
  return params.get('q') || null;
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
      console.error('[ShoppingAgent] Backend error:', response.statusText);
      return false;
    }

    if (CONFIG.debug) console.log('[ShoppingAgent] Product sent to backend');
    return true;
  } catch (error) {
    console.error('[ShoppingAgent] Error sending to backend:', error);
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
      console.error('[ShoppingAgent] Batch backend error:', response.statusText);
      return false;
    }

    if (CONFIG.debug) console.log(`[ShoppingAgent] Batch of ${products.length} products sent`);
    return true;
  } catch (error) {
    console.error('[ShoppingAgent] Error sending batch to backend:', error);
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

  if (CONFIG.debug) console.log('[ShoppingAgent] No products detected on page');
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
