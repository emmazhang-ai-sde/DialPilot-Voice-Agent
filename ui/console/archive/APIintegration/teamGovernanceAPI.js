/**
 * DialForge Team Governance API Integration Layer
 * 
 * Team Governance-specific API operations:
 * - Organization details retrieval
 * - Team member directory
 * - Integration owner ID mapping
 * - Governance audit trail from webhook log
 * - Permission/role information
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 */

// ============================================================================
// CACHE KEYS
// ============================================================================

const TEAM_GOVERNANCE_CACHE_KEYS = {
  ORGANIZATION_DETAILS: 'tg_organization_details',
  TEAM_MEMBERS: 'tg_team_members',
  AUDIT_LOG: 'tg_audit_log',
  OWNER_MAPPING: 'tg_owner_mapping'
};

// ============================================================================
// ORGANIZATION DETAILS
// ============================================================================

/**
 * Get organization details
 * 
 * NOTE: Backend does not currently expose organization details via HTTP endpoint.
 * This function documents the limitation and returns placeholder structure.
 * 
 * @returns {Promise<Object>} Organization details
 */
async function getOrganizationDetails() {
  try {
    // Check localStorage for cached organization details
    const cached = localStorage.getItem(TEAM_GOVERNANCE_CACHE_KEYS.ORGANIZATION_DETAILS);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide organization details endpoint
    // This would need to be added by backend team if organization details
    // are needed for the governance page.
    
    return {
      id: null,
      name: 'Organization',
      seatTypes: [],
      isAvailable: false,
      error: 'Organization details not available from backend'
    };
  } catch (error) {
    console.error('[Team Governance API] Error getting organization details:', error);
    return {
      id: null,
      name: 'Organization',
      seatTypes: [],
      isAvailable: false,
      error: error.message
    };
  }
}

// ============================================================================
// TEAM MEMBER DIRECTORY
// ============================================================================

/**
 * Get team members from organization details
 * 
 * NOTE: Backend does not currently expose team members via HTTP endpoint.
 * This function documents the limitation.
 * 
 * @returns {Promise<Array>} Array of team member objects
 */
async function getTeamMembers() {
  try {
    // Backend does not currently provide team members endpoint
    // Organization details would be needed, but that endpoint doesn't exist either
    
    console.warn('[Team Governance API] Team member data not available from backend');
    return [];
  } catch (error) {
    console.error('[Team Governance API] Error getting team members:', error);
    return [];
  }
}

/**
 * Format team member for display
 * 
 * @param {Object} member - Team member from backend
 * @returns {Object} Formatted member object
 */
function formatTeamMember(member) {
  if (!member) return null;

  return {
    id: member.id || member.user_id,
    name: member.name || member.full_name || 'Unknown',
    email: member.email || '',
    title: member.title || member.job_title || 'Team Member',
    department: member.department || member.dept || '',
    role: member.role || 'Member',
    status: member.status || 'Active',
    lastActive: member.last_active || 'Unknown',
    seatType: member.seat_type || member.seat || '',
    hubspotOwnerId: member.hubspot_owner_id || null,
    customPermissions: member.custom_permissions || null,
    avatar: member.avatar || null
  };
}

// ============================================================================
// INTEGRATION OWNER MAPPING
// ============================================================================

/**
 * Get user/owner mapping for integrations
 * 
 * Attempts to retrieve HubSpot owner IDs and vendor mappings
 * 
 * @returns {Promise<Object>} Map of user IDs to owner information
 */
async function getUserOwnerMapping() {
  try {
    // Check localStorage cache
    const cached = localStorage.getItem(TEAM_GOVERNANCE_CACHE_KEYS.OWNER_MAPPING);
    if (cached) {
      return JSON.parse(cached);
    }

    // Backend does not currently provide a dedicated owner mapping endpoint
    // This would need to be added by backend team if owner mapping is needed
    
    console.warn('[Team Governance API] Owner mapping not available from backend');
    return {};
  } catch (error) {
    console.error('[Team Governance API] Error getting owner mapping:', error);
    return {};
  }
}

/**
 * Find owner information for a user
 * 
 * @param {string} userId - User ID
 * @param {Object} ownerMap - Owner mapping from getUserOwnerMapping()
 * @returns {Object|null} Owner information or null
 */
