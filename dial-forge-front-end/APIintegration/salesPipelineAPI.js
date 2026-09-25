/**
 * DialForge Sales Pipeline API Integration Layer
 * 
 * Sales Pipeline-specific API operations:
 * - Fetch HubSpot contacts and normalize to pipeline format
 * - Update contact lifecycle stage via HubSpot API
 * - Map HubSpot lifecycle values to internal pipeline stages
 * - Apollo prospect discovery (if available)
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const SALES_PIPELINE_CACHE_KEYS = {
  CONTACTS: 'sp_hubspot_contacts',
  STAGE_UPDATES: 'sp_stage_updates'
};

// ============================================================================
// HUBSPOT LIFECYCLE STAGE MAPPING
// ============================================================================

/**
 * Map HubSpot lifecycle_stage values to internal pipeline stages
 * HubSpot provides: lead, opportunity, customer, etc.
 * Internal pipeline stages: prospect, contacted, demo, proposal, closing
 */
const HUBSPOT_TO_PIPELINE_STAGE_MAP = {
  'lead': 'prospect',           // New lead stage
  'prospect': 'prospect',        // Prospect stage (if HubSpot uses it)
  'opportunity': 'demo',        // Demo/evaluation stage
  'customer': 'closing',        // Closed won
  'evangelist': 'closing',      // Existing customer advocate
  'other': 'prospect'           // Unknown maps to prospect
};

/**
 * Map internal pipeline stages back to HubSpot lifecycle_stage values
 */
const PIPELINE_TO_HUBSPOT_STAGE_MAP = {
  'prospect': 'lead',
  'contacted': 'lead',
  'demo': 'opportunity',
  'proposal': 'opportunity',
  'closing': 'customer'
};

/**
 * Convert HubSpot lifecycle_stage to internal pipeline stage
 * 
 * @param {string} hubspotStage - HubSpot lifecycle_stage value
 * @returns {string} Internal pipeline stage
 */
function mapHubSpotStageToPipeline(hubspotStage) {
  if (!hubspotStage) return 'prospect';
  
  const normalized = (hubspotStage || '').toLowerCase().trim();
  return HUBSPOT_TO_PIPELINE_STAGE_MAP[normalized] || 'prospect';
}

/**
 * Convert internal pipeline stage to HubSpot lifecycle_stage
 * 
 * @param {string} pipelineStage - Internal pipeline stage
 * @returns {string} HubSpot lifecycle_stage value
 */
function mapPipelineStageToHubSpot(pipelineStage) {
  if (!pipelineStage) return 'lead';
  return PIPELINE_TO_HUBSPOT_STAGE_MAP[pipelineStage] || 'lead';
}

// ============================================================================
// FETCH HUBSPOT CONTACTS FOR PIPELINE
// ============================================================================

/**
 * Fetch HubSpot contacts and normalize to pipeline format
 * 
 * @returns {Promise<Array>} Array of contact objects formatted for pipeline
 */
async function fetchPipelineContacts() {
  try {
    // Use centralized crmAPI to fetch HubSpot contacts
    if (typeof crmAPI === 'undefined') {
      console.warn('[Sales Pipeline API] crmAPI not available');
      return [];
    }

    const contacts = await crmAPI.getHubSpotContacts();
    
    if (!contacts || contacts.length === 0) {
      console.log('[Sales Pipeline API] No HubSpot contacts found');
      return [];
    }

    // Transform HubSpot contacts to pipeline deal format
    const deals = contacts.map((contact, index) => {
      const hubspotStage = contact.lifecycle_stage || contact.lifecycleStage || 'lead';
      const pipelineStage = mapHubSpotStageToPipeline(hubspotStage);

      return {
        id: contact.id || `contact-${index}`,
        name: contact.name || 'Unknown Contact',
        company: contact.company || 'Unknown Company',
        email: contact.email,
        phone: contact.phone,
        jobTitle: contact.jobTitle,
        
        // Pipeline-specific fields
        stage: pipelineStage,
        hubspotStage: hubspotStage,      // Keep original for sync
        hubspotId: contact.id,
        
        // Deal mock values (frontend only, not from backend)
        value: generateMockDealValue(contact),
        winProb: generateMockWinProb(contact),
        logo: null,
        
        // Metadata
        isFromAPI: true,
        createdAt: contact.createdAt,
        updatedAt: contact.updatedAt
      };
    });

    // Cache the contacts
    dialforgeApi.cacheData(SALES_PIPELINE_CACHE_KEYS.CONTACTS, deals);

    console.log('[Sales Pipeline API] Loaded', deals.length, 'contacts from HubSpot');
    return deals;
  } catch (error) {
    console.error('[Sales Pipeline API] Error fetching pipeline contacts:', error);
    return [];
  }
}

/**
 * Generate a mock deal value based on company characteristics
 * In a real system, this would come from HubSpot deal data
 * 
 * @param {Object} contact - Contact object
 * @returns {number} Mock deal value
 */
function generateMockDealValue(contact) {
  // Create deterministic but varied values based on contact data
  const seed = (contact.name || '').split('').reduce((a, b) => a + b.charCodeAt(0), 0);
  const baseValue = 10000 + ((seed * 7919) % 150000); // Vary from 10k to 160k
  return Math.round(baseValue / 100) * 100; // Round to nearest 100
}

