(function () {
  const POLL_MS = 1500;
  const ACTIVE_CALL_PATH = '/activeCall.html';
  const DISMISSED_KEY = 'dialforgeDismissedSipRuntimeSession';
  const ACCEPTED_KEY = 'dialforgeAcceptedRuntimeSession';

  if (window.DialForgeSipRuntimeGlobal) return;
  window.DialForgeSipRuntimeGlobal = { started: true };

  const path = window.location.pathname;
  if (path.endsWith('/login.html') || path.endsWith(ACTIVE_CALL_PATH)) return;

  let currentSessionId = null;
  let currentRoom = null;
  let pollHandle = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function authHeaders() {
    try {
      const token = localStorage.getItem('dialforgeAuthToken');
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch (error) {
      return {};
    }
  }

  async function fetchRuntimeSession() {
    const response = await fetch('/api/runtime/session', {
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`runtime session HTTP ${response.status}`);
    return response.json();
  }

  function dismissedSessionId() {
    try {
      return sessionStorage.getItem(DISMISSED_KEY);
    } catch (error) {
      return null;
    }
  }

  function rememberDismissed(sessionId) {
    try {
      sessionStorage.setItem(DISMISSED_KEY, sessionId);
    } catch (error) {
      // Best effort only; polling state remains authoritative.
    }
  }

  function rememberAccepted(sessionId) {
    try {
      sessionStorage.setItem(ACCEPTED_KEY, sessionId);
    } catch (error) {
      // Best effort only; activeCall.html can still discover the live session.
    }
  }

  function callerFromRoom(room) {
    const context = room?.initial_context || {};
    const extension = context.dialed_extension || room?.company_key || 'SIP';
    const displayName = room?.display_name || 'GlobiFYE';
    return {
      name: `${displayName} live call`,
      company: `${room?.direction || 'inbound'} SIP runtime`,
      number: `Extension ${extension}`,
      avatar: '',
    };
  }

  function showOverlay(room) {
    const overlay = byId('incomingCallOverlay');
    if (!overlay) return false;

    const caller = callerFromRoom(room);
    const avatar = byId('incomingCallAvatar');
    const name = byId('incomingCallName');
    const company = byId('incomingCallCompany');
    const number = byId('incomingCallNumber');

    if (avatar) {
      avatar.alt = caller.name;
      if (caller.avatar) avatar.src = caller.avatar;
    }
    if (name) name.textContent = caller.name;
    if (company) company.textContent = caller.company;
    if (number) number.textContent = caller.number;

    if (window.CALL) {
      window.CALL.caller = caller;
      window.CALL.status = 'ringing';
      window.CALL.direction = room?.direction || 'inbound';
    }

    overlay.classList.remove('hidden');
    return true;
  }

  function hideOverlay() {
    byId('incomingCallOverlay')?.classList.add('hidden');
  }

  function showActiveBar(room) {
    const bar = byId('activeCallBar');
    if (!bar) return;
    const caller = callerFromRoom(room);
    const name = byId('activeCallName');
    const company = byId('activeCallCompany');
    const status = byId('activeCallStatusLabel');
    if (name) name.textContent = caller.name;
    if (company) company.textContent = caller.company;
    if (status) status.textContent = 'SIP Call Live';
    bar.classList.remove('hidden');
  }

  function clearRuntimeUi(sessionId) {
    if (currentSessionId && sessionId && currentSessionId !== sessionId) return;
    currentSessionId = null;
    currentRoom = null;
    hideOverlay();
  }

  function openActiveCall(sessionId) {
    if (sessionId) rememberAccepted(sessionId);
    window.location.href = sessionId
      ? `./activeCall.html?call_session_id=${encodeURIComponent(sessionId)}`
      : './activeCall.html';
  }

  function bindControls() {
    const accept = byId('acceptCallBtn');
    const decline = byId('declineCallBtn');
    const voicemail = byId('voicemailCallBtn');

    accept?.addEventListener('click', (event) => {
      if (!currentSessionId) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      openActiveCall(currentSessionId);
    }, true);

    const dismiss = (event) => {
      if (!currentSessionId) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      rememberDismissed(currentSessionId);
      hideOverlay();
      showActiveBar(currentRoom);
    };

    decline?.addEventListener('click', dismiss, true);
    voicemail?.addEventListener('click', dismiss, true);
  }

  async function pollRuntime() {
    let room;
    try {
      room = await fetchRuntimeSession();
    } catch (error) {
      return;
    }

    const active = Boolean(room?.ok !== false && room?.status === 'active' && room?.call_session_id);
    if (!active) {
      clearRuntimeUi(room?.call_session_id);
      return;
    }

    currentSessionId = room.call_session_id;
    currentRoom = room;

    if (dismissedSessionId() === currentSessionId) {
      showActiveBar(room);
      return;
    }

    if (!showOverlay(room)) {
      showActiveBar(room);
    }
  }

  function start() {
    bindControls();
    pollRuntime();
    pollHandle = window.setInterval(pollRuntime, POLL_MS);
    window.addEventListener('beforeunload', () => {
      if (pollHandle) window.clearInterval(pollHandle);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
