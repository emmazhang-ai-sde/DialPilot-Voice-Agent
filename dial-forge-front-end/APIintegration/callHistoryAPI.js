/**
 * DialForge Call History API Integration Layer
 * 
 * Call History-specific API operations:
 * - Fetch call events from Zapier webhook log
 * - Fetch HubSpot contacts for caller ID resolution
 * - Create Zendesk support tickets from calls
 * - Enrich unknown callers with Apollo
 * - Log call notes through Zapier
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const CALL_HISTORY_CACHE_KEYS = {
  WEBHOOK_LOG: 'ch_webhook_log',
  HUBSPOT_CONTACTS: 'ch_hubspot_contacts'
};

// ============================================================================
// WEBHOOK LOG FETCHING
// ============================================================================

/**
 * Fetch call events from Zapier webhook log
 * 
 * @returns {Promise<Array>} Array of call events
 */
async function fetchCallHistory() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: CALL_HISTORY_CACHE_KEYS.WEBHOOK_LOG,
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
    console.error('[Call History API] Error fetching webhook log:', error);
    return [];
  }
}

// ============================================================================
// HUBSPOT CONTACT LOOKUP
// ============================================================================

/**
 * Fetch HubSpot contacts for caller ID resolution
 * 
 * @returns {Promise<Array>} Array of HubSpot contacts
 */
async function fetchHubSpotContactsForLookup() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Call History API] crmAPI not available for contact lookup');
      return [];
    }

    const contacts = await crmAPI.getHubSpotContacts();
    
    if (!contacts || contacts.length === 0) {
      console.log('[Call History API] No HubSpot contacts found');
      return [];
    }

    return contacts;
  } catch (error) {
    console.error('[Call History API] Error fetching HubSpot contacts:', error);
    return [];
  }
}

// ============================================================================
// PHONE NUMBER NORMALIZATION & MATCHING
// ============================================================================

/**
 * Normalize phone number for matching
 * Removes spaces, parentheses, hyphens, dots, and country codes
 * 
 * @param {string} phoneNumber - Phone number to normalize
 * @returns {string} Normalized phone number (digits only)
 */
function normalizePhoneNumber(phoneNumber) {
  if (!phoneNumber || typeof phoneNumber !== 'string') return '';
  
  // Remove all non-digit characters
  const digitsOnly = phoneNumber.replace(/\D/g, '');
  
  // Remove country code (1 for US/Canada) if it's 11 digits
  if (digitsOnly.length === 11 && digitsOnly.startsWith('1')) {
    return digitsOnly.substring(1);
  }
  
  return digitsOnly;
}

/**
 * Create phone lookup map from contacts
 * Maps normalized phone numbers to contact information
 * 
 * @param {Array} contacts - Array of HubSpot contacts
 * @returns {Object} Map of normalized phone → contact
 */
function createPhoneLookupMap(contacts) {
  const map = {};
  
  if (!Array.isArray(contacts)) {
    return map;
  }

  contacts.forEach(contact => {
    if (contact.phone) {
      const normalized = normalizePhoneNumber(contact.phone);
      if (normalized) {
        map[normalized] = {
          name: contact.name || '',
          firstName: contact.firstname || '',
          lastName: contact.lastname || '',
          company: contact.company || '',
          email: contact.email || '',
          phone: contact.phone,
          jobTitle: contact.jobTitle || contact.job_title || ''
        };
      }
    }
  });

  return map;
}

/**
 * Find contact from phone number
 * 
 * @param {string} phoneNumber - Phone number to look up
 * @param {Object} phoneLookupMap - Map from createPhoneLookupMap
 * @returns {Object|null} Contact object or null if not found
 */
function findContactByPhone(phoneNumber, phoneLookupMap) {
  if (!phoneNumber || !phoneLookupMap) {
    return null;
  }

  const normalized = normalizePhoneNumber(phoneNumber);
  return phoneLookupMap[normalized] || null;
}

// ============================================================================
// WEBHOOK EVENT TRANSFORMATION
// ============================================================================

/**
 * Transform webhook event to call history record
 * 
 * @param {Object} event - Webhook event from /api/zapier/webhook/log
 * @param {Object} contact - Contact info (from HubSpot lookup)
 * @returns {Object} Call history record
 */
function transformWebhookEventToCall(event, contact) {
  if (!event) return null;

  // Determine direction based on event data
  let direction = 'inbound';
  if (event.direction) {
    direction = event.direction.toLowerCase() === 'outbound' ? 'outbound' : 'inbound';
  } else if (event.type && event.type.toLowerCase().includes('outbound')) {
    direction = 'outbound';
  }

  // Determine status
  let status = 'COMPLETED';
  if (event.status) {
    const eventStatus = event.status.toLowerCase();
    if (eventStatus.includes('missed') || eventStatus.includes('voicemail')) {
      status = 'MISSED';
    } else if (eventStatus.includes('completed')) {
      status = 'COMPLETED';
    }
  }

  // Format duration
  const durationSeconds = event.duration_seconds || event.durationSeconds || 0;
  const durationLabel = formatDuration(durationSeconds);

  // Format timestamp
  const timestamp = event.timestamp || event.created_at || new Date().toISOString();
  const dateLabel = formatTimestamp(timestamp);

  // Get caller info
  const phoneNumber = event.phone_number || event.phone || '';
  const name = contact?.name || contact?.firstName ? 
    `${contact.firstName || ''} ${contact.lastName || ''}`.trim() : 
    'Unknown Caller';
  const company = contact?.company || '';
  const email = contact?.email || '';
  const avatar = contact?.avatar || '';

  return {
    id: event.id || `event-${Date.now()}`,
    name: name,
    number: phoneNumber,
    company: company,
    email: email,
    avatar: avatar,
    direction: direction,
    status: status,
    durationSeconds: durationSeconds,
    durationLabel: durationLabel,
    timestamp: timestamp,
    dateLabel: dateLabel,
    recordingUrl: event.recording_url || null,
    isEnriched: !!contact,
    isFromAPI: true,
    webhookEvent: event  // Keep original for later operations
  };
}

