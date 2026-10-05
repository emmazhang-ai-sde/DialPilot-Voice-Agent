/**
 * DialForge Numbers API Integration Layer
 * 
 * Numbers-specific API operations:
 * - Manage assigned phone numbers (virtual number inventory)
 * - Track webhook activity per number
 * - Match numbers to HubSpot contacts
 * - Manage primary caller ID selection for outbound calls
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (HubSpot contact operations)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const NUMBERS_CACHE_KEYS = {
  ASSIGNED_NUMBERS: 'numbers_assigned_list',
  PRIMARY_CALLER_ID: 'numbers_primary_caller_id',
  WEBHOOK_LOG: 'numbers_webhook_log',
  HUBSPOT_CONTACTS: 'numbers_hubspot_contacts'
};

// ============================================================================
// PRIMARY CALLER ID STATE
// ============================================================================

/**
 * Get the currently selected primary caller ID
 * 
 * @returns {Object|null} { number, name, assetId } or null
 */
function getPrimaryCallerId() {
  try {
    const stored = localStorage.getItem(NUMBERS_CACHE_KEYS.PRIMARY_CALLER_ID);
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
    console.error('[Numbers API] Error getting primary caller ID:', error);
    return null;
  }
}

/**
 * Set the primary caller ID for outbound calls
 * Stores in localStorage and can optionally notify backend
 * 
 * @param {string} number - Phone number
 * @param {string} name - Display name
 * @param {string} assetId - Asset ID
 * @returns {Object} { success: boolean }
 */
function setPrimaryCallerId(number, name, assetId) {
  try {
    const data = { number, name, assetId, timestamp: new Date().toISOString() };
    localStorage.setItem(NUMBERS_CACHE_KEYS.PRIMARY_CALLER_ID, JSON.stringify(data));
    
    console.log('[Numbers API] Primary caller ID set:', number);
    return { success: true };
  } catch (error) {
    console.error('[Numbers API] Error setting primary caller ID:', error);
    return { success: false, error: error.message };
  }
}

/**
 * Clear the primary caller ID
 */
function clearPrimaryCallerId() {
  try {
    localStorage.removeItem(NUMBERS_CACHE_KEYS.PRIMARY_CALLER_ID);
    console.log('[Numbers API] Primary caller ID cleared');
    return { success: true };
  } catch (error) {
    console.error('[Numbers API] Error clearing primary caller ID:', error);
    return { success: false, error: error.message };
  }
}

// ============================================================================
// ASSIGNED NUMBERS MANAGEMENT
// ============================================================================

/**
 * Get assigned numbers for the current agent
 * 
 * Returns stored assigned numbers from frontend state
 * (Backend does not appear to provide a dedicated /api/numbers endpoint)
 * 
 * @returns {Promise<Array>} Array of assigned number objects
 */
async function getAssignedNumbers() {
  try {
    // Attempt to get from localStorage/frontend state
    const stored = localStorage.getItem(NUMBERS_CACHE_KEYS.ASSIGNED_NUMBERS);
    if (stored) {
      const numbers = JSON.parse(stored);
      return Array.isArray(numbers) ? numbers : [];
    }

    // Return empty array if no assigned numbers stored
    return [];
  } catch (error) {
    console.error('[Numbers API] Error getting assigned numbers:', error);
    return [];
  }
}

/**
 * Store assigned numbers in localStorage
 * 
 * @param {Array} numbers - Array of number objects
 */
function storeAssignedNumbers(numbers) {
  try {
    localStorage.setItem(NUMBERS_CACHE_KEYS.ASSIGNED_NUMBERS, JSON.stringify(numbers));
  } catch (error) {
    console.error('[Numbers API] Error storing assigned numbers:', error);
  }
}

// ============================================================================
// WEBHOOK ACTIVITY RETRIEVAL
// ============================================================================

/**
 * Fetch webhook log from backend
 * 
 * @returns {Promise<Array>} Array of webhook events
 */
async function fetchWebhookLog() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: NUMBERS_CACHE_KEYS.WEBHOOK_LOG,
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
    console.error('[Numbers API] Error fetching webhook log:', error);
    return [];
  }
}

/**
 * Get webhook activity filtered for a specific phone number
 * 
 * Handles phone number normalization for matching
 * 
 * @param {string} phoneNumber - Phone number to filter by
 * @param {Array} webhookEvents - Complete webhook event array
 * @returns {Array} Filtered webhook events for this number
 */
function filterWebhooksByNumber(phoneNumber, webhookEvents) {
  if (!phoneNumber || !Array.isArray(webhookEvents)) {
    return [];
  }

  const normalized = normalizePhoneNumber(phoneNumber);

  return webhookEvents.filter(event => {
    // Check phone_number field
    if (event.phone_number) {
      const eventPhone = normalizePhoneNumber(event.phone_number);
      if (eventPhone === normalized) return true;
    }

    // Check phone field
    if (event.phone) {
      const eventPhone = normalizePhoneNumber(event.phone);
      if (eventPhone === normalized) return true;
    }

    // Check destination_number field
    if (event.destination_number) {
      const eventPhone = normalizePhoneNumber(event.destination_number);
      if (eventPhone === normalized) return true;
    }

    return false;
  });
}