/**
 * Generate a mock win probability based on pipeline stage
 * In a real system, this would come from HubSpot deal probability or AI scoring
 * 
 * @param {Object} contact - Contact object
 * @returns {number} Mock win probability (0-100)
 */
function generateMockWinProb(contact) {
  const stage = contact.lifecycle_stage || contact.lifecycleStage || 'lead';
  const baseProbability = {
    'lead': 15,
    'prospect': 15,
    'opportunity': 45,
    'demo': 55,
    'proposal': 75,
    'customer': 100,
    'evangelist': 100
  };
  
  const base = baseProbability[stage.toLowerCase()] || 25;
  // Add a small variation based on contact name
  const variation = (contact.name || '').split('').reduce((a, b) => a + b.charCodeAt(0), 0) % 20;
  return Math.max(10, Math.min(100, base + (variation > 10 ? variation - 10 : -(10 - variation))));
}

// ============================================================================
// UPDATE CONTACT LIFECYCLE STAGE
// ============================================================================

/**
 * Update a contact's lifecycle stage
 * Syncs change to HubSpot via crmAPI
 * 
 * @param {string} contactId - HubSpot contact ID
 * @param {string} newPipelineStage - New internal pipeline stage
 * @returns {Promise<Object>} { success: boolean, message: string, data: Object }
 */
async function updateContactStage(contactId, newPipelineStage) {
  if (!contactId || !newPipelineStage) {
    return {
      success: false,
      message: 'Missing contact ID or stage'
    };
  }

  try {
    // Verify crmAPI is available
    if (typeof crmAPI === 'undefined') {
      console.warn('[Sales Pipeline API] crmAPI not available for update');
      return {
        success: false,
        message: 'API not available - demo mode',
        isDemo: true
      };
    }

    // Convert internal stage to HubSpot lifecycle_stage
    const hubspotStage = mapPipelineStageToHubSpot(newPipelineStage);

    console.log('[Sales Pipeline API] Updating contact', contactId, 'to stage', newPipelineStage, '→', hubspotStage);

    // Call HubSpot update via crmAPI
    const result = await crmAPI.updateHubSpotContact({
      vendorId: contactId,
      lifecycleStage: hubspotStage
    });

    if (result) {
      // Cache the successful update
      dialforgeApi.cacheData(
        SALES_PIPELINE_CACHE_KEYS.STAGE_UPDATES,
        { contactId, newStage: newPipelineStage, timestamp: new Date().toISOString() }
      );

      return {
        success: true,
        message: `Contact moved to ${newPipelineStage}`,
        data: result
      };
    } else {
      return {
        success: false,
        message: 'Update did not return confirmation'
      };
    }
  } catch (error) {
    console.error('[Sales Pipeline API] Error updating contact stage:', error);
    return {
      success: false,
      message: `Error: ${error.message || 'Failed to update stage'}`,
      error
    };
  }
}

// ============================================================================
// APOLLO PROSPECT DISCOVERY
// ============================================================================

/**
 * Search for prospects via Apollo
 * 
 * @param {Object} searchParams - { company, title, seniority, location }
 * @returns {Promise<Array>} Array of prospect results
 */
async function searchApolloProspects(searchParams) {
  if (!searchParams) {
    return { success: false, message: 'No search parameters provided', results: [] };
  }

  try {
    // Build Apollo search request
    const payload = {
      ...searchParams
      // Apollo fields like: company, title, seniority, location, industry, etc.
    };

    console.log('[Sales Pipeline API] Searching Apollo for prospects:', payload);

    const response = await dialforgeApi.fetch('/api/apollo/leads/search', {
      method: 'POST',
      body: payload,
      fallbackValue: []
    });

    if (!response) {
      return {
        success: false,
        message: 'No results found',
        results: []
      };
    }

    // Handle different response formats
    const results = Array.isArray(response)
      ? response
      : (response.data || response.results || response.leads || []);

    // Transform Apollo results to pipeline contact format
    const prospects = (results || [])
      .slice(0, 10)  // Limit to 10 results
      .map((prospect, index) => ({
        id: prospect.id || `apollo-${Date.now()}-${index}`,
        name: prospect.first_name && prospect.last_name
          ? `${prospect.first_name} ${prospect.last_name}`
          : prospect.name || 'Unknown',
        company: prospect.organization || prospect.company || 'Unknown',
        email: prospect.email,
        phone: prospect.phone_number || prospect.phone,
        jobTitle: prospect.job_title || prospect.title,
        
        // Pipeline fields
        stage: 'prospect',
        hubspotStage: 'lead',
        hubspotId: null,  // Not yet in HubSpot
        
        // Mock values
        value: generateMockDealValue({ name: prospect.name }),
        winProb: 15,
        logo: null,
        
        // Metadata
        isFromApollo: true,
        createdAt: new Date().toISOString()
      }));

    return {
      success: true,
      message: `Found ${prospects.length} prospects`,
      results: prospects
    };
  } catch (error) {
    console.error('[Sales Pipeline API] Error searching Apollo:', error);
    return {
      success: false,
      message: `Search error: ${error.message}`,
      error,
      results: []
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const salesPipelineAPI = {
  // Fetching
  fetchPipelineContacts,
  searchApolloProspects,
  
  // Updates
  updateContactStage,
  
  // Stage mapping
  mapHubSpotStageToPipeline,
  mapPipelineStageToHubSpot,
  
  // Cache keys
  cacheKeys: SALES_PIPELINE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.salesPipelineAPI = salesPipelineAPI;
}