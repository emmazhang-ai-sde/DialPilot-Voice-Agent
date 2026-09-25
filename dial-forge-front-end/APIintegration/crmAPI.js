/**
 * DialForge CRM API Integration Layer
 * 
 * Centralized reusable CRM operations for HubSpot and Zendesk.
 * Used by: Profile, Active Call, Post Call, Power Dialer, Dashboard, Call History
 * 
 * This layer contains ALL CRM-specific API logic.
 * General API infrastructure remains in dialforgeApi.js.
 * 
 * Dependencies:
 * - dialforgeApi.js (universal fetch wrapper, error handling, localStorage fallback)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const CRM_CACHE_KEYS = {
  HUBSPOT_CONTACTS: 'crm_hubspot_contacts',
  HUBSPOT_CONTACT_SYNC: 'crm_hubspot_contact_sync',
  ZENDESK_TICKETS: 'crm_zendesk_tickets'
};

// ============================================================================
// PHONE NORMALIZATION UTILITY
// ============================================================================

/**
 * Normalize phone number for comparison
 * Removes spaces, parentheses, dashes; handles country codes
 */
function normalizePhone(phone) {
  if (!phone) return '';
  try {
    let normalized = phone.replace(/^(\+)/, '__PLUS__');
    normalized = normalized.replace(/\D/g, '');
    normalized = normalized.replace('__PLUS__', '+');
    return normalized.trim();
  } catch (e) {
    console.warn('[CRM API] Error normalizing phone:', e);
    return phone;
  }
}

/**
 * Compare two phone numbers after normalization
 */
function phonesMatch(phone1, phone2) {
  if (!phone1 || !phone2) return false;
  const normalized1 = normalizePhone(phone1);
  const normalized2 = normalizePhone(phone2);
  return normalized1 === normalized2 && normalized1.length > 0;
}

// ============================================================================
// HUBSPOT CONTACTS - CORE OPERATIONS
// ============================================================================

/**
 * Fetch all HubSpot contacts
 * Used by multiple pages to retrieve contact list
 * 
 * @returns {Promise<Array>} Array of HubSpot contact objects
 */
async function getHubSpotContacts() {
  try {
    const response = await dialforgeApi.fetch('/api/hubspot/contacts', {
      fallbackKey: CRM_CACHE_KEYS.HUBSPOT_CONTACTS,
      fallbackValue: []
    });

    let contacts = Array.isArray(response) 
      ? response 
      : (response?.contacts || response?.data || []);

    console.log('[CRM API] Fetched HubSpot contacts:', contacts.length);
    return contacts || [];
  } catch (error) {
    console.error('[CRM API] Error fetching HubSpot contacts:', error);
    return [];
  }
}

/**
 * Find a HubSpot contact by strongest available identifier
 * 
 * Priority order:
 * 1. HubSpot vendor ID / ID
 * 2. Email address
 * 3. Phone number (normalized)
 * 4. Name
 * 
 * @param {Object} identifier - Object with name, email, phone, hubspotId
 * @returns {Promise<Object|null>} Matched contact or null
 */
async function findHubSpotContact(identifier) {
  if (!identifier) {
    console.warn('[CRM API] No identifier provided for contact search');
    return null;
  }

  try {
    const contacts = await getHubSpotContacts();
    if (!contacts || contacts.length === 0) return null;

    // Try vendor_id first
    if (identifier.hubspotId) {
      const byId = contacts.find(c => 
        c.id === identifier.hubspotId || c.vendor_id === identifier.hubspotId
      );
      if (byId) return byId;
    }

    // Try email
    if (identifier.email) {
      const byEmail = contacts.find(c => 
        c.email && c.email.toLowerCase() === identifier.email.toLowerCase()
      );
      if (byEmail) return byEmail;
    }

    // Try phone (normalized)
    if (identifier.phone) {
      const byPhone = contacts.find(c => 
        c.phone && phonesMatch(identifier.phone, c.phone)
      );
      if (byPhone) return byPhone;
    }

    // Try name
    if (identifier.name) {
      const byName = contacts.find(c => 
        c.name && c.name.toLowerCase() === identifier.name.toLowerCase() ||
        (c.firstname && c.lastname && 
         `${c.firstname} ${c.lastname}`.toLowerCase() === identifier.name.toLowerCase())
      );
      if (byName) return byName;
    }

    return null;
  } catch (error) {
    console.error('[CRM API] Error finding contact:', error);
    return null;
  }
}

