/**
 * DialForge Post Call API Integration Layer
 * 
 * Provides Post Call-specific API functionality:
 * - Zendesk support ticket creation
 * - Zapier workflow triggers
 * - Apollo lead enrichment
 * - HubSpot contact synchronization
 * - Data normalization for Post Call context
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const POST_CALL_CACHE_KEYS = {
  ZENDESK_TICKET: 'postcall_zendesk_ticket',
  APOLLO_ENRICHMENT: 'postcall_apollo_enrichment',
  HUBSPOT_SYNC: 'postcall_hubspot_sync'
};

// ============================================================================
// ZENDESK TICKET CREATION
// ============================================================================

/**
 * Create a Zendesk support ticket from post-call information
 * 
 * Endpoint: POST /api/zendesk/tickets
 * 
 * Purpose: Convert call outcome into support ticket without manual re-entry
 * 
 * @param {Object} ticketData - Pre-filled ticket information
 * @returns {Promise<Object>} - Created ticket info from Zendesk
 */
async function createZendeskTicket(ticketData) {
  if (!ticketData) {
    console.warn('[Post Call API] No ticket data provided for Zendesk');
    return null;
  }

  try {
    // Build request body with ticket information
    const requestBody = {
      subject: ticketData.subject || 'Support Request from Call',
      description: ticketData.description || '',
      requester_phone: ticketData.requester_phone || '',
      priority: ticketData.priority || 'normal',
      status: ticketData.status || 'new',
      
      // Optional context
      ...(ticketData.disposition && { disposition: ticketData.disposition }),
      ...(ticketData.call_duration && { call_duration: ticketData.call_duration }),
      ...(ticketData.caller_name && { caller_name: ticketData.caller_name }),
      ...(ticketData.caller_company && { caller_company: ticketData.caller_company })
    };

    console.log('[Post Call API] Creating Zendesk ticket:', requestBody);

    // Make the API request
    const response = await dialforgeApi.fetch('/api/zendesk/tickets', {
      method: 'POST',
      body: requestBody,
      fallbackKey: POST_CALL_CACHE_KEYS.ZENDESK_TICKET,
      fallbackValue: null
    });

    if (response) {
      console.log('[Post Call API] Zendesk ticket created:', response);
      return normalizeZendeskTicketResponse(response);
    } else {
      console.warn('[Post Call API] No Zendesk ticket response');
      return null;
    }
  } catch (error) {
    console.error('[Post Call API] Error creating Zendesk ticket:', error);
    return null;
  }
}

/**
 * Normalize Zendesk ticket response for display
 */
function normalizeZendeskTicketResponse(response) {
  if (!response) return null;

  return {
    ticketId: response.id || response.ticket_id,
    subject: response.subject,
    status: response.status,
    url: response.url || response.link,
    createdAt: response.created_at || new Date().toISOString()
  };
}

/**
 * Pre-fill ticket data from current call
 */
function buildZendeskTicketPayload(callData) {
  return {
    subject: `Call Outcome: ${callData.disposition || 'Follow-up Needed'}`,
    description: callData.summary || callData.notes || 'Call summary not available',
    requester_phone: callData.callerPhone || '',
    disposition: callData.disposition,
    call_duration: callData.duration,
    caller_name: callData.callerName,
    caller_company: callData.callerCompany,
    priority: determinePriority(callData.disposition)
  };
}

function determinePriority(disposition) {
  if (!disposition) return 'normal';
  
  const lowerDisposition = disposition.toLowerCase();
  if (lowerDisposition.includes('urgent') || lowerDisposition.includes('critical')) return 'high';
  if (lowerDisposition.includes('complaint') || lowerDisposition.includes('issue')) return 'high';
  return 'normal';
}

// ============================================================================
// ZAPIER WORKFLOW TRIGGER
// ============================================================================

/**
 * Trigger external Zapier workflow with post-call information
 * 
 * Endpoint: POST /api/zapier/trigger
 * 
 * Purpose: Send call summary to external systems (Slack, email, follow-up, etc.)
 * 
 * @param {Object} workflowData - Call data to send
 * @returns {Promise<Object>} - Zapier response
 */
async function triggerZapierWorkflow(workflowData) {
  if (!workflowData) {
    console.warn('[Post Call API] No workflow data provided for Zapier');
    return null;
  }

  try {
    // Build structured payload
    const requestBody = buildZapierPayload(workflowData);

    console.log('[Post Call API] Triggering Zapier workflow:', requestBody);

    // Make the API request
    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: requestBody,
      fallbackValue: null
    });

    if (response) {
      console.log('[Post Call API] Zapier workflow triggered successfully');
      return response;
    } else {
      console.warn('[Post Call API] No Zapier response');
      return null;
    }
  } catch (error) {
    console.error('[Post Call API] Error triggering Zapier workflow:', error);
    return null;
  }
}

/**
 * Build structured Zapier payload from post-call data
 */
function buildZapierPayload(callData) {
  return {
    event: callData.event || 'call_completed',
    timestamp: new Date().toISOString(),
    call: {
      duration: callData.duration,
      direction: callData.direction || 'inbound',
      disposition: callData.disposition,
      status: 'completed'
    },
    caller: {
      name: callData.callerName,
      phone: callData.callerPhone,
      email: callData.callerEmail,
      company: callData.callerCompany
    },
    summary: {
      ai_summary: callData.aiSummary,
      notes: callData.notes,
      outcome: callData.disposition
    },
    ...(callData.transcript && { transcript: callData.transcript })
  };
}

