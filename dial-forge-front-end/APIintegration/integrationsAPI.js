/**
 * DialForge Integrations Hub API Integration Layer
 * 
 * Integrations-specific API operations:
 * - Fetch integration status from /api/status
 * - Display missing configuration warnings
 * - Test Zapier webhook trigger
 * - Verify webhook delivery in logs
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const INTEGRATIONS_CACHE_KEYS = {
  STATUS: 'integ_status',
  WEBHOOK_LOG: 'integ_webhook_log',
  LAST_TEST: 'integ_last_test'
};

// ============================================================================
// INTEGRATION STATUS
// ============================================================================

/**
 * Fetch integration status from backend
 * 
 * @returns {Promise<Object>} Integration status object with configured vendors
 */
async function getIntegrationStatus() {
  try {
    const response = await dialforgeApi.fetch('/api/status', {
      fallbackKey: INTEGRATIONS_CACHE_KEYS.STATUS,
      fallbackValue: {
        status: 'unavailable',
        configured: {},
        missing: []
      }
    });

    if (!response) {
      return {
        status: 'unavailable',
        configured: {},
        missing: [],
        timestamp: new Date().toISOString()
      };
    }

    return {
      status: response.status || 'available',
      configured: response.configured || {},
      missing: response.missing || [],
      timestamp: new Date().toISOString(),
      mode: response.mode || 'live'
    };
  } catch (error) {
    console.error('[Integrations API] Error fetching status:', error);
    return {
      status: 'unavailable',
      configured: {},
      missing: [],
      timestamp: new Date().toISOString(),
      error: error.message
    };
  }
}

/**
 * Determine if an integration is configured
 * 
 * @param {Object} status - Status object from getIntegrationStatus
 * @param {string} vendor - Vendor name (hubspot, zendesk, apollo, zapier)
 * @returns {Object} { configured: boolean, isDemo: boolean, status: string }
 */
function getIntegrationState(status, vendor) {
  if (!status || !status.configured) {
    return { configured: false, isDemo: true, status: 'unavailable' };
  }

  const vendorConfig = status.configured[vendor.toLowerCase()];
  
  if (!vendorConfig) {
    return { configured: false, isDemo: true, status: 'not_configured' };
  }

  // Check if it's demo or live
  const isDemo = vendorConfig.mode === 'demo' || vendorConfig.demo === true;
  const isConfigured = vendorConfig.configured === true || vendorConfig.live === true;

  return {
    configured: isConfigured,
    isDemo: isDemo,
    status: isConfigured ? (isDemo ? 'demo' : 'live') : 'not_configured'
  };
}

/**
 * Get missing configuration keys from backend
 * 
 * @param {Object} status - Status object from getIntegrationStatus
 * @returns {Array} Array of missing configuration keys
 */
function getMissingConfiguration(status) {
  if (!status || !status.missing) return [];
  return status.missing;
}

// ============================================================================
// ZAPIER TEST TRIGGER
// ============================================================================

/**
 * Send a test payload to Zapier webhook
 * 
 * @returns {Promise<Object>} { success: boolean, message: string, data: Object }
 */
async function triggerZapierTest() {
  try {
    // Build test payload
    const payload = {
      title: 'DialForge Test Webhook',
      message: 'This is a test payload from the Integrations Hub',
      type: 'test',
      timestamp: new Date().toISOString(),
      data: {
        source: 'integrations_hub_test',
        testId: `test-${Date.now()}`
      }
    };

    console.log('[Integrations API] Sending Zapier test payload:', payload);

    // Send to Zapier
    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Zapier trigger returned no response',
        data: null
      };
    }

    // Cache the test timestamp
    dialforgeApi.cacheData(INTEGRATIONS_CACHE_KEYS.LAST_TEST, {
      timestamp: new Date().toISOString(),
      testId: payload.data.testId
    });

    console.log('[Integrations API] Zapier test sent:', response);

    return {
      success: true,
      message: 'Test payload sent to Zapier',
      data: response
    };
  } catch (error) {
    console.error('[Integrations API] Error triggering Zapier test:', error);
    return {
      success: false,
      message: `Error: ${error.message}`,
      data: null,
      error
    };
  }
}

