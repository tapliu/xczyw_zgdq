// ==================== CONSTANTS ====================
const BOARD_ROWS = 8, BOARD_COLS = 8;
const PLAYER_ROWS = [4,5,6,7], AI_ROWS = [0,1,2,3];
const PLACE_PER_ROUND = 5;
const DRAW_PER_ROUND = 3;
const INIT_DRAW = 10;
const INIT_TROOPS = 50000;
const MAX_TROOPS_PER_UNIT = 10000;
const TROOP_INCOME = 10000;
const MAX_TOTAL_TROOPS = 300000;
const TERRAIN_PATTERNS = {
  normal: new Array(64).fill(true),
  tennozan: (()=>{
    const m = new Array(64).fill(false);
    const actives = [8,6,4,2,2,4,6,8];
    for (let r=0;r<8;r++) {
      const n = actives[r], off = (8-n)/2;
      for (let c=off;c<off+n;c++) m[r*8+c] = true;
    }
    return m;
  })(),
  nagashino: (()=>{
    const m = new Array(64).fill(true);
    for (let c=0;c<8;c++) { if (c!==1&&c!==2&&c!==5&&c!==6) { m[3*8+c]=false; m[4*8+c]=false; } }
    return m;
  })()
};
const MAX_UNITS_PER_SIDE = 20;
function maxUnits() { return terrainMode === 'tennozan' ? 10 : terrainMode === 'nagashino' ? 16 : MAX_UNITS_PER_SIDE; }
const RATING_COLORS = { 'S+':'#e94560','S':'#9b59b6','A':'#3498db','B':'#2ecc71','C':'#607d8b','D':'#7f8c8d' };
const TYPE_COLORS = { '全能':'#f5a623','武将':'#e94560','文臣':'#3498db','特才':'#9b59b6' };
const MON_CRESTS = ['◈','◆','★','✿','❖','⚘','✧','❀','✦','♰'];
const CAT_NAMES = ['全能','武将','文臣','特才'];

// ==================== STATE ====================
let gameId = null;
let round = 0, gamePhase = 'idle', drawPileCount = 100, placedThisTurn = 0;
let player = { collection: [], board: Array(64).fill(null), troops: INIT_TROOPS, placed: 0, flagIdx: -1 };
let ai = { collection: [], board: Array(64).fill(null), troops: INIT_TROOPS, placed: 0, flagIdx: -1 };
let selectedChar = null, selectedCell = null;
let playerCatFilter = 'all', aiCatFilter = 'all', playerSortBy = 'default';
let avatarCache = {};
let playerCooldowns = [], aiCooldowns = [];
let autoPlay = false;
let scatterDebuff = {}, deadList = [], flagScatterCount = { player: 0, ai: 0 };
let spectatorPool = [];
let combatStats = {}, uidCharMap = {}, uidSideMap = {};
let terrainMode = 'normal';

// ==================== APPLY STATE FROM SERVER ====================
function normalizeSide(obj) {
  if (!obj) return obj;
  return {
    collection: obj.collection || [],
    board: obj.board || Array(64).fill(null),
    troops: obj.troops || 0,
    flagIdx: obj.flag_idx ?? obj.flagIdx ?? -1,
    placed: obj.placed ?? 0,
  };
}

function applyStateFromServer(data) {
  const s = data.state || data;
  if (s.game_id) gameId = s.game_id;
  gamePhase = s.game_phase ?? s.gamePhase ?? gamePhase;
  if (s.round !== undefined) round = s.round;
  drawPileCount = s.draw_pile_count ?? s.drawPileCount ?? drawPileCount;
  placedThisTurn = s.placed_this_turn ?? s.placedThisTurn ?? placedThisTurn;
  if (s.player) player = normalizeSide(s.player);
  if (s.ai) ai = normalizeSide(s.ai);
  playerCooldowns = s.player_cooldowns ?? s.playerCooldowns ?? playerCooldowns;
  aiCooldowns = s.ai_cooldowns ?? s.aiCooldowns ?? aiCooldowns;
  scatterDebuff = s.scatter_debuff ?? s.scatterDebuff ?? scatterDebuff;
  if (s.dead_list ?? s.deadList) deadList = s.dead_list ?? s.deadList;
  flagScatterCount = s.flag_scatter_count ?? s.flagScatterCount ?? flagScatterCount;
  if (s.spectator_pool ?? s.spectatorPool) spectatorPool = s.spectator_pool ?? s.spectatorPool;
  if (s.combat_stats ?? s.combatStats) combatStats = s.combat_stats ?? s.combatStats;
  if (s.uid_char_map ?? s.uidCharMap) uidCharMap = s.uid_char_map ?? s.uidCharMap;
  if (s.uid_side_map ?? s.uidSideMap) uidSideMap = s.uid_side_map ?? s.uidSideMap;
  terrainMode = s.terrain_mode ?? s.terrainMode ?? terrainMode;
  const logs = s.battle_log ?? s.battleLog;
  if (logs && logs.length) {
    logs.forEach(entry => addBattleLog(entry.msg || entry.message, entry.type || 'info'));
  }
  updateTerrainUI();
  renderBoardFull();
  updateUI();
  updateSpectatorGrid();
  updateButtonStates();
}