/**
 * Normalize phone number for matching
 * 
 * @param {string} phoneNumber - Phone number to normalize
 * @returns {string} Normalized phone number (digits only)
 */
function normalizePhoneNumber(phoneNumber) {
  if (!phoneNumber || typeof phoneNumber !== 'string') return '';

  // Remove all non-digit characters
  const digitsOnly = phoneNumber.replace(/\D/g, '');

  // Remove leading 1 for US/Canada if 11 digits
  if (digitsOnly.length === 11 && digitsOnly.startsWith('1')) {
    return digitsOnly.substring(1);
  }

  return digitsOnly;
}

// ============================================================================
// HUBSPOT CONTACT MATCHING
// ============================================================================

/**
 * Get HubSpot contacts for matching with numbers
 * 
 * Reuses crmAPI functionality
 * 
 * @returns {Promise<Array>} Array of HubSpot contacts
 */
async function fetchHubSpotContacts() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Numbers API] crmAPI not available');
      return [];
    }

    const contacts = await crmAPI.getHubSpotContacts();
    return Array.isArray(contacts) ? contacts : [];
  } catch (error) {
    console.error('[Numbers API] Error fetching HubSpot contacts:', error);
    return [];
  }
}

/**
 * Find HubSpot contact that matches a phone number
 * 
 * @param {string} phoneNumber - Phone number to match
 * @param {Array} contacts - HubSpot contacts array
 * @returns {Object|null} Contact object or null if no match
 */
function findContactByPhoneNumber(phoneNumber, contacts) {
  if (!phoneNumber || !Array.isArray(contacts)) {
    return null;
  }

  const normalized = normalizePhoneNumber(phoneNumber);

  for (const contact of contacts) {
    // Check contact.phone field
    if (contact.phone) {
      const contactPhone = normalizePhoneNumber(contact.phone);
      if (contactPhone === normalized) return contact;
    }

    // Check contact.phone_number field
    if (contact.phone_number) {
      const contactPhone = normalizePhoneNumber(contact.phone_number);
      if (contactPhone === normalized) return contact;
    }
  }

  return null;
}

// ============================================================================
// WEBHOOK EVENT TRANSFORMATION
// ============================================================================

/**
 * Transform webhook event to display format
 * 
 * @param {Object} event - Raw webhook event
 * @returns {Object} Transformed event for UI
 */
function formatWebhookEvent(event) {
  if (!event) return null;

  const timestamp = event.timestamp || event.created_at || new Date().toISOString();
  const timeLabel = formatTimeLabel(timestamp);

  return {
    id: event.id || `event-${Date.now()}`,
    type: event.type || event.event_type || 'Call',
    direction: event.direction || 'inbound',
    fromPhone: event.phone_number || event.from || 'Unknown',
    toPhone: event.destination_number || event.to || 'Unknown',
    status: event.status || 'completed',
    timestamp: timestamp,
    timeLabel: timeLabel,
    duration: event.duration || event.duration_seconds || 0,
    provider: event.provider || 'Unknown'
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

    if (diffMins < 1) {
      return 'Just now';
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  } catch (error) {
    return 'Unknown time';
  }
}

// ============================================================================
// ZAPIER WEBHOOK TRIGGER (Optional)
// ============================================================================

/**
 * Trigger Zapier webhook for number/routing update
 * 
 * Only use if backend supports routing updates via Zapier
 * 
 * @param {Object} payload - Webhook payload
 * @returns {Promise<Object>} { success: boolean }
 */
async function triggerZapierWebhook(payload) {
  try {
    if (typeof dialforgeApi === 'undefined') {
      return { success: false, message: 'API not available' };
    }

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return { success: false, message: 'No response from webhook' };
    }

    return {
      success: true,
      message: 'Webhook triggered successfully'
    };
  } catch (error) {
    console.error('[Numbers API] Error triggering webhook:', error);
    return {
      success: false,
      message: error.message
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const numbersAPI = {
  // Primary caller ID management
  getPrimaryCallerId,
  setPrimaryCallerId,
  clearPrimaryCallerId,

  // Assigned numbers
  getAssignedNumbers,
  storeAssignedNumbers,

  // Webhook management
  fetchWebhookLog,
  filterWebhooksByNumber,
  formatWebhookEvent,

  // HubSpot matching
  fetchHubSpotContacts,
  findContactByPhoneNumber,

  // Phone utilities
  normalizePhoneNumber,

  // Zapier
  triggerZapierWebhook,

  // Cache keys
  cacheKeys: NUMBERS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.numbersAPI = numbersAPI;
}