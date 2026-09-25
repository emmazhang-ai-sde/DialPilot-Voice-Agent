/**
 * DialForge Call Coaching API Integration Layer
 * 
 * Call Coaching-specific API operations:
 * - Determine flagged calls based on coaching criteria
 * - Fetch and calculate agent performance metrics
 * - Send flagged calls to manager for review via Zapier
 * - Retrieve system integration health
 * 
 * Dependencies:
 * - dialforgeApi.js (universal API infrastructure)
 * - crmAPI.js (agent metrics from Zendesk/HubSpot)
 * 
 * NOTE: Call records are stored locally (no /api/calls endpoint exists)
 * Real call transcripts, AI scores, and sentiment are provided by local data
 */

// ============================================================================
// CACHE KEY DEFINITIONS
// ============================================================================

const CALL_COACHING_CACHE_KEYS = {
  INTEGRATION_HEALTH: 'cc_integration_health',
  AGENT_METRICS: 'cc_agent_metrics'
};

// ============================================================================
// FLAGGING CRITERIA & THRESHOLDS
// ============================================================================

const COACHING_THRESHOLDS = {
  LOW_SCORE: 70,           // Flag if AI score < 70
  HIGH_TALK_RATIO: 75,     // Flag if talk ratio > 75% (not listening enough)
  LONG_DURATION: 900,      // Flag if duration > 15 minutes (talking too long)
  NEGATIVE_SENTIMENT: true // Flag if sentiment is negative (frustrated, dissatisfied)
};

/**
 * Determine if a call should be flagged for coaching
 * 
 * @param {Object} call - Call object with score, mood, talkListen, durationSec
 * @returns {Object} - { isFlagged, reasons: [array of reason strings] }
 */
function determineCallFlags(call) {
  const reasons = [];

  // Check AI score
  if (call.score && call.score < COACHING_THRESHOLDS.LOW_SCORE) {
    reasons.push(`Low AI score (${call.score}/100)`);
  }

  // Check sentiment
  if (call.mood && call.mood.text) {
    const negativeSentiments = ['Frustrated', 'Dissatisfied', 'Negative', 'Angry'];
    if (negativeSentiments.some(s => call.mood.text.includes(s))) {
      reasons.push(`Negative sentiment: ${call.mood.text}`);
    }
  }

  // Check talk ratio (too much talking = not listening)
  if (call.talkListen && call.talkListen.you > COACHING_THRESHOLDS.HIGH_TALK_RATIO) {
    reasons.push(`High talk ratio (${call.talkListen.you}% - not enough listening)`);
  }

  // Check call duration
  if (call.durationSec && call.durationSec > COACHING_THRESHOLDS.LONG_DURATION) {
    const minutes = Math.round(call.durationSec / 60);
    reasons.push(`Long call duration (${minutes} minutes)`);
  }

  // Check for growth coaching notes
  if (call.notes) {
    const growthNotes = call.notes.filter(n => n.kind === 'growth');
    if (growthNotes.length > 0) {
      reasons.push(`${growthNotes.length} growth area(s) identified`);
    }
  }

  return {
    isFlagged: reasons.length > 0,
    reasons
  };
}

// ============================================================================
// GET INTEGRATION HEALTH
// ============================================================================

/**
 * Fetch system integration health from backend
 * 
 * @returns {Promise<Object>} Integration health status
 */