function updateButtonStates() {
  if (gamePhase === 'gameover') {
    document.getElementById('btnDraw').disabled = true;
    document.getElementById('btnEndTurn').disabled = true;
    document.getElementById('btnAutoPlace').disabled = true;
  } else if (gamePhase === 'idle' || gamePhase === 'draw') {
    document.getElementById('btnDraw').disabled = false;
    document.getElementById('btnEndTurn').disabled = false;
    document.getElementById('btnAutoPlace').disabled = false;
  } else if (gamePhase === 'place_player') {
    document.getElementById('btnDraw').disabled = true;
    document.getElementById('btnEndTurn').disabled = false;
    document.getElementById('btnAutoPlace').disabled = false;
  } else {
    document.getElementById('btnDraw').disabled = true;
    document.getElementById('btnEndTurn').disabled = true;
    document.getElementById('btnAutoPlace').disabled = true;
  }
}

function updateTerrainUI() {
  document.getElementById('btnTerrainNormal').className = 'btn btn-xs btn-outline' + (terrainMode==='normal'?' active':'');
  document.getElementById('btnTerrainNagashino').className = 'btn btn-xs btn-outline' + (terrainMode==='nagashino'?' active':'');
  document.getElementById('btnTerrainTennozan').className = 'btn btn-xs btn-outline' + (terrainMode==='tennozan'?' active':'');
}

// ==================== AVATAR ====================
function generateAvatar(char, size) {
  const key = char.id + '-' + size;
  if (avatarCache[key]) return avatarCache[key];
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const r = size / 2;
  const rc = RATING_COLORS[char.rating] || '#555';
  const tc = TYPE_COLORS[char.type] || '#888';
  ctx.beginPath(); ctx.arc(r,r,r,0,Math.PI*2);
  const grad = ctx.createRadialGradient(r*0.3,r*0.3,0,r*0.8,r*0.8,r);
  grad.addColorStop(0,rc); grad.addColorStop(1,'#0a0a1a');
  ctx.fillStyle=grad; ctx.fill();
  const crest = MON_CRESTS[char.id % MON_CRESTS.length];
  ctx.fillStyle='rgba(255,255,255,0.08)'; ctx.font=Math.round(size*0.26)+'px serif';
  ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(crest,r,r*0.3);
  let initials = char.name.charAt(0);
  if (char.name.length >= 2 && size >= 24) initials = char.name.substring(0, 2);
  ctx.fillStyle='#fff';
  ctx.shadowColor='rgba(0,0,0,0.7)'; ctx.shadowBlur=Math.max(3, size*0.08);
  ctx.font='bold '+Math.round(size*0.4)+'px "Microsoft YaHei",sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(initials,r,r+r*0.22);
  ctx.shadowBlur=0;
  const bw = Math.max(2, size*0.06);
  ctx.beginPath(); ctx.arc(r,r,r-bw/2,0,Math.PI*2);
  ctx.strokeStyle=tc; ctx.lineWidth=bw; ctx.stroke();
  if (size>=26&&char.rating) {
    const bx=r+r*0.7,by=r+r*0.7,br=Math.max(5,size*0.08);
    ctx.beginPath(); ctx.arc(bx,by,br,0,Math.PI*2); ctx.fillStyle='#1a1a2e'; ctx.fill();
    ctx.beginPath(); ctx.arc(bx,by,br-1,0,Math.PI*2); ctx.strokeStyle=rc; ctx.lineWidth=1.5; ctx.stroke();
    ctx.fillStyle='#fff'; ctx.font='bold '+Math.round(br*0.8)+'px sans-serif';
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(char.rating,bx,by+1);
  }
  avatarCache[key]=c.toDataURL();
  return avatarCache[key];
}

// ==================== BOARD ====================
function idx(r,c){return r*BOARD_COLS+c}
function rowOf(i){return Math.floor(i/BOARD_COLS)}
function colOf(i){return i%BOARD_COLS}
function inRange(r,c){return r>=0&&r<BOARD_ROWS&&c>=0&&c<BOARD_COLS}
function isActiveCell(i) { return TERRAIN_PATTERNS[terrainMode][i]; }

function initBoard() {
  const el = document.getElementById('board');
  el.innerHTML = '<div class="divider"></div>';
  for (let i = 0; i < 64; i++) {
    const cell = document.createElement('div');
    cell.className = 'cell ' + (rowOf(i) < 4 ? 'ai-zone' : 'player-zone');
    cell.dataset.index = i;
    cell.addEventListener('click', () => onCellClick(i));
    cell.addEventListener('contextmenu', e => { e.preventDefault(); onRightClick(i); });
    el.appendChild(cell);
  }
}

