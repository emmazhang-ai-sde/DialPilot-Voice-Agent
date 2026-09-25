/**
 * DialForge Support Queue API Integration Layer
 * 
 * Support Queue-specific API operations:
 * - Fetch active Zendesk tickets (filtered by status)
 * - Fetch Zapier webhook activity
 * - Format queue items for display
 * - Handle queue actions (assign, pickup, etc.)
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations - Zendesk tickets)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const SUPPORT_QUEUE_CACHE_KEYS = {
  ACTIVE_TICKETS: 'sq_active_tickets',
  WEBHOOK_ACTIVITY: 'sq_webhook_activity'
};

/**
 * Map Zendesk priority to internal priority key
 */
function mapZendeskPriority(zendeskPriority) {
  const priority = (zendeskPriority || 'normal').toLowerCase();
  
  if (priority === 'urgent' || priority === 'high') return 'high';
  if (priority === 'medium' || priority === 'med' || priority === 'normal') return 'med';
  return 'low';
}

// ============================================================================
// FETCH ACTIVE ZENDESK TICKETS
// ============================================================================

/**
 * Fetch active Zendesk tickets (status: new, open, pending)
 * Uses centralized crmAPI.getZendeskTickets()
 * 
 * @returns {Promise<Array>} Array of normalized queue ticket items
 */
async function fetchActiveTickets() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Support Queue API] crmAPI not available');
      return [];
    }

    // Get all Zendesk tickets from crmAPI
    const allTickets = await crmAPI.getZendeskTickets();
    
    if (!allTickets || allTickets.length === 0) {
      console.log('[Support Queue API] No Zendesk tickets found');
      return [];
    }

    // Filter for active statuses only (new, open, pending)
    const activeTickets = allTickets.filter(ticket => {
      const status = (ticket.status || '').toLowerCase();
      return status === 'new' || status === 'open' || status === 'pending';
    });

    // Normalize and format for queue display
    const queueItems = activeTickets.map(ticket => {
      // Normalize using crmAPI function
      const normalized = crmAPI.normalizeZendeskTicket(ticket);
      
      // Calculate wait time (time since created)
      let waitSeconds = 0;
      if (normalized.createdAt) {
        const createdTime = new Date(normalized.createdAt);
        const now = new Date();
        waitSeconds = Math.floor((now - createdTime) / 1000);
      }

      // Map priority to config
      const priorityKey = mapZendeskPriority(normalized.priority);

      return {
        id: `ticket-${normalized.id}`,
        type: 'ticket',
        title: `#${normalized.id}: ${normalized.subject || 'Support Request'}`,
        subtitle: `Requester: ${normalized.requesterEmail || normalized.requesterPhone || 'Unknown'}`,
        priority: priorityKey,
        waitSeconds,
        isMono: true,
        
        // Store original ticket data for actions
        ticketId: normalized.id,
        requesterPhone: normalized.requesterPhone,
        requesterEmail: normalized.requesterEmail,
        description: normalized.description,
        url: normalized.url,
        status: normalized.status,
        createdAt: normalized.createdAt
      };
    });

    // Sort by priority (high to low) then by wait time (longest first)
    queueItems.sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return b.waitSeconds - a.waitSeconds;
    });

    // Cache the tickets
    if (queueItems.length > 0) {
      dialforgeApi.cacheData(SUPPORT_QUEUE_CACHE_KEYS.ACTIVE_TICKETS, queueItems);
    }

    console.log('[Support Queue API] Loaded', queueItems.length, 'active tickets');
    return queueItems;
  } catch (error) {
    console.error('[Support Queue API] Error fetching active tickets:', error);
    return [];
  }
}

// ============================================================================
// FETCH ZAPIER WEBHOOK ACTIVITY
// ============================================================================

/**
 * Fetch Zapier webhook activity log for external alerts/requests
 * Transforms webhook events into queue items
 * 
 * @returns {Promise<Array>} Array of webhook activity queue items
 */
