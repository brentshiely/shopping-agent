/**
 * Extension Popup Script
 * Displays extension status and user interactions
 */

// Get user ID
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

// Update status display
function updateStatus() {
  chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
    if (response) {
      document.getElementById('queue-size').textContent = response.queueSize;
    }
  });

  document.getElementById('user-id').textContent = getUserId();
}

// Button handlers
document.getElementById('open-dashboard').addEventListener('click', () => {
  chrome.tabs.create({ url: 'http://localhost:3000' }); // TODO: update to production URL
});

document.getElementById('settings').addEventListener('click', () => {
  // TODO: Open settings page
  alert('Settings coming soon');
});

// File upload handlers
const uploadBox = document.getElementById('upload-box');
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-input');
const uploadStatus = document.getElementById('upload-status');
const uploadResults = document.getElementById('upload-results');

// Click to select files
uploadBtn.addEventListener('click', () => {
  fileInput.click();
});

// Drag and drop
uploadBox.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadBox.classList.add('dragover');
});

uploadBox.addEventListener('dragleave', () => {
  uploadBox.classList.remove('dragover');
});

uploadBox.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadBox.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});

// File selection
fileInput.addEventListener('change', (e) => {
  handleFiles(e.target.files);
});

// Handle file upload
async function handleFiles(files) {
  if (files.length === 0) return;

  const formData = new FormData();
  const userId = getUserId();

  // Add user ID and files
  formData.append('user_id', userId);

  for (let file of files) {
    formData.append('files', file);
  }

  try {
    // Show upload status
    uploadStatus.style.display = 'block';
    uploadResults.style.display = 'none';
    document.getElementById('upload-message').textContent =
      `Uploading ${files.length} file${files.length > 1 ? 's' : ''}...`;

    // Simulate progress (real progress would come from fetch events)
    let progress = 0;
    const progressInterval = setInterval(() => {
      progress = Math.min(progress + Math.random() * 30, 90);
      document.getElementById('progress-fill').style.width = progress + '%';
    }, 200);

    // Send to backend
    const response = await fetch('http://localhost:8000/api/v1/import/historical', {
      method: 'POST',
      body: formData,
      // Note: Don't set Content-Type header, let the browser set it with boundary
    });

    clearInterval(progressInterval);
    document.getElementById('progress-fill').style.width = '100%';

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    const result = await response.json();

    // Show results
    uploadStatus.style.display = 'none';
    uploadResults.style.display = 'block';
    document.getElementById('results-message').innerHTML =
      `✓ Imported ${result.imported_count || 0} products<br>` +
      `${result.skipped_count > 0 ? `Skipped: ${result.skipped_count}<br>` : ''}` +
      `${result.message || 'Import complete'}`;

    // Reset file input
    fileInput.value = '';

    // Refresh status after a moment
    setTimeout(updateStatus, 500);

  } catch (error) {
    clearInterval(progressInterval);
    console.error('Upload error:', error);

    uploadStatus.style.display = 'none';
    uploadResults.style.display = 'block';
    document.getElementById('results-message').innerHTML =
      `❌ Upload failed: ${error.message}`;

    fileInput.value = '';
  }
}

// Copy user ID
document.getElementById('copy-user-id').addEventListener('click', () => {
  const userId = getUserId();
  navigator.clipboard.writeText(userId).then(() => {
    const btn = document.getElementById('copy-user-id');
    const originalText = btn.textContent;
    btn.textContent = '✓';
    setTimeout(() => {
      btn.textContent = originalText;
    }, 2000);
  });
});

// Best deals display
async function loadBestDeals() {
  try {
    const response = await fetch('http://localhost:8000/api/v1/price-captures?limit=50');
    if (!response.ok) return;

    const prices = await response.json();
    const container = document.getElementById('best-deals-container');

    if (prices.length === 0) {
      container.innerHTML = '<div class="no-deals">Browse stores to see best deals</div>';
      return;
    }

    // Group by product and find best price for each
    const productDeals = {};
    prices.forEach(p => {
      if (!productDeals[p.product_name]) {
        productDeals[p.product_name] = [];
      }
      productDeals[p.product_name].push(p);
    });

    // Find best deal overall
    let overallBestPrice = Infinity;
    let overallBestProduct = null;

    const dealsHtml = Object.entries(productDeals)
      .map(([productName, captures]) => {
        // Find cheapest price for this product
        const best = captures.reduce((min, p) => p.price < min.price ? p : min);

        if (best.price < overallBestPrice) {
          overallBestPrice = best.price;
          overallBestProduct = productName;
        }

        const isOverallBest = productName === overallBestProduct && best.price === overallBestPrice;

        return `
          <div class="deal-item ${isOverallBest ? 'best' : ''}">
            <div class="deal-product-info">
              <div class="deal-product-name">${productName.substring(0, 25)}${productName.length > 25 ? '...' : ''}</div>
              <div class="deal-product-store">${best.platform.toUpperCase()}${best.store_location ? ' • ' + best.store_location : ''}</div>
            </div>
            <div class="deal-price-box">
              <div class="deal-item-price">$${best.price.toFixed(2)}</div>
            </div>
          </div>
        `;
      })
      .join('');

    container.innerHTML = dealsHtml;
  } catch (error) {
    console.error('Error loading best deals:', error);
  }
}

// Update status on popup open
updateStatus();
loadBestDeals();

// Refresh status every 2 seconds
setInterval(() => {
  updateStatus();
  loadBestDeals();
}, 2000);