function getUnit(idx) { return player.board[idx] || ai.board[idx]; }
function isPlayerUnit(idx) { return player.board[idx] !== null; }

function renderBoardFull() {
  const cells = document.querySelectorAll('.cell');
  cells.forEach((cell, i) => {
    cell.className = 'cell ' + (rowOf(i) < 4 ? 'ai-zone' : 'player-zone');
    if (!isActiveCell(i)) cell.classList.add('inactive');
    const pu = player.board[i], au = ai.board[i];
    const u = pu || au;
    if (u) {
      const isPlayer = !!pu;
      const both = !!(pu && au);
      cell.classList.add(isPlayer ? 'has-player' : 'has-ai');
      if (both) cell.classList.add('has-both');
      if (selectedCell === i) cell.classList.add('highlight');
      if (both) {
        const pFlag = player.flagIdx === i, aFlag = ai.flagIdx === i;
        const pPower = Math.round(calcPower(i, true)), aPower2 = Math.round(calcPower(i, false));
        cell.innerHTML = `<div class="both-units"><span class="bu-player">▲${generateAvatar(pu.char,18)}<span class="bu-name">${pu.char.name}</span><span class="bu-troops">${pu.troops.toLocaleString()}</span>${pFlag?'🚩':''}</span><span class="bu-vs">⚔</span><span class="bu-ai">${aFlag?'🚩':''}${generateAvatar(au.char,18)}<span class="bu-name">${au.char.name}</span><span class="bu-troops">${au.troops.toLocaleString()}</span>▼</span></div>`;
      } else {
        const isFlag = (isPlayer && player.flagIdx === i) || (!isPlayer && ai.flagIdx === i);
        const flagIcon = isFlag ? '<span class="u-flag">🚩</span>' : '';
        const dirIcon = isPlayer ? '▲' : '▼';
        const power = Math.round(calcPower(i, isPlayer));
        cell.innerHTML = `${flagIcon}<img class="u-avatar" src="${generateAvatar(u.char,24)}" alt="">
          <span class="u-name">${u.char.name}</span>
          <span class="u-power">${power}</span>
          <span class="u-troops">${u.troops.toLocaleString()}</span>
          <span class="u-owner">${dirIcon}</span>`;
      }
    } else {
      if (selectedCell === i) cell.classList.add('highlight');
      cell.innerHTML = '';
    }
  });
  if (window.animQueue) window.animQueue.forEach(a=>{
    const el=document.querySelector(`.cell[data-index="${a.idx}"]`);
    if (el) el.classList.add(a.type);
  });
  document.getElementById('playerTroops').textContent = player.troops ? player.troops.toLocaleString() : '0';
  document.getElementById('aiTroops').textContent = ai.troops ? ai.troops.toLocaleString() : '0';
}

function onCellClick(index) {
  const u = getUnit(index);
  if (!u) {
    if (gamePhase === 'place_player' && placedThisTurn < PLACE_PER_ROUND && PLAYER_ROWS.includes(rowOf(index))) {
      if (!isActiveCell(index)) { setPhase('❌ 此格不可用'); return; }
      if (player.board.filter(u=>u).length >= maxUnits()) { setPhase('❌ 已达上限'+maxUnits()+'名武将'); return; }
      if (isBehindEnemyLine(index, true)) { setPhase('❌ 不可放置在敌方棋子后方'); return; }
      if (selectedChar) { selectedCell = index; showTroopModal(selectedChar, index); }
      else setPhase('请在下方武将册中选择一名武将');
    }
    return;
  }
  showDetailUnit(u, isPlayerUnit(index), index);
  selectedCell = index;
  renderBoardFull();
}

function onRightClick(index) {
  // Right-click removal not supported in API-based architecture;
  // use reset to undo placements.
}

// ==================== COMBAT DISPLAY UTILITIES ====================
function getNeighborIndices(i) {
  const r = rowOf(i), c = colOf(i), res = [];
  for (let dr = -1; dr <= 1; dr++)
    for (let dc = -1; dc <= 1; dc++)
      if (dr!==0||dc!==0) { const nr=r+dr,nc=c+dc; if (inRange(nr,nc)) res.push(idx(nr,nc)); }
  return res;
}

function getConeIndices(i, isPlayer) {
  const r = rowOf(i), c = colOf(i);
  const dir = isPlayer ? -1 : 1;
  const res = [];
  for (let dc = -1; dc <= 1; dc++) { const nr=r+dir,nc=c+dc; if (inRange(nr,nc)) res.push(idx(nr,nc)); }
  for (let dc = -2; dc <= 2; dc++) { const nr=r+dir*2,nc=c+dc; if (inRange(nr,nc)) res.push(idx(nr,nc)); }
  return res;
}

function isFlagUnit(idx, isPlayer) {
  return isPlayer ? player.flagIdx === idx : ai.flagIdx === idx;
}

