/**
 * DialForge Notifications API Integration Layer
 * 
 * This file provides Notifications-specific API functionality.
 * It uses the universal API infrastructure from dialforgeApi.js and adds
 * Notifications-specific logic such as:
 * - Fetching Zapier webhook activity logs
 * - Fetching Zendesk support tickets
 * - Checking system/integration status
 * - Triggering Zapier outbound notifications
 * - Transforming backend data to notification model
 * - Preventing duplicate notifications
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * 
 * Responsibilities:
 * - Fetch webhook activity from Zapier integration
 * - Fetch support tickets from Zendesk
 * - Fetch system and integration status
 * - Transform API responses to notification model
 * - Prevent duplicates using backend IDs
 * - Provide polling support for real-time updates
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const NOTIFICATIONS_CACHE_KEYS = {
  WEBHOOK_LOG: 'notif_webhook_log',
  ZENDESK_TICKETS: 'notif_zendesk_tickets',
  SYSTEM_STATUS: 'notif_system_status',
  NOTIFICATION_IDS: 'notif_processed_ids'  // Prevent duplicates
};

// ============================================================================
// POLLING MANAGEMENT
// ============================================================================

let pollingIntervals = {};

/**
 * Stop all active polling
 * Called when page unloads to prevent orphaned timers
 */
function stopAllPolling() {
  Object.values(pollingIntervals).forEach(interval => {
    if (interval) clearInterval(interval);
  });
  pollingIntervals = {};
  console.log('[Notifications API] All polling stopped');
}

// Stop polling when page unloads
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', stopAllPolling);
}

// ============================================================================
// DUPLICATE PREVENTION
// ============================================================================

/**
 * Get set of already-processed notification IDs from localStorage
 * Prevents duplicate notifications on refresh/polling
 */
function getProcessedIds() {
  try {
    const stored = localStorage.getItem(NOTIFICATIONS_CACHE_KEYS.NOTIFICATION_IDS);
    return stored ? new Set(JSON.parse(stored)) : new Set();
  } catch (e) {
    console.warn('[Notifications API] Error reading processed IDs:', e);
    return new Set();
  }
}

/**
 * Save processed notification IDs to localStorage
 */
function saveProcessedIds(idSet) {
  try {
    localStorage.setItem(
      NOTIFICATIONS_CACHE_KEYS.NOTIFICATION_IDS,
      JSON.stringify(Array.from(idSet))
    );
  } catch (e) {
    console.warn('[Notifications API] Error saving processed IDs:', e);
  }
}

/**
 * Check if a notification ID has already been processed
 */
function isNotificationProcessed(id) {
  return getProcessedIds().has(id);
}

/**
 * Mark notification ID as processed
 */
function markAsProcessed(id) {
  const ids = getProcessedIds();
  ids.add(id);
  saveProcessedIds(ids);
}

// ============================================================================
// ZAPIER WEBHOOK LOG
// ============================================================================

/**
 * Fetch Zapier webhook activity log
 * 
 * Endpoint: GET /api/zapier/webhook/log
 * 
 * Purpose: Get incoming webhook events from Zapier-connected external systems
 * (forms, Slack, third-party apps, email triggers, etc.)
 * 
 * @returns {Promise<Array>} - Array of webhook event notifications
 */
async function fetchWebhookLog() {
  try {
    const response = await dialforgeApi.fetch('/api/zapier/webhook/log', {
      fallbackKey: NOTIFICATIONS_CACHE_KEYS.WEBHOOK_LOG,
      fallbackValue: []
    });

    if (!response) {
      console.warn('[Notifications API] No webhook log response');
      return [];
    }

    // Handle response formats: { data: [...] }, { events: [...] }, or [...]
    const events = Array.isArray(response) 
      ? response 
      : (response.data || response.events || []);

    // Transform webhook events to notification model
    return transformWebhookEvents(events);
  } catch (error) {
    console.error('[Notifications API] Error fetching webhook log:', error);
    return [];
  }
}

