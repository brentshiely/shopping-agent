/**
 * Kroger.com Content Script
 * Extracts product data from Kroger product pages (PDPs and PLPs)
 */

console.log('[ShoppingAgent] Kroger content script loaded');

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

// Extract product data from Kroger product detail page (PDP)
function extractFromPDP() {
  try {
    // Kroger stores product data in data attributes and spans
    const productName = document.querySelector('[data-testid="product-title"]') ||
                       document.querySelector('h1');
    const nameText = productName?.textContent?.trim();

    if (!nameText) return null;

    const priceElement = document.querySelector('[data-testid="product-price"]') ||
                        document.querySelector('[class*="price"]');

    const productId = extractProductId();
    if (!productId) return null;

    const product = {
      user_id: getUserId(),
      platform: 'kroger',
      domain: 'kroger.com',
      product_id: productId,
      product_name: nameText,
      price: parsePrice(priceElement?.textContent),
      store_location: extractStoreLocation(),
      page_type: 'PDP',
      search_query: null,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    if (CONFIG.debug) console.log('[ShoppingAgent] Extracted Kroger PDP:', product);

    return product;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Kroger PDP data:', error);
    return null;
  }
}

// Extract product data from Kroger search/category pages (PLPs)
function extractFromPLP() {
  try {
    const products = [];

    // Kroger uses [data-testid="product-tile"] for product cards in lists
    const productCards = document.querySelectorAll('[data-testid="product-tile"]') ||
                        document.querySelectorAll('[class*="product-tile"]');

    productCards.forEach((card) => {
      try {
        // Extract product name
        const nameElement = card.querySelector('[data-testid="product-title"]') ||
                           card.querySelector('h3');
        const name = nameElement?.textContent?.trim();

        // Extract product ID from card
        const productId = card.getAttribute('data-product-id') ||
                         card.querySelector('[data-testid]')?.getAttribute('data-testid');

        // Extract price
        const priceElement = card.querySelector('[data-testid="product-price"]') ||
                            card.querySelector('[class*="price"]');
        const price = parsePrice(priceElement?.textContent);

        if (!name || !productId || !price) return;

        const product = {
          user_id: getUserId(),
          platform: 'kroger',
          domain: 'kroger.com',
          product_id: productId,
          product_name: name,
          price: price,
          store_location: extractStoreLocation(),
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

    if (CONFIG.debug) console.log(`[ShoppingAgent] Extracted ${products.length} products from Kroger PLP`);

    return products;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Kroger PLP data:', error);
    return [];
  }
}

// Helper: Extract product ID from URL or page
function extractProductId() {
  const match = window.location.href.match(/product\/(\d+)/);
  if (match) return match[1];

  const idElement = document.querySelector('[data-product-id]');
  return idElement?.getAttribute('data-product-id');
}

// Helper: Extract price from price text
function parsePrice(priceText) {
  if (!priceText) return null;
  const match = priceText.match(/\$?([\d.]+)/);
  return match ? parseFloat(match[1]) : null;
}

// Helper: Extract store location from page
function extractStoreLocation() {
  // Kroger shows selected store
  const storeInfo = document.querySelector('[data-testid="selected-store"]')?.textContent ||
                   document.querySelector('[class*="store"]')?.textContent;
  if (storeInfo) {
    const match = storeInfo.match(/(\d{5})/);
    if (match) return match[1];
  }
  return null;
}

// Helper: Extract search query from URL
function extractSearchQuery() {
  const params = new URLSearchParams(window.location.search);
  return params.get('query') || params.get('q') || null;
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