function calcPower(index, isPlayer) {
  const myBoard = isPlayer ? player.board : ai.board;
  const enBoard = isPlayer ? ai.board : player.board;
  const u = myBoard[index];
  if (!u) return 0;
  const flagMul = isFlagUnit(index, isPlayer) ? 1.1 : 1;
  let power = u.char.martial * 2 * flagMul;
  power *= (1 + u.troops / 30000);
  getNeighborIndices(index).forEach(ni => { const nu = myBoard[ni]; if (nu) power += nu.char.leadership * 0.05; });
  power += u.char.leadership * flagMul * 0.05;
  for (let ei=0;ei<64;ei++) {
    const eu = enBoard[ei];
    if (!eu) continue;
    const cone = getConeIndices(ei, !isPlayer);
    if (cone.indexOf(index) >= 0) power -= eu.char.intelligence * 0.03;
  }
  return Math.max(1, Math.round(power));
}

function isBehindEnemyLine(idx, isPlayer) {
  const r=rowOf(idx), c=colOf(idx);
  const enBoard=isPlayer?ai.board:player.board;
  if (isPlayer) { for (let rr=r+1;rr<8;rr++) if (enBoard[rr*8+c]) return true; }
  else { for (let rr=r-1;rr>=0;rr--) if (enBoard[rr*8+c]) return true; }
  return false;
}

// ==================== DETAIL PANEL ====================
function showDetailUnit(u, isPlayer, idx) {
  const panel = document.getElementById('detailPanel');
  panel.className = 'detail-panel show';
  const char = u.char;
  const rc = RATING_COLORS[char.rating] || '#888';
  const isFlag = (isPlayer && player.flagIdx === idx) || (!isPlayer && ai.flagIdx === idx);
  const power = Math.round(calcPower(idx, isPlayer));
  panel.innerHTML = `
    <div class="d-top">
      <img class="d-avatar" src="${generateAvatar(char,44)}" alt="">
      <div class="d-info">
        <div class="dname" style="color:${rc}">${char.name} ${isFlag?'🚩':''}</div>
        <div class="dmeta">${char.type||''} · ${char.rating||''} · 战力 ${power}</div>
      </div>
    </div>
    <div class="d-troops ${isPlayer?'player':'ai'}">⚔ ${u.troops.toLocaleString()} 兵力</div>
    ${statBar('统率',char.leadership,'#e94560')}
    ${statBar('武力',char.martial,'#f5a623')}
    ${statBar('智力',char.intelligence,'#2ecc71')}
    ${statBar('政治',char.politics,'#3498db')}
    <div class="dmeta" style="margin-top:4px">MAX ${char.max_stat} · 邻接+统率×5% · 锥形-智力×3%</div>
  `;
}

function showCharDetail(char, onBoard, onAi) {
  const panel = document.getElementById('detailPanel');
  panel.className = 'detail-panel show';
  const rc = RATING_COLORS[char.rating] || '#888';
  const status = onBoard ? '已上场' : onAi ? '敌方已上场' : '未上场';
  panel.innerHTML = `
    <div class="d-top">
      <img class="d-avatar" src="${generateAvatar(char,44)}" alt="">
      <div class="d-info">
        <div class="dname" style="color:${rc}">${char.name}</div>
        <div class="dmeta">${char.type||''} · ${char.rating||''} · ${status}</div>
      </div>
    </div>
    ${statBar('统率',char.leadership,'#e94560')}
    ${statBar('武力',char.martial,'#f5a623')}
    ${statBar('智力',char.intelligence,'#2ecc71')}
    ${statBar('政治',char.politics,'#3498db')}
    <div class="dmeta" style="margin-top:4px">MAX ${char.max_stat} · 邻接+统率×5% · 锥形-智力×3%</div>
  `;
}

function statBar(label, val, color) {
  return `<div class="stat-row"><span class="slabel">${label}</span><div class="sbar"><div class="sfill" style="width:${val}%;background:${color}"></div></div><span class="sval">${val}</span></div>`;
}

// ==================== TROOP MODAL ====================
let pendingChar = null, pendingCell = -1;

function showTroopModal(char, cellIdx) {
  pendingChar = char; pendingCell = cellIdx;
  const maxT = Math.min(MAX_TROOPS_PER_UNIT, char.leadership * 100, player.troops || INIT_TROOPS);
  document.getElementById('tmName').textContent = char.name;
  document.getElementById('tmSub').textContent = `统率 ${char.leadership} · 最大 ${Math.min(MAX_TROOPS_PER_UNIT, char.leadership*100)}`;
  const slider = document.getElementById('troopSlider');
  slider.max = Math.max(1, maxT); slider.min = 1;
  slider.value = Math.min(5000, maxT);
  updateTroopDisplay();
  document.getElementById('troopModal').classList.add('show');
}

function updateTroopDisplay() {
  document.getElementById('troopValue').textContent = parseInt(document.getElementById('troopSlider').value);
}