/**
 * Transform Zapier webhook events to notification model
 * 
 * Backend webhook event format (expected):
 * {
 *   id: "webhook_12345",
 *   timestamp: "2026-09-01T10:30:00Z",
 *   source: "form" | "slack" | "email" | "app",
 *   title: "New Form Submission",
 *   message: "Contact form submitted from example.com",
 *   data: { ... }
 * }
 * 
 * Maps to notification model:
 * {
 *   id: string (unique identifier),
 *   type: "integrations" (category),
 *   title: string,
 *   description: string,
 *   time: "Xm ago" | "Xh ago" (formatted),
 *   read: boolean (defaults to false)
 * }
 */
function transformWebhookEvents(events) {
  if (!Array.isArray(events)) return [];

  return events
    .filter(event => event && event.id) // Only valid events with IDs
    .filter(event => !isNotificationProcessed(`webhook:${event.id}`)) // Skip duplicates
    .map(event => {
      markAsProcessed(`webhook:${event.id}`);
      
      return {
        id: `webhook:${event.id}`,
        type: 'integrations',  // Map to existing notification types
        title: event.title || 'External Activity',
        description: event.message || event.description || 'New webhook activity received',
        time: formatTime(event.timestamp),
        read: false
      };
    });
}

// ============================================================================
// ZENDESK TICKETS
// ============================================================================

/**
 * Fetch Zendesk support tickets
 * 
 * Endpoint: GET /api/zendesk/tickets
 * 
 * Purpose: Get support ticket information including:
 * - Ticket ID
 * - Status (open, pending, solved, closed)
 * - Customer info
 * - Subject
 * - Creation timestamp
 * - Priority
 * 
 * @returns {Promise<Array>} - Array of ticket notifications
 */
async function fetchZendeskTickets() {
  try {
    const response = await dialforgeApi.fetch('/api/zendesk/tickets', {
      fallbackKey: NOTIFICATIONS_CACHE_KEYS.ZENDESK_TICKETS,
      fallbackValue: []
    });

    if (!response) {
      console.warn('[Notifications API] No Zendesk tickets response');
      return [];
    }

    // Handle response formats: { tickets: [...] }, { data: [...] }, or [...]
    const tickets = Array.isArray(response) 
      ? response 
      : (response.tickets || response.data || []);

    // Transform tickets to notification model
    return transformZendeskTickets(tickets);
  } catch (error) {
    console.error('[Notifications API] Error fetching Zendesk tickets:', error);
    return [];
  }
}

/**
 * Transform Zendesk tickets to notification model
 * 
 * Backend ticket format (expected):
 * {
 *   id: "ticket_12345",
 *   status: "open" | "pending" | "solved" | "closed",
 *   subject: "Billing Issue",
 *   description: "Customer reports incorrect charge",
 *   created_at: "2026-09-01T10:30:00Z",
 *   customer_email: "customer@example.com",
 *   priority: "high" | "normal" | "low"
 * }
 * 
 * Maps to notification model with "support" type
 */
function transformZendeskTickets(tickets) {
  if (!Array.isArray(tickets)) return [];

  return tickets
    .filter(ticket => ticket && ticket.id) // Only valid tickets with IDs
    .filter(ticket => !isNotificationProcessed(`zendesk:${ticket.id}`)) // Skip duplicates
    .map(ticket => {
      markAsProcessed(`zendesk:${ticket.id}`);
      
      // Determine notification title based on status
      let title = `Support Ticket: ${ticket.subject || 'New Ticket'}`;
      if (ticket.status === 'open') {
        title = `🔴 Open Ticket: ${ticket.subject || 'New Support Request'}`;
      } else if (ticket.status === 'pending') {
        title = `⏳ Pending: ${ticket.subject || 'Awaiting Response'}`;
      } else if (ticket.status === 'solved') {
        title = `✅ Resolved: ${ticket.subject || 'Ticket Resolved'}`;
      }

      return {
        id: `zendesk:${ticket.id}`,
        type: 'support',  // Support-specific type
        title: title,
        description: ticket.description || `Ticket created for ${ticket.customer_email || 'customer'}`,
        time: formatTime(ticket.created_at),
        read: false,
        // Store additional data for reference
        priority: ticket.priority,
        status: ticket.status
      };
    });
}

// ============================================================================
// SYSTEM & INTEGRATION STATUS
// ============================================================================