async function getIntegrationHealth() {
  try {
    const response = await dialforgeApi.fetch('/api/status', {
      fallbackKey: CALL_COACHING_CACHE_KEYS.INTEGRATION_HEALTH,
      fallbackValue: { status: 'unavailable', mode: 'demo' }
    });

    if (!response) {
      return {
        status: 'unavailable',
        mode: 'demo',
        zendesk: { connected: false },
        hubspot: { connected: false },
        ai: { available: false },
        timestamp: new Date().toISOString()
      };
    }

    return {
      status: response.status || 'available',
      mode: response.mode || 'live',
      zendesk: { connected: response.zendesk_connected !== false },
      hubspot: { connected: response.hubspot_connected !== false },
      ai: { available: response.ai_available !== false },
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    console.error('[Call Coaching API] Error fetching integration health:', error);
    return {
      status: 'unavailable',
      mode: 'demo',
      zendesk: { connected: false },
      hubspot: { connected: false },
      ai: { available: false },
      timestamp: new Date().toISOString()
    };
  }
}

// ============================================================================
// GET AGENT METRICS
// ============================================================================

/**
 * Fetch agent performance metrics from backend
 * Uses centralized crmAPI for data aggregation
 * 
 * @param {string} agentEmail - Agent email address
 * @returns {Promise<Object>} Agent metrics object
 */
async function getAgentMetrics(agentEmail) {
  if (!agentEmail) {
    console.warn('[Call Coaching API] No agent email provided');
    return null;
  }

  try {
    if (typeof crmAPI === 'undefined') {
      console.warn('[Call Coaching API] crmAPI not available');
      return null;
    }

    // Get metrics from centralized crmAPI
    const metrics = await crmAPI.getAgentMetrics(agentEmail);
    
    if (metrics) {
      // Cache the metrics
      dialforgeApi.cacheData(
        CALL_COACHING_CACHE_KEYS.AGENT_METRICS,
        { agent: agentEmail, ...metrics, timestamp: new Date().toISOString() }
      );

      console.log('[Call Coaching API] Agent metrics:', metrics);
      return metrics;
    }

    console.warn('[Call Coaching API] No metrics returned for agent:', agentEmail);
    return null;
  } catch (error) {
    console.error('[Call Coaching API] Error fetching agent metrics:', error);
    return null;
  }
}

// ============================================================================
// SEND TO MANAGER FOR REVIEW (ZAPIER)
// ============================================================================

/**
 * Send flagged call to manager for review via Zapier webhook
 * 
 * @param {Object} call - Call object with all details
 * @param {string} agentName - Name of the agent
 * @param {string} managerEmail - Manager email (if known)
 * @returns {Promise<Object>} { success: boolean, message: string }
 */
async function sendCallToManager(call, agentName, managerEmail = null) {
  if (!call) {
    console.warn('[Call Coaching API] No call provided for manager review');
    return { success: false, message: 'No call data provided' };
  }

  try {
    // Determine coaching flags
    const flagInfo = determineCallFlags(call);

    // Build the payload for Zapier
    const payload = {
      type: 'call_coaching_review',
      timestamp: new Date().toISOString(),
      call: {
        id: call.id,
        agentName: agentName || 'Unknown Agent',
        contactName: call.name || 'Unknown Contact',
        dealName: call.deal || 'Unknown Deal',
        date: call.date,
        durationSeconds: call.durationSec,
        aiScore: call.score,
        status: call.status
      },
      coaching: {
        isFlagged: flagInfo.isFlagged,
        reasons: flagInfo.reasons,
        sentiment: call.mood?.text || 'Unknown',
        talkRatio: call.talkListen?.you || 0,
        confidence: call.confidence
      },
      scores: {
        talkRatio: call.breakdown?.talkRatio,
        patience: call.breakdown?.patience,
        objections: call.breakdown?.objections,
        close: call.breakdown?.close
      },
      notes: {
        strengths: call.notes?.filter(n => n.kind === 'strength') || [],
        growth: call.notes?.filter(n => n.kind === 'growth') || [],
        ai: call.notes?.filter(n => n.kind === 'ai') || []
      },
      keyMoments: call.moments?.slice(0, 3) || [], // Include top 3 moments
      manager: {
        email: managerEmail || 'unassigned',
        action: 'review_requested'
      }
    };

    console.log('[Call Coaching API] Sending to Zapier:', payload);

    // Send via Zapier webhook
    const response = await dialforgeApi.fetch('/api/zapier/trigger', {
      method: 'POST',
      body: payload,
      fallbackValue: null
    });

    if (response && (response.status === 'queued' || response.status === 'received' || response.success)) {
      console.log('[Call Coaching API] Successfully downloaded insights');
      
      // Cache success
      dialforgeApi.cacheData(
        'cc_last_manager_send',
        { callId: call.id, timestamp: new Date().toISOString(), status: 'sent' }
      );

      return {
        success: true,
        message: `Call #${call.id} downloaded`,
        data: response
      };
    } else {
      console.warn('[Call Coaching API] Zapier returned unexpected response:', response);
      return {
        success: false,
        data: response
      };
    }
  } catch (error) {
    console.error('[Call Coaching API] Error exporting insights:', error);
    return {
      success: false,
      message: `Error: ${error.message || 'Unknown error'}`,
      error
    };
  }
}

// ============================================================================
// FILTER FLAGGED CALLS
// ============================================================================

/**
 * Filter call array to only flagged calls
 * 
 * @param {Array} calls - Array of call objects
 * @returns {Array} Flagged calls with flag information
 */
function getFlaggedCalls(calls) {
  if (!Array.isArray(calls)) return [];

  return calls
    .map(call => ({
      ...call,
      flagInfo: determineCallFlags(call)
    }))
    .filter(call => call.flagInfo.isFlagged)
    .sort((a, b) => {
      // Sort by number of reasons (most critical first)
      return b.flagInfo.reasons.length - a.flagInfo.reasons.length;
    });
}

// ============================================================================
// AGENT SCORECARD DATA
// ============================================================================

/**
 * Build agent scorecard with real backend data
 * Combines local coaching data with backend metrics
 * 
 * @param {string} agentName - Agent name from coaching data
 * @param {string} agentEmail - Agent email for metrics lookup
 * @param {Array} allCalls - All call coaching records
 * @returns {Promise<Object>} Agent scorecard data
 */
async function buildAgentScorecard(agentName, agentEmail, allCalls = []) {
  try {
    // Get backend metrics
    const metrics = await getAgentMetrics(agentEmail);

    // Filter calls for this agent
    const agentCalls = allCalls.filter(c => 
      c.name && c.name.toLowerCase() === agentName.toLowerCase()
    );

    // Calculate coaching stats
    const flaggedCalls = getFlaggedCalls(agentCalls);
    const avgScore = agentCalls.length > 0
      ? Math.round(agentCalls.reduce((sum, c) => sum + (c.score || 0), 0) / agentCalls.length)
      : 0;

    return {
      agentName,
      agentEmail,
      scorecard: {
        callsCoached: agentCalls.length,
        averageScore: avgScore,
        flaggedCalls: flaggedCalls.length,
        
        // From backend
        callsHandled: metrics?.totalContacts || 0,
        ticketsSolved: metrics?.activeTickets || 0,
        followupsLogged: metrics?.personalPipeline || 0
      },
      flaggedCalls,
      recentCalls: agentCalls.slice(-5).reverse()
    };
  } catch (error) {
    console.error('[Call Coaching API] Error building scorecard:', error);
    return null;
  }
}

// ============================================================================
// EXPORTS / GLOBAL NAMESPACE
// ============================================================================

const callCoachingAPI = {
  // Flagging
  determineCallFlags,
  getFlaggedCalls,
  
  // Metrics
  getAgentMetrics,
  buildAgentScorecard,
  
  // Manager review
  sendCallToManager,
  
  // Health
  getIntegrationHealth,
  
  // Thresholds
  thresholds: COACHING_THRESHOLDS,
  
  // Cache keys
  cacheKeys: CALL_COACHING_CACHE_KEYS
};

// Make globally accessible
if (typeof window !== 'undefined') {
  window.callCoachingAPI = callCoachingAPI;
}