// ============================================================================
// WEBHOOK LOG VERIFICATION
// ============================================================================

/**
 * Fetch webhook activity log to verify delivery
 * 
 * @returns {Promise<Array>} Array of webhook events
 */
async function fetchWebhookLog() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: INTEGRATIONS_CACHE_KEYS.WEBHOOK_LOG,
      fallbackValue: []
    });

    if (!response) {
      return [];
    }

    // Handle different response formats
    const events = Array.isArray(response)
      ? response
      : (response.data || response.events || []);

    return Array.isArray(events) ? events : [];
  } catch (error) {
    console.error('[Integrations API] Error fetching webhook log:', error);
    return [];
  }
}

/**
 * Check if a test was delivered by looking at webhook log
 * 
 * @param {Array} webhookLog - Webhook log from fetchWebhookLog
 * @param {string} testId - Test ID from the trigger
 * @returns {boolean} Whether the test appears in the webhook log
 */
function isTestDelivered(webhookLog, testId) {
  if (!webhookLog || !Array.isArray(webhookLog) || !testId) {
    return false;
  }

  // Look for webhook event with matching test ID
  return webhookLog.some(event => {
    if (!event) return false;
    // Check if event data contains our test ID
    if (event.data && event.data.testId === testId) return true;
    if (event.testId === testId) return true;
    if (event.message && event.message.includes(testId)) return true;
    return false;
  });
}

/**
 * Get credential submission requirements for a vendor
 * 
 * @param {string} vendor - Vendor name
 * @returns {Object} Credential requirements info
 */
function getVendorCredentialInfo(vendor) {
  const vendorInfo = {
    hubspot: {
      name: 'HubSpot',
      keyName: 'HUBSPOT_TOKEN',
      keyLabel: 'Private App Token',
      envVar: 'HUBSPOT_TOKEN',
      docsUrl: 'https://developers.hubspot.com/docs/api/private-apps',
      instructions: 'Create a Private App in your HubSpot account and copy the token'
    },
    zendesk: {
      name: 'Zendesk',
      keyName: 'ZENDESK_API_KEY',
      keyLabel: 'API Token',
      envVar: 'ZENDESK_API_KEY',
      docsUrl: 'https://support.zendesk.com/hc/en-us/articles/226062247',
      instructions: 'Generate an API token in Zendesk Admin > Apps and integrations > APIs'
    },
    apollo: {
      name: 'Apollo',
      keyName: 'APOLLO_API_KEY',
      keyLabel: 'API Key',
      envVar: 'APOLLO_API_KEY',
      docsUrl: 'https://apolloio.github.io/apollo-api-docs/',
      instructions: 'Get your API key from Apollo Account > API Keys'
    },
    zapier: {
      name: 'Zapier',
      keyName: 'ZAPIER_WEBHOOK_URL',
      keyLabel: 'Webhook URL',
      envVar: 'ZAPIER_WEBHOOK_URL',
      docsUrl: 'https://zapier.com/help/articles/set-up-webhooks',
      instructions: 'Create a Catch Hook in Zapier and copy the webhook URL'
    }
  };

  return vendorInfo[vendor.toLowerCase()] || null;
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const integrationsAPI = {
  // Status
  getIntegrationStatus,
  getIntegrationState,
  getMissingConfiguration,
  
  // Zapier testing
  triggerZapierTest,
  fetchWebhookLog,
  isTestDelivered,
  
  // Credential info (for UI guidance only - no actual submission)
  getVendorCredentialInfo,
  
  // Cache keys
  cacheKeys: INTEGRATIONS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.integrationsAPI = integrationsAPI;
}