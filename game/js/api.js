const API_BASE = '';

const api = {
  async request(method, path, body) {
    const opts = { method, headers: {} };
    if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) { const err = await res.json().catch(() => ({detail: res.statusText})); const msg = err.detail || 'API Error'; throw new Error(`[${res.status}] ${msg}`); }
    return res.json();
  },
  newGame(body) { return this.request('POST', '/api/game/new', body); },
  getState(gameId) { return this.request('GET', `/api/game/${gameId}`); },
  drawOptions(gameId) { return this.request('POST', `/api/game/${gameId}/draw-options`); },
  pickCard(gameId, charId) { return this.request('POST', `/api/game/${gameId}/pick-card`, {char_id: charId}); },
  place(gameId, charId, cell, troops) { return this.request('POST', `/api/game/${gameId}/place`, {char_id: charId, cell, troops}); },
  endTurn(gameId) { return this.request('POST', `/api/game/${gameId}/end-turn`); },
  autoPlace(gameId) { return this.request('POST', `/api/game/${gameId}/auto-place`); },
  resetGame(gameId) { return this.request('POST', `/api/game/${gameId}/reset`); },
  setTerrain(gameId, terrain) { return this.request('POST', `/api/game/${gameId}/set-terrain`, {terrain}); },
  // Room API
  roomCreate(body) { return this.request('POST', '/api/room/create', body); },
  roomJoin(body) { return this.request('POST', '/api/room/join', body); },
  roomLeave(body) { return this.request('POST', '/api/room/leave', body); },
  roomStart(body) { return this.request('POST', '/api/room/start', body); },
  roomReady(body) { return this.request('POST', '/api/room/ready', body); },
  roomList() { return this.request('GET', '/api/room/list'); },
  roomStatus(body) { return this.request('POST', '/api/room/status', body); },
  roomSetTerrain(body) { return this.request('POST', '/api/room/terrain', body); },
  // Guest multiplayer endpoints
  drawOptionsGuest(gameId) { return this.request('POST', `/api/game/${gameId}/draw-options-guest`); },
  pickCardGuest(gameId, charId) { return this.request('POST', `/api/game/${gameId}/pick-card-guest`, {char_id: charId}); },
  placeGuest(gameId, charId, cell, troops) { return this.request('POST', `/api/game/${gameId}/place-guest`, {char_id: charId, cell, troops}); },
  endPlacementGuest(gameId) { return this.request('POST', `/api/game/${gameId}/end-placement-guest`); },
  autoPlaceMp(gameId) { return this.request('POST', `/api/game/${gameId}/auto-place-mp`); },
  autoPlaceMySide(gameId, isHost) { return this.request('POST', `/api/game/${gameId}/auto-place-my-side`, { is_host: isHost }); },
  submitRps(gameId, choice) { return this.request('POST', `/api/game/${gameId}/submit-rps`, { choice }); },
  pickTennozanFlag(gameId, charId) { return this.request('POST', `/api/game/${gameId}/pick-tennozan-flag`, { char_id: charId }); },
};
