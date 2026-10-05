/**
 * DialForge Calling Configuration API Integration Layer
 * 
 * Calling Configuration-specific API operations:
 * - Save calling configuration (POST /api/zapier/trigger)
 * - Retrieve webhook activity log
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const CALLING_CONFIG_CACHE_KEYS = {
  WEBHOOK_ACTIVITY: 'cc_webhook_activity'
};

// ============================================================================
// SAVE CALLING CONFIGURATION
// ============================================================================

/**
 * Save calling configuration to backend
 * 
 * @param {Object} config - Configuration object
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function saveCallingConfiguration(config) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return {
        success: false,
        message: 'API not available'
      };
    }

    if (!config) {
      return {
        success: false,
        message: 'No configuration provided'
      };
    }

    // Build payload for Zapier webhook
    const payload = {
      action: 'update_calling_config',
      outbound_line: config.outboundLine || config.callerId || null,
      recording_enabled: config.recordingEnabled === true,
      post_call_webhook_url: config.webhookUrl || null,
      timestamp: new Date().toISOString(),
      source: 'calling_configuration'
    };

    console.log('[Calling Config API] Sending configuration update:', payload);

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Configuration update failed'
      };
    }

    return {
      success: true,
      message: 'Calling configuration saved successfully'
    };
  } catch (error) {
    console.error('[Calling Config API] Error saving configuration:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// WEBHOOK ACTIVITY
// ============================================================================

/**
 * Get webhook activity log
 * 
 * @returns {Promise<Array>} Array of webhook events
 */
async function getWebhookActivity() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: CALLING_CONFIG_CACHE_KEYS.WEBHOOK_ACTIVITY,
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
    console.error('[Calling Config API] Error fetching webhook activity:', error);
    return [];
  }
}

/**
 * Filter webhook events related to calling configuration
 * 
 * @param {Array} events - Array of webhook events
 * @returns {Array} Filtered events
 */
function filterCallingConfigEvents(events) {
  if (!Array.isArray(events)) return [];
  
  return events.filter(event => {
    const type = (event.type || event.action || '').toLowerCase();
    return type.includes('config') || 
           type.includes('calling') || 
           type.includes('webhook') ||
           event.source === 'calling_configuration';
  });
}

/**
 * Format webhook event for display
 * 
 * @param {Object} event - Event from webhook log
 * @returns {Object} Formatted event
 */
function formatWebhookEvent(event) {
  if (!event) return null;

  const timestamp = event.timestamp || event.created_at || new Date().toISOString();
  const timeLabel = formatTimeLabel(timestamp);

  return {
    id: event.id || `event-${Date.now()}`,
    timestamp: timestamp,
    timeLabel: timeLabel,
    type: event.type || event.action || 'Event',
    status: event.status || 'completed',
    details: event.details || event.message || ''
  };
}

/**
 * Format timestamp for display
 * 
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Formatted time label
 */
function formatTimeLabel(timestamp) {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'just now';
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  } catch (error) {
    return 'Unknown time';
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const callingConfigAPI = {
  // Configuration
  saveCallingConfiguration,

  // Webhook activity
  getWebhookActivity,
  filterCallingConfigEvents,
  formatWebhookEvent,

  // Helpers
  formatTimeLabel,

  // Cache keys
  cacheKeys: CALLING_CONFIG_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.callingConfigAPI = callingConfigAPI;
}