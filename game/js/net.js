/**
 * net.js — Network Protocol Layer (Client)
 * =========================================
 * Layer 1: WebSocket with query‑param token auth
 * Layer 2: JSON message framing + delta state merge
 * Layer 3: Input queue + reconnection state recovery
 * Layer 4: Delegates to main.js for state application
 */

// ── Message Type Constants ──────────────────────────────────────────

const C2S = { HEARTBEAT: 1, JOIN_BATTLE: 2, LEAVE: 3, INPUT: 4, PING: 5, SNAPSHOT_REQ: 6 };
const S2C = { HEARTBEAT: 129, STATE: 130, ACK: 131, ERROR: 132, PHASE: 133, EVENT: 134, PONG: 135, SNAPSHOT_RES: 136, FLOW_CONTROL: 137 };

// ── State ────────────────────────────────────────────────────────────

let _ws = null;
let _seq = 0;
let _heartbeatTimer = null;
let _reconnectTimer = null;
let _gameId = null;
let _role = null;
let _token = null;
let _connected = false;
let _inputQueue = [];
let _reconnectAttempts = 0;
let _lastFullState = null;        // keeps the last full state for delta merge
let _lastTick = 0;

// ── Backpressure state ──────────────────────────────────────────────
let _backpressure = false;        // true when server asks us to slow down
let _throttleTimer = null;        // interval timer for rate-limited send
let _currentAllowRate = 30;       // inputs/sec allowed by server
let _inputBuffer = [];            // queue for inputs held during backpressure

const BASE_RECONNECT_MS = 500;
const MAX_RECONNECT_MS = 5000;

// ── net object (global) ──────────────────────────────────────────────

window.net = {
  onState: null,
  onEvent: null,
  onPhase: null,
  onError: null,
  onConnectionChange: null,

  get connected() { return _connected; },
  get role() { return _role; },
  get gameId() { return _gameId; },

  // ── Connect / Disconnect ────────────────────────────────────────

  async connect(gameId, role, token) {
    _gameId = gameId;
    _role = role;
    _token = token || '';
    _inputQueue = [];
    _reconnectAttempts = 0;
    _lastFullState = null;
    _lastTick = 0;
    return _connect();
  },

  disconnect() {
    _clearReconnect();
    _stopHeartbeat();
    _stopThrottle();
    if (_ws) {
      _ws.onclose = null;
      _ws.onerror = null;
      _ws.close();
      _ws = null;
    }
    _connected = false;
    _gameId = null;
    _role = null;
    _lastFullState = null;
    _inputBuffer = [];
    _backpressure = false;
    if (net.onConnectionChange) net.onConnectionChange(false);
  },

  // ── Send ─────────────────────────────────────────────────────────

  sendInput(data) {
    if (!_connected) { _inputQueue.push(data); return -1; }
    if (_backpressure) {
      // Under server backpressure — buffer instead of sending
      _inputBuffer.push(data);
      return 0; // 0 = buffered
    }
    return _send(C2S.INPUT, data);
  },

  joinBattle() { _send(C2S.JOIN_BATTLE, {}); },

  requestSnapshot(tick) {
    _send(C2S.SNAPSHOT_REQ, { tick: tick || 0 });
  },

  ping() { _send(C2S.PING, {}); },

  leave() { _send(C2S.LEAVE, {}); },
};

// ── Internal ────────────────────────────────────────────────────────

function _connect() {
  return new Promise((resolve, reject) => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws/${_gameId}/${_role}?token=${encodeURIComponent(_token)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      _ws = ws;
      _connected = true;
      _startHeartbeat();
      while (_inputQueue.length) net.sendInput(_inputQueue.shift());
      if (net.onConnectionChange) net.onConnectionChange(true);
      resolve();
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      const t = msg.t, data = msg.d || {}, seq = msg.seq || 0, tick = msg.tick || 0;

      switch (t) {
        case S2C.STATE:
          _handleState(data, tick);
          break;
        case S2C.SNAPSHOT_RES:
          // Reconnection: server sent the closest snapshot
          _lastFullState = data.snapshot;
          _lastTick = data.tick || 0;
          if (net.onState) net.onState(data.snapshot, data.current_tick, false);
          break;
        case S2C.EVENT:
          if (net.onEvent) net.onEvent(data);
          break;
        case S2C.PHASE:
          if (net.onPhase) net.onPhase(data.phase, data.round, data.role);
          break;
        case S2C.ACK:
          break;
        case S2C.ERROR:
          console.warn('[net] Server error:', data.message);
          if (net.onError) net.onError(data.message, data.seq);
          break;
        case S2C.FLOW_CONTROL:
          _handleFlowControl(data);
          break;
        case S2C.HEARTBEAT:
        case S2C.PONG:
          break;
      }
    };

    ws.onclose = () => {
      _connected = false;
      _stopHeartbeat();
      if (net.onConnectionChange) net.onConnectionChange(false);
      _scheduleReconnect();
    };

    ws.onerror = (err) => { reject(err); };
  });
}