// ============================================================================
// APOLLO LEAD ENRICHMENT
// ============================================================================

/**
 * Enrich unknown/unsaved caller with Apollo data
 * 
 * Endpoint: POST /api/apollo/leads/enrich
 * 
 * Purpose: Get verified contact information for new prospects
 * 
 * @param {Object} callerData - Caller information to enrich
 * @returns {Promise<Object>} - Apollo enrichment response
 */
async function enrichCallerWithApollo(callerData) {
  if (!callerData) {
    console.warn('[Post Call API] No caller data provided for Apollo enrichment');
    return null;
  }

  try {
    // Build request with available identifiers
    const requestBody = {};
    
    if (callerData.phone) requestBody.phone = callerData.phone;
    if (callerData.email) requestBody.email = callerData.email;
    if (callerData.name) requestBody.name = callerData.name;
    if (callerData.company) requestBody.company = callerData.company;

    if (Object.keys(requestBody).length === 0) {
      console.warn('[Post Call API] No identifiers available for Apollo enrichment');
      return null;
    }

    console.log('[Post Call API] Enriching caller with Apollo:', requestBody);

    // Make the API request
    const response = await dialforgeApi.fetch('/api/apollo/leads/enrich', {
      method: 'POST',
      body: requestBody,
      fallbackKey: POST_CALL_CACHE_KEYS.APOLLO_ENRICHMENT,
      fallbackValue: null
    });

    if (response) {
      console.log('[Post Call API] Apollo enrichment successful:', response);
      return normalizeApolloResponse(response);
    } else {
      console.warn('[Post Call API] No Apollo enrichment response');
      return null;
    }
  } catch (error) {
    console.error('[Post Call API] Error enriching caller with Apollo:', error);
    return null;
  }
}

/**
 * Normalize Apollo enrichment response
 */
function normalizeApolloResponse(apolloData) {
  if (!apolloData) return null;

  return {
    // Contact info
    email: apolloData.email || apolloData.email_verified,
    phone: apolloData.phone || apolloData.phone_direct,
    
    // Professional info
    jobTitle: apolloData.job_title || apolloData.title,
    department: apolloData.department,
    seniority: apolloData.seniority,
    
    // Company info
    company: apolloData.company,
    companySize: apolloData.company_size,
    companyLocation: apolloData.company_location,
    industry: apolloData.industry,
    
    // Social profiles
    linkedinUrl: apolloData.linkedin_url,
    twitterUrl: apolloData.twitter_url,
    
    // Enrichment metadata
    enrichedAt: new Date().toISOString(),
    enrichedSource: 'Apollo'
  };
}

// ============================================================================
// HUBSPOT CONTACT SYNCHRONIZATION
// ============================================================================

/**
 * Update HubSpot contact with post-call disposition and lifecycle stage
 * 
 * Endpoint: POST /api/hubspot/contacts (or appropriate sync endpoint)
 * 
 * Purpose: Update CRM with call outcome without leaving DialForge
 * 
 * @param {Object} syncData - Contact and call outcome data
 * @returns {Promise<Object>} - HubSpot sync response
 */
async function updateHubSpotContact(syncData) {
  if (!syncData) {
    console.warn('[Post Call API] No sync data provided for HubSpot');
    return null;
  }

  try {
    // Build request body
    const requestBody = {
      // Contact identification
      ...(syncData.hubspotId && { id: syncData.hubspotId }),
      ...(syncData.email && { email: syncData.email }),
      ...(syncData.phone && { phone: syncData.phone }),
      
      // Call outcome
      disposition: syncData.disposition,
      lifecycle_stage: syncData.lifecycleStage,
      
      // Context
      ...(syncData.lastCallDate && { last_call_date: syncData.lastCallDate }),
      ...(syncData.callNotes && { notes: syncData.callNotes }),
      ...(syncData.callerName && { name: syncData.callerName })
    };

    console.log('[Post Call API] Updating HubSpot contact:', requestBody);

    // Make the API request
    const response = await dialforgeApi.fetch('/api/hubspot/contacts', {
      method: 'POST',
      body: requestBody,
      fallbackKey: POST_CALL_CACHE_KEYS.HUBSPOT_SYNC,
      fallbackValue: null
    });

    if (response) {
      console.log('[Post Call API] HubSpot contact updated:', response);
      return normalizeHubSpotSyncResponse(response);
    } else {
      console.warn('[Post Call API] No HubSpot sync response');
      return null;
    }
  } catch (error) {
    console.error('[Post Call API] Error updating HubSpot contact:', error);
    return null;
  }
}

/**
 * Normalize HubSpot sync response
 */
function normalizeHubSpotSyncResponse(response) {
  if (!response) return null;

  return {
    hubspotId: response.id || response.vendor_id,
    synced: response.synced === true || !!response.vendor_id,
    lifecycleStage: response.lifecycle_stage,
    syncedAt: new Date().toISOString(),
    syncStatus: 'success'
  };
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

/**
 * Expose Post Call API utilities globally
 */
const postCallAPI = {
  // Zendesk
  createZendeskTicket,
  buildZendeskTicketPayload,
  
  // Zapier
  triggerZapierWorkflow,
  buildZapierPayload,
  
  // Apollo
  enrichCallerWithApollo,
  
  // HubSpot
  updateHubSpotContact,
  
  // Cache keys
  cacheKeys: POST_CALL_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.postCallAPI = postCallAPI;
}
