/**
 * DialForge Calling Compliance API Integration Layer
 * 
 * Calling Compliance-specific API operations:
 * - Save compliance settings (allowed hours, recording disclaimer)
 * - Mark phone number as Do Not Call (DNC)
 * - Audit compliance events
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const CALLING_COMPLIANCE_CACHE_KEYS = {
  COMPLIANCE_SETTINGS: 'cc_compliance_settings',
  DNC_LIST: 'cc_dnc_list'
};

// ============================================================================
// COMPLIANCE SETTINGS
// ============================================================================

/**
 * Get compliance settings from localStorage
 * 
 * @returns {Object} Compliance settings
 */
function getComplianceSettings() {
  try {
    const cached = localStorage.getItem(CALLING_COMPLIANCE_CACHE_KEYS.COMPLIANCE_SETTINGS);
    if (cached) {
      return JSON.parse(cached);
    }

    // Default settings
    return {
      allowedHours: { start: '08:00', end: '21:00' }, // 8 AM - 9 PM
      recordingDisclaimer: true,
      timezoneGuards: true,
      dncSync: true
    };
  } catch (error) {
    console.error('[Calling Compliance API] Error getting settings:', error);
    return {
      allowedHours: { start: '08:00', end: '21:00' },
      recordingDisclaimer: true,
      timezoneGuards: true,
      dncSync: true
    };
  }
}

/**
 * Save compliance settings to localStorage
 * 
 * @param {Object} settings - Settings object
 * @returns {Object} { success: boolean, message: string }
 */
function saveComplianceSettings(settings) {
  try {
    if (!settings) {
      return {
        success: false,
        message: 'No settings provided'
      };
    }

    localStorage.setItem(CALLING_COMPLIANCE_CACHE_KEYS.COMPLIANCE_SETTINGS, JSON.stringify(settings));

    return {
      success: true,
      message: 'Compliance settings saved'
    };
  } catch (error) {
    console.error('[Calling Compliance API] Error saving settings:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// DNC FLAGGING
// ============================================================================

/**
 * Mark a phone number as Do Not Call
 * 
 * @param {string} phone - Phone number to mark DNC
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function markDNC(phone) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return {
        success: false,
        message: 'API not available'
      };
    }

    if (!phone) {
      return {
        success: false,
        message: 'No phone number provided'
      };
    }

    // Payload for HubSpot contact update
    const payload = {
      phone: phone,
      do_not_call: true
    };

    console.log('[Calling Compliance API] Marking DNC:', payload);

    const response = await dialforgeApi.fetch('/api/hubspot/contacts', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'DNC update failed'
      };
    }

    // Store DNC locally as well
    addToDNCList(phone);

    return {
      success: true,
      message: 'Phone number marked as Do Not Call'
    };
  } catch (error) {
    console.error('[Calling Compliance API] Error marking DNC:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

/**
 * Add phone to local DNC list
 * 
 * @param {string} phone - Phone number
 */
function addToDNCList(phone) {
  try {
    const dncList = getDNCList();
    if (!dncList.includes(phone)) {
      dncList.push(phone);
      localStorage.setItem(CALLING_COMPLIANCE_CACHE_KEYS.DNC_LIST, JSON.stringify(dncList));
    }
  } catch (error) {
    console.error('[Calling Compliance API] Error adding to DNC list:', error);
  }
}

/**
 * Get local DNC list
 * 
 * @returns {Array} List of DNC phone numbers
 */
function getDNCList() {
  try {
    const cached = localStorage.getItem(CALLING_COMPLIANCE_CACHE_KEYS.DNC_LIST);
    return cached ? JSON.parse(cached) : [];
  } catch (error) {
    console.error('[Calling Compliance API] Error getting DNC list:', error);
    return [];
  }
}

/**
 * Check if phone is in DNC list
 * 
 * @param {string} phone - Phone number
 * @returns {boolean} True if in DNC list
 */
function isPhoneDNC(phone) {
  const dncList = getDNCList();
  return dncList.includes(phone);
}

// ============================================================================
// COMPLIANCE AUDIT EVENT
// ============================================================================

/**
 * Send compliance audit event to backend
 * 
 * @param {Object} event - Audit event object
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function sendComplianceAudit(event) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      console.warn('[Calling Compliance API] dialforgeApi not available for audit');
      // Don't fail the main operation if audit fails
      return {
        success: false,
        message: 'Audit logging unavailable'
      };
    }

    if (!event) {
      return {
        success: false,
        message: 'No event provided'
      };
    }

    // Build audit payload
    const payload = {
      type: 'compliance_update',
      action: event.action || 'update_compliance',
      details: event.details || {},
      timestamp: new Date().toISOString(),
      source: 'calling_compliance'
    };

    console.log('[Calling Compliance API] Sending compliance audit:', payload);

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      console.warn('[Calling Compliance API] Audit event delivery failed');
      // Don't fail main operation if audit fails
      return {
        success: false,
        message: 'Audit logging failed'
      };
    }

    return {
      success: true,
      message: 'Compliance audit logged'
    };
  } catch (error) {
    console.error('[Calling Compliance API] Error sending audit:', error);
    // Don't fail main operation if audit fails
    return {
      success: false,
      message: 'Audit logging error'
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const callingComplianceAPI = {
  // Settings
  getComplianceSettings,
  saveComplianceSettings,

  // DNC
  markDNC,
  addToDNCList,
  getDNCList,
  isPhoneDNC,

  // Audit
  sendComplianceAudit,

  // Cache keys
  cacheKeys: CALLING_COMPLIANCE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.callingComplianceAPI = callingComplianceAPI;
}