/**
 * Side Panel Script
 * Shows best deals from real-time price captures
 */

const BACKEND_URL = 'http://localhost:8000';
let allPrices = [];

// Load deals on page load
window.addEventListener('load', () => {
  loadDeals();
  // Refresh every 2 seconds for real-time updates
  setInterval(loadDeals, 2000);
});

async function loadDeals() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/price-captures?limit=50`);
    if (!response.ok) return;

    const prices = await response.json();
    allPrices = prices;

    updateCaptureCount();
    renderDeals();
    updateTimestamp();

  } catch (error) {
    console.error('Error loading deals:', error);
  }
}

function updateCaptureCount() {
  const count = allPrices.length;
  document.getElementById('capture-count').textContent = count;

  const statusDot = document.querySelector('.status-indicator');
  if (count > 0) {
    statusDot.classList.remove('inactive');
  }
}

function renderDeals() {
  const container = document.getElementById('deals-container');

  if (allPrices.length === 0) {
    container.innerHTML = '<div class="placeholder">Browse stores to see deals</div>';
    return;
  }

  // Group by product and find best price
  const productDeals = {};
  allPrices.forEach(p => {
    if (!productDeals[p.product_name]) {
      productDeals[p.product_name] = [];
    }
    productDeals[p.product_name].push(p);
  });

  // Find overall best deal
  let overallBestPrice = Infinity;
  let overallBestProduct = null;

  // Create deal items
  const dealsHtml = Object.entries(productDeals)
    .map(([productName, captures]) => {
      // Find cheapest for this product
      const best = captures.reduce((min, p) => p.price < min.price ? p : min);

      if (best.price < overallBestPrice) {
        overallBestPrice = best.price;
        overallBestProduct = productName;
      }

      const isOverallBest = productName === overallBestProduct && best.price === overallBestPrice;

      // Find second best for savings calculation
      const otherPrices = captures.filter(p => p.price !== best.price).map(p => p.price);
      const secondPrice = otherPrices.length > 0 ? Math.min(...otherPrices) : Infinity;
      const savings = secondPrice - best.price;

      return `
        <div class="deal-item ${isOverallBest ? 'best' : ''}">
          <div class="deal-header">
            <div class="deal-product">
              <div class="deal-name">${productName.substring(0, 30)}${productName.length > 30 ? '...' : ''}</div>
              <div class="deal-store">${best.platform.toUpperCase()}${best.store_location ? ' • ' + best.store_location : ''}</div>
            </div>
            <div class="deal-price">$${best.price.toFixed(2)}</div>
          </div>
          ${savings > 0 ? `<div class="deal-savings">Save $${savings.toFixed(2)}</div>` : ''}
        </div>
      `;
    })
    .join('');

  container.innerHTML = dealsHtml || '<div class="placeholder">No deals found</div>';
}

function updateTimestamp() {
  const lastUpdate = document.getElementById('last-update');
  const now = new Date();
  lastUpdate.textContent = `Updated ${now.toLocaleTimeString()}`;
}

// "View All" button opens full dashboard
document.getElementById('view-all').addEventListener('click', () => {
  chrome.tabs.create({ url: `${BACKEND_URL}/dashboard` });
});

// Periodically try to extract product data from the active tab
setInterval(async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) return;

    // Check if tab is a Walmart product page
    if (!tab.url.includes('walmart.com/ip/')) return;

    // Inject extraction code into the page
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: extractWalmartProduct
    });
  } catch (error) {
    // Silently fail if not able to inject script
  }
}, 5000); // Check every 5 seconds

// Function to run in the page context to extract product data
function extractWalmartProduct() {
  try {
    // Extract SKU from URL
    const urlMatch = window.location.pathname.match(/\/ip\/([^/?]+)/);
    if (!urlMatch || !/^\d+$/.test(urlMatch[1])) return;

    const sku = urlMatch[1];

    // Extract product name from h1
    const h1 = document.querySelector('h1');
    const productName = h1?.textContent?.trim() || 'Unknown Product';

    // Extract price - look for price patterns
    let price = null;
    const priceSelectors = [
      '[data-testid="product-price"]',
      '[itemprop="price"]',
      '[class*="Price"]',
      '.Price'
    ];

    for (const selector of priceSelectors) {
      const el = document.querySelector(selector);
      if (el) {
        const match = el.textContent?.match(/\$?\s?(\d+\.?\d{0,2})/);
        if (match) {
          price = parseFloat(match[1]);
          break;
        }
      }
    }

    if (!price) {
      const bodyMatch = document.body.innerText.match(/\$\s?(\d+\.?\d{0,2})/);
      if (bodyMatch) price = parseFloat(bodyMatch[1]);
    }

    if (!price) return;

    // Send to background script
    chrome.runtime.sendMessage({
      action: 'logPrice',
      data: {
        platform: 'walmart',
        domain: 'walmart.com',
        product_id: sku,
        product_name: productName,
        price: price,
        store_location: null,
        page_type: 'PDP',
        search_query: null,
        url: window.location.href,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error('Error extracting Walmart product:', error);
  }
}
