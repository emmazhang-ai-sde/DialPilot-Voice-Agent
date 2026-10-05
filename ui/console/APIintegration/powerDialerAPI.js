/**
 * DialForge Power Dialer API Integration Layer
 * 
 * Power Dialer-specific API functionality.
 * CRM operations (HubSpot) delegated to centralized crmAPI.js
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const POWER_DIALER_CACHE_KEYS = {
  HUBSPOT_CONTACT: 'pd_hubspot_contact',
  SEARCH_HISTORY: 'pd_search_history',
  CALL_QUEUE: 'pd_call_queue'
};

// ============================================================================
// CALL QUEUE
// ============================================================================

function normalizePriorityLabel(priority, priorityValue) {
  if (priority === 'high' || priority === 'medium' || priority === 'low') {
    return priority;
  }
  const numericPriority = Number(priorityValue || 0);
  if (numericPriority >= 3) return 'high';
  if (numericPriority === 2) return 'medium';
  return 'low';
}

function normalizeCallQueueItem(item, index) {
  const priority = normalizePriorityLabel(item.priority, item.priority_value);
  return {
    id: item.queue_id || item.id || index + 1,
    queueId: item.queue_id || item.id || null,
    contactId: item.contact_id || null,
    name: item.name || 'Unknown Prospect',
    company: item.company || '',
    phone: item.phone || '',
    email: item.email || '',
    title: item.title || 'PROSPECT',
    status: item.status || 'waiting',
    dbStatus: item.db_status || item.dbStatus || '',
    priority,
    priorityValue: Number(item.priority_value || 0),
    callMode: item.call_mode || '',
    scheduledAt: item.scheduled_at || '',
    avatar: item.avatar || item.avatar_url || null,
    duration: item.duration || 0
  };
}

async function loadCallQueue() {
  const response = await dialforgeApi.fetch('/api/call-queue', {
    fallbackKey: POWER_DIALER_CACHE_KEYS.CALL_QUEUE,
    fallbackValue: null
  });
  const queue = dialforgeApi.extractArray(response, 'queue');
  const normalized = queue.map(normalizeCallQueueItem);
  if (normalized.length) {
    dialforgeApi.cacheData(POWER_DIALER_CACHE_KEYS.CALL_QUEUE, { queue: normalized });
  }
  return normalized;
}

async function updateCallQueueItem(queueId, status, details = {}) {
  if (!queueId) {
    return null;
  }

  const response = await dialforgeApi.fetch(`/api/call-queue/${queueId}`, {
    method: 'PATCH',
    body: {
      status,
      ...details
    },
    fallbackValue: null
  });

  if (!response || !response.item) {
    return null;
  }

  return normalizeCallQueueItem(response.item, 0);
}

async function loadCallQueueEvents(queueId) {
  if (!queueId) {
    return [];
  }

  const response = await dialforgeApi.fetch(`/api/call-queue/${queueId}/events`, {
    fallbackValue: { events: [] }
  });

  return dialforgeApi.extractArray(response, 'events');
}

// ============================================================================
// HUBSPOT CONTACT SEARCH
// ============================================================================

/**
 * Search for a contact in HubSpot by phone number or email
 * DELEGATED to crmAPI.js - using centralized function
 */
async function searchHubSpotContact(prospect) {
  if (!prospect) {
    console.warn('[Power Dialer API] No prospect provided for HubSpot search');
    return null;
  }

  try {
    // Use centralized crmAPI function
    if (typeof crmAPI === 'undefined') {
      console.warn('[Power Dialer API] crmAPI not available');
      return null;
    }

    const contact = await crmAPI.findHubSpotContact({
      name: prospect.name,
      phone: prospect.phone,
      email: prospect.email
    });

    if (contact) {
      console.log('[Power Dialer API] HubSpot contact found:', contact);
      return contact;
    }

    console.log('[Power Dialer API] No HubSpot contact found');
    return null;
  } catch (error) {
    console.error('[Power Dialer API] Error searching HubSpot:', error);
    return null;
  }
}

// ============================================================================
// CONTACT DATA ENRICHMENT
// ============================================================================