/**
 * Format duration in seconds to HH:MM:SS
 * 
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration
 */
function formatDuration(seconds) {
  if (!seconds || seconds < 0) {
    return '00:00';
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Format timestamp to readable date/time
 * 
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Formatted date/time
 */
function formatTimestamp(timestamp) {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'Just now';
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      // Format as "Mon Jan 15, 2:30 PM"
      const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true };
      return date.toLocaleDateString('en-US', options);
    }
  } catch (error) {
    console.warn('[Call History API] Error formatting timestamp:', error);
    return 'Unknown time';
  }
}

// ============================================================================
// ZENDESK TICKET CREATION
// ============================================================================

/**
 * Create a Zendesk support ticket from a call
 * 
 * @param {Object} call - Call history record
 * @returns {Promise<Object>} { success: boolean, ticketId: string, message: string }
 */
async function createZendeskTicket(call) {
  if (!call) {
    return { success: false, message: 'No call data provided' };
  }

  try {
    if (typeof crmAPI === 'undefined') {
      return { success: false, message: 'CRM API not available' };
    }

    // Build ticket payload
    const payload = {
      requester_email: call.email || 'noemail@dialforge.local',
      requester_phone: call.number,
      subject: `Call: ${call.name} (${call.direction.toUpperCase()})`,
      description: `Call Summary\n\nCaller: ${call.name}\nCompany: ${call.company || 'N/A'}\nPhone: ${call.number}\nDirection: ${call.direction}\nDuration: ${call.durationLabel}\nTime: ${call.dateLabel}`,
      priority: 'normal',
      type: 'problem',
      custom_fields: {
        call_direction: call.direction,
        call_duration: call.durationSeconds,
        call_timestamp: call.timestamp
      }
    };

    console.log('[Call History API] Creating Zendesk ticket:', payload);

    const response = await dialforgeApi.fetch('/api/zendesk/tickets', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Zendesk ticket creation returned no response'
      };
    }

    const ticketId = response.id || response.ticket_id;

    return {
      success: true,
      ticketId: ticketId,
      message: `Ticket #${ticketId} created successfully`
    };
  } catch (error) {
    console.error('[Call History API] Error creating Zendesk ticket:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// APOLLO ENRICHMENT
// ============================================================================

/**
 * Enrich a call with Apollo
 * 
 * @param {Object} call - Call history record
 * @returns {Promise<Object>} { success: boolean, enrichedContact: Object, message: string }
 */
async function enrichCallWithApollo(call) {
  if (!call || !call.number) {
    return {
      success: false,
      message: 'No phone number to enrich'
    };
  }

  try {
    if (typeof contactsAPI === 'undefined') {
      console.warn('[Call History API] contactsAPI not available');
      return {
        success: false,
        message: 'Enrichment API not available'
      };
    }

    // Use contactsAPI enrichment
    const result = await contactsAPI.enrichContactWithApollo({
      phone: call.number,
      firstName: call.name ? call.name.split(' ')[0] : '',
      lastName: call.name ? call.name.split(' ').slice(1).join(' ') : ''
    });

    if (result.success && result.enrichedContact) {
      return {
        success: true,
        enrichedContact: result.enrichedContact,
        message: 'Contact enriched successfully'
      };
    }

    return {
      success: false,
      message: result.message
    };
  } catch (error) {
    console.error('[Call History API] Error enriching call:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// ZAPIER NOTE LOGGING
// ============================================================================

/**
 * Log a call note through Zapier
 * 
 * @param {Object} call - Call history record
 * @param {string} note - Note/disposition text
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function logCallNoteToZapier(call, note) {
  if (!call || !note) {
    return {
      success: false,
      message: 'Call and note required'
    };
  }

  try {
    const payload = {
      type: 'call_note',
      phone: call.number,
      caller: call.name,
      company: call.company,
      direction: call.direction,
      duration: call.durationLabel,
      timestamp: call.timestamp,
      note: note,
      source: 'call_history'
    };

    console.log('[Call History API] Logging call note to Zapier:', payload);

    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Zapier trigger returned no response'
      };
    }

    return {
      success: true,
      message: 'Note logged successfully'
    };
  } catch (error) {
    console.error('[Call History API] Error logging call note:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const callHistoryAPI = {
  // Call history loading
  fetchCallHistory,
  fetchHubSpotContactsForLookup,
  transformWebhookEventToCall,
  
  // Phone matching
  normalizePhoneNumber,
  createPhoneLookupMap,
  findContactByPhone,
  
  // Formatting
  formatDuration,
  formatTimestamp,
  
  // Actions
  createZendeskTicket,
  enrichCallWithApollo,
  logCallNoteToZapier,
  
  // Cache keys
  cacheKeys: CALL_HISTORY_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.callHistoryAPI = callHistoryAPI;
}