async function fetchWebhookActivity() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: SUPPORT_QUEUE_CACHE_KEYS.WEBHOOK_ACTIVITY,
      fallbackValue: []
    });

    if (!response) {
      console.log('[Support Queue API] No webhook activity found');
      return [];
    }

    // Handle different response formats
    const events = Array.isArray(response) 
      ? response 
      : (response.data || response.events || []);

    if (!Array.isArray(events)) return [];

    // Transform webhook events into queue items
    const queueItems = events
      .filter(event => event && event.id)
      .slice(0, 10) // Limit to 10 most recent
      .map(event => {
        // Calculate wait time
        let waitSeconds = 0;
        if (event.timestamp) {
          const eventTime = new Date(event.timestamp);
          const now = new Date();
          waitSeconds = Math.floor((now - eventTime) / 1000);
        }

        return {
          id: `webhook-${event.id}`,
          type: 'webhook',
          title: event.title || 'External Alert',
          subtitle: event.message || event.description || 'New incoming request',
          priority: 'med',  // Webhooks default to medium priority
          waitSeconds,
          isMono: false,
          
          // Store event data for actions
          eventId: event.id,
          eventData: event
        };
      });

    console.log('[Support Queue API] Loaded', queueItems.length, 'webhook events');
    return queueItems;
  } catch (error) {
    console.error('[Support Queue API] Error fetching webhook activity:', error);
    return [];
  }
}

// ============================================================================
// COMBINED QUEUE FETCH
// ============================================================================

/**
 * Get priority rank for sorting
 */
function getPriorityRank(priority) {
  const priorityMap = { 'high': 0, 'med': 1, 'low': 2 };
  return priorityMap[priority] || 1;
}

/**
 * Fetch all queue items (tickets + webhook alerts)
 * Returns combined and sorted queue
 * 
 * @returns {Promise<Array>} Combined queue items
 */
async function fetchQueueItems() {
  try {
    // Fetch both in parallel
    const [tickets, webhooks] = await Promise.all([
      fetchActiveTickets(),
      fetchWebhookActivity()
    ]);

    // Combine and sort by priority and wait time
    const combined = [...tickets, ...webhooks];
    
    combined.sort((a, b) => {
      const rankA = getPriorityRank(a.priority);
      const rankB = getPriorityRank(b.priority);
      if (rankA !== rankB) return rankA - rankB;
      return b.waitSeconds - a.waitSeconds;
    });

    console.log('[Support Queue API] Total queue items:', combined.length);
    return combined;
  } catch (error) {
    console.error('[Support Queue API] Error fetching queue items:', error);
    return [];
  }
}

// ============================================================================
// QUEUE ACTIONS
// ============================================================================

/**
 * Assign a ticket to an agent
 * Updates ticket status if backend supports it
 * 
 * @param {string} ticketId - Ticket ID
 * @returns {Promise<Object>} Assignment result
 */
async function assignTicket(ticketId) {
  try {
    console.log('[Support Queue API] Assigning ticket:', ticketId);
    
    // TODO: Implement ticket assignment via backend
    // For now, this just logs the action
    // Backend may support: PATCH /api/zendesk/tickets/:id or similar
    
    return {
      success: true,
      ticketId,
      message: 'Ticket assigned'
    };
  } catch (error) {
    console.error('[Support Queue API] Error assigning ticket:', error);
    return { success: false, error };
  }
}

/**
 * Get ticket details for dialer integration
 * Extracts phone and contact info for calling
 * 
 * @param {Object} queueItem - Queue item data
 * @returns {Object} Dialer-compatible contact object
 */
function getDialerContact(queueItem) {
  if (!queueItem) return null;

  return {
    type: 'support-ticket',
    name: queueItem.subtitle || 'Unknown',
    number: queueItem.requesterPhone || '',
    email: queueItem.requesterEmail || '',
    company: queueItem.company || '',
    ticketId: queueItem.ticketId,
    ticketSubject: queueItem.title,
    isSupport: true
  };
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const supportQueueAPI = {
  // Fetch operations
  fetchActiveTickets,
  fetchWebhookActivity,
  fetchQueueItems,
  
  // Actions
  assignTicket,
  getDialerContact,
  
  // Cache keys
  cacheKeys: SUPPORT_QUEUE_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.supportQueueAPI = supportQueueAPI;
}