/**
 * Filter HubSpot contacts by owner
 * Used for personal pipeline, team metrics
 * 
 * @param {string} ownerEmail - Email of contact owner
 * @returns {Promise<Array>} Contacts owned by specified email
 */
async function getContactsByOwner(ownerEmail) {
  if (!ownerEmail) return [];

  try {
    const contacts = await getHubSpotContacts();
    const owned = contacts.filter(c => 
      c.owner === ownerEmail || 
      c.owner_email === ownerEmail ||
      c.assigned_to === ownerEmail
    );
    
    console.log('[CRM API] Found', owned.length, 'contacts for owner:', ownerEmail);
    return owned;
  } catch (error) {
    console.error('[CRM API] Error filtering contacts by owner:', error);
    return [];
  }
}

// ============================================================================
// HUBSPOT SYNC STATUS & LIFECYCLE
// ============================================================================

/**
 * Get HubSpot sync status for a contact
 * 
 * Determines if contact is synced to HubSpot CRM:
 * - Synced: synced === true OR valid vendor_id exists
 * - Local Only: no sync or vendor_id
 * 
 * @param {Object} contact - Contact object with sync info
 * @returns {Object} Sync status object
 */
function getHubSpotSyncStatus(contact) {
  if (!contact) {
    return {
      isSynced: false,
      status: 'Local Only',
      vendorId: null
    };
  }

  const isSynced = contact.synced === true || !!contact.vendor_id;
  
  return {
    isSynced,
    status: isSynced ? 'Synced' : 'Local Only',
    vendorId: contact.vendor_id || contact.id,
    syncedAt: contact.synced_at || null
  };
}

/**
 * Get lifecycle stage from HubSpot contact
 * 
 * Returns the actual lifecycle_stage from backend, no fabrication
 * 
 * @param {Object} contact - HubSpot contact object
 * @returns {string} Lifecycle stage (or empty string if not available)
 */
function getLifecycleStage(contact) {
  if (!contact) return '';
  
  // Handle multiple field name possibilities
  const stage = contact.lifecycle_stage || 
                contact.lifecycleStage || 
                contact.stage || 
                '';
  
  return stage;
}

/**
 * Format lifecycle stage for display
 * Converts snake_case to Title Case
 */