async function confirmPlace() {
  if (!pendingChar||pendingCell<0) return;
  const troops = parseInt(document.getElementById('troopSlider').value);
  if (troops > (player.troops || 0)) { addBattleLog('兵力不足！','lose'); return; }
  if (getUnit(pendingCell)) { cancelPlace(); return; }
  if (!isActiveCell(pendingCell)) { addBattleLog('此格不可用！','lose'); cancelPlace(); return; }
  if (player.board.some(u=>u&&u.char.id===pendingChar.id) || ai.board.some(u=>u&&u.char.id===pendingChar.id)) {
    addBattleLog('该武将已在棋盘上！','lose'); cancelPlace(); return;
  }
  if (isBehindEnemyLine(pendingCell, true)) {
    addBattleLog('不可放置在敌方棋子后方！','lose'); cancelPlace(); return;
  }
  try {
    const data = await api.place(gameId, pendingChar.id, pendingCell, troops);
    cancelPlace();
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('放置失败：' + e.message, 'lose');
    cancelPlace();
  }
}

function cancelPlace() {
  document.getElementById('troopModal').classList.remove('show');
  pendingChar=null; pendingCell=-1;
}

// ==================== COLLECTION GRIDS ====================
function isDead(charId) { return deadList.includes(charId); }

function isOnCooldown(charId, isPlayer) {
  const arr = isPlayer ? playerCooldowns : aiCooldowns;
  return arr.some(c => c.id === charId && c.round + 4 >= round);
}

