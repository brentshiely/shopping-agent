/**
 * Walmart.com Content Script
 * Runs in the page context and extracts product data
 * Sends via chrome.runtime.sendMessage to background script for relay + user_id injection
 */

console.log('[ShoppingAgent] Walmart content script loaded on', window.location.href);

// Send diagnostic message via background script
if (chrome && chrome.runtime) {
  chrome.runtime.sendMessage({
    action: 'logPrice',
    data: {
      platform: 'walmart',
      domain: 'walmart.com',
      product_id: 'diagnostic',
      product_name: 'CONTENT_SCRIPT_LOADED_' + new Date().getTime(),
      price: 0.01,  // Use 0.01 instead of 0 to pass validation
      page_type: 'DIAGNOSTIC',
      search_query: null,
      store_location: null,
      url: window.location.href,
      timestamp: new Date().toISOString()
    }
  }, (response) => {
    if (response) {
      console.log('[ShoppingAgent] Diagnostic sent:', response);
    }
  });
}

// Extract and send product data
function captureProduct() {
  try {
    // Check if this is a product page by looking for SKU in URL
    const urlMatch = window.location.pathname.match(/\/ip\/([^/?]+)/);
    if (!urlMatch || !/^\d+$/.test(urlMatch[1])) {
      console.log('[ShoppingAgent] Not a product page');
      return;
    }

    const sku = urlMatch[1];
    console.log('[ShoppingAgent] Found product SKU:', sku);

    // Extract product name
    const h1 = document.querySelector('h1');
    const productName = h1?.textContent?.trim() || 'Unknown Product';
    console.log('[ShoppingAgent] Product name:', productName);

    // Extract price
    let price = null;
    const priceSelectors = [
      '[data-testid="product-price"]',
      '[class*="Price"]',
      '.Price',
      '[itemprop="price"]'
    ];

    for (const selector of priceSelectors) {
      const el = document.querySelector(selector);
      if (el) {
        const match = el.textContent?.match(/\$\s?(\d+\.?\d{0,2})/);
        if (match) {
          price = parseFloat(match[1]);
          console.log('[ShoppingAgent] Found price:', price);
          break;
        }
      }
    }

    // Fallback: search page text
    if (!price) {
      const bodyMatch = document.body.innerText.match(/\$\s?(\d+\.?\d{0,2})/);
      if (bodyMatch) {
        price = parseFloat(bodyMatch[1]);
        console.log('[ShoppingAgent] Found price from body:', price);
      }
    }

    if (!price) {
      console.log('[ShoppingAgent] Could not extract price');
      return;
    }

    // Send to background script via message
    if (chrome && chrome.runtime) {
      chrome.runtime.sendMessage({
        action: 'logPrice',
        data: {
          platform: 'walmart',
          domain: 'walmart.com',
          product_id: sku,
          product_name: productName,
          price: price,
          page_type: 'PDP',
          search_query: null,
          store_location: null,
          url: window.location.href,
          timestamp: new Date().toISOString()
        }
      }, (response) => {
        if (response) {
          console.log('[ShoppingAgent] ✓ Product sent to backend:', response);
        }
      });
    }

  } catch (error) {
    console.error('[ShoppingAgent] Error in captureProduct:', error);
  }
}

// Run on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', captureProduct);
} else {
  captureProduct();
}

// Also run on dynamic updates
const observer = new MutationObserver(() => {
  captureProduct();
});

observer.observe(document.body, {
  childList: true,
  subtree: true,
});