/**
 * Fetch system and integration status
 * 
 * Endpoint: GET /api/status
 * 
 * Purpose: Check vendor/service status and integration credentials
 * Returns information such as:
 * - HubSpot: connected/demo/expired
 * - Zendesk: connected/unavailable
 * - Zapier: connected/error
 * - System health
 * 
 * @returns {Promise<Array>} - Array of system status notifications
 */
async function fetchSystemStatus() {
  try {
    const response = await dialforgeApi.fetch('/api/status', {
      fallbackKey: NOTIFICATIONS_CACHE_KEYS.SYSTEM_STATUS,
      fallbackValue: {}
    });

    if (!response) {
      console.warn('[Notifications API] No system status response');
      return [];
    }

    // Transform status to notification model
    return transformSystemStatus(response);
  } catch (error) {
    console.error('[Notifications API] Error fetching system status:', error);
    return [];
  }
}

/**
 * Transform system status response to notification model
 * 
 * Backend status format (expected):
 * {
 *   hubspot: { status: "connected" | "demo" | "expired", message: "..." },
 *   zendesk: { status: "connected" | "unavailable" },
 *   zapier: { status: "connected" | "error" },
 *   system: { status: "ok" | "warning" | "error" }
 * }
 * 
 * Generates notifications for non-ok statuses
 */
function transformSystemStatus(status) {
  const notifications = [];
  const statusId = `status:${Date.now()}`; // Unique ID per status check

  // Skip duplicate check for status notifications (they can update)
  // but use a unique ID based on timestamp so they don't repeat identically

  // Check each integration's status
  const integrations = ['hubspot', 'zendesk', 'zapier'];
  
  integrations.forEach(integration => {
    const intStatus = status[integration];
    if (!intStatus) return;

    const statusValue = intStatus.status || 'unknown';

    // Only create notifications for non-normal statuses
    if (statusValue === 'ok' || statusValue === 'connected') {
      return; // Skip normal statuses
    }

    // Generate appropriate notification
    let title = '';
    let description = intStatus.message || '';

    if (integration === 'hubspot') {
      if (statusValue === 'demo') {
        title = '⚠️ HubSpot: Demo Mode Active';
        description = 'HubSpot is operating in demo mode. Upgrade to production credentials.';
      } else if (statusValue === 'expired') {
        title = '🔴 HubSpot: Token Expired';
        description = 'HubSpot authentication token has expired. Re-authenticate required.';
      } else if (statusValue === 'unavailable') {
        title = '🔴 HubSpot: Unavailable';
        description = 'Unable to connect to HubSpot. Check credentials and network.';
      }
    } else if (integration === 'zendesk') {
      if (statusValue === 'unavailable') {
        title = '🔴 Zendesk: Unavailable';
        description = 'Unable to connect to Zendesk. Service may be down or credentials invalid.';
      } else if (statusValue === 'error') {
        title = '🔴 Zendesk: Error';
        description = 'Error connecting to Zendesk integration.';
      }
    } else if (integration === 'zapier') {
      if (statusValue === 'error') {
        title = '⚠️ Zapier: Connection Error';
        description = 'Error with Zapier integration. Check your Zapier account.';
      } else if (statusValue === 'unavailable') {
        title = '🔴 Zapier: Unavailable';
        description = 'Zapier integration is currently unavailable.';
      }
    }

    if (title) {
      notifications.push({
        id: `status:${integration}`,  // Stable ID per integration
        type: 'system',  // System notifications
        title: title,
        description: description || `${integration} status: ${statusValue}`,
        time: 'Now',
        read: false,
        priority: statusValue === 'unavailable' || statusValue === 'expired' ? 'high' : 'normal'
      });
    }
  });

  return notifications;
}

// ============================================================================
// ZAPIER OUTBOUND TRIGGER
// ============================================================================

/**
 * Trigger a Zapier outbound notification
 * 
 * Endpoint: POST /api/zapier/trigger
 * 
 * Purpose: Send an event payload to a Zapier Catch Hook for outbound actions
 * (Slack notifications, email alerts, webhook triggers, etc.)
 * 
 * @param {Object} payload - Event data to send to Zapier
 * @param {string} payload.title - Event title
 * @param {string} payload.message - Event message
 * @param {string} payload.type - Event type (notification, alert, etc.)
 * @param {Object} payload.data - Additional event data
 * @returns {Promise<Object>} - Result from Zapier trigger
 */
