/**
 * DialForge Billing & Subscription API Integration Layer
 * 
 * Billing-specific API operations:
 * - API tier and feature access status
 * - Organization details (if available)
 * - Seat allocation information (if available)
 * - Upgrade request notifications
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const BILLING_CACHE_KEYS = {
  API_STATUS: 'billing_api_status',
  ORGANIZATION_DETAILS: 'billing_org_details',
  UPGRADE_REQUEST: 'billing_last_upgrade_request'
};

// ============================================================================
// API STATUS & FEATURE ACCESS
// ============================================================================

/**
 * Get API status and feature access information
 * 
 * @returns {Promise<Object>} { configured, mode, missing, status }
 */
async function getApiStatus() {
  try {
    const response = await dialforgeApi.fetch('/api/status', {
      fallbackKey: BILLING_CACHE_KEYS.API_STATUS,
      fallbackValue: {
        configured: {},
        status: 'unavailable',
        mode: 'demo',
        missing: []
      }
    });

    if (!response) {
      return {
        configured: {},
        status: 'unavailable',
        mode: 'demo',
        missing: []
      };
    }

    return {
      configured: response.configured || {},
      status: response.status || 'unavailable',
      mode: response.mode || 'demo',
      missing: response.missing || []
    };
  } catch (error) {
    console.error('[Billing API] Error fetching API status:', error);
    return {
      configured: {},
      status: 'unavailable',
      mode: 'demo',
      missing: []
    };
  }
}

/**
 * Get feature status for a specific vendor
 * 
 * @param {string} vendor - Vendor name (e.g., 'hubspot', 'zendesk', 'apollo', 'zapier')
 * @param {Object} status - API status object from getApiStatus()
 * @returns {Object} { vendor, status, mode, message }
 */
function getVendorFeatureStatus(vendor, status) {
  if (!status || !status.configured) {
    return {
      vendor: vendor,
      status: 'unavailable',
      mode: 'unknown',
      message: 'Status unavailable'
    };
  }

  const vendorLower = vendor.toLowerCase();
  const vendorConfig = status.configured[vendorLower];

  if (!vendorConfig) {
    return {
      vendor: vendor,
      status: 'unavailable',
      mode: 'unknown',
      message: 'Not configured'
    };
  }

  if (vendorConfig.configured === false) {
    return {
      vendor: vendor,
      status: 'unavailable',
      mode: 'none',
      message: 'Missing configuration'
    };
  }

  if (vendorConfig.configured === true) {
    const mode = vendorConfig.mode || 'standard';
    
    if (mode === 'demo') {
      return {
        vendor: vendor,
        status: 'available',
        mode: 'demo',
        message: 'Demo Mode'
      };
    } else if (mode === 'live') {
      return {
        vendor: vendor,
        status: 'active',
        mode: 'live',
        message: 'Connected'
      };
    } else {
      return {
        vendor: vendor,
        status: 'available',
        mode: mode,
        message: `${mode.charAt(0).toUpperCase()}${mode.slice(1)}`
      };
    }
  }

  return {
    vendor: vendor,
    status: 'unknown',
    mode: 'unknown',
    message: 'Unknown status'
  };
}

/**
 * Check if a vendor has a specific capability
 * 
 * For Apollo, checks for master key capability
 * 
 * @param {string} vendor - Vendor name
 * @param {string} capability - Capability name (e.g., 'master_key', 'search')
 * @param {Object} status - API status object
 * @returns {boolean} True if capability is available
 */
function hasVendorCapability(vendor, capability, status) {
  if (!status || !status.configured) {
    return false;
  }

  const vendorLower = vendor.toLowerCase();
  const vendorConfig = status.configured[vendorLower];

  if (!vendorConfig || !vendorConfig.configured) {
    return false;
  }

  // Special handling for Apollo master key
  if (vendorLower === 'apollo' && capability === 'search') {
    // If configured and not in demo mode, assume search is available
    return vendorConfig.mode === 'live';
  }

  return vendorConfig.configured === true;
}

// ============================================================================
// ORGANIZATION DETAILS
// ============================================================================

/**
 * Get organization details
 * 
 * NOTE: Backend does not currently expose organization details via HTTP endpoint.
 * This function documents the limitation and returns placeholder structure.
 * 
 * @returns {Promise<Object>} Organization details (if available)
 */
