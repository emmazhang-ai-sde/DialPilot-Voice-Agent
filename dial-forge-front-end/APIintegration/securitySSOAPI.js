/**
 * DialForge Security & SSO API Integration Layer
 * 
 * Security/SSO-specific API operations:
 * - Tool/integration permission health diagnostics
 * - Re-authorization URL handling
 * - Local security preferences persistence
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const SECURITY_SSO_CACHE_KEYS = {
  TOOL_INFORMATION: 'sec_tool_information',
  LOCAL_PREFERENCES: 'sec_local_preferences'
};

// ============================================================================
// TOOL INFORMATION & PERMISSION HEALTH
// ============================================================================

/**
 * Get tool/integration information from backend
 * 
 * @returns {Promise<Array>} Array of tool information objects
 */
async function getToolInformation() {
  try {
    // Check localStorage for cached data
    const cached = localStorage.getItem(SECURITY_SSO_CACHE_KEYS.TOOL_INFORMATION);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide tool information endpoint
    // This would need to be added by backend team
    
    console.warn('[Security SSO API] Tool information not available from backend');
    return [];
  } catch (error) {
    console.error('[Security SSO API] Error getting tool information:', error);
    return [];
  }
}

/**
 * Get status for a specific tool
 * 
 * @param {string} toolName - Name of the tool (e.g., 'hubspot', 'zendesk', 'zapier')
 * @param {Array} tools - Array of tool information from backend
 * @returns {Object} Tool status object
 */
function getToolStatus(toolName, tools) {
  if (!Array.isArray(tools)) {
    return {
      tool: toolName,
      status: 'UNKNOWN',
      message: 'Unknown status',
      requiresReauth: false,
      oauthUrl: null
    };
  }

  const tool = tools.find(t => 
    (t.name && t.name.toLowerCase() === toolName.toLowerCase()) ||
    (t.id && t.id.toLowerCase() === toolName.toLowerCase())
  );

  if (!tool) {
    return {
      tool: toolName,
      status: 'UNKNOWN',
      message: 'Tool not found',
      requiresReauth: false,
      oauthUrl: null
    };
  }

  const status = tool.status || 'UNKNOWN';
  const requiresReauth = status === 'REQUIRES_REAUTHORIZATION';

  return {
    tool: toolName,
    status: status,
    message: formatStatusMessage(status),
    requiresReauth: requiresReauth,
    oauthUrl: tool.oauth_url || tool.oauthUrl || null,
    lastChecked: tool.last_checked || null,
    permissions: tool.permissions || null
  };
}

/**
 * Format status message for display
 * 
 * @param {string} status - Status from backend
 * @returns {string} User-friendly message
 */
function formatStatusMessage(status) {
  const messages = {
    'AVAILABLE': 'Connected',
    'REQUIRES_REAUTHORIZATION': 'Reconnect Required',
    'REQUIRES_PERMISSION_MODIFICATION': 'Permissions Update Needed',
    'UNKNOWN': 'Status Unknown',
    'UNAVAILABLE': 'Not Available',
    'DISABLED': 'Disabled',
    'CONNECTING': 'Connecting...',
    'ERROR': 'Connection Error'
  };

  return messages[status] || `Status: ${status}`;
}

/**
 * Get status badge styling
 * 
 * @param {string} status - Status value
 * @returns {Object} Badge styling
 */
function getStatusBadgeStyle(status) {
  const styles = {
    'AVAILABLE': {
      bgColor: 'bg-tertiary/10',
      textColor: 'text-tertiary',
      icon: 'check_circle'
    },
    'REQUIRES_REAUTHORIZATION': {
      bgColor: 'bg-warning/10',
      textColor: 'text-warning',
      icon: 'sync'
    },
    'REQUIRES_PERMISSION_MODIFICATION': {
      bgColor: 'bg-secondary/10',
      textColor: 'text-secondary',
      icon: 'security'
    },
    'UNKNOWN': {
      bgColor: 'bg-white/5',
      textColor: 'text-on-surface-variant/60',
      icon: 'help'
    },
    'UNAVAILABLE': {
      bgColor: 'bg-error-red/10',
      textColor: 'text-error-red',
      icon: 'cancel'
    },
    'ERROR': {
      bgColor: 'bg-error-red/10',
      textColor: 'text-error-red',
      icon: 'error'
    }
  };

  return styles[status] || styles['UNKNOWN'];
}

// ============================================================================
// LOCAL SECURITY PREFERENCES
// ============================================================================

/**
 * Get local security preferences from localStorage
 * 
 * @returns {Object} Local preferences
 */
function getLocalSecurityPreferences() {
  try {
    const cached = localStorage.getItem(SECURITY_SSO_CACHE_KEYS.LOCAL_PREFERENCES);
    if (cached) {
      return JSON.parse(cached);
    }

    // Default preferences
    return {
      sessionTimeout: 30,     // minutes
      twoFactorEnforced: false,
      ipWhitelistEnabled: false,
      auditLogsEnabled: true
    };
  } catch (error) {
    console.error('[Security SSO API] Error getting preferences:', error);
    return {
      sessionTimeout: 30,
      twoFactorEnforced: false,
      ipWhitelistEnabled: false,
      auditLogsEnabled: true
    };
  }
}

/**
 * Save local security preferences to localStorage
 * 
 * @param {Object} preferences - Preferences to save
 * @returns {Object} { success: boolean, message: string }
 */
function saveLocalSecurityPreferences(preferences) {
  try {
    if (!preferences) {
      return {
        success: false,
        message: 'No preferences provided'
      };
    }

    localStorage.setItem(SECURITY_SSO_CACHE_KEYS.LOCAL_PREFERENCES, JSON.stringify(preferences));

    return {
      success: true,
      message: 'Preferences saved'
    };
  } catch (error) {
    console.error('[Security SSO API] Error saving preferences:', error);
    return {
      success: false,
      message: `Error: ${error.message}`
    };
  }
}

// ============================================================================
// RE-AUTHORIZATION HANDLING
// ============================================================================

/**
 * Get OAuth authorization URL for a tool
 * 
 * @param {string} toolName - Tool name
 * @param {Array} tools - Tool information array
 * @returns {string|null} OAuth URL or null if unavailable
 */
function getOAuthUrl(toolName, tools) {
  const toolStatus = getToolStatus(toolName, tools);
  
  if (!toolStatus.oauthUrl) {
    console.warn(`[Security SSO API] No OAuth URL available for ${toolName}`);
    return null;
  }

  return toolStatus.oauthUrl;
}

/**
 * Check if tool requires reauthorization
 * 
 * @param {string} toolName - Tool name
 * @param {Array} tools - Tool information array
 * @returns {boolean} True if reauth required
 */
function requiresReauthorization(toolName, tools) {
  const toolStatus = getToolStatus(toolName, tools);
  return toolStatus.status === 'REQUIRES_REAUTHORIZATION';
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const securitySSOAPI = {
  // Tool information
  getToolInformation,
  getToolStatus,
  formatStatusMessage,
  getStatusBadgeStyle,
  requiresReauthorization,

  // OAuth/reauth
  getOAuthUrl,

  // Local preferences
  getLocalSecurityPreferences,
  saveLocalSecurityPreferences,

  // Cache keys
  cacheKeys: SECURITY_SSO_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.securitySSOAPI = securitySSOAPI;
}