function updateCollectionGrid() {
  const el = document.getElementById('collectionGrid');
  const empty = document.getElementById('emptyTip');
  if (!player.collection || !player.collection.length) { el.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  let filtered = [...player.collection];
  if (playerCatFilter !== 'all') filtered = filtered.filter(c => c.type === playerCatFilter);
  const sortAttr = playerSortBy;
  const ratingOrder={ 'S+':0,'S':1,'A':2,'B':3,'C':4,'D':5 };
  filtered.sort((a,b) => {
    const aDead=isDead(a.id), bDead=isDead(b.id);
    const aCd=isOnCooldown(a.id,true), bCd=isOnCooldown(b.id,true);
    const aOn=player.board.some(u=>u&&u.char.id===a.id)||ai.board.some(u=>u&&u.char.id===a.id);
    const bOn=player.board.some(u=>u&&u.char.id===b.id)||ai.board.some(u=>u&&u.char.id===b.id);
    const aG=aDead?3:(aCd?2:(aOn?1:0));
    const bG=bDead?3:(bCd?2:(bOn?1:0));
    if (aG!==bG) return aG-bG;
    if (sortAttr !== 'default') {
      return (b[sortAttr]||0) - (a[sortAttr]||0);
    }
    return (ratingOrder[a.rating]??9)-(ratingOrder[b.rating]??9);
  });
  el.innerHTML = '';
  filtered.forEach(c => {
    const onBoard = player.board.some(u=>u&&u.char.id===c.id);
    const onAi = ai.board.some(u=>u&&u.char.id===c.id);
    const div = document.createElement('div');
    const onCooldown = isOnCooldown(c.id, true);
    const cdRemaining = onCooldown ? (playerCooldowns.find(x => x.id === c.id)) : null;
    const freezeRemaining = cdRemaining ? Math.max(0, (cdRemaining.round + 4) - round + 1) : 0;
    const dead = isDead(c.id);
    div.className = 'char-card';
    if (dead) div.classList.add('dead');
    else if (onBoard||onAi) div.classList.add('used');
    else if (onCooldown) div.classList.add('cooldown');
    if (selectedChar&&selectedChar.id===c.id) div.classList.add('selected');
    const showAttr = playerSortBy !== 'default' ? `<div class="cattr">${c[playerSortBy]}</div>` : '';
    div.innerHTML = `<img class="cc-avatar" src="${generateAvatar(c,22)}"><div class="cname">${c.name}</div><div class="cmeta">${c.type||''}</div><div class="crating">${c.rating||''}</div>${dead ? '<div class="dead-badge">死</div>' : onCooldown ? `<div class="freeze-badge ${cdRemaining.type==='scatter'?'scatter':''}">${cdRemaining.type==='scatter'?'溃':'❄'}${freezeRemaining}</div>` : ''}${showAttr}</div>`;
    div.addEventListener('click', ()=>{
      showCharDetail(c, onBoard, onAi || onCooldown || dead);
      if (onBoard||onAi||onCooldown||dead) return;
      selectedChar=c; updateCollectionGrid();
      if (gamePhase==='place_player') setPhase(`已选 ${c.name} · 点击下方空位放置`);
    });
    el.appendChild(div);
  });
}

function updateAiCollectionGrid() {
  const el = document.getElementById('aiCollectionGrid');
  const empty = document.getElementById('aiEmptyTip');
  if (!ai.collection || !ai.collection.length) { el.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  let filtered = [...ai.collection];
  if (aiCatFilter !== 'all') filtered = filtered.filter(c => c.type === aiCatFilter);
  const totalScore = ch => ch.leadership+ch.martial+ch.intelligence+ch.politics;
  const ratingOrder={ 'S+':0,'S':1,'A':2,'B':3,'C':4,'D':5 };
  filtered.sort((a,b) => {
    const aDead=isDead(a.id), bDead=isDead(b.id);
    const aCd=isOnCooldown(a.id,false), bCd=isOnCooldown(b.id,false);
    const aGrp=aDead?2:(aCd?1:0);
    const bGrp=bDead?2:(bCd?1:0);
    if (aGrp!==bGrp) return aGrp-bGrp;
    const ra=ratingOrder[a.rating]??9, rb=ratingOrder[b.rating]??9;
    if (ra!==rb) return ra-rb;
    return totalScore(b)-totalScore(a);
  });
  el.innerHTML = '';
  filtered.forEach(c => {
    const onBoard = ai.board.some(u=>u&&u.char.id===c.id);
    const onCooldown = isOnCooldown(c.id, false);
    const cdRemaining = onCooldown ? (aiCooldowns.find(x => x.id === c.id)) : null;
    const freezeRemaining = cdRemaining ? Math.max(0, (cdRemaining.round + 4) - round + 1) : 0;
    const dead = isDead(c.id);
    const div = document.createElement('div');
    div.className = 'char-card';
    if (dead) div.classList.add('dead');
    else if (onBoard) div.classList.add('used');
    else if (onCooldown) div.classList.add('cooldown');
    div.innerHTML = `<img class="cc-avatar" src="${generateAvatar(c,22)}"><div class="cname">${c.name}</div><div class="cmeta">${c.type||''}</div><div class="crating">${c.rating||''}</div>${dead ? '<div class="dead-badge">死</div>' : onCooldown ? `<div class="freeze-badge ${cdRemaining.type==='scatter'?'scatter':''}">${cdRemaining.type==='scatter'?'溃':'❄'}${freezeRemaining}</div>` : ''}`;
    el.appendChild(div);
  });
}

// ==================== SPECTATOR ====================
function updateSpectatorGrid() {
  const el = document.getElementById('spectatorGrid');
  const section = document.getElementById('spectatorSection');
  const pSurvive = player.collection ? player.collection.filter(c => !isDead(c.id)).length : 0;
  const canRecruit = pSurvive < 10;
  if (!spectatorPool || !spectatorPool.length) { section.style.display='none'; return; }
  section.style.display='block';
  document.getElementById('specHint').textContent = canRecruit ? `己方存活${pSurvive}/10 · 点击招募` : `己方存活${pSurvive}/10`;
  el.innerHTML = '';
  const ratingOrder={ 'S+':0,'S':1,'A':2,'B':3,'C':4,'D':5 };
  const totalScore = ch => ch.leadership+ch.martial+ch.intelligence+ch.politics;
  const sorted = [...spectatorPool].sort((a,b) => {
    const ra=ratingOrder[a.rating]??9, rb=ratingOrder[b.rating]??9;
    if (ra!==rb) return ra-rb;
    return totalScore(b)-totalScore(a);
  });
  sorted.forEach(c => {
    const div = document.createElement('div');
    div.className = 'char-card';
    let html = `<img class="cc-avatar" src="${generateAvatar(c,22)}"><div class="cname">${c.name}</div><div class="cmeta">${c.type||''}</div><div class="crating">${c.rating||''}</div>`;
    if (canRecruit) { html += '<div style="font-size:9px;color:#4caf50;text-align:center">招募</div>'; }
    div.innerHTML = html;
    if (canRecruit) div.addEventListener('click', () => recruitFromSpectator(c.id, true));
    el.appendChild(div);
  });
}

function recruitFromSpectator(charId, isPlayer) {
  const idx = spectatorPool.findIndex(c => c.id === charId);
  if (idx < 0) return;
  const ch = spectatorPool.splice(idx, 1)[0];
  (isPlayer ? player : ai).collection.push(ch);
  addBattleLog(`${isPlayer?'':'敌方'}招募了 ${ch.name} 加入阵营`,'info');
  updateUI();
}

// ==================== BATTLE LOG ====================
function addBattleLog(msg, type='info') {
  const el = document.getElementById('battleLog');
  const div = document.createElement('div');
  div.className = 'entry ' + type;
  div.textContent = msg;
  el.appendChild(div); el.scrollTop = el.scrollHeight;
}

// ==================== UI ====================
function setPhase(msg) { document.getElementById('phaseBanner').innerHTML = msg; }

function showVictory(win) {
  const ov=document.getElementById('victoryOverlay');
  document.getElementById('vIcon').textContent=win?'🏆':'💀';
  document.getElementById('vTitle').textContent=win?'胜利！':'战败...';
  document.getElementById('vTitle').className='v-title '+(win?'win':'lose');
  document.getElementById('vSub').textContent=win?'敌阵已被突破，天下尽在掌中！':'防线崩溃...来日再战！';
  document.getElementById('vIcon').style.animation='vBounce 1s ease-out';
  const mvpEl=document.getElementById('mvpDisplay');
  const side=win?player:ai;
  let bestUid=null, bestDmg=-1, bestChar=null;
  for (const uid in combatStats) {
    const unitOnBoard = side.board.some(u=>u&&u.uid==uid);
    const stat=combatStats[uid];
    if (unitOnBoard && stat.damage>bestDmg) { bestDmg=stat.damage; bestUid=uid; }
  }
  if (bestUid) {
    for (const u of side.board) if (u&&u.uid==bestUid) { bestChar=u.char; break; }
  }
  if (bestChar) {
    const s=combatStats[bestUid];
    const avgMelee=s.meleeHits>0?Math.round(s.meleeDmg/s.meleeHits):0;
    const avgRanged=s.rangedHits>0?Math.round(s.rangedDmg/s.rangedHits):0;
    mvpEl.style.display='block';
    mvpEl.innerHTML=`<div class="v-mvp"><div class="v-mvp-title">🏅 MVP — ${bestChar.name}</div><div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><img class="v-mvp-avatar" src="${generateAvatar(bestChar,40)}"><div><div class="v-mvp-name">${bestChar.name}</div><div class="v-mvp-meta">${bestChar.type||''} · ${bestChar.rating||''} · 统${bestChar.leadership} 武${bestChar.martial} 智${bestChar.intelligence} 政${bestChar.politics}</div></div></div><div class="v-mvp-row"><span class="lab">总伤害</span><span class="val">${s.damage.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">近战均伤</span><span class="val">${s.meleeHits}次 · 每次${avgMelee.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">远程均伤</span><span class="val">${s.rangedHits}次 · 每次${avgRanged.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">击溃/击毙</span><span class="val">${s.kills}人</span></div><div class="v-mvp-row"><span class="lab">大威风</span><span class="val">${s.retreatTriggers}次</span></div></div>`;
  } else {
    mvpEl.style.display='none';
  }
  const rankEl=document.getElementById('rankDisplay');
  const allStats=[];
  for (const uid in combatStats) {
    const ch=uidCharMap[uid];
    if (!ch) continue;
    allStats.push({ uid, char:ch, side:uidSideMap[uid]||'player', ...combatStats[uid] });
  }
  const sideLabel = s => s==='player'?'<span class="v-rank-side p">己</span>':'<span class="v-rank-side a">敌</span>';
  const entryHTML = (item, rank, valLabel, valKey) => {
    const v = valKey ? item[valKey] : item;
    return `<div class="v-rank-entry"><span class="v-rank-num">${rank}</span><img class="v-rank-avatar" src="${generateAvatar(item.char,24)}"><span class="v-rank-name">${item.char.name}</span>${sideLabel(item.side)}<span class="v-rank-val">${typeof v==='number'?v.toLocaleString():v}${valLabel}</span></div>`;
  };
  const topN = (arr, key, n=3) => arr.filter(i=>i[key]>0).sort((a,b)=>b[key]-a[key]).slice(0,n);
  const killsTop = topN(allStats, 'kills');
  const meleeTop = topN(allStats, 'meleeDmg');
  const rangedTop = topN(allStats, 'rangedDmg');
  let html='<div class="v-rank-grid">';
  html+='<div class="v-rank-section"><div class="v-rank-title">⚔ 击溃/击毙 TOP3</div>';
  if (killsTop.length) killsTop.forEach((item,i)=>html+=entryHTML(item,i+1,'人','kills'));
  else html+='<div style="color:#666;font-size:12px;text-align:center">无</div>';
  html+='</div>';
  html+='<div class="v-rank-section"><div class="v-rank-title">🗡 近战伤害 TOP3</div>';
  if (meleeTop.length) meleeTop.forEach((item,i)=>html+=entryHTML(item,i+1,'','meleeDmg'));
  else html+='<div style="color:#666;font-size:12px;text-align:center">无</div>';
  html+='</div>';
  html+='<div class="v-rank-section"><div class="v-rank-title">🏹 远程伤害 TOP3</div>';
  if (rangedTop.length) rangedTop.forEach((item,i)=>html+=entryHTML(item,i+1,'','rangedDmg'));
  else html+='<div style="color:#666;font-size:12px;text-align:center">无</div>';
  html+='</div>';
  html+='</div>';
  rankEl.innerHTML=html;
  ov.className='show';
}

function totalTroops(side) {
  let t = 0;
  for (let i=0;i<64;i++) if (side.board[i]) t += side.board[i].troops;
  return t;
}

function updateIncomeDisplay() {
  document.getElementById('pIncome').textContent = '+0/回合';
  document.getElementById('aIncome').textContent = '+0/回合';
}

function updateUI() {
  document.getElementById('playerTroops').textContent = (player.troops||0).toLocaleString();
  document.getElementById('aiTroops').textContent = (ai.troops||0).toLocaleString();
  document.getElementById('playerTotalTroops').textContent = totalTroops(player).toLocaleString();
  document.getElementById('aiTotalTroops').textContent = totalTroops(ai).toLocaleString();
  document.getElementById('drawPileCount').textContent = drawPileCount !== undefined ? drawPileCount : 0;
  document.getElementById('placementCount').textContent = `已放 ${placedThisTurn}/${PLACE_PER_ROUND}`;
  document.getElementById('roundDisplay').textContent = round;
  document.getElementById('pFlagScatter').textContent = `🚩溃散 ${flagScatterCount.player}/3`;
  document.getElementById('aFlagScatter').textContent = `🚩溃散 ${flagScatterCount.ai}/3`;
  updateCollectionGrid(); updateAiCollectionGrid(); updateSpectatorGrid(); updateIncomeDisplay();
}

function initFilters() {
  ['catFilters','aiCatFilters'].forEach(id => {
    const el = document.getElementById(id);
    el.innerHTML = '';
    const add = (label, cat) => {
      const btn = document.createElement('button');
      btn.className = 'cat-btn' + (cat==='all'?' active':'');
      btn.textContent = label;
      btn.addEventListener('click', ()=>{
        el.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        if (id==='catFilters') { playerCatFilter=cat; updateCollectionGrid(); }
        else { aiCatFilter=cat; updateAiCollectionGrid(); }
      });
      el.appendChild(btn);
    };
    add('全部','all');
    CAT_NAMES.forEach(n => add(n,n));
  });
}

function initSortBar() {
  document.querySelectorAll('.sort-btn').forEach(btn => {
    btn.addEventListener('click', ()=>{
      document.querySelectorAll('.sort-btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      playerSortBy = btn.dataset.sort;
      updateCollectionGrid();
    });
  });
}

// ==================== API ACTIONS ====================
async function drawPhase() {
  try {
    const data = await api.draw(gameId);
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('抽卡失败：' + e.message, 'lose');
  }
}

async function endPlacement() {
  if (gamePhase !== 'place_player') return;
  try {
    const data = await api.endTurn(gameId);
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('结束回合失败：' + e.message, 'lose');
  }
}

function toggleAutoPlay() {
  autoPlay = !autoPlay;
  if (autoPlay) {
    document.getElementById('btnAutoPlace').textContent = '⚡自动中';
    document.getElementById('btnAutoPlace').className = 'btn btn-small active';
    document.getElementById('btnDraw').disabled = true;
    document.getElementById('btnEndTurn').disabled = true;
    runAutoPlay();
  } else {
    document.getElementById('btnAutoPlace').textContent = '托管';
    document.getElementById('btnAutoPlace').className = 'btn btn-small';
    updateButtonStates();
  }
}

async function runAutoPlay() {
  if (!autoPlay) return;
  if (gamePhase === 'gameover') { toggleAutoPlay(); return; }
  try {
    let data;
    if (gamePhase === 'idle' || gamePhase === 'draw') {
      data = await api.draw(gameId);
    } else if (gamePhase === 'place_player') {
      data = await api.autoPlace(gameId);
      if (data.gamePhase === 'place_player' || data.game_phase === 'place_player') {
        data = await api.endTurn(gameId);
      }
    } else {
      setTimeout(runAutoPlay, 300);
      return;
    }
    applyStateFromServer(data);
    if (autoPlay && gamePhase !== 'gameover') setTimeout(runAutoPlay, 100);
  } catch (e) {
    addBattleLog('操作失败：' + e.message, 'lose');
    toggleAutoPlay();
  }
}

async function resetGame() {
  if (gameId) {
    try {
      const data = await api.resetGame(gameId);
      applyStateFromServer(data);
    } catch (e) {
      addBattleLog('重置失败：' + e.message, 'lose');
    }
  } else {
    const data = await api.newGame();
    gameId = data.game_id;
    applyStateFromServer(data);
  }
}

async function setTerrain(mode) {
  const names = { normal:'普通对战', tennozan:'天王山之战', nagashino:'长篠之战' };
  if (round > 0 || gamePhase !== 'idle') {
    if (!confirm(`切换${names[mode]}模式将重新开始游戏，确认？`)) return;
    try {
      const data = await api.setTerrain(gameId, mode);
      applyStateFromServer(data);
    } catch (e) {
      addBattleLog('地形切换失败：' + e.message, 'lose');
    }
    return;
  }
  terrainMode = mode;
  updateTerrainUI();
  renderBoardFull();
}

// ==================== INIT ====================
async function init() {
  initBoard();
  initSortBar();
  initFilters();
  try {
    const data = await api.newGame();
    gameId = data.game_id;
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('连接服务器失败：' + e.message, 'lose');
    setPhase('⚠ 无法连接服务器');
  }
}

init();