function formatLifecycleStage(stage) {
  if (!stage) return '—';
  
  return stage
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

// ============================================================================
// HUBSPOT CONTACT OPERATIONS
// ============================================================================

/**
 * Get or create normalized HubSpot contact info
 * Returns standardized contact object for UI display
 * 
 * @param {Object} contact - Raw HubSpot contact
 * @returns {Object} Normalized contact object
 */
function normalizeHubSpotContact(contact) {
  if (!contact) return null;

  const syncStatus = getHubSpotSyncStatus(contact);
  
  return {
    // Identity
    id: contact.id,
    vendorId: contact.vendor_id,
    name: contact.name || 
          (contact.firstname && contact.lastname ? 
           `${contact.firstname} ${contact.lastname}` : 
           ''),
    
    // Contact info
    email: contact.email,
    phone: contact.phone,
    
    // Business info
    company: contact.company,
    jobTitle: contact.job_title || contact.title,
    
    // CRM state
    lifecycleStage: getLifecycleStage(contact),
    owner: contact.owner,
    synced: syncStatus.isSynced,
    
    // Metadata
    createdAt: contact.created_at,
    updatedAt: contact.updated_at
  };
}

/**
 * Update HubSpot contact with call outcome
 * 
 * Used after a call to sync disposition, lifecycle, notes to HubSpot
 * 
 * @param {Object} updateData - Data to update
 * @returns {Promise<Object|null>} Update response or null
 */
async function updateHubSpotContact(updateData) {
  if (!updateData) {
    console.warn('[CRM API] No update data provided');
    return null;
  }

  try {
    // Build request body with actual backend contract
    const requestBody = {
      // Contact identification - use strongest available
      ...(updateData.vendorId && { id: updateData.vendorId }),
      ...(updateData.email && { email: updateData.email }),
      ...(updateData.phone && { phone: updateData.phone }),
      
      // Call outcome
      ...(updateData.disposition && { disposition: updateData.disposition }),
      ...(updateData.lifecycleStage && { lifecycle_stage: updateData.lifecycleStage }),
      
      // Additional context
      ...(updateData.notes && { notes: updateData.notes }),
      ...(updateData.lastCallDate && { last_call_date: updateData.lastCallDate })
    };

    console.log('[CRM API] Updating HubSpot contact:', requestBody);

    const response = await dialforgeApi.fetch('/api/hubspot/contacts', {
      method: 'POST',
      body: requestBody,
      fallbackKey: CRM_CACHE_KEYS.HUBSPOT_CONTACT_SYNC,
      fallbackValue: null
    });

    if (response) {
      console.log('[CRM API] HubSpot contact updated successfully');
      return normalizeHubSpotContact(response);
    }

    return null;
  } catch (error) {
    console.error('[CRM API] Error updating HubSpot contact:', error);
    return null;
  }
}

// ============================================================================
// ZENDESK TICKETS
// ============================================================================

/**
 * Fetch all Zendesk tickets
 * 
 * @returns {Promise<Array>} Array of Zendesk ticket objects
 */
async function getZendeskTickets() {
  try {
    const response = await dialforgeApi.fetch('/api/zendesk/tickets', {
      fallbackKey: CRM_CACHE_KEYS.ZENDESK_TICKETS,
      fallbackValue: []
    });

    let tickets = Array.isArray(response) 
      ? response 
      : (response?.tickets || response?.data || []);

    console.log('[CRM API] Fetched Zendesk tickets:', tickets.length);
    return tickets || [];
  } catch (error) {
    console.error('[CRM API] Error fetching Zendesk tickets:', error);
    return [];
  }
}

/**
 * Get support tickets for a contact by phone matching
 * Primary matching method: requester_phone normalized comparison
 * 
 * Used by: Profile, Active Call, Post Call for support history display
 * 
 * @param {string} contactPhone - Phone number to match
 * @returns {Promise<Array>} Matching tickets sorted by date (newest first)
 */
async function getTicketsByPhone(contactPhone) {
  if (!contactPhone) {
    console.warn('[CRM API] No phone provided for ticket lookup');
    return [];
  }

  try {
    const tickets = await getZendeskTickets();
    if (!tickets || tickets.length === 0) return [];

    // Filter by phone match (normalized)
    const matching = tickets.filter(ticket => 
      ticket.requester_phone && phonesMatch(contactPhone, ticket.requester_phone)
    );

    // Sort by creation date (newest first)
    matching.sort((a, b) => {
      const dateA = new Date(a.created_at || 0);
      const dateB = new Date(b.created_at || 0);
      return dateB - dateA;
    });

    console.log('[CRM API] Found', matching.length, 'tickets for phone:', contactPhone);
    return matching;
  } catch (error) {
    console.error('[CRM API] Error getting tickets by phone:', error);
    return [];
  }
}

/**
 * Get support tickets for a contact by email
 * Secondary matching method if email field available in ticket response
 * 
 * @param {string} contactEmail - Email to match
 * @returns {Promise<Array>} Matching tickets sorted by date (newest first)
 */
async function getTicketsByEmail(contactEmail) {
  if (!contactEmail) return [];

  try {
    const tickets = await getZendeskTickets();
    if (!tickets || tickets.length === 0) return [];

    // Filter by email match
    const matching = tickets.filter(ticket => 
      (ticket.requester_email || ticket.customer_email) === contactEmail.toLowerCase()
    );

    // Sort by creation date (newest first)
    matching.sort((a, b) => {
      const dateA = new Date(a.created_at || 0);
      const dateB = new Date(b.created_at || 0);
      return dateB - dateA;
    });

    return matching;
  } catch (error) {
    console.error('[CRM API] Error getting tickets by email:', error);
    return [];
  }
}

/**
 * Get active (open/pending) Zendesk tickets for assigned agent
 * Used for workload metrics
 * 
 * @param {string} agentEmail - Agent email to filter by
 * @returns {Promise<Array>} Active tickets assigned to agent
 */
async function getActiveTicketsByAgent(agentEmail) {
  if (!agentEmail) return [];

  try {
    const tickets = await getZendeskTickets();
    if (!tickets) return [];

    const active = tickets.filter(t => 
      (t.assigned_email === agentEmail || t.assignee === agentEmail) &&
      (t.status === 'open' || t.status === 'pending' || t.status === 'new')
    );

    return active;
  } catch (error) {
    console.error('[CRM API] Error getting active tickets:', error);
    return [];
  }
}

/**
 * Normalize Zendesk ticket for display
 * 
 * @param {Object} ticket - Raw Zendesk ticket
 * @returns {Object} Normalized ticket object
 */
function normalizeZendeskTicket(ticket) {
  if (!ticket) return null;

  return {
    id: ticket.id || ticket.ticket_id,
    subject: ticket.subject || 'Support Request',
    description: ticket.description || '',
    status: ticket.status || 'unknown',
    requesterPhone: ticket.requester_phone,
    requesterEmail: ticket.requester_email,
    createdAt: ticket.created_at,
    updatedAt: ticket.updated_at,
    priority: ticket.priority,
    url: ticket.url || ticket.link
  };
}

// ============================================================================
// AGENT/OWNER METRICS
// ============================================================================

/**
 * Get metrics for a specific agent/team member
 * Used by Profile, Dashboard for personal/team metrics
 * 
 * @param {string} agentEmail - Email of agent/team member
 * @returns {Promise<Object>} Aggregated metrics
 */
async function getAgentMetrics(agentEmail) {
  if (!agentEmail) return null;

  try {
    const [contacts, activeTickets] = await Promise.all([
      getContactsByOwner(agentEmail),
      getActiveTicketsByAgent(agentEmail)
    ]);

    return {
      totalContacts: contacts.length,
      activeTickets: activeTickets.length,
      personalPipeline: contacts.filter(c => 
        (c.lifecycle_stage === 'opportunity' || c.lifecycle_stage === 'lead')
      ).length
    };
  } catch (error) {
    console.error('[CRM API] Error getting agent metrics:', error);
    return null;
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const crmAPI = {
  // HubSpot contacts
  getHubSpotContacts,
  findHubSpotContact,
  getContactsByOwner,
  normalizeHubSpotContact,
  updateHubSpotContact,
  
  // HubSpot sync & lifecycle
  getHubSpotSyncStatus,
  getLifecycleStage,
  formatLifecycleStage,
  
  // Zendesk tickets
  getZendeskTickets,
  getTicketsByPhone,
  getTicketsByEmail,
  getActiveTicketsByAgent,
  normalizeZendeskTicket,
  
  // Metrics
  getAgentMetrics,
  
  // Utilities
  normalizePhone,
  phonesMatch,
  
  // Cache keys
  cacheKeys: CRM_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.crmAPI = crmAPI;
}
