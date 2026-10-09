/**
 * Amazon.com Content Script
 * Extracts product data from Amazon product pages (PDPs and PLPs)
 * Focus on Fresh/Grocery products
 */

console.log('[ShoppingAgent] Amazon content script loaded');

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

// Extract product data from Amazon product detail page (PDP)
function extractFromPDP() {
  try {
    // Amazon stores ASIN in data attributes or URL
    const asin = extractASIN();
    if (!asin) return null;

    // Get product title
    const titleElement = document.querySelector('h1 span[data-a-color="base"]') ||
                        document.querySelector('#productTitle');
    const title = titleElement?.textContent?.trim();

    // Get price
    const priceElement = document.querySelector('.a-price-whole') ||
                        document.querySelector('[data-a-color="price"]');
    const price = parsePrice(priceElement?.textContent);

    if (!title || !price) return null;

    const product = {
      user_id: getUserId(),
      platform: 'amazon',
      domain: 'amazon.com',
      product_id: asin,
      product_name: title,
      price: price,
      store_location: null,
      page_type: 'PDP',
      search_query: null,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    if (CONFIG.debug) console.log('[ShoppingAgent] Extracted Amazon PDP:', product);

    return product;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Amazon PDP data:', error);
    return null;
  }
}

// Extract product data from Amazon search/category pages (PLPs)
function extractFromPLP() {
  try {
    const products = [];

    // Amazon uses [data-component-type="s-search-result"] for search results
    const productCards = document.querySelectorAll('[data-component-type="s-search-result"]');

    productCards.forEach((card) => {
      try {
        // Extract ASIN
        const asin = card.getAttribute('data-asin');
        if (!asin) return;

        // Extract title
        const titleElement = card.querySelector('h2 a span') ||
                            card.querySelector('[class*="title"]');
        const title = titleElement?.textContent?.trim();

        // Extract price
        const priceElement = card.querySelector('.a-price-whole') ||
                            card.querySelector('[class*="price"]');
        const price = parsePrice(priceElement?.textContent);

        if (!title || !price) return;

        const product = {
          user_id: getUserId(),
          platform: 'amazon',
          domain: 'amazon.com',
          product_id: asin,
          product_name: title,
          price: price,
          store_location: null,
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

    if (CONFIG.debug) console.log(`[ShoppingAgent] Extracted ${products.length} products from Amazon PLP`);

    return products;
  } catch (error) {
    if (CONFIG.debug) console.error('[ShoppingAgent] Error extracting Amazon PLP data:', error);
    return [];
  }
}

// Helper: Extract ASIN from URL or page
function extractASIN() {
  const match = window.location.href.match(/\/dp\/([A-Z0-9]{10})/);
  if (match) return match[1];

  const asinElement = document.querySelector('[data-asin]');
  return asinElement?.getAttribute('data-asin');
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
  return params.get('k') || null;
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