function _handleFlowControl(data) {
  const wasBackpressure = _backpressure;
  _backpressure = !!data.backpressure;
  _currentAllowRate = data.allow_rate || 30;

  if (!_backpressure && wasBackpressure) {
    // Pressure relieved — drain buffer
    _startThrottleDrain();
  } else if (_backpressure && _inputBuffer.length > 0) {
    // We're still under pressure but have buffered inputs — drain slowly
    _startThrottleDrain();
  } else if (!_backpressure && !wasBackpressure) {
    // Normal state, no throttling needed
    _stopThrottle();
  }
}

function _startThrottleDrain() {
  _stopThrottle();
  if (_backpressure && _currentAllowRate < 5) {
    // Severe backpressure: only send 1 input per interval
    _throttleTimer = setInterval(() => {
      if (!_connected) { _stopThrottle(); return; }
      if (_inputBuffer.length === 0) {
        // Buffer drained but still under pressure — wait
        return;
      }
      const data = _inputBuffer.shift();
      _send(C2S.INPUT, data);
    }, 200); // 5 / sec max
  } else {
    // Mild or no backpressure: drain buffer at allow_rate
    const intervalMs = Math.max(33, Math.round(1000 / Math.min(_currentAllowRate, 30)));
    _throttleTimer = setInterval(() => {
      if (!_connected) { _stopThrottle(); return; }
      if (_inputBuffer.length === 0) {
        if (!_backpressure) _stopThrottle();
        return;
      }
      const data = _inputBuffer.shift();
      _send(C2S.INPUT, data);
    }, intervalMs);
  }
}

function _stopThrottle() {
  if (_throttleTimer) {
    clearInterval(_throttleTimer);
    _throttleTimer = null;
  }
}

function _handleState(data, tick) {
  if (data.full) {
    // Full snapshot — replace local state
    _lastFullState = data.snapshot;
    _lastTick = tick;
    if (net.onState) net.onState(data.snapshot, tick, data.final);
  } else if (data.delta) {
    // Delta — merge into local state
    if (_lastFullState) {
      for (const k in data.delta) {
        if (data.delta[k] === null) {
          delete _lastFullState[k];
        } else {
          _lastFullState[k] = data.delta[k];
        }
      }
      _lastTick = tick;
      if (net.onState) net.onState(_lastFullState, tick, data.final);
    } else {
      // No base state — request a full snapshot
      net.requestSnapshot();
    }
  }
}

function _send(type, data) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return -1;
  const seq = ++_seq;
  _ws.send(JSON.stringify({ t: type, seq, ts: Date.now(), tick: _lastTick, d: data }));
  return seq;
}

function _startHeartbeat() {
  _stopHeartbeat();
  _heartbeatTimer = setInterval(() => {
    if (_connected) _send(C2S.HEARTBEAT, {});
  }, 10000);
}

function _stopHeartbeat() {
  if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
}

function _scheduleReconnect() {
  if (_reconnectTimer || !_gameId) return;
  const delay = Math.min(BASE_RECONNECT_MS * Math.pow(2, _reconnectAttempts), MAX_RECONNECT_MS);
  _reconnectAttempts++;
  console.log(`[net] Reconnecting in ${delay}ms (attempt ${_reconnectAttempts})`);
  _reconnectTimer = setTimeout(async () => {
    _reconnectTimer = null;
    try {
      await _connect();
      _reconnectAttempts = 0;
      // Request state snapshot for recovery
      net.requestSnapshot(_lastTick);
    } catch (e) {
      _scheduleReconnect();
    }
  }, delay);
}

function _clearReconnect() {
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  _reconnectAttempts = 0;
}
