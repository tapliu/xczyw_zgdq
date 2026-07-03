const API_BASE = '';

const api = {
  async request(method, path, body) {
    const opts = { method, headers: {} };
    if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) { const err = await res.json().catch(() => ({detail: res.statusText})); throw new Error(err.detail || 'API Error'); }
    return res.json();
  },
  newGame() { return this.request('POST', '/api/game/new'); },
  getState(gameId) { return this.request('GET', `/api/game/${gameId}`); },
  draw(gameId) { return this.request('POST', `/api/game/${gameId}/draw`); },
  place(gameId, charId, cell, troops) { return this.request('POST', `/api/game/${gameId}/place`, {char_id: charId, cell, troops}); },
  endTurn(gameId) { return this.request('POST', `/api/game/${gameId}/end-turn`); },
  autoPlace(gameId) { return this.request('POST', `/api/game/${gameId}/auto-place`); },
  resetGame(gameId) { return this.request('POST', `/api/game/${gameId}/reset`); },
  setTerrain(gameId, terrain) { return this.request('POST', `/api/game/${gameId}/set-terrain`, {terrain}); }
};