async function getOrganizationDetails() {
  try {
    // Check localStorage for cached organization details
    const cached = localStorage.getItem(BILLING_CACHE_KEYS.ORGANIZATION_DETAILS);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide /api/organization endpoint
    // This would need to be added by backend team if organization details
    // are needed for the billing page.
    
    // Return empty/default organization object
    return {
      id: null,
      name: 'Organization',
      currency: 'USD',
      seatTypes: [],
      isAvailable: false,
      error: 'Organization details not available from backend'
    };
  } catch (error) {
    console.error('[Billing API] Error getting organization details:', error);
    return {
      id: null,
      name: 'Organization',
      currency: 'USD',
      seatTypes: [],
      isAvailable: false,
      error: error.message
    };
  }
}

/**
 * Get seat allocation information
 * 
 * NOTE: Backend does not currently expose seat allocation data via HTTP endpoint.
 * This function documents the limitation.
 * 
 * @returns {Promise<Object>} Seat allocation data (if available)
 */
async function getSeatAllocations() {
  try {
    // Backend does not currently provide seat allocation endpoint
    // This would need to be added by backend team if seat management is needed.
    
    return {
      seats: [],
      isAvailable: false,
      error: 'Seat allocation data not available from backend'
    };
  } catch (error) {
    console.error('[Billing API] Error getting seat allocations:', error);
    return {
      seats: [],
      isAvailable: false,
      error: error.message
    };
  }
}

// ============================================================================
// UPGRADE REQUEST
// ============================================================================

/**
 * Send upgrade request notification through Zapier
 * 
 * @param {Object} upgradeRequest - Upgrade request data
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function requestUpgrade(upgradeRequest) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return {
        success: false,
        message: 'API not available'
      };
    }

    if (!upgradeRequest) {
      return {
        success: false,
        message: 'No upgrade request data provided'
      };
    }

    // Build payload for Zapier webhook
    const payload = {
      type: 'upgrade_request',
      feature: upgradeRequest.feature || 'Unknown',
      currentTier: upgradeRequest.currentTier || 'starter',
      requestedTier: upgradeRequest.requestedTier || 'pro',
      reason: upgradeRequest.reason || '',
      timestamp: new Date().toISOString(),
      source: 'billing_page'
    };

    console.log('[Billing API] Sending upgrade request:', payload);

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Webhook trigger failed'
      };
    }

    // Store in localStorage for reference
    const requests = JSON.parse(localStorage.getItem(BILLING_CACHE_KEYS.UPGRADE_REQUEST) || '[]');
    requests.push({
      ...upgradeRequest,
      timestamp: new Date().toISOString(),
      success: true
    });
    localStorage.setItem(BILLING_CACHE_KEYS.UPGRADE_REQUEST, JSON.stringify(requests.slice(-10)));

    return {
      success: true,
      message: 'Upgrade request sent successfully. Our team will contact you soon.'
    };
  } catch (error) {
    console.error('[Billing API] Error requesting upgrade:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

/**
 * Get recent upgrade requests
 * 
 * @returns {Array} Array of upgrade request records
 */
function getUpgradeRequestHistory() {
  try {
    const stored = localStorage.getItem(BILLING_CACHE_KEYS.UPGRADE_REQUEST);
    return stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error('[Billing API] Error getting upgrade history:', error);
    return [];
  }
}

// ============================================================================
// FORMATTING HELPERS
// ============================================================================

/**
 * Get status badge color and icon
 * 
 * @param {string} status - Status value ('active', 'available', 'unavailable', 'unknown')
 * @returns {Object} { color, icon, label }
 */
function getStatusBadgeStyle(status) {
  const styles = {
    'active': {
      color: 'text-tertiary bg-tertiary/10',
      icon: 'check_circle',
      label: 'Active'
    },
    'available': {
      color: 'text-secondary bg-secondary/10',
      icon: 'circle',
      label: 'Available'
    },
    'unavailable': {
      color: 'text-on-surface-variant bg-white/5',
      icon: 'cancel',
      label: 'Unavailable'
    },
    'unknown': {
      color: 'text-on-surface-variant bg-white/5',
      icon: 'help',
      label: 'Unknown'
    }
  };

  return styles[status] || styles['unknown'];
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const billingAPI = {
  // API status
  getApiStatus,
  getVendorFeatureStatus,
  hasVendorCapability,

  // Organization
  getOrganizationDetails,
  getSeatAllocations,

  // Upgrade
  requestUpgrade,
  getUpgradeRequestHistory,

  // Formatting
  getStatusBadgeStyle,

  // Cache keys
  cacheKeys: BILLING_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.billingAPI = billingAPI;
}