/**
 * DialForge Team & Role API Integration Layer
 * 
 * Team & Role-specific API operations:
 * - Organization details (teams, seats, job titles)
 * - User details (teams and roles)
 * - Owner directory (search owners)
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const TEAM_ROLE_CACHE_KEYS = {
  ORGANIZATION_DETAILS: 'tr_organization_details',
  USER_DETAILS: 'tr_user_details',
  OWNER_DIRECTORY: 'tr_owner_directory'
};

// ============================================================================
// ORGANIZATION DETAILS
// ============================================================================

/**
 * Get organization details including teams, seats, and job titles
 * 
 * @returns {Promise<Object>} Organization data with teams, seats, job_titles
 */
async function getOrganizationDetails() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(TEAM_ROLE_CACHE_KEYS.ORGANIZATION_DETAILS);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide organization details endpoint
    // This would need to be added by backend team
    
    console.warn('[Team Role API] Organization details not available from backend');
    return {
      teams: [],
      seats: [],
      jobTitles: [],
      isAvailable: false,
      error: 'Organization details not available from backend'
    };
  } catch (error) {
    console.error('[Team Role API] Error getting organization details:', error);
    return {
      teams: [],
      seats: [],
      jobTitles: [],
      isAvailable: false,
      error: error.message
    };
  }
}

/**
 * Normalize organization details response
 * 
 * @param {Object} data - Raw response from backend
 * @returns {Object} Normalized structure
 */
function normalizeOrganizationDetails(data) {
  if (!data) {
    return {
      teams: [],
      seats: [],
      jobTitles: []
    };
  }

  return {
    teams: Array.isArray(data.teams) ? data.teams : [],
    seats: Array.isArray(data.seats) ? data.seats : [],
    jobTitles: Array.isArray(data.job_titles) ? data.job_titles : 
               Array.isArray(data.jobTitles) ? data.jobTitles : []
  };
}

// ============================================================================
// USER DETAILS
// ============================================================================

/**
 * Get user details including teams and roles
 * 
 * @returns {Promise<Array>} Array of user objects with teams and roles
 */
async function getUserDetails() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(TEAM_ROLE_CACHE_KEYS.USER_DETAILS);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide user details endpoint
    // This would need to be added by backend team
    
    console.warn('[Team Role API] User details not available from backend');
    return [];
  } catch (error) {
    console.error('[Team Role API] Error getting user details:', error);
    return [];
  }
}

/**
 * Format user details for display
 * 
 * @param {Object} user - User object from backend
 * @returns {Object} Formatted user
 */
function formatUserForDisplay(user) {
  if (!user) return null;

  return {
    id: user.id || user.user_id || '',
    name: user.name || user.full_name || 'Unknown',
    email: user.email || '',
    role: user.role || 'Member',
    team: user.team || user.teams?.[0] || '',
    teams: Array.isArray(user.teams) ? user.teams : [],
    jobTitle: user.job_title || user.title || '',
    status: user.status || 'Active'
  };
}

// ============================================================================
// OWNER DIRECTORY
// ============================================================================

/**
 * Search for owners in the organization
 * 
 * @returns {Promise<Array>} Array of owner objects
 */
async function searchOwners() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(TEAM_ROLE_CACHE_KEYS.OWNER_DIRECTORY);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide owner search endpoint
    // This would need to be added by backend team
    
    console.warn('[Team Role API] Owner directory not available from backend');
    return [];
  } catch (error) {
    console.error('[Team Role API] Error searching owners:', error);
    return [];
  }
}

/**
 * Format owner for display
 * 
 * @param {Object} owner - Owner object from backend
 * @returns {Object} Formatted owner
 */
function formatOwnerForDisplay(owner) {
  if (!owner) return null;

  return {
    id: owner.id || owner.owner_id || '',
    name: owner.name || owner.full_name || 'Unknown',
    email: owner.email || '',
    ownerId: owner.owner_id || 'Not Mapped',
    hubspotOwnerId: owner.hubspot_owner_id || 'Not Mapped',
    status: owner.status || 'Active'
  };
}

/**
 * Check if owner is mapped to a user
 * 
 * @param {Object} owner - Owner object
 * @returns {boolean} True if mapped
 */
function isOwnerMapped(owner) {
  if (!owner) return false;
  
  const ownerId = owner.owner_id || owner.ownerId;
  const hsOwnerId = owner.hubspot_owner_id || owner.hubspotOwnerId;
  
  return (ownerId && ownerId !== 'Not Mapped') || 
         (hsOwnerId && hsOwnerId !== 'Not Mapped');
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const teamRoleAPI = {
  // Organization details
  getOrganizationDetails,
  normalizeOrganizationDetails,

  // User details
  getUserDetails,
  formatUserForDisplay,

  // Owner directory
  searchOwners,
  formatOwnerForDisplay,
  isOwnerMapped,

  // Cache keys
  cacheKeys: TEAM_ROLE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.teamRoleAPI = teamRoleAPI;
}