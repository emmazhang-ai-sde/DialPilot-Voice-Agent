/**
 * DialForge API Settings API Integration Layer
 * 
 * API Settings-specific API operations:
 * - Vendor/API connection status (GET /api/status)
 * - Webhook event history (GET /api/zapier/webhook/log)
 * - Test webhook delivery (POST /api/zapier/trigger)
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const API_SETTINGS_CACHE_KEYS = {
  STATUS_BOARD: 'api_settings_status_board',
  WEBHOOK_LOG: 'api_settings_webhook_log'
};

// ============================================================================
// STATUS BOARD
// ============================================================================

/**
 * Get API status from backend
 * 
 * @returns {Promise<Object>} API status with configured, missing, demo_mode
 */
async function getApiStatus() {
  try {
    const response = await dialforgeApi.fetch('/api/status', {
      fallbackKey: API_SETTINGS_CACHE_KEYS.STATUS_BOARD,
      fallbackValue: {
        configured: {},
        missing: [],
        demo_mode: [],
        status: 'unavailable'
      }
    });

    if (!response) {
      return {
        configured: {},
        missing: [],
        demo_mode: [],
        status: 'unavailable'
      };
    }

    return {
      configured: response.configured || {},
      missing: response.missing || [],
      demo_mode: response.demo_mode || [],
      status: response.status || 'unknown'
    };
  } catch (error) {
    console.error('[API Settings API] Error fetching API status:', error);
    return {
      configured: {},
      missing: [],
      demo_mode: [],
      status: 'unavailable'
    };
  }
}

/**
 * Get vendor status badge information
 * 
 * @param {string} vendor - Vendor name
 * @param {Object} status - API status from getApiStatus()
 * @returns {Object} { vendor, statusText, badgeClass, icon }
 */
function getVendorStatusBadge(vendor, status) {
  if (!status) {
    return {
      vendor: vendor,
      statusText: 'Unknown',
      badgeClass: 'bg-white/5 text-on-surface-variant',
      icon: 'help'
    };
  }

  const vendorLower = vendor.toLowerCase();
  
  // Check if missing
  if (Array.isArray(status.missing) && status.missing.includes(vendorLower)) {
    return {
      vendor: vendor,
      statusText: 'Missing Configuration',
      badgeClass: 'bg-error-red/10 text-error-red border-error-red/30',
      icon: 'cancel'
    };
  }

  // Check if demo mode
  if (Array.isArray(status.demo_mode) && status.demo_mode.includes(vendorLower)) {
    return {
      vendor: vendor,
      statusText: 'Demo Mode',
      badgeClass: 'bg-secondary/10 text-secondary border-secondary/30',
      icon: 'info'
    };
  }

  // Check if configured
  if (status.configured && status.configured[vendorLower]) {
    return {
      vendor: vendor,
      statusText: 'Connected',
      badgeClass: 'bg-tertiary/10 text-tertiary border-tertiary/30',
      icon: 'check_circle'
    };
  }

  return {
    vendor: vendor,
    statusText: 'Not Configured',
    badgeClass: 'bg-white/5 text-on-surface-variant',
    icon: 'cancel'
  };
}

// ============================================================================
// WEBHOOK EVENT LOG
// ============================================================================

/**
 * Get webhook event log from backend
 * 
 * @returns {Promise<Array>} Array of webhook events
 */
async function getWebhookLog() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: API_SETTINGS_CACHE_KEYS.WEBHOOK_LOG,
      fallbackValue: []
    });

    if (!response) {
      return [];
    }

    const events = Array.isArray(response)
      ? response
      : (response.data || response.events || []);

    return Array.isArray(events) ? events : [];
  } catch (error) {
    console.error('[API Settings API] Error fetching webhook log:', error);
    return [];
  }
}

/**
 * Format webhook event for display
 * 
 * @param {Object} event - Webhook event
 * @returns {Object} Formatted event
 */
function formatWebhookEvent(event) {
  if (!event) return null;

  const timestamp = event.timestamp || event.created_at || 'Unknown';
  const eventType = event.event_type || event.type || 'Unknown';
  const status = event.status || 'unknown';

  return {
    id: event.id || `event-${Date.now()}`,
    timestamp: timestamp,
    event_type: eventType,
    status: status
  };
}

// ============================================================================
// TEST WEBHOOK
// ============================================================================

/**
 * Send test webhook payload to Zapier
 * 
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function sendTestWebhook() {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return {
        success: false,
        message: 'API not available'
      };
    }

    // Use the static payload as specified
    const payload = {
      event: 'ping',
      test: true
    };

    console.log('[API Settings API] Sending test webhook:', payload);

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

    return {
      success: true,
      message: 'Test webhook sent successfully'
    };
  } catch (error) {
    console.error('[API Settings API] Error sending test webhook:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const apiSettingsAPI = {
  // Status board
  getApiStatus,
  getVendorStatusBadge,

  // Webhook log
  getWebhookLog,
  formatWebhookEvent,

  // Test webhook
  sendTestWebhook,

  // Cache keys
  cacheKeys: API_SETTINGS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.apiSettingsAPI = apiSettingsAPI;
}