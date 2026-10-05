/**
 * DialForge General Settings API Integration Layer
 * 
 * General Settings-specific API operations:
 * - Account metadata (organization details)
 * - User profile information
 * - Localization and timezone settings
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const SETTINGS_GENERAL_CACHE_KEYS = {
  ACCOUNT_METADATA: 'sg_account_metadata',
  USER_PROFILE: 'sg_user_profile'
};

// ============================================================================
// ACCOUNT METADATA
// ============================================================================

/**
 * Get account metadata from backend
 * 
 * @returns {Promise<Object>} Account information
 */
async function getAccountMetadata() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(SETTINGS_GENERAL_CACHE_KEYS.ACCOUNT_METADATA);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide account metadata endpoint
    // This would need to be added by backend team
    
    console.warn('[Settings General API] Account metadata not available from backend');
    return {
      accountId: null,
      companyName: null,
      timezone: null,
      currency: null,
      isAvailable: false,
      error: 'Account metadata not available from backend'
    };
  } catch (error) {
    console.error('[Settings General API] Error getting account metadata:', error);
    return {
      accountId: null,
      companyName: null,
      timezone: null,
      currency: null,
      isAvailable: false,
      error: error.message
    };
  }
}

/**
 * Normalize account metadata response
 * 
 * @param {Object} data - Raw response from backend
 * @returns {Object} Normalized structure
 */
function normalizeAccountMetadata(data) {
  if (!data) {
    return {
      accountId: null,
      companyName: null,
      timezone: null,
      currency: null
    };
  }

  return {
    accountId: data.account_id || data.accountId || data.portal_id || data.portalId || null,
    companyName: data.company_name || data.companyName || data.portal_name || data.portalName || null,
    timezone: data.timezone || data.account_timezone || data.accountTimezone || null,
    currency: data.currency || data.primary_currency || data.primaryCurrency || null
  };
}

// ============================================================================
// USER PROFILE
// ============================================================================

/**
 * Get user profile information from backend
 * 
 * @returns {Promise<Object>} User profile information
 */
async function getUserProfile() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(SETTINGS_GENERAL_CACHE_KEYS.USER_PROFILE);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide user profile endpoint
    // This would need to be added by backend team
    
    console.warn('[Settings General API] User profile not available from backend');
    return {
      userId: null,
      displayName: null,
      email: null,
      isAvailable: false,
      error: 'User profile not available from backend'
    };
  } catch (error) {
    console.error('[Settings General API] Error getting user profile:', error);
    return {
      userId: null,
      displayName: null,
      email: null,
      isAvailable: false,
      error: error.message
    };
  }
}

/**
 * Normalize user profile response
 * 
 * @param {Object} data - Raw response from backend
 * @returns {Object} Normalized structure
 */
function normalizeUserProfile(data) {
  if (!data) {
    return {
      userId: null,
      displayName: null,
      email: null
    };
  }

  return {
    userId: data.user_id || data.userId || data.id || null,
    displayName: data.display_name || data.displayName || data.full_name || data.fullName || null,
    email: data.email || null
  };
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const settingsGeneralAPI = {
  // Account metadata
  getAccountMetadata,
  normalizeAccountMetadata,

  // User profile
  getUserProfile,
  normalizeUserProfile,

  // Cache keys
  cacheKeys: SETTINGS_GENERAL_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.settingsGeneralAPI = settingsGeneralAPI;
}