/**
 * DialForge Contacts API Integration Layer
 * 
 * Contacts-specific API operations:
 * - Fetch HubSpot contacts for directory
 * - Apollo lead enrichment
 * - Local Apollo profile cache
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const CONTACTS_CACHE_KEYS = {
  HUBSPOT_CONTACTS: 'contacts_hubspot',
  APOLLO_PROFILES: 'contacts_apollo_profiles'
};

// ============================================================================
// FETCH HUBSPOT CONTACTS FOR DIRECTORY
// ============================================================================

/**
 * Fetch HubSpot contacts for the Contacts directory
 * 
 * @returns {Promise<Array>} Array of normalized contact objects
 */
async function fetchContactsFromHubSpot() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Contacts API] crmAPI not available');
      return [];
    }

    const contacts = await crmAPI.getHubSpotContacts();
    
    if (!contacts || contacts.length === 0) {
      console.log('[Contacts API] No HubSpot contacts found');
      return [];
    }

    // Transform HubSpot contacts to Contacts page format
    const formattedContacts = contacts.map((contact, index) => ({
      // Identity
      id: contact.id || `contact-${index}`,
      hubspotId: contact.id,
      
      // Basic info
      name: contact.name || '',
      firstName: contact.firstname || (contact.name ? contact.name.split(' ')[0] : ''),
      lastName: contact.lastname || (contact.name ? contact.name.split(' ').slice(1).join(' ') : ''),
      email: contact.email || '',
      phone: contact.phone || '',
      
      // Business info
      company: contact.company || '',
      title: contact.jobTitle || contact.job_title || '',
      
      // CRM state
      lifecycleStage: contact.lifecycleStage || contact.lifecycle_stage || 'lead',
      synced: contact.synced !== false,  // Default to true if not specified
      
      // Metadata
      createdAt: contact.createdAt || contact.created_at,
      updatedAt: contact.updatedAt || contact.updated_at,
      
      // UI fields (generated)
      status: 'cold',  // Will be set based on API data
      dealValue: 0,
      dealStage: '',
      dealProgress: 0,
      callCount: 0,
      bio: '',
      tags: [],
      calls: [],
      avatarUrl: '',
      
      // Mark as API-sourced
      isFromAPI: true
    }));

    // Cache the contacts
    dialforgeApi.cacheData(CONTACTS_CACHE_KEYS.HUBSPOT_CONTACTS, formattedContacts);

    console.log('[Contacts API] Loaded', formattedContacts.length, 'contacts from HubSpot');
    return formattedContacts;
  } catch (error) {
    console.error('[Contacts API] Error fetching HubSpot contacts:', error);
    return [];
  }
}

// ============================================================================
// APOLLO ENRICHMENT
// ============================================================================

/**
 * Enrich a contact using Apollo
 * 
 * @param {Object} contact - Contact object with name, email, phone, company
 * @returns {Promise<Object>} { success: boolean, enrichedContact: Object, message: string }
 */
async function enrichContactWithApollo(contact) {
  if (!contact) {
    return {
      success: false,
      message: 'No contact provided',
      enrichedContact: null
    };
  }

  try {
    // Build Apollo enrichment request
    const payload = {
      ...(contact.firstName && { first_name: contact.firstName }),
      ...(contact.lastName && { last_name: contact.lastName }),
      ...(contact.email && { email: contact.email }),
      ...(contact.phone && { phone_number: contact.phone }),
      ...(contact.company && { organization: contact.company })
    };

    // Only proceed if we have something to enrich
    if (Object.keys(payload).length === 0) {
      return {
        success: false,
        message: 'No contact information to enrich',
        enrichedContact: null
      };
    }

    console.log('[Contacts API] Enriching contact with Apollo:', payload);

    const response = await dialforgeApi.fetch('/api/apollo/leads/enrich', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (!response) {
      return {
        success: false,
        message: 'Apollo enrichment returned no data',
        enrichedContact: null
      };
    }

    // Transform Apollo response to contact format
    const enrichedData = {
      email: response.email || contact.email,
      phone: response.phone_number || response.phone || contact.phone,
      company: response.organization || response.company || contact.company,
      title: response.job_title || response.title || contact.title,
      firstName: response.first_name || contact.firstName,
      lastName: response.last_name || contact.lastName,
      bio: response.headline || response.bio || '',
      linkedinUrl: response.linkedin_url || response.linkedin || '',
      location: response.location || '',
      enriched: true,
      enrichedAt: new Date().toISOString()
    };

    // Cache the Apollo profile
    dialforgeApi.cacheData(
      CONTACTS_CACHE_KEYS.APOLLO_PROFILES,
      { contactId: contact.id || contact.hubspotId, ...enrichedData }
    );

    return {
      success: true,
      message: 'Contact enriched successfully',
      enrichedContact: enrichedData
    };
  } catch (error) {
    console.error('[Contacts API] Error enriching contact with Apollo:', error);
    return {
      success: false,
      message: `Enrichment error: ${error.message}`,
      enrichedContact: null,
      error
    };
  }
}

/**
 * Get cached Apollo profile for a contact
 * 
 * @param {string} contactId - Contact ID
 * @returns {Object|null} Cached profile or null
 */
function getCachedApolloProfile(contactId) {
  try {
    const cached = dialforgeApi.getCachedData(CONTACTS_CACHE_KEYS.APOLLO_PROFILES);
    if (cached && cached.contactId === contactId) {
      return cached;
    }
    return null;
  } catch (error) {
    console.warn('[Contacts API] Could not retrieve Apollo profile cache:', error);
    return null;
  }
}

// ============================================================================
// CONTACT FORMATTING HELPERS
// ============================================================================

/**
 * Determine if a contact needs enrichment
 * Returns true if missing critical fields
 * 
 * @param {Object} contact - Contact object
 * @returns {boolean} Whether contact should be offered for enrichment
 */
function needsEnrichment(contact) {
  if (!contact) return false;
  
  // Needs enrichment if missing phone, email, or title
  const hasMissingFields = !contact.phone || !contact.email || !contact.title;
  return hasMissingFields && !contact.enriched;
}

/**
 * Get display phone number for a contact
 * Returns first available phone, or empty string
 * 
 * @param {Object} contact - Contact object
 * @returns {string} Phone number or empty string
 */
function getDisplayPhone(contact) {
  if (!contact) return '';
  return contact.phone || contact.mobilePhone || contact.workPhone || '';
}

/**
 * Get status color based on deal stage or lifecycle
 * 
 * @param {Object} contact - Contact object
 * @returns {string} Status: 'hot', 'warm', or 'cold'
 */
function getContactStatus(contact) {
  if (!contact) return 'cold';
  
  if (contact.dealStage === 'Proposal' || contact.dealStage === 'Closing') return 'hot';
  if (contact.dealStage === 'Demo' || contact.dealStage === 'Discovery') return 'warm';
  
  if (contact.lifecycleStage === 'customer') return 'hot';
  if (contact.lifecycleStage === 'opportunity') return 'warm';
  
  return 'cold';
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const contactsAPI = {
  // HubSpot fetching
  fetchContactsFromHubSpot,
  
  // Apollo enrichment
  enrichContactWithApollo,
  getCachedApolloProfile,
  
  // Helpers
  needsEnrichment,
  getDisplayPhone,
  getContactStatus,
  
  // Cache keys
  cacheKeys: CONTACTS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.contactsAPI = contactsAPI;
}