/**
 * Enrich prospect data with HubSpot contact information
 * 
 * Merges Power Dialer prospect data with HubSpot contact details.
 * If HubSpot search fails or returns no contact, returns enriched data
 * with original prospect information intact.
 * 
 * @param {Object} prospect - Prospect from Power Dialer queue
 * @param {Object|null} hubspotContact - Contact from HubSpot search (may be null)
 * @returns {Object} - Enriched contact data for Active Call
 */
function enrichContactData(prospect, hubspotContact) {
  if (!prospect) {
    return null;
  }

  // Start with Power Dialer prospect as base
  const enrichedContact = {
    // Core identification
    name: prospect.name || '',
    number: prospect.phone || '',
    email: prospect.email || '',
    
    // Organization info
    company: prospect.company || '',
    jobTitle: prospect.title || '',
    
    // Call-related fields
    location: prospect.company || '',
    avatar: prospect.avatar || '',
    dealValue: prospect.dealValue || '',
    pipelineStage: prospect.pipelineStage || '',
    
    // Track if this came from HubSpot enrichment
    isEnriched: false,
    sourceProspectId: prospect.id || null
  };

  // If HubSpot contact found, merge/override with HubSpot data
  if (hubspotContact) {
    enrichedContact.isEnriched = true;
    
    // Merge HubSpot fields (these override prospect fields)
    if (hubspotContact.name) enrichedContact.name = hubspotContact.name;
    if (hubspotContact.phone) enrichedContact.number = hubspotContact.phone;
    if (hubspotContact.email) enrichedContact.email = hubspotContact.email;
    if (hubspotContact.company) enrichedContact.company = hubspotContact.company;
    if (hubspotContact.jobTitle) enrichedContact.jobTitle = hubspotContact.jobTitle;
    if (hubspotContact.title) enrichedContact.jobTitle = hubspotContact.title;
    
    // Store HubSpot ID for future operations
    if (hubspotContact.id) enrichedContact.hubspotId = hubspotContact.id;
    
    // Store full HubSpot contact for reference
    if (hubspotContact) enrichedContact.hubspotContact = hubspotContact;
  }

  return enrichedContact;
}

// ============================================================================
// CALL CONNECTED WORKFLOW
// ============================================================================

/**
 * Execute the complete workflow when a prospect is marked as connected
 * 
 * This is the main integration point that orchestrates:
 * 1. Searching HubSpot for contact information
 * 2. Enriching the prospect with HubSpot data
 * 3. Preparing the contact for Active Call transition
 * 
 * The workflow is non-blocking: if HubSpot search fails, the call
 * continues with the original prospect data.
 * 
 * @param {Object} prospect - Prospect from Power Dialer queue
 * @returns {Promise<Object>} - Enriched contact data ready for Active Call
 */
async function onProspectConnected(prospect) {
  if (!prospect) {
    console.error('[Power Dialer API] No prospect data provided');
    return null;
  }

  try {
    // Search HubSpot for contact information
    const hubspotContact = await searchHubSpotContact(prospect);
    
    // Enrich prospect data with HubSpot information
    const enrichedContact = enrichContactData(prospect, hubspotContact);
    
    // Log enrichment result
    if (hubspotContact) {
      console.log('[Power Dialer API] Prospect enriched with HubSpot data');
    } else {
      console.log('[Power Dialer API] Prospect using local data (HubSpot not available)');
    }
    
    return enrichedContact;
  } catch (error) {
    console.error('[Power Dialer API] Error in onProspectConnected:', error);
    // Fall back to basic prospect data
    return enrichContactData(prospect, null);
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

/**
 * Expose Power Dialer API utilities globally
 * 
 * Usage:
 *   const enrichedContact = await powerDialerAPI.onProspectConnected(prospect);
 *   const contact = await powerDialerAPI.searchHubSpotContact(prospect);
 */
const powerDialerAPI = {
  loadCallQueue,
  updateCallQueueItem,
  loadCallQueueEvents,

  // Main workflow
  onProspectConnected,
  
  // Individual functions
  searchHubSpotContact,
  enrichContactData,
  
  // Cache key references
  cacheKeys: POWER_DIALER_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.powerDialerAPI = powerDialerAPI;
}