function findOwnerInfo(userId, ownerMap) {
  if (!userId || !ownerMap) {
    return null;
  }

  return ownerMap[userId] || null;
}

// ============================================================================
// GOVERNANCE AUDIT TRAIL
// ============================================================================

/**
 * Get governance audit trail from webhook log
 * 
 * Uses GET /api/zapier/webhook/log as the source of truth for audit events
 * Filters and classifies events for governance context
 * 
 * @returns {Promise<Array>} Array of audit events
 */
async function getGovernanceAuditTrail() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: TEAM_GOVERNANCE_CACHE_KEYS.AUDIT_LOG,
      fallbackValue: []
    });

    if (!response) {
      return [];
    }

    const events = Array.isArray(response)
      ? response
      : (response.data || response.events || []);

    if (!Array.isArray(events)) {
      return [];
    }

    // Format and normalize audit events
    return events.map(event => formatAuditEvent(event)).filter(e => e !== null);
  } catch (error) {
    console.error('[Team Governance API] Error fetching audit trail:', error);
    return [];
  }
}

/**
 * Format webhook event as audit trail entry
 * 
 * @param {Object} event - Webhook event from /api/zapier/webhook/log
 * @returns {Object|null} Formatted audit event or null if not governance-related
 */
function formatAuditEvent(event) {
  if (!event) return null;

  const timestamp = event.timestamp || event.created_at || new Date().toISOString();
  const timeLabel = formatTimeLabel(timestamp);

  // Try to extract governance-relevant information from event
  const actor = event.actor || event.user || 'System';
  const action = event.action || event.type || 'Event';
  const target = event.target || event.resource || '';
  const integration = event.integration || event.provider || event.vendor || '';

  return {
    id: event.id || `event-${Date.now()}`,
    timestamp: timestamp,
    timeLabel: timeLabel,
    actor: actor,
    action: action,
    target: target,
    integration: integration,
    status: event.status || 'completed',
    details: event.details || event.message || '',
    eventType: classifyEventType(event),
    rawEvent: event
  };
}

/**
 * Classify event type for governance context
 * 
 * @param {Object} event - Raw webhook event
 * @returns {string} Event type classification
 */
function classifyEventType(event) {
  const typeStr = (event.type || event.action || '').toLowerCase();
  const msgStr = (event.message || event.details || '').toLowerCase();

  if (typeStr.includes('role') || msgStr.includes('role')) return 'role_change';
  if (typeStr.includes('permission') || msgStr.includes('permission')) return 'permission_change';
  if (typeStr.includes('user') || typeStr.includes('member')) return 'member_action';
  if (typeStr.includes('seat') || typeStr.includes('allocation')) return 'seat_action';
  if (typeStr.includes('invite') || msgStr.includes('invite')) return 'invite_action';
  if (typeStr.includes('access') || typeStr.includes('grant')) return 'access_change';
  
  return 'governance_event';
}

/**
 * Format timestamp for display
 * 
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Formatted time label
 */
function formatTimeLabel(timestamp) {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'just now';
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  } catch (error) {
    return 'Unknown time';
  }
}

/**
 * Filter audit events by criteria
 * 
 * @param {Array} events - Array of formatted audit events
 * @param {Object} filters - Filter criteria
 * @returns {Array} Filtered events
 */
function filterAuditEvents(events, filters) {
  if (!Array.isArray(events)) return [];
  if (!filters) return events;

  return events.filter(event => {
    if (filters.eventType && event.eventType !== filters.eventType) return false;
    if (filters.actor && !event.actor.toLowerCase().includes(filters.actor.toLowerCase())) return false;
    if (filters.integration && !event.integration.toLowerCase().includes(filters.integration.toLowerCase())) return false;
    if (filters.status && event.status !== filters.status) return false;
    return true;
  });
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const teamGovernanceAPI = {
  // Organization
  getOrganizationDetails,

  // Team members
  getTeamMembers,
  formatTeamMember,

  // Owner mapping
  getUserOwnerMapping,
  findOwnerInfo,

  // Audit trail
  getGovernanceAuditTrail,
  formatAuditEvent,
  filterAuditEvents,

  // Helpers
  formatTimeLabel,

  // Cache keys
  cacheKeys: TEAM_GOVERNANCE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.teamGovernanceAPI = teamGovernanceAPI;
}