async function triggerZapierNotification(payload) {
  if (!payload) {
    console.warn('[Notifications API] No payload provided for Zapier trigger');
    return null;
  }

  try {
    // Build request body with event information
    const requestBody = {
      title: payload.title || 'Notification',
      message: payload.message || '',
      type: payload.type || 'notification',
      timestamp: new Date().toISOString(),
      ...(payload.data && { data: payload.data })
    };

    // Make the API request
    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: requestBody,
      fallbackValue: null
    });

    if (response) {
      console.log('[Notifications API] Zapier trigger sent:', response);
      return response;
    } else {
      console.warn('[Notifications API] No response from Zapier trigger');
      return null;
    }
  } catch (error) {
    console.error('[Notifications API] Error triggering Zapier notification:', error);
    return null;
  }
}

// ============================================================================
// TIME FORMATTING
// ============================================================================

/**
 * Format ISO timestamp to relative time format
 * Examples: "2m ago", "1h ago", "Yesterday", "Monday"
 */
function formatTime(isoTimestamp) {
  if (!isoTimestamp) return 'Just now';

  try {
    const date = new Date(isoTimestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return date.toLocaleDateString('en-US', { weekday: 'short' });
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch (e) {
    return 'Recently';
  }
}

// ============================================================================
// COMPREHENSIVE NOTIFICATION FETCH
// ============================================================================

/**
 * Fetch all notifications from all sources
 * 
 * Combines:
 * - Zapier webhook log
 * - Zendesk tickets
 * - System status notifications
 * 
 * @returns {Promise<Array>} - Array of all notifications from API sources
 */
async function fetchAllNotifications() {
  try {
    // Fetch from all sources in parallel
    const [webhooks, tickets, status] = await Promise.all([
      fetchWebhookLog(),
      fetchZendeskTickets(),
      fetchSystemStatus()
    ]);

    // Combine all notifications
    const allNotifications = [
      ...webhooks,
      ...tickets,
      ...status
    ];

    console.log(`[Notifications API] Fetched ${allNotifications.length} API notifications`);
    return allNotifications;
  } catch (error) {
    console.error('[Notifications API] Error in fetchAllNotifications:', error);
    return [];
  }
}

/**
 * Start polling for new notifications
 * 
 * @param {Function} onNewNotifications - Callback when new notifications arrive
 * @param {number} intervalMs - Polling interval in milliseconds (default 30s)
 */
function startPollingNotifications(onNewNotifications, intervalMs = 30000) {
  // Stop existing polling
  if (pollingIntervals.notifications) {
    clearInterval(pollingIntervals.notifications);
  }

  console.log(`[Notifications API] Starting notification polling (${intervalMs}ms interval)`);

  // Fetch immediately
  fetchAllNotifications().then(notifications => {
    if (onNewNotifications && typeof onNewNotifications === 'function') {
      onNewNotifications(notifications);
    }
  });

  // Setup polling interval
  pollingIntervals.notifications = setInterval(() => {
    fetchAllNotifications().then(notifications => {
      if (onNewNotifications && typeof onNewNotifications === 'function') {
        onNewNotifications(notifications);
      }
    });
  }, intervalMs);
}

/**
 * Stop polling for notifications
 */
function stopPollingNotifications() {
  if (pollingIntervals.notifications) {
    clearInterval(pollingIntervals.notifications);
    pollingIntervals.notifications = null;
    console.log('[Notifications API] Notification polling stopped');
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

/**
 * Expose Notifications API utilities globally
 * 
 * Usage:
 *   const allNotifications = await notificationsAPI.fetchAllNotifications();
 *   notificationsAPI.startPollingNotifications(callback, 30000);
 */
const notificationsAPI = {
  // Main fetch functions
  fetchWebhookLog,
  fetchZendeskTickets,
  fetchSystemStatus,
  fetchAllNotifications,
  
  // Outbound action
  triggerZapierNotification,
  
  // Polling
  startPollingNotifications,
  stopPollingNotifications,
  stopAllPolling,
  
  // Transformations
  transformWebhookEvents,
  transformZendeskTickets,
  transformSystemStatus,
  
  // Time formatting
  formatTime,
  
  // Cache keys
  cacheKeys: NOTIFICATIONS_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.notificationsAPI = notificationsAPI;
}
