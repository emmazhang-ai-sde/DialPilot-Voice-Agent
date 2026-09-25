/**
 * DialForge Notifications Settings API Integration Layer
 * 
 * Notifications-specific API operations:
 * - Local notification preferences persistence
 * - External webhook notification testing
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const NOTIFICATIONS_CACHE_KEYS = {
  PREFERENCES: 'notif_preferences',
  EXTERNAL_WEBHOOK: 'notif_external_webhook'
};

// ============================================================================
// LOCAL NOTIFICATION PREFERENCES
// ============================================================================

/**
 * Get local notification preferences from localStorage
 * 
 * @returns {Object} Notification preferences
 */
function getNotificationPreferences() {
  try {
    const cached = localStorage.getItem(NOTIFICATIONS_CACHE_KEYS.PREFERENCES);
    if (cached) {
      return JSON.parse(cached);
    }

    // Default preferences
    return {
      // Real-time alerts
      dealAlerts: true,
      missedCallAlerts: true,
      
      // Summaries
      weeklySummary: false,
      dailyDigest: false,
      
      // Delivery preferences
      preferredChannel: 'push',     // push, email, sms
      quietHours: 'off',            // off, night, weekend
      
      // Sound & visual
      soundAlerts: true,
      toastDuration: 5,             // seconds
      missedCallPopups: true
    };
  } catch (error) {
    console.error('[Notifications API] Error getting preferences:', error);
    return getDefaultPreferences();
  }
}

/**
 * Get default preferences
 * 
 * @returns {Object} Default preferences
 */
function getDefaultPreferences() {
  return {
    dealAlerts: true,
    missedCallAlerts: true,
    weeklySummary: false,
    dailyDigest: false,
    preferredChannel: 'push',
    quietHours: 'off',
    soundAlerts: true,
    toastDuration: 5,
    missedCallPopups: true
  };
}

/**
 * Save local notification preferences to localStorage
 * 
 * @param {Object} preferences - Preferences to save
 * @returns {Object} { success: boolean, message: string }
 */
function saveNotificationPreferences(preferences) {
  try {
    if (!preferences) {
      return {
        success: false,
        message: 'No preferences provided'
      };
    }

    localStorage.setItem(NOTIFICATIONS_CACHE_KEYS.PREFERENCES, JSON.stringify(preferences));

    return {
      success: true,
      message: 'Preferences saved'
    };
  } catch (error) {
    console.error('[Notifications API] Error saving preferences:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

/**
 * Update a single preference value
 * 
 * @param {string} key - Preference key
 * @param {any} value - Preference value
 * @returns {Object} { success: boolean, message: string }
 */
function updatePreference(key, value) {
  try {
    const preferences = getNotificationPreferences();
    preferences[key] = value;
    return saveNotificationPreferences(preferences);
  } catch (error) {
    console.error('[Notifications API] Error updating preference:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// EXTERNAL WEBHOOK TESTING
// ============================================================================

/**
 * Send test notification to external webhook
 * 
 * @param {string} webhookUrl - Webhook URL to test
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function sendTestNotification(webhookUrl) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return {
        success: false,
        message: 'API not available'
      };
    }

    if (!webhookUrl || !webhookUrl.trim()) {
      return {
        success: false,
        message: 'No webhook URL configured'
      };
    }

    // Build test payload for Zapier webhook
    const payload = {
      type: 'test_notification',
      action: 'test_alert',
      notification: {
        title: 'Test Notification',
        message: 'This is a test notification from DialForge',
        timestamp: new Date().toISOString()
      },
      destination: webhookUrl,
      source: 'notifications_settings'
    };

    console.log('[Notifications API] Sending test notification:', payload);

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Test notification failed'
      };
    }

    return {
      success: true,
      message: 'Test notification sent successfully'
    };
  } catch (error) {
    console.error('[Notifications API] Error sending test notification:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

/**
 * Get stored external webhook URL
 * 
 * @returns {string|null} Webhook URL or null
 */
function getExternalWebhookUrl() {
  try {
    return localStorage.getItem(NOTIFICATIONS_CACHE_KEYS.EXTERNAL_WEBHOOK) || null;
  } catch (error) {
    console.error('[Notifications API] Error getting webhook URL:', error);
    return null;
  }
}

/**
 * Save external webhook URL
 * 
 * @param {string} webhookUrl - Webhook URL
 * @returns {boolean} True if saved
 */
function saveExternalWebhookUrl(webhookUrl) {
  try {
    if (webhookUrl && webhookUrl.trim()) {
      localStorage.setItem(NOTIFICATIONS_CACHE_KEYS.EXTERNAL_WEBHOOK, webhookUrl);
      return true;
    } else {
      localStorage.removeItem(NOTIFICATIONS_CACHE_KEYS.EXTERNAL_WEBHOOK);
      return true;
    }
  } catch (error) {
    console.error('[Notifications API] Error saving webhook URL:', error);
    return false;
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const notificationsSettingsAPI = {
  // Preferences
  getNotificationPreferences,
  getDefaultPreferences,
  saveNotificationPreferences,
  updatePreference,

  // External webhooks
  getExternalWebhookUrl,
  saveExternalWebhookUrl,
  sendTestNotification,

  // Cache keys
  cacheKeys: NOTIFICATIONS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.notificationsSettingsAPI = notificationsSettingsAPI;
}