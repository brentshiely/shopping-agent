/**
 * Background Service Worker
 * Manages extension state, messaging, and eventually batching
 */

console.log('[ShoppingAgent] Background service worker loaded');

// Configuration
const CONFIG = {
  backend_url: 'https://shoppingagent.brentshiely.workers.dev',
  batch_interval_ms: 60000, // 1 minute
  batch_size: 50,
  debug: true,
};

// In-memory batch queue (will be persisted to storage later)
let batchQueue = [];
let batchTimer = null;

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (CONFIG.debug) console.log('[ShoppingAgent] Message received:', request);

  if (request.action === 'logPrice') {
    // Content scripts can send price data via message
    addToBatch(request.data);
    sendResponse({ status: 'queued' });
  } else if (request.action === 'getStatus') {
    sendResponse({
      queueSize: batchQueue.length,
      debug: CONFIG.debug,
    });
  }
});

// Add product to batch queue
function addToBatch(product) {
  batchQueue.push(product);

  if (CONFIG.debug) console.log(`[ShoppingAgent] Product queued. Queue size: ${batchQueue.length}`);

  // Start batching timer if not already running
  if (!batchTimer) {
    batchTimer = setTimeout(flushBatch, CONFIG.batch_interval_ms);
  }

  // Flush if batch reaches size limit
  if (batchQueue.length >= CONFIG.batch_size) {
    clearTimeout(batchTimer);
    flushBatch();
  }
}

// Get or create user ID
async function getUserId() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['userId'], (result) => {
      if (result.userId) {
        resolve(result.userId);
      } else {
        // Generate new user ID
        const newUserId = crypto.randomUUID();
        chrome.storage.local.set({ userId: newUserId }, () => {
          resolve(newUserId);
        });
      }
    });
  });
}

// Send queued products to backend
async function flushBatch() {
  if (batchQueue.length === 0) {
    batchTimer = null;
    return;
  }

  const toSend = [...batchQueue];
  batchQueue = [];

  // Add user_id to each product before sending
  const userId = await getUserId();
  const productsWithUserId = toSend.map(product => ({
    ...product,
    user_id: userId
  }));

  if (CONFIG.debug) console.log(`[ShoppingAgent] Flushing ${productsWithUserId.length} items to backend`);

  try {
    const response = await fetch(`${CONFIG.backend_url}/api/v1/price-captures/batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(productsWithUserId),
    });

    if (!response.ok) {
      console.error('[ShoppingAgent] Backend error:', response.statusText);
      // Re-queue items if send failed
      batchQueue.unshift(...toSend);
      batchTimer = setTimeout(flushBatch, CONFIG.batch_interval_ms);
      return;
    }

    const result = await response.json();
    if (CONFIG.debug) console.log('[ShoppingAgent] Batch sent successfully:', result);
  } catch (error) {
    console.error('[ShoppingAgent] Error sending batch:', error);
    console.error('[ShoppingAgent] Error details:', {
      message: error.message,
      name: error.name,
      url: `${CONFIG.backend_url}/api/v1/price-captures/batch`
    });
    // Re-queue items if send failed with exponential backoff
    batchQueue.unshift(...toSend);
    const retryDelay = Math.min(CONFIG.batch_interval_ms * 2, 30000); // Max 30 seconds
    batchTimer = setTimeout(flushBatch, retryDelay);
  }

  // Reset timer
  batchTimer = null;
}

// Periodic flush (in case batch never reaches size limit)
setInterval(() => {
  if (batchQueue.length > 0) {
    if (CONFIG.debug) console.log('[ShoppingAgent] Periodic batch flush');
    flushBatch();
  }
}, CONFIG.batch_interval_ms);

// Handle extension icon click - toggle side panel
chrome.action.onClicked.addListener((tab) => {
  if (CONFIG.debug) console.log('[ShoppingAgent] Extension icon clicked on tab:', tab.id);

  // Open the side panel for this tab
  chrome.sidePanel.open({ tabId: tab.id });
});
