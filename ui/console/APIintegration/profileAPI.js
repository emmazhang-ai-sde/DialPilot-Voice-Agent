/**
 * DialForge Profile API Integration Layer
 * 
 * Profile-specific API operations (Apollo enrichment, etc.)
 * CRM operations (HubSpot, Zendesk) are now centralized in crmAPI.js
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const PROFILE_CACHE_KEYS = {
  APOLLO_ENRICHMENT: 'profile_apollo_enrichment'
};

// ============================================================================
// APOLLO LEAD ENRICHMENT
// ============================================================================

/**
 * Enrich profile with Apollo lead data
 * 
 * Endpoint: POST /api/apollo/leads/enrich
 */
async function enrichProfileWithApollo(profileData) {
  if (!profileData) {
    console.warn('[Profile API] No profile data provided for Apollo enrichment');
    return null;
  }

  try {
    const enrichmentRequest = {};
    
    if (profileData.name) enrichmentRequest.name = profileData.name;
    if (profileData.email) enrichmentRequest.email = profileData.email;
    if (profileData.phone) enrichmentRequest.phone = profileData.phone;
    if (profileData.company) enrichmentRequest.company = profileData.company;

    if (Object.keys(enrichmentRequest).length === 0) {
      console.warn('[Profile API] No enrichment fields available for Apollo');
      return null;
    }

    console.log('[Profile API] Sending Apollo enrichment request:', enrichmentRequest);

    const response = await dialforgeApi.fetch('/api/apollo/leads/enrich', {
      method: 'POST',
      body: enrichmentRequest,
      fallbackKey: PROFILE_CACHE_KEYS.APOLLO_ENRICHMENT,
      fallbackValue: null
    });

    if (response) {
      console.log('[Profile API] Apollo enrichment successful:', response);
      return normalizeApolloResponse(response, profileData);
    } else {
      console.warn('[Profile API] No Apollo enrichment response');
      return null;
    }
  } catch (error) {
    console.error('[Profile API] Error enriching profile with Apollo:', error);
    return null;
  }
}

/**
 * Normalize Apollo enrichment response to profile model
 */
function normalizeApolloResponse(apolloData, existingProfile) {
  if (!apolloData) return null;

  const enriched = { ...existingProfile };

  // Only update fields that Apollo actually returned
  if (apolloData.phone_direct) enriched.phone = apolloData.phone_direct;
  if (apolloData.phone) enriched.phone = apolloData.phone;
  
  if (apolloData.email_verified) enriched.email = apolloData.email_verified;
  if (apolloData.email) enriched.email = apolloData.email;
  
  if (apolloData.job_title) enriched.jobTitle = apolloData.job_title;
  if (apolloData.title) enriched.jobTitle = apolloData.title;
  
  if (apolloData.department) enriched.department = apolloData.department;
  if (apolloData.company) enriched.company = apolloData.company;
  if (apolloData.company_location) enriched.companyLocation = apolloData.company_location;
  if (apolloData.seniority) enriched.seniority = apolloData.seniority;
  
  // Social profiles if returned
  if (apolloData.linkedin_url) enriched.linkedinUrl = apolloData.linkedin_url;
  if (apolloData.twitter_url) enriched.twitterUrl = apolloData.twitter_url;
  
  enriched.enrichedAt = new Date().toISOString();
  enriched.enrichedSource = 'Apollo';

  return enriched;
}

// ============================================================================
// HUBSPOT INTEGRATION (now using centralized crmAPI.js)
// ============================================================================

/**
 * Get HubSpot contact for profile
 * DELEGATED to crmAPI.js - using centralized function
 */
async function getHubSpotContactForProfile(profileData) {
  if (!profileData) {
    console.warn('[Profile API] No profile data provided for HubSpot lookup');
    return null;
  }

  try {
    // Use centralized crmAPI function
    if (typeof crmAPI === 'undefined') {
      console.warn('[Profile API] crmAPI not available');
      return null;
    }

    const contact = await crmAPI.findHubSpotContact({
      name: profileData.name,
      email: profileData.email,
      phone: profileData.phone,
      hubspotId: profileData.hubspotId
    });

    if (contact) {
      return crmAPI.normalizeHubSpotContact(contact);
    }

    return null;
  } catch (error) {
    console.error('[Profile API] Error fetching HubSpot contact:', error);
    return null;
  }
}

// ============================================================================
// ZENDESK INTEGRATION (now using centralized crmAPI.js)
// ============================================================================

/**
 * Get Zendesk tickets for profile
 * DELEGATED to crmAPI.js - using centralized function
 */
async function getZendeskTicketsForProfile(profileData) {
  if (!profileData || !profileData.phone) {
    console.warn('[Profile API] No phone number for Zendesk lookup');
    return [];
  }

  try {
    // Use centralized crmAPI function
    if (typeof crmAPI === 'undefined') {
      console.warn('[Profile API] crmAPI not available');
      return [];
    }

    const tickets = await crmAPI.getTicketsByPhone(profileData.phone);
    return tickets.map(t => crmAPI.normalizeZendeskTicket(t));
  } catch (error) {
    console.error('[Profile API] Error getting Zendesk tickets:', error);
    return [];
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const profileAPI = {
  // Apollo enrichment (Profile-specific)
  enrichProfileWithApollo,
  
  // HubSpot (delegated to crmAPI)
  getHubSpotContactForProfile,
  
  // Zendesk (delegated to crmAPI)
  getZendeskTicketsForProfile,
  
  // Cache keys
  cacheKeys: PROFILE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.profileAPI = profileAPI;
}