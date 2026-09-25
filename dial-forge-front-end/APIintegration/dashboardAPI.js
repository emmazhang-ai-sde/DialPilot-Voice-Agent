/**
 * DialForge Dashboard API Integration Layer
 * 
 * Dashboard-specific API functionality.
 * CRM operations (HubSpot, Zendesk) delegated to centralized crmAPI.js
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (centralized CRM operations)
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const DASHBOARD_CACHE_KEYS = {
  CONTACTS: 'df_contacts',
  TICKETS: 'df_tickets',
  STATUS: 'df_api_status'
};

// ============================================================================
// API STATUS
// ============================================================================

/**
 * Fetch API/system status
 * 
 * Endpoint: GET /api/status
 */
async function fetchDashboardStatus() {
  const response = await dialforgeApi.fetch('/api/status', {
    fallbackKey: DASHBOARD_CACHE_KEYS.STATUS,
    fallbackValue: { status: 'unavailable' }
  });

  return response || { status: 'unavailable' };
}

// ============================================================================
// HUBSPOT CONTACTS (delegated to crmAPI)
// ============================================================================

/**
 * Fetch HubSpot contacts from backend
 * DELEGATED to crmAPI.js - using centralized function
 */
async function fetchDashboardContacts() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Dashboard API] crmAPI not available');
      return [];
    }

    const contacts = await crmAPI.getHubSpotContacts();
    
    if (Array.isArray(contacts) && contacts.length > 0) {
      dialforgeApi.cacheData(DASHBOARD_CACHE_KEYS.CONTACTS, contacts);
    }

    return contacts || [];
  } catch (error) {
    console.error('[Dashboard API] Error fetching contacts:', error);
    return [];
  }
}

// ============================================================================
// ZENDESK TICKETS (delegated to crmAPI)
// ============================================================================

/**
 * Fetch Zendesk support tickets from backend
 * DELEGATED to crmAPI.js - using centralized function
 */
async function fetchDashboardTickets() {
  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Dashboard API] crmAPI not available');
      return [];
    }

    const tickets = await crmAPI.getZendeskTickets();
    
    if (Array.isArray(tickets) && tickets.length > 0) {
      dialforgeApi.cacheData(DASHBOARD_CACHE_KEYS.TICKETS, tickets);
    }

    return tickets || [];
  } catch (error) {
    console.error('[Dashboard API] Error fetching tickets:', error);
    return [];
  }
}

// ============================================================================
// DASHBOARD DATA TRANSFORMATIONS
// ============================================================================

/**
 * Count open tickets from ticket array
 * 
 * Counts tickets with open/new/pending status (case-insensitive).
 * Used internally by Dashboard to determine open ticket count.
 * 
 * @param {Array} tickets - Array of ticket objects
 * @returns {number} - Count of open tickets
 */
function countOpenTickets(tickets) {
  if (!Array.isArray(tickets)) return 0;

  return tickets.filter(ticket => {
    const status = (ticket.status || '').toLowerCase();
    return status === 'open' || status === 'new' || status === 'pending';
  }).length;
}

/**
 * Transform tickets data for Dashboard display
 * 
 * Adds computed properties to ticket data for Dashboard metrics.
 * 
 * @param {Array} tickets - Array of ticket objects
 * @returns {Object} - Transformed data with counts and metadata
 */
function transformTicketsForDashboard(tickets) {
  if (!Array.isArray(tickets)) {
    return {
      all: 0,
      open: 0,
      tickets: []
    };
  }

  return {
    all: tickets.length,
    open: countOpenTickets(tickets),
    tickets: tickets
  };
}

/**
 * Transform contacts data for Dashboard display
 * 
 * Adds computed properties to contact data for Dashboard metrics.
 * 
 * @param {Array} contacts - Array of contact objects
 * @returns {Object} - Transformed data with counts and metadata
 */
function transformContactsForDashboard(contacts) {
  if (!Array.isArray(contacts)) {
    return {
      total: 0,
      contacts: []
    };
  }

  return {
    total: contacts.length,
    contacts: contacts
  };
}

// ============================================================================
// ORCHESTRATION: LOAD ALL DASHBOARD DATA
// ============================================================================

/**
 * Load all Dashboard API data
 * 
 * Fetches API status, contacts, and tickets in parallel.
 * Handles errors gracefully with fallback to localStorage.
 * 
 * Returns an object with three properties:
 * - status: System/API status
 * - contacts: Contact data with transformations
 * - tickets: Ticket data with transformations
 * 
 * This function orchestrates the API calls but does NOT update the DOM.
 * DOM updates should be handled by Dashboard.html.
 * 
 * Usage:
 *   const dashboardData = await dashboardAPI.loadDashboardData();
 *   updateDashboardUI(dashboardData);
 * 
 * @returns {Promise<Object>} - Dashboard data object
 */
async function loadDashboardData() {
  try {
    // Fetch all data in parallel
    const [statusResponse, contactsArray, ticketsArray] = await Promise.all([
      fetchDashboardStatus(),
      fetchDashboardContacts(),
      fetchDashboardTickets()
    ]);

    // Determine API availability
    const isApiAvailable = statusResponse && 
      (statusResponse.status === 'available' || statusResponse.status === 'ok');

    // Transform data for Dashboard display
    const contactsData = transformContactsForDashboard(contactsArray);
    const ticketsData = transformTicketsForDashboard(ticketsArray);

    // Return structured data for Dashboard UI
    return {
      isApiAvailable,
      status: statusResponse,
      contacts: contactsData,
      tickets: ticketsData,
      timestamp: new Date()
    };
  } catch (error) {
    // Log error but don't throw - Dashboard should still render
    console.error('[Dashboard API] Error loading dashboard data:', error);

    // Return fallback data structure
    return {
      isApiAvailable: false,
      status: { status: 'unavailable' },
      contacts: { total: 0, contacts: [] },
      tickets: { all: 0, open: 0, tickets: [] },
      timestamp: new Date(),
      error: error.message
    };
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

/**
 * Expose Dashboard API utilities globally
 * 
 * Usage:
 *   dashboardAPI.loadDashboardData()
 *   dashboardAPI.fetchStatus()
 *   dashboardAPI.fetchContacts()
 *   dashboardAPI.fetchTickets()
 */
const dashboardAPI = {
  // Main orchestration
  loadDashboardData,

  // Individual endpoint functions
  fetchStatus: fetchDashboardStatus,
  fetchContacts: fetchDashboardContacts,
  fetchTickets: fetchDashboardTickets,

  // Data transformations
  transformContactsForDashboard,
  transformTicketsForDashboard,
  countOpenTickets,

  // Cache key references (for Dashboard UI to use if needed)
  cacheKeys: DASHBOARD_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.dashboardAPI = dashboardAPI;
}