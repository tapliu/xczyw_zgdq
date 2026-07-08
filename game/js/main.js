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
const RATING_COLORS = { 'S+':'#8b0000','S':'#e94560','A':'#8b4513','B':'#ffd700','C':'#2e8b57','D':'#1e90ff' };
const TYPE_COLORS = { '全能':'#f5a623','武将':'#e94560','文臣':'#3498db','特才':'#9b59b6' };
const MON_CRESTS = ['◈','◆','★','✿','❖','⚘','✧','❀','✦','♰'];
const CAT_NAMES = ['全能','武将','文臣','特才'];
const FACTION_COLORS = {
  '织田家':'#e94560','丰臣家':'#f5a623','德川家':'#4fc3f7','武田家':'#e91e63',
  '上杉家':'#2196f3','北条家':'#9c27b0','毛利家':'#ff5722','岛津家':'#4caf50',
  '伊达家':'#00bcd4','长宗我部家':'#8bc34a','龙造寺家':'#607d8b','大友家':'#795548',
  '斋藤家':'#795548','今川家':'#ff9800','浅井家':'#cddc39','朝仓家':'#bdbdbd',
  '本愿寺':'#9e9e9e','三好家':'#ffeb3b','尼子家':'#3f51b5','群雄':'#aaaaaa',
};
const FACTION_NAMES = Object.keys(FACTION_COLORS).sort();
const FACTION_ENEMIES = {
  '织田家': ['武田家', '上杉家', '毛利家', '今川家', '斋藤家', '浅井家', '朝仓家', '本愿寺'],
  '丰臣家': ['北条家', '长宗我部家'],
  '德川家': ['武田家'],
  '武田家': ['上杉家', '织田家'],
  '上杉家': ['武田家', '北条家', '织田家'],
  '北条家': ['上杉家', '织田家', '丰臣家'],
  '毛利家': ['织田家'],
  '岛津家': ['龙造寺家', '大友家'],
  '长宗我部家': ['织田家', '丰臣家'],
  '龙造寺家': ['岛津家', '大友家'],
  '大友家': ['岛津家', '龙造寺家'],
  '斋藤家': ['织田家'],
  '今川家': ['织田家'],
  '浅井家': ['织田家'],
  '朝仓家': ['织田家'],
  '本愿寺': ['织田家'],
  '群雄': [],
};

function getFactions(c) {
  return c.factions && c.factions.length ? c.factions : (c.faction ? [c.faction] : []);
}

function renderFactionBadges(factions, sep) {
  if (!factions || !factions.length) return '';
  return factions.map(f => `<span style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join(sep || '/');
}

function flagIcon(color) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18"><rect x="3" y="2" width="2.5" height="20" rx="1" fill="#888"/><polygon points="5.5,2 20,7 5.5,12" fill="${color}"/></svg>`;
}

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
let quickDrawMode = false;
let scatterDebuff = {}, deadList = [], flagScatterCount = { player: 0, ai: 0 };
let spectatorPool = [];
let pendingFlagPicks = 0;
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
    flagGenerals: obj.flag_generals || [],
    lockedFlagIds: obj.locked_flag_ids || [],
    currentFlagCharId: obj.current_flag_char_id ?? null,
  };
}

function applyStateFromServer(data) {
  const s = data.state || data;
  // Strip type multipliers for display (show original stats)
  function restoreOrig(arr) {
    if (!arr) return;
    arr.forEach(item => {
      const c = item?.char || item;
      if (c && c.orig_leadership !== undefined) {
        c.leadership = c.orig_leadership;
        c.martial = c.orig_martial;
        c.intelligence = c.orig_intelligence;
        c.politics = c.orig_politics;
      }
    });
  }
  if (s.player) { restoreOrig(s.player.board); restoreOrig(s.player.collection); player = normalizeSide(s.player); }
  if (s.ai) { restoreOrig(s.ai.board); restoreOrig(s.ai.collection); ai = normalizeSide(s.ai); }
  restoreOrig(s.spectator_pool);
  restoreOrig(s.dead_list);
  if (s.game_id) gameId = s.game_id;
  gamePhase = s.game_phase ?? s.gamePhase ?? gamePhase;
  if (s.round !== undefined) round = s.round;
  drawPileCount = s.draw_pile_count ?? s.drawPileCount ?? drawPileCount;
  placedThisTurn = s.placed_this_turn ?? s.placedThisTurn ?? placedThisTurn;
  playerCooldowns = s.player_cooldowns ?? s.playerCooldowns ?? playerCooldowns;
  aiCooldowns = s.ai_cooldowns ?? s.aiCooldowns ?? aiCooldowns;
  scatterDebuff = s.scatter_debuff ?? s.scatterDebuff ?? scatterDebuff;
  if (s.dead_list ?? s.deadList) deadList = s.dead_list ?? s.deadList;
  flagScatterCount = s.flag_scatter_count ?? s.flagScatterCount ?? flagScatterCount;
  if (s.spectator_pool ?? s.spectatorPool) spectatorPool = s.spectator_pool ?? s.spectatorPool;
  if (s.pending_flag_picks !== undefined) pendingFlagPicks = s.pending_flag_picks;
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
  if (gamePhase === 'gameover') {
    setTimeout(() => showVictory(s.winner), 500);
    if (autoPlay) toggleAutoPlay();
    MusicManager.play(s.winner ? 'victory' : 'defeat');
  } else if (gamePhase === 'draw' || gamePhase === 'pick_card') {
    MusicManager.play('draw');
  } else if (gamePhase === 'place_ai') {
    MusicManager.play('battle');
  } else if (gamePhase === 'idle' || gamePhase === 'place_player') {
    MusicManager.play('place');
  }
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
  // Use webp portrait when available
  const pid = char.avatarId || char.id;
  if (pid >= 1 && pid <= 100 || pid >= 501 && pid <= 520) {
    avatarCache[key] = 'portraits/' + pid + '.webp';
    return avatarCache[key];
  }
  // Fallback: canvas-generated avatar
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
        if (pFlag||aFlag) cell.classList.add('flag-cell');
        const pPower = Math.round(calcPower(i, true)), aPower2 = Math.round(calcPower(i, false));
        const pfBadges = getFactions(pu.char).map(f => `<span class="bu-faction-badge player-faction" style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('');
        const afBadges = getFactions(au.char).map(f => `<span class="bu-faction-badge ai-faction" style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('');
        cell.innerHTML = `${pfBadges}${afBadges}<div class="both-units"><span class="bu-player">▲${generateAvatar(pu.char,18)}<span class="bu-name">${pu.char.name}</span><span class="bu-troops">${pu.troops.toLocaleString()}</span>${pFlag?flagIcon('#ffd700'):''}</span><span class="bu-vs">⚔</span><span class="bu-ai">${aFlag?flagIcon('#4caf50'):''}${generateAvatar(au.char,18)}<span class="bu-name">${au.char.name}</span><span class="bu-troops">${au.troops.toLocaleString()}</span>▼</span></div>`;
      } else {
        const isFlag = (isPlayer && player.flagIdx === i) || (!isPlayer && ai.flagIdx === i);
        if (isFlag) cell.classList.add('flag-cell');
        const flagIconSvg = isFlag ? `<span class="u-flag-abs">${flagIcon(isPlayer ? '#ffd700' : '#4caf50')}</span>` : '';
        const dirIcon = isPlayer ? '▲' : '▼';
        const power = Math.round(calcPower(i, isPlayer));
        const fBadges = getFactions(u.char).map(f => `<span class="u-faction-badge" style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('');
        cell.innerHTML = `${fBadges}${flagIconSvg}<img class="u-avatar" src="${generateAvatar(u.char,24)}" alt="">
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

function isHostileFaction(fa, fb) {
  if (!fa || !fb || fa === fb) return false;
  const enemies = FACTION_ENEMIES[fa];
  return enemies ? enemies.includes(fb) : false;
}

function calcPower(index, isPlayer) {
  const myBoard = isPlayer ? player.board : ai.board;
  const enBoard = isPlayer ? ai.board : player.board;
  const side = isPlayer ? player : ai;
  const u = myBoard[index];
  if (!u) return 0;
  const flagMul = isFlagUnit(index, isPlayer) ? 1.1 : 1;
  let power = u.char.martial * 2 * flagMul;
  power *= (1 + u.troops / 30000);
  let factionBonus = 1.0;
  const uFactions = getFactions(u.char);
  const hasQunxiong = uFactions.includes('群雄');
  getNeighborIndices(index).forEach(ni => {
    const nu = myBoard[ni];
    if (nu) {
      power += nu.char.leadership * 0.05;
      const nf = nu.char.faction || '';
      if (nf && uFactions.includes(nf)) factionBonus += hasQunxiong ? 0.03 : 0.05;
    }
    const eu = enBoard[ni];
    if (eu) {
      const ef = eu.char.faction || '';
      if (ef && uFactions.some(uf => isHostileFaction(uf, ef))) factionBonus -= 0.05;
    }
  });
  power += u.char.leadership * flagMul * 0.05;
  for (let ei=0;ei<64;ei++) {
    const eu = enBoard[ei];
    if (!eu) continue;
    const cone = getConeIndices(ei, !isPlayer);
    if (cone.indexOf(index) >= 0) power -= eu.char.intelligence * 0.03;
  }
  power *= factionBonus;
  const isLord = u.char.lord_name === u.char.name;
  if (isLord && !hasQunxiong) {
    let count = 0;
    for (let i=0;i<64;i++) {
      const fu = myBoard[i];
      if (fu && fu !== u && uFactions.includes(fu.char.faction)) count++;
    }
    power *= (1 + count * 0.05);
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
        <div class="dmeta">${char.type||''} · ${char.rating||''}${char.identity?' · '+char.identity:''}${getFactions(char).length ? ' · ' + renderFactionBadges(getFactions(char)) : ''}${char.lord_name === char.name ? ' · 👑 主公' : ''} · 战力 ${power}</div>${getFactions(char).length ? `<div class="d-faction">${renderFactionBadges(getFactions(char), ' ')}</div>` : ''}
        ${char.note ? `<div class="dnote">${escHtml(char.note)}</div>` : ''}
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
  const dead = isDead(char.id);
  const onCooldown = isOnCooldown(char.id, true) || isOnCooldown(char.id, false);
  const isFlagGen = player.flagGenerals.some(fg => fg.id === char.id);
  const isLocked = player.lockedFlagIds.includes(char.id);
  const isCurrentFlag = player.currentFlagCharId === char.id;
  let status = onBoard ? '已上场' : dead ? '已战死' : onAi ? '敌方已上场' : onCooldown ? '冷却中' : '未上场';
  if (isLocked) status = '🔒 旗本已锁定';
  else if (isFlagGen && isCurrentFlag) status = '🚩 旗本（当前旗手）';
  else if (isFlagGen && !onBoard) status = '🚩 旗本候选';
  panel.innerHTML = `
    <div class="d-top">
      <img class="d-avatar" src="${generateAvatar(char,44)}" alt="">
      <div class="d-info">
        <div class="dname" style="color:${rc}">${isFlagGen ? '🚩 ' : ''}${char.name}</div>
        <div class="dmeta">${char.type||''} · ${char.rating||''}${char.identity?' · '+char.identity:''}${getFactions(char).length ? ' · ' + renderFactionBadges(getFactions(char)) : ''} · ${status}</div>${getFactions(char).length ? `<div class="d-faction">${renderFactionBadges(getFactions(char), ' ')}</div>` : ''}
        ${char.note ? `<div class="dnote">${escHtml(char.note)}</div>` : ''}
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

function miniAttrBars(c) {
  const attrs = [
    {l:'统',v:c.leadership,c:'#e94560'},
    {l:'武',v:c.martial,c:'#f5a623'},
    {l:'智',v:c.intelligence,c:'#2ecc71'},
    {l:'政',v:c.politics,c:'#3498db'},
  ];
  return attrs.map(a => `<div class="attr-row"><span class="alabel">${a.l}</span><span class="abar" style="width:${a.v}%;background:${a.c}"></span></div>`).join('');
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
  const isFlagGen = player.flagGenerals.some(fg => fg.id === pendingChar.id);
  if (isFlagGen && player.lockedFlagIds.includes(pendingChar.id)) {
    addBattleLog('该旗本已被锁定，无法上场！','lose'); cancelPlace(); return;
  }
  if (isFlagGen && player.currentFlagCharId !== null && player.currentFlagCharId !== pendingChar.id) {
    addBattleLog('已有旗本在场上，只能同时放置一名旗本！','lose'); cancelPlace(); return;
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
  const hasActiveFlagOnBoard = player.currentFlagCharId !== null && player.board.some(u => u && u.char.id === player.currentFlagCharId);

  const isFlagGen = c => player.flagGenerals.some(fg => fg.id === c.id);

  filtered.sort((a,b) => {
    const aDead=isDead(a.id), bDead=isDead(b.id);
    const aCd=isOnCooldown(a.id,true), bCd=isOnCooldown(b.id,true);
    const aOn=player.board.some(u=>u&&u.char.id===a.id)||ai.board.some(u=>u&&u.char.id===a.id);
    const bOn=player.board.some(u=>u&&u.char.id===b.id)||ai.board.some(u=>u&&u.char.id===b.id);
    const aLocked=player.lockedFlagIds.includes(a.id);
    const bLocked=player.lockedFlagIds.includes(b.id);
    const aFg=isFlagGen(a);
    const bFg=isFlagGen(b);
    const aWait=aFg && !aLocked && !(aOn && player.currentFlagCharId===a.id) && hasActiveFlagOnBoard;
    const bWait=bFg && !bLocked && !(bOn && player.currentFlagCharId===b.id) && hasActiveFlagOnBoard;
    const aG=aLocked?5:(aDead?4:(aWait?3:(aCd?2:(aOn?1:0))));
    const bG=bLocked?5:(bDead?4:(bWait?3:(bCd?2:(bOn?1:0))));
    if (aG!==bG) return aG-bG;
    // Flag generals before regulars in same group
    if (aFg !== bFg) return aFg ? -1 : 1;
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
    const isFlagGen = player.flagGenerals.some(fg => fg.id === c.id);
    const isLocked = player.lockedFlagIds.includes(c.id);
    const cTotal = c.leadership + c.martial + c.intelligence + c.politics;
    const isCurrentFlag = player.currentFlagCharId === c.id && onBoard;
    const isOtherFlagWaiting = isFlagGen && !isLocked && !isCurrentFlag && hasActiveFlagOnBoard;
    div.className = 'char-card';
    if (isLocked) div.classList.add('locked-flag');
    else if (dead) div.classList.add('dead');
    else if (onBoard||onAi) div.classList.add('used');
    else if (isOtherFlagWaiting) div.classList.add('cooldown');
    else if (onCooldown) div.classList.add('cooldown');
    if (isFlagGen && !isLocked && !isOtherFlagWaiting) div.classList.add('flag-gen');
    if (selectedChar&&selectedChar.id===c.id) div.classList.add('selected');
    const showAttr = playerSortBy !== 'default' ? `<div class="cattr">${c[playerSortBy]}</div>` : '';
    const flagBadge = isLocked ? '<div class="freeze-badge" style="background:rgba(100,0,0,0.7);color:#ef5350">🔒 已锁定</div>'
      : isCurrentFlag ? '<div class="freeze-badge" style="background:rgba(0,100,0,0.7);color:#4caf50">🚩 旗手中</div>'
      : isOtherFlagWaiting ? '<div class="freeze-badge" style="background:rgba(80,80,80,0.7);color:#999">⏳ 旗本在场</div>'
      : isFlagGen ? '<div class="freeze-badge" style="background:rgba(100,50,0,0.7);color:#f5a623">🚩 旗本</div>'
      : '';
    const factionTag = getFactions(c).map(f => `<span class="c-faction" style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('');
    div.innerHTML = `<img class="cc-avatar" src="${generateAvatar(c,38)}"><div class="cname">${isFlagGen ? '🚩 ' : ''}${c.name}</div>${factionTag ? `<div class="cmeta">${factionTag}</div>` : ''}<div class="cmeta">${c.type||''} · ${c.rating||''}${c.identity?' · '+c.identity:''}</div>${miniAttrBars(c)}<div class="cattr">${cTotal}</div>${flagBadge}${dead ? '<div class="dead-badge">死</div>' : onCooldown ? `<div class="freeze-badge ${cdRemaining.type==='scatter'?'scatter':''}">${cdRemaining.type==='scatter'?'溃':'❄'}${freezeRemaining}</div>` : ''}${showAttr}</div>`;
    div.addEventListener('click', ()=>{
      showCharDetail(c, onBoard, onAi || onCooldown || dead || isLocked || isOtherFlagWaiting);
      if (onBoard||onAi||onCooldown||dead||isLocked||isOtherFlagWaiting) return;
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
  const isAiFlagGen = c => ai.flagGenerals.some(fg => fg.id === c.id);

  filtered.sort((a,b) => {
    const aDead=isDead(a.id), bDead=isDead(b.id);
    const aCd=isOnCooldown(a.id,false), bCd=isOnCooldown(b.id,false);
    const aOn=ai.board.some(u=>u&&u.char.id===a.id)||player.board.some(u=>u&&u.char.id===a.id);
    const bOn=ai.board.some(u=>u&&u.char.id===b.id)||player.board.some(u=>u&&u.char.id===b.id);
    const aFg=isAiFlagGen(a), bFg=isAiFlagGen(b);
    const aGrp=aDead?3:(aCd?2:(aOn?1:0));
    const bGrp=bDead?3:(bCd?2:(bOn?1:0));
    if (aGrp!==bGrp) return aGrp-bGrp;
    if (aFg !== bFg) return aFg ? -1 : 1;
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
    const isFlagGen = isAiFlagGen(c);
    const isLocked = ai.lockedFlagIds.includes(c.id);
    const isCurrentFlag = ai.currentFlagCharId === c.id && onBoard;
    const cTotal = c.leadership + c.martial + c.intelligence + c.politics;
    const div = document.createElement('div');
    div.className = 'char-card';
    if (isLocked) div.classList.add('locked-flag');
    else if (dead) div.classList.add('dead');
    else if (onBoard) div.classList.add('used');
    else if (onCooldown) div.classList.add('cooldown');
    if (isFlagGen && !isLocked) div.classList.add('flag-gen');
    const flagBadge = isLocked ? '<div class="freeze-badge" style="background:rgba(100,0,0,0.7);color:#ef5350">🔒</div>'
      : isCurrentFlag ? '<div class="freeze-badge" style="background:rgba(0,100,0,0.7);color:#4caf50">🚩</div>'
      : isFlagGen ? '<div class="freeze-badge" style="background:rgba(100,50,0,0.7);color:#f5a623">🚩</div>'
      : '';
    const factionTag = getFactions(c).map(f => `<span class="c-faction" style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('');
    div.innerHTML = `<img class="cc-avatar" src="${generateAvatar(c,38)}"><div class="cname">${isFlagGen ? '🚩 ' : ''}${c.name}</div>${factionTag ? `<div class="cmeta">${factionTag}</div>` : ''}<div class="cmeta">${c.type||''} · ${c.rating||''}${c.identity?' · '+c.identity:''}</div>${miniAttrBars(c)}<div class="cattr">${cTotal}</div>${flagBadge}${dead ? '<div class="dead-badge">死</div>' : onCooldown ? `<div class="freeze-badge ${cdRemaining.type==='scatter'?'scatter':''}">${cdRemaining.type==='scatter'?'溃':'❄'}${freezeRemaining}</div>` : ''}`;
    div.addEventListener('click', ()=> showCharDetail(c, onBoard, false));
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
    const cTotal = c.leadership + c.martial + c.intelligence + c.politics;
    const fTag = getFactions(c).map(f => `<span style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('/');
    let html = `<img class="cc-avatar" src="${generateAvatar(c,38)}"><div class="cname">${c.name}</div>${fTag ? `<div class="cmeta">${fTag}</div>` : ''}<div class="cmeta">${c.type||''} · ${c.rating||''}${c.identity?' · '+c.identity:''}</div>${miniAttrBars(c)}<div class="cattr">${cTotal}</div>`;
    if (canRecruit) { html += '<div style="font-size:9px;color:#4caf50;text-align:center;cursor:pointer">招募</div>'; }
    div.innerHTML = html;
    div.addEventListener('click', (e) => {
      if (canRecruit && e.target && e.target.textContent === '招募') {
        recruitFromSpectator(c.id, true);
      } else {
        showCharDetail(c, false, false);
      }
    });
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
const MAX_LOG = 200;
function addBattleLog(msg, type='info') {
  const el = document.getElementById('battleLog');
  const div = document.createElement('div');
  div.className = 'entry ' + type;
  div.textContent = msg;
  el.appendChild(div);
  while (el.children.length > MAX_LOG) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

// ==================== UI ====================
function setPhase(msg) { document.getElementById('phaseBanner').innerHTML = msg; }

function toggleRankExpand(id) {
  const items = document.querySelectorAll(`[data-expand="${id}"]`);
  const btn = document.querySelector(`[data-expand-btn="${id}"]`);
  if (!btn) return;
  const isExpanded = btn.classList.toggle('expanded');
  items.forEach(el => el.classList.toggle('v-rank-entry-hidden', !isExpanded));
  btn.textContent = isExpanded ? '收起 ▴' : '展开 ▾';
}

function showVictory(win) {
  const ov=document.getElementById('victoryOverlay');
  document.getElementById('vIcon').textContent=win?'🏆':'💀';
  document.getElementById('vTitle').textContent=win?'胜利！':'战败...';
  document.getElementById('vTitle').className='v-title '+(win?'win':'lose');
  document.getElementById('vSub').textContent=win?'敌阵已被突破，天下尽在掌中！':'防线崩溃...来日再战！';
  document.getElementById('vIcon').style.animation='vBounce 1s ease-out';
  const mvpEl=document.getElementById('mvpDisplay');
  const side=win?player:ai;

  // Aggregate combat stats by char.id (unifies damage across retreat/re-deploy)
  const charAgg = {};
  for (const uid in combatStats) {
    const ch = uidCharMap[uid];
    if (!ch) continue;
    const cid = ch.id;
    if (!charAgg[cid]) charAgg[cid] = { char: ch, side: uidSideMap[uid] || 'player', damage: 0, meleeDmg: 0, rangedDmg: 0, meleeHits: 0, rangedHits: 0, kills: 0, retreatTriggers: 0, damage_to: {}, damage_from: {} };
    const s = combatStats[uid];
    charAgg[cid].damage += s.damage || 0;
    charAgg[cid].meleeDmg += s.meleeDmg || 0;
    charAgg[cid].rangedDmg += s.rangedDmg || 0;
    charAgg[cid].meleeHits += s.meleeHits || 0;
    charAgg[cid].rangedHits += s.rangedHits || 0;
    charAgg[cid].kills += s.kills || 0;
    charAgg[cid].retreatTriggers += s.retreatTriggers || 0;
    for (const [tuid, d] of Object.entries(s.damage_to || {})) {
      const tch = uidCharMap[tuid];
      if (tch) charAgg[cid].damage_to[tch.id] = (charAgg[cid].damage_to[tch.id] || 0) + d;
    }
    for (const [suid, d] of Object.entries(s.damage_from || {})) {
      const sch = uidCharMap[suid];
      if (sch) charAgg[cid].damage_from[sch.id] = (charAgg[cid].damage_from[sch.id] || 0) + d;
    }
  }

  // Find MVP: character with most total damage that is still on the board
  let bestCid = null, bestDmg = -1;
  for (const cid in charAgg) {
    const isOnBoard = side.board.some(u => u && u.char.id == cid);
    if (isOnBoard && charAgg[cid].damage > bestDmg) { bestDmg = charAgg[cid].damage; bestCid = cid; }
  }
  const bestChar = bestCid ? charAgg[bestCid].char : null;

  if (bestChar) {
    const agg = charAgg[bestCid];
    const avgMelee = agg.meleeHits > 0 ? Math.round(agg.meleeDmg / agg.meleeHits) : 0;
    const avgRanged = agg.rangedHits > 0 ? Math.round(agg.rangedDmg / agg.rangedHits) : 0;
    mvpEl.style.display = 'block';
    mvpEl.innerHTML = `<div class="v-mvp"><div class="v-mvp-title">🏅 MVP — ${bestChar.name}</div><div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><img class="v-mvp-avatar" src="${generateAvatar(bestChar,56)}"><div><div class="v-mvp-name">${bestChar.name}</div><div class="v-mvp-meta">${renderFactionBadges(getFactions(bestChar))} · ${bestChar.type||''} · ${bestChar.rating||''} · 统${bestChar.leadership} 武${bestChar.martial} 智${bestChar.intelligence} 政${bestChar.politics}</div></div></div><div class="v-mvp-sub-title">⚔ 造成伤害</div><div class="v-mvp-row"><span class="lab">总伤害</span><span class="val">${agg.damage.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">近战总伤</span><span class="val">${agg.meleeDmg.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">近战</span><span class="val">${agg.meleeHits}次 · 均伤 ${avgMelee.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">远程总伤</span><span class="val">${agg.rangedDmg.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">远程</span><span class="val">${agg.rangedHits}次 · 均伤 ${avgRanged.toLocaleString()}</span></div><div class="v-mvp-row"><span class="lab">击溃/击毙</span><span class="val">${agg.kills}人</span></div><div class="v-mvp-row"><span class="lab">大威风</span><span class="val">${agg.retreatTriggers}次</span></div></div>`;
  } else {
    mvpEl.style.display = 'none';
  }

  const rankEl = document.getElementById('rankDisplay');
  const allStats = Object.values(charAgg);
  const sideLabel = s => s === 'player' ? '<span class="v-rank-side p">己</span>' : '<span class="v-rank-side a">敌</span>';

  function expandableSection(title, allItems, expandId, renderItem) {
    if (!allItems.length) return `<div class="v-rank-section"><div class="v-rank-title">${title}</div><div style="color:#666;font-size:12px;text-align:center">无</div></div>`;
    const top3 = allItems.slice(0, 3);
    const rest = allItems.slice(3);
    let html = `<div class="v-rank-section"><div class="v-rank-title"><span>${title}</span>`;
    if (rest.length) html += `<span class="v-expand-btn" data-expand-btn="${expandId}" onclick="toggleRankExpand('${expandId}')">展开 ▾</span>`;
    html += `</div>`;
    top3.forEach((item, i) => html += renderItem(item, i + 1, false));
    rest.forEach((item, i) => html += renderItem(item, i + 4, true, expandId));
    html += `</div>`;
    return html;
  }

  // Top row: MVP dealt/received (aggregated by char.id)
  let topHtml = '<div class="v-rank-grid v-top-grid">';
  if (bestCid) {
    const agg = charAgg[bestCid];
    const dealtAll = Object.entries(agg.damage_to).map(([cid, dmg]) => ({ char: charAgg[cid]?.char, damage: dmg })).filter(e => e.char).sort((a, b) => b.damage - a.damage);
    const receivedAll = Object.entries(agg.damage_from).map(([cid, dmg]) => ({ char: charAgg[cid]?.char, damage: dmg })).filter(e => e.char).sort((a, b) => b.damage - a.damage);
    topHtml += expandableSection('🗡 MVP造成伤害', dealtAll, 'mvpDealt', (item, rank, hidden, eid) =>
      `<div class="v-rank-entry${hidden ? ' v-rank-entry-hidden' : ''}"${hidden ? ` data-expand="${eid}"` : ''}><span class="v-rank-num">${rank}</span><img class="v-rank-avatar" src="${generateAvatar(item.char,32)}"><span class="v-rank-name">${item.char.name}</span><span class="v-rank-val">${item.damage.toLocaleString()}</span></div>`
    );
    topHtml += expandableSection('🛡 对MVP造成伤害', receivedAll, 'mvpRecv', (item, rank, hidden, eid) =>
      `<div class="v-rank-entry${hidden ? ' v-rank-entry-hidden' : ''}"${hidden ? ` data-expand="${eid}"` : ''}><span class="v-rank-num">${rank}</span><img class="v-rank-avatar" src="${generateAvatar(item.char,32)}"><span class="v-rank-name">${item.char.name}</span><span class="v-rank-val">${item.damage.toLocaleString()}</span></div>`
    );
  }
  topHtml += '</div>';

  // Bottom row: general rankings (3 columns)
  const allKills = allStats.filter(i => i.kills > 0).sort((a, b) => b.kills - a.kills);
  const allMelee = allStats.filter(i => i.meleeDmg > 0).sort((a, b) => b.meleeDmg - a.meleeDmg);
  const allRanged = allStats.filter(i => i.rangedDmg > 0).sort((a, b) => b.rangedDmg - a.rangedDmg);
  let bottomHtml = '<div class="v-rank-grid v-bottom-grid">';
  const entryContent = (item, rank, valLabel, valKey) => {
    const v = valKey ? item[valKey] : item;
    const hits = valKey === 'meleeDmg' ? item.meleeHits : valKey === 'rangedDmg' ? item.rangedHits : 0;
    const avg = hits > 0 ? (v / hits).toFixed(1) : '';
    return `<span class="v-rank-num">${rank}</span><img class="v-rank-avatar" src="${generateAvatar(item.char,32)}"><span class="v-rank-name">${item.char.name}</span>${sideLabel(item.side)}<span class="v-rank-val">${typeof v === 'number' ? v.toLocaleString() : v}${valLabel}</span>${avg ? `<div class="v-rank-hits">均伤 ${avg}</div>` : ''}`;
  };
  bottomHtml += expandableSection('⚔ 击溃/击毙', allKills, 'kills', (item, rank, hidden, eid) =>
    `<div class="v-rank-entry${hidden ? ' v-rank-entry-hidden' : ''}"${hidden ? ` data-expand="${eid}"` : ''}>${entryContent(item, rank, '人', 'kills')}</div>`
  );
  bottomHtml += expandableSection('🗡 近战伤害', allMelee, 'melee', (item, rank, hidden, eid) =>
    `<div class="v-rank-entry${hidden ? ' v-rank-entry-hidden' : ''}"${hidden ? ` data-expand="${eid}"` : ''}>${entryContent(item, rank, '', 'meleeDmg')}</div>`
  );
  bottomHtml += expandableSection('🏹 远程伤害', allRanged, 'ranged', (item, rank, hidden, eid) =>
    `<div class="v-rank-entry${hidden ? ' v-rank-entry-hidden' : ''}"${hidden ? ` data-expand="${eid}"` : ''}>${entryContent(item, rank, '', 'rangedDmg')}</div>`
  );
  bottomHtml += '</div>';

  rankEl.innerHTML = topHtml + bottomHtml;
  ov.className = 'show';
}

function totalTroops(side) {
  let t = 0;
  for (let i=0;i<64;i++) if (side.board[i]) t += side.board[i].troops;
  return t;
}

function updateIncomeDisplay() {
  const calc = (side) => {
    const boardT = side.board.reduce((s, u) => s + (u ? u.troops : 0), 0);
    let inc = Math.floor(TROOP_INCOME * Math.max(0, 1 - boardT / MAX_TOTAL_TROOPS));
    const sumPol = side.board.reduce((s, u) => s + (u ? (u.char.politics || 0) : 0), 0);
    const mult = Math.max(0.2, Math.min(2.0, sumPol * 0.001));
    inc = Math.floor(inc * mult);
    const maxAdd = MAX_TOTAL_TROOPS - boardT - (side.troops || 0);
    return Math.max(0, Math.min(inc, maxAdd));
  };
  document.getElementById('pIncome').textContent = `+${calc(player)}/回合`;
  document.getElementById('aIncome').textContent = `+${calc(ai)}/回合`;
}

function updateUI() {
  document.getElementById('playerTroops').textContent = (player.troops||0).toLocaleString();
  document.getElementById('aiTroops').textContent = (ai.troops||0).toLocaleString();
  document.getElementById('playerTotalTroops').textContent = totalTroops(player).toLocaleString();
  document.getElementById('aiTotalTroops').textContent = totalTroops(ai).toLocaleString();
  document.getElementById('drawPileCount').textContent = drawPileCount !== undefined ? drawPileCount : 0;
  document.getElementById('placementCount').textContent = `已放 ${placedThisTurn}/${PLACE_PER_ROUND}`;
  document.getElementById('roundDisplay').textContent = round;
  document.getElementById('pFlagScatter').textContent = `🏴溃散 ${flagScatterCount.player}/3`;
  document.getElementById('aFlagScatter').textContent = `🏴溃散 ${flagScatterCount.ai}/3`;
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
    const data = await api.drawOptions(gameId);
    applyStateFromServer(data.state);
    if (data.options && data.options.length) {
      // Restore original display stats
      data.options.forEach(c => {
        if (c.orig_leadership !== undefined) {
          c.leadership = c.orig_leadership; c.martial = c.orig_martial;
          c.intelligence = c.orig_intelligence; c.politics = c.orig_politics;
        }
      });
      showPickModal(data.options);
      if (pendingFlagPicks > 0) {
        setPhase(`🎴 选择旗本武将（${pendingFlagPicks}名剩余）`);
      }
      if (quickDrawMode) {
        setTimeout(() => {
          autoPickCard();
          if (gamePhase !== 'pick_card') quickDrawMode = false;
        }, 60);
      }
    }
  } catch (e) {
    addBattleLog('抽卡失败：' + e.message, 'lose');
    quickDrawMode = false;
  }
}

function quickDrawPhase() {
  quickDrawMode = true;
  document.getElementById('pickAutoBtn').disabled = true;
  document.getElementById('pickQuickBtn').disabled = true;
  if (gamePhase === 'pick_card') {
    autoPickCard();
  } else {
    drawPhase();
  }
}

function showPickModal(options) {
  const grid = document.getElementById('pickGrid');
  const isFlagPick = pendingFlagPicks > 0;
  const title = document.querySelector('#pickModal h2');
  if (title) title.textContent = isFlagPick ? `选择旗本武将（剩余${pendingFlagPicks}名）` : '选择武将牌';
  grid.innerHTML = '';
  options.forEach(c => {
    const div = document.createElement('div');
    div.className = 'pick-card';
    const ratingColor = RATING_COLORS[c.rating] || '#aaa';
    const typeColor = TYPE_COLORS[c.type] || '#aaa';
    const total = c.leadership + c.martial + c.intelligence + c.politics;
    const factionClr = FACTION_COLORS[c.faction] || '#888';
    const factionPickTags = getFactions(c).map(f => `<span style="font-size:9px;color:${FACTION_COLORS[f]||'#888'};background:rgba(0,0,0,.4);padding:0 4px;border-radius:3px">${f}</span>`).join(' ');
    div.innerHTML = `
      <img class="pc-avatar" src="${generateAvatar(c, 70)}" alt="${c.name}">
      <div class="pc-name">${c.name} ${factionPickTags}</div>
      <div class="pc-type" style="color:${typeColor}">${c.type}</div>
      <div class="pc-rating" style="color:${ratingColor}">${c.rating}</div>
      ${c.identity ? `<div class="pc-identity" style="font-size:9px;color:#f5a623;margin-top:1px">${c.identity}</div>` : ''}
      <div class="pc-stats">统${c.leadership} 武${c.martial} 智${c.intelligence} 政${c.politics}</div>
      <div class="pc-attr-bar"><span class="pc-attr-l">统</span><span class="pc-attr-f" style="width:${c.leadership}%"></span></div>
      <div class="pc-attr-bar"><span class="pc-attr-l">武</span><span class="pc-attr-f" style="width:${c.martial}%;background:#f5a623"></span></div>
      <div class="pc-attr-bar"><span class="pc-attr-l">智</span><span class="pc-attr-f" style="width:${c.intelligence}%;background:#2ecc71"></span></div>
      <div class="pc-attr-bar"><span class="pc-attr-l">政</span><span class="pc-attr-f" style="width:${c.politics}%;background:#3498db"></span></div>
      <div class="pc-total">总分 ${total}</div>
      ${isFlagPick ? '<div style="font-size:10px;color:#f5a623;margin-top:4px">🚩 旗本候选</div>' : ''}
    `;
    div.addEventListener('click', () => pickCard(c.id));
    grid.appendChild(div);
  });
  document.getElementById('pickModal').classList.add('show');
}

async function pickCard(charId) {
  try {
    const data = await api.pickCard(gameId, charId);
    document.getElementById('pickModal').classList.remove('show');
    applyStateFromServer(data.state);
    if (gamePhase === 'pick_card') {
      drawPhase();
    } else {
      quickDrawMode = false;
      const qb = document.getElementById('pickQuickBtn');
      if (qb) qb.disabled = false;
      const ab = document.getElementById('pickAutoBtn');
      if (ab) ab.disabled = false;
    }
  } catch (e) {
    addBattleLog('选卡失败：' + e.message, 'lose');
    quickDrawMode = false;
    const qb = document.getElementById('pickQuickBtn');
    if (qb) qb.disabled = false;
    const ab = document.getElementById('pickAutoBtn');
    if (ab) ab.disabled = false;
  }
}

function autoPickCard() {
  const grid = document.getElementById('pickGrid');
  const cards = grid.querySelectorAll('.pick-card');
  if (!cards.length) return;
  // Gather current options from the DOM data
  let options = [];
  cards.forEach(el => {
    const name = el.querySelector('.pc-name')?.textContent || '';
    const totalText = el.querySelector('.pc-total')?.textContent || '';
    const total = parseInt(totalText.replace('总分 ', '')) || 0;
    const type = el.querySelector('.pc-type')?.textContent || '';
    options.push({el, name, total, type});
  });
  // Pick best: highest total, tiebreak by type 全能, else random
  const maxTotal = Math.max(...options.map(o => o.total));
  let best = options.filter(o => o.total === maxTotal);
  const quanNeng = best.filter(o => o.type === '全能');
  if (quanNeng.length > 0) {
    best = quanNeng;
  }
  const picked = best.length === 1 ? best[0] : best[Math.floor(Math.random() * best.length)];
  picked.el.click();
}

async function endPlacement() {
  if (gamePhase !== 'place_player') return;
  MusicManager.play('battle');
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
    if (gamePhase === 'idle' || gamePhase === 'draw' || gamePhase === 'pick_card') {
      const data = await api.drawOptions(gameId);
      applyStateFromServer(data.state);
      if (data.options && data.options.length) {
        const pickData = await api.pickCard(gameId, data.options[0].id);
        applyStateFromServer(pickData.state);
      }
    } else if (gamePhase === 'place_player') {
      let data = await api.autoPlace(gameId);
      applyStateFromServer(data.state || data);
      data = data.state || data;
      if (data.game_phase === 'place_player' || data.gamePhase === 'place_player') {
        MusicManager.play('battle');
        data = await api.endTurn(gameId);
        applyStateFromServer(data.state || data);
      }
    } else {
      setTimeout(runAutoPlay, 300);
      return;
    }
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

async function restartGame() {
  if (!confirm('确定要重新开始吗？当前对局数据将被清空。')) return;
  clearGameState();
  try {
    const data = await api.newGame();
    gameId = data.game_id;
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('重新开始失败：' + e.message, 'lose');
  }
}

function clearGameState() {
  document.getElementById('battleLog').innerHTML = '';
  if (autoPlay) toggleAutoPlay();
}

function backToMenu() {
  if (round > 0 || (gamePhase !== 'idle' && gamePhase !== 'gameover')) {
    if (!confirm('确定要返回主菜单吗？本局对战数据将丢失。')) return;
  }
  if (autoPlay) toggleAutoPlay();
  document.getElementById('mainMenu').style.display = 'flex';
  document.getElementById('gameHeader').style.display = 'none';
  document.getElementById('gameContent').style.display = 'none';
  MusicManager.play('menu');
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

// ==================== MAIN MENU ====================
function menuPlaceholder(name) {
  if (name === '游戏设置') { openSettings(); return; }
  addBattleLog(`「${name}」功能开发中，敬请期待`, 'info');
}

function quitGame() {
  if (confirm('确定要退出游戏吗？')) {
    try { window.close(); } catch(e) {}
    document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;color:#888;font-size:18px">窗口即将关闭...</div>';
  }
}

function openEditor() {
  document.getElementById('menuButtons').style.display = 'none';
  document.getElementById('editorButtons').style.display = 'flex';
}

function closeEditor() {
  document.getElementById('editorButtons').style.display = 'none';
  document.getElementById('menuButtons').style.display = 'flex';
}

function editorPlaceholder(name) {
  addBattleLog(`「${name}」功能开发中，敬请期待`, 'info');
  alert(`「${name}」功能开发中，敬请期待`);
}

// ==================== CHARACTER EDITOR ====================
let editorChars = [];
let editorOriginals = [];
let editorFactionMap = {};

async function openCharEditor() {
  openEditor(); // switch to editor submenu
  document.getElementById('mainMenu').style.display = 'none';
  const ov = document.getElementById('editorOverlay');
  ov.classList.add('show');
  const grid = document.getElementById('editorGrid');
  grid.innerHTML = '<div style="color:#888;padding:40px;text-align:center">加载武将数据中...</div>';
  try {
    const [charRes, factionRes] = await Promise.all([
      fetch('characters.json'),
      fetch('/api/factions/map'),
    ]);
    const data = await charRes.json();
    const factionData = await factionRes.json();
    editorFactionMap = factionData.factions || {};
    editorOriginals = data.map(c => JSON.parse(JSON.stringify(c)));
    editorChars = data.map(c => JSON.parse(JSON.stringify(c)));
    recalcRatings(editorOriginals);
    recalcRatings(editorChars);
    renderEditorGrid();
  } catch (e) {
    grid.innerHTML = `<div style="color:#e94560;padding:40px;text-align:center">加载失败: ${e.message}</div>`;
  }
}

function closeCharEditor() {
  document.getElementById('editorOverlay').classList.remove('show');
  document.getElementById('mainMenu').style.display = 'flex';
  // Restore original editor header
  const hdr = document.querySelector('#editorOverlay .editor-hdr');
  if (hdr) hdr.innerHTML = `<h2>✏️ 编辑现有武将</h2>
    <div class="editor-hdr-btns">
      <button class="btn btn-outline btn-small" onclick="saveCharEdits()">保存</button>
      <button class="btn btn-outline btn-small" onclick="resetAllEdits()">恢复全部</button>
      <button class="btn btn-outline btn-small" onclick="closeCharEditor()">返回</button>
    </div>`;
}

function renderEditorGrid() {
  const grid = document.getElementById('editorGrid');
  const factionOptions = Object.keys(FACTION_COLORS).sort().map(f => `<option value="${f}">${f}</option>`).join('');
  grid.innerHTML = editorChars.map((c, i) => {
    const orig = editorOriginals[i];
    const mapEntry = editorFactionMap[c.name];
    const defaultFaction = typeof mapEntry === 'string' ? mapEntry : (mapEntry?.primary || '群雄');
    const defaultFactions = typeof mapEntry === 'string' ? [mapEntry] : (mapEntry?.all || [defaultFaction]);
    const curFactions = c.factions || (c.faction ? [c.faction] : defaultFactions);
    const curFaction = curFactions[0];
    const hasChangedFaction = c.faction && c.faction !== (typeof editorFactionMap[c.name] === 'string' ? editorFactionMap[c.name] : (editorFactionMap[c.name]?.primary || '群雄'));
    const changed = c.leadership !== orig.leadership || c.martial !== orig.martial ||
      c.intelligence !== orig.intelligence || c.politics !== orig.politics ||
      c.type !== orig.type || hasChangedFaction;
    return `<div class="ec-card${changed ? ' ec-changed' : ''}">
      <div class="ec-id">#${c.id}</div>
      <div class="ec-avatar-row"><img class="ec-avatar" src="${generateAvatar(c, 64)}"></div>
      <div class="ec-name-static">${escHtml(c.name)}</div>
      <div class="ec-field"><span class="ec-label">类</span>
        <select class="ec-input ec-type" data-idx="${i}">${['全能','文臣','武将','特才'].map(t => `<option${t===c.type?' selected':''}>${t}</option>`).join('')}</select>
      </div>
      <div class="ec-field"><span class="ec-label">评</span><span class="ec-rating-static" style="color:${RATING_COLORS[c.rating]||'#ccc'}">${c.rating}</span></div>
      <div class="ec-field"><span class="ec-label">势</span>
        <select class="ec-input ec-faction" data-idx="${i}" style="color:${FACTION_COLORS[curFaction]||'#888'}">${factionOptions.replace(`value="${curFaction}"`, `value="${curFaction}" selected`)}</select>
        <span style="font-size:8px;color:#888;margin-left:2px">${curFactions.map(f => `<span style="color:${FACTION_COLORS[f]||'#888'}">${f}</span>`).join('/')}</span>
      </div>
      <div class="ec-field"><span class="ec-label">统</span><input class="ec-input ec-stat" data-idx="${i}" data-stat="leadership" type="number" min="0" max="100" value="${c.leadership}"></div>
      <div class="ec-field"><span class="ec-label">武</span><input class="ec-input ec-stat" data-idx="${i}" data-stat="martial" type="number" min="0" max="100" value="${c.martial}"></div>
      <div class="ec-field"><span class="ec-label">智</span><input class="ec-input ec-stat" data-idx="${i}" data-stat="intelligence" type="number" min="0" max="100" value="${c.intelligence}"></div>
      <div class="ec-field"><span class="ec-label">政</span><input class="ec-input ec-stat" data-idx="${i}" data-stat="politics" type="number" min="0" max="100" value="${c.politics}"></div>
      <div class="ec-total">总分 ${c.leadership + c.martial + c.intelligence + c.politics}</div>
      <button class="ec-btn${changed ? '' : ' ec-btn-disabled'}" data-idx="${i}" onclick="restoreChar(${i})">恢复</button>
    </div>`;
  }).join('');
  // Attach input listeners
  grid.querySelectorAll('.ec-stat').forEach(el => {
    el.addEventListener('input', onStatChange);
  });
  grid.querySelectorAll('.ec-type').forEach(el => {
    el.addEventListener('change', onSelectChange);
  });
  grid.querySelectorAll('.ec-faction').forEach(el => {
    el.addEventListener('change', onFactionChange);
  });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function onStatChange(e) {
  const el = e.target;
  const idx = parseInt(el.dataset.idx);
  const stat = el.dataset.stat;
  const v = parseInt(el.value) || 0;
  editorChars[idx][stat] = Math.max(0, Math.min(100, v));
  renderEditorGrid();
}

function onSelectChange(e) {
  const el = e.target;
  const idx = parseInt(el.dataset.idx);
  editorChars[idx].type = el.value;
  renderEditorGrid();
}

function onFactionChange(e) {
  const el = e.target;
  const idx = parseInt(el.dataset.idx);
  editorChars[idx].faction = el.value;
  delete editorChars[idx].factions; // clear multi-faction override so display uses primary
  renderEditorGrid();
}

function restoreChar(idx) {
  editorChars[idx] = JSON.parse(JSON.stringify(editorOriginals[idx]));
  // Remove any faction override so it reverts to the map default
  delete editorChars[idx].faction;
  delete editorChars[idx].factions;
  renderEditorGrid();
}

function recalcRatings(chars) {
  const splus = new Set();
  for (const c of chars) {
    if (c.leadership === 100 || c.martial === 100 || c.intelligence === 100 || c.politics === 100) {
      splus.add(c.id);
    }
  }
  const rest = chars.filter(c => !splus.has(c.id));
  rest.sort((a, b) => (b.leadership + b.martial + b.intelligence + b.politics) -
                      (a.leadership + a.martial + a.intelligence + a.politics));
  const n = rest.length;
  const tiers = [
    [1/11, 'S'], [3/11, 'A'], [5/11, 'B'], [8/11, 'C'], [1, 'D'],
  ];
  for (let i = 0; i < n; i++) {
    const p = i / n;
    rest[i].rating = tiers.find(t => p < t[0])?.[1] || 'D';
  }
  for (const c of chars) {
    if (splus.has(c.id)) c.rating = 'S+';
  }
}

async function saveCharEdits() {
  recalcRatings(editorChars);
  renderEditorGrid();
  try {
    const r = await fetch('/api/characters/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({characters: editorChars})
    });
    const d = await r.json();
    if (d.ok) {
      addBattleLog(`已保存 ${d.saved} 名武将的修改至游戏中`, 'win');
      if (!window._toast) { window._toast = document.createElement('div'); window._toast.className = 'toast-msg'; document.body.appendChild(window._toast); }
      window._toast.textContent = `✓ 已保存 ${d.saved} 名武将的修改`;
      window._toast.classList.add('show');
      setTimeout(() => window._toast.classList.remove('show'), 2000);
    }
  } catch (e) {
    addBattleLog(`保存失败: ${e.message}`, 'lose');
    if (!window._toast) { window._toast = document.createElement('div'); window._toast.className = 'toast-msg'; document.body.appendChild(window._toast); }
    window._toast.textContent = '✗ 保存失败: ' + e.message;
    window._toast.classList.add('show');
    setTimeout(() => window._toast.classList.remove('show'), 3000);
  }
}

async function resetAllEdits() {
  if (!confirm('确认恢复全部武将至原始数据？此操作将清除所有保存的修改。')) return;
  try {
    const r = await fetch('/api/characters/reset-all', {method: 'POST'});
    const d = await r.json();
    if (d.ok) {
      // Reset local editor data to originals
      editorChars = editorOriginals.map(c => JSON.parse(JSON.stringify(c)));
      renderEditorGrid();
      addBattleLog('已清除所有修改，游戏将使用原始武将数据', 'win');
      if (!window._toast) { window._toast = document.createElement('div'); window._toast.className = 'toast-msg'; document.body.appendChild(window._toast); }
      window._toast.textContent = '✓ 已恢复全部武将至原始数据';
      window._toast.classList.add('show');
      setTimeout(() => window._toast.classList.remove('show'), 2000);
    }
  } catch (e) {
    addBattleLog(`恢复失败: ${e.message}`, 'lose');
  }
}

function toggleMusic() {
  const enabled = MusicManager.toggle();
  const bgmBtn = document.getElementById('bgmBtn');
  if (bgmBtn) bgmBtn.textContent = enabled ? '♪ BGM' : '♪ BGM OFF';
  const settingsBtn = document.getElementById('settingsMusicToggle');
  if (settingsBtn) settingsBtn.textContent = enabled ? '♪ 开启' : '♪ 关闭';
}

function setMusicVolume(val) {
  const v = parseInt(val) / 100;
  MusicManager.setVolume(v);
  document.getElementById('settingsVolDisplay').textContent = val;
}

function closeSettings() {
  document.getElementById('settingsOverlay').classList.remove('show');
}

function openSettings() {
  document.getElementById('settingsOverlay').classList.add('show');
  const vol = Math.round(MusicManager.getVolume() * 100);
  document.getElementById('settingsVolume').value = vol;
  document.getElementById('settingsVolDisplay').textContent = vol;
  const enabled = MusicManager.isEnabled();
  document.getElementById('settingsMusicToggle').textContent = enabled ? '♪ 开启' : '♪ 关闭';
}

// Random poster background on load
(function initMenuBg() {
  const n = Math.floor(Math.random() * 3) + 1;
  const bg = document.createElement('div');
  bg.className = 'main-menu-bg';
  bg.style.backgroundImage = `url(posters/${n}.webp)`;
  document.getElementById('mainMenu').insertBefore(bg, document.getElementById('mainMenu').firstChild);
  // Attempt autoplay (may be blocked by browser policy)
  MusicManager.play('menu');
  // Fallback: unlock audio on first user interaction
  const unlockAudio = () => {
    MusicManager.play('menu');
    document.removeEventListener('click', unlockAudio);
    document.removeEventListener('touchstart', unlockAudio);
  };
  document.addEventListener('click', unlockAudio, { once: true });
  document.addEventListener('touchstart', unlockAudio, { once: true });
})();

async function startSinglePlayer() {
  const includeCustom = confirm('本局对战是否加入自建武将？\n\n选择「确定」：自建武将将加入卡池\n选择「取消」：仅使用预设武将');
  MusicManager.play('menu');
  document.getElementById('mainMenu').style.display = 'none';
  document.getElementById('gameHeader').style.display = 'flex';
  document.getElementById('gameContent').style.display = 'flex';
  initBoard();
  initSortBar();
  initFilters();
  try {
    const data = await api.newGame({ include_custom_generals: includeCustom });
    gameId = data.game_id;
    applyStateFromServer(data);
  } catch (e) {
    addBattleLog('连接服务器失败：' + e.message, 'lose');
    setPhase('⚠ 无法连接服务器');
  }
}

// ==================== CUSTOM GENERAL EDITOR ====================
let cgSelectedAvatar = 501;
let cgEditingId = null; // null = new creation
let cgFromList = false; // opened from listCustomGenerals

function openCustomEditor(editId) {
  openEditor();
  document.getElementById('mainMenu').style.display = 'none';
  // If editorOverlay is showing (from listCustomGenerals), hide it and mark
  cgFromList = document.getElementById('editorOverlay').classList.contains('show');
  document.getElementById('editorOverlay').classList.remove('show');
  const ov = document.getElementById('customEditorOverlay');
  ov.classList.add('show');
  cgEditingId = editId || null;
  // Populate faction dropdown
  const sel = document.getElementById('cgFaction');
  if (!sel.options.length) {
    const factions = Object.keys(FACTION_COLORS).sort();
    factions.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f; opt.textContent = f;
      sel.appendChild(opt);
    });
  }
  renderAvatarGrid();
  // Populate fields if editing
  if (editId) {
    Promise.resolve().then(() => loadCustomGeneralForEdit(editId));
  } else {
    resetCustomForm();
  }
  // Listen for stat changes to validate, update total & type constraint
  document.querySelectorAll('#customEditorOverlay .cg-stat').forEach(el => {
    const clamp = () => {
      if (el.value === '') return;
      const num = Number(el.value);
      if (num > 100) {
        showToast('属性值不可超过100', 'error');
        el.value = 100;
      } else if (num < 1) {
        showToast('属性值不可低于1', 'error');
        el.value = 1;
      }
      updateCgTotal(); enforceCgTypeConstraint();
    };
    el.addEventListener('input', clamp);
    el.addEventListener('blur', clamp);
  });
  document.getElementById('cgName').addEventListener('input', updateCgPreview);
  document.querySelectorAll('#customEditorOverlay .cg-stat, #cgType, #cgFaction').forEach(el => {
    el.addEventListener('change', updateCgPreview);
  });
}

function closeCustomEditor() {
  document.getElementById('customEditorOverlay').classList.remove('show');
  if (cgFromList) {
    document.getElementById('editorOverlay').classList.add('show');
  } else {
    document.getElementById('mainMenu').style.display = 'flex';
  }
}

function resetCustomForm() {
  cgSelectedAvatar = 501;
  document.getElementById('cgName').value = '';
  document.getElementById('cgType').value = '全能';
  document.getElementById('cgFaction').value = '群雄';
  document.getElementById('cgIdentity').value = '非大名';
  ['cgLead','cgMar','cgInt','cgPol'].forEach(id => {
    document.getElementById(id).value = 50;
  });
  updateCgTotal();
  enforceCgTypeConstraint();
  renderAvatarGrid();
  updateCgPreview();
  updateSelectedAvatar();
}

function renderAvatarGrid() {
  const grid = document.getElementById('cgAvatarGrid');
  grid.innerHTML = '';
  for (let id = 501; id <= 520; id++) {
    const img = document.createElement('img');
    img.className = 'cg-avatar-opt' + (id === cgSelectedAvatar ? ' selected' : '');
    img.src = `portraits/${id}.webp`;
    img.onclick = () => { cgSelectedAvatar = id; renderAvatarGrid(); updateCgPreview(); updateSelectedAvatar(); };
    grid.appendChild(img);
  }
}

function updateSelectedAvatar() {
  const img = document.querySelector('#cgSelectedAvatar img');
  img.src = `portraits/${cgSelectedAvatar}.webp`;
}

function updateCgTotal() {
  const ld = parseInt(document.getElementById('cgLead').value) || 0;
  const mr = parseInt(document.getElementById('cgMar').value) || 0;
  const it = parseInt(document.getElementById('cgInt').value) || 0;
  const po = parseInt(document.getElementById('cgPol').value) || 0;
  document.getElementById('cgTotal').textContent = `总分 ${ld + mr + it + po}`;
}

function enforceCgTypeConstraint() {
  const ld = parseInt(document.getElementById('cgLead').value) || 0;
  const mr = parseInt(document.getElementById('cgMar').value) || 0;
  const it = parseInt(document.getElementById('cgInt').value) || 0;
  const po = parseInt(document.getElementById('cgPol').value) || 0;
  const sel = document.getElementById('cgType');
  const isMartial = (ld + mr) >= (it + po);
  for (const opt of sel.options) {
    if (opt.value === '武将') opt.disabled = !isMartial;
    else if (opt.value === '文臣') opt.disabled = isMartial;
    else opt.disabled = false;
  }
  if (sel.value === '武将' && !isMartial) sel.value = '全能';
  else if (sel.value === '文臣' && isMartial) sel.value = '全能';
}

function updateCgPreview() {
  const name = document.getElementById('cgName').value || '未命名';
  const type = document.getElementById('cgType').value;
  const faction = document.getElementById('cgFaction').value;
  const ld = parseInt(document.getElementById('cgLead').value) || 0;
  const mr = parseInt(document.getElementById('cgMar').value) || 0;
  const it = parseInt(document.getElementById('cgInt').value) || 0;
  const po = parseInt(document.getElementById('cgPol').value) || 0;
  const total = ld + mr + it + po;
  const char = { id: cgEditingId || 9999, avatarId: cgSelectedAvatar, name, type, faction, leadership: ld, martial: mr, intelligence: it, politics: po, rating: 'C' };
  const fColor = FACTION_COLORS[faction] || '#888';
  const pv = document.getElementById('cgPreview');
  pv.innerHTML = `<img class="cg-prev-avatar" src="${generateAvatar(char, 48)}">
    <div class="cg-prev-info">
      <div style="font-weight:600;color:#f5a623">${escHtml(name)}</div>
      <div style="color:${fColor};font-size:10px">${faction}</div>
      <div>${document.getElementById('cgIdentity').value} · ${type} · 统${ld} 武${mr} 智${it} 政${po} · 总分${total}</div>
    </div>`;
}

async function loadCustomGeneralForEdit(id) {
  try {
    const r = await fetch('/api/characters/custom');
    const d = await r.json();
    const g = d.generals.find(x => x.id === id);
    if (!g) { showToast('未找到该武将', 'error'); return; }
    document.getElementById('cgName').value = g.name || '';
    document.getElementById('cgType').value = g.type || '全能';
    document.getElementById('cgFaction').value = g.faction || '群雄';
    document.getElementById('cgIdentity').value = g.identity || '非大名';
    document.getElementById('cgLead').value = g.leadership || 50;
    document.getElementById('cgMar').value = g.martial || 50;
    document.getElementById('cgInt').value = g.intelligence || 50;
    document.getElementById('cgPol').value = g.politics || 50;
    cgSelectedAvatar = g.avatarId || 501;
    renderAvatarGrid();
    updateCgTotal();
    enforceCgTypeConstraint();
    updateCgPreview();
  } catch (e) {
    showToast('加载失败: ' + e.message, 'error');
  }
}

async function saveCustomGeneral() {
  const name = document.getElementById('cgName').value.trim();
  if (!name) { showToast('请输入武将姓名', 'error'); return; }
  const type = document.getElementById('cgType').value;
  const ld = parseInt(document.getElementById('cgLead').value) || 0;
  const mr = parseInt(document.getElementById('cgMar').value) || 0;
  const it = parseInt(document.getElementById('cgInt').value) || 0;
  const po = parseInt(document.getElementById('cgPol').value) || 0;
  const isMartial = (ld + mr) >= (it + po);
  if (type === '武将' && !isMartial) { showToast('统武<智政时不可选择武将类型', 'error'); return; }
  if (type === '文臣' && isMartial) { showToast('统武>=智政时不可选择文臣类型', 'error'); return; }
  if (ld > 100 || mr > 100 || it > 100 || po > 100) { showToast('属性值不可超过100', 'error'); return; }
  if (ld < 1 || mr < 1 || it < 1 || po < 1) { showToast('属性值不可低于1', 'error'); return; }
  const ld2 = Math.min(100, Math.max(1, ld));
  const mr2 = Math.min(100, Math.max(1, mr));
  const it2 = Math.min(100, Math.max(1, it));
  const po2 = Math.min(100, Math.max(1, po));
  const total = ld2 + mr2 + it2 + po2;
  let rating = 'C';
  if (ld2 === 100 || mr2 === 100 || it2 === 100 || po2 === 100) rating = 'S+';
  else if (total >= 360) rating = 'S';
  else if (total >= 330) rating = 'A';
  else if (total >= 300) rating = 'B';
  else if (total >= 270) rating = 'C';
  else rating = 'D';

  const generals = [];
  // Load existing custom generals from server
  try {
    const r = await fetch('/api/characters/custom');
    const d = await r.json();
    generals.push(...d.generals);
  } catch (_) {}
  // Remove existing entry with same id, or generate new id
  if (cgEditingId) {
    const idx = generals.findIndex(x => x.id === cgEditingId);
    if (idx >= 0) generals.splice(idx, 1);
  } else {
    cgEditingId = 501; // find next available id
    const used = new Set(generals.map(x => x.id));
    while (used.has(cgEditingId)) cgEditingId++;
  }
  const entry = {
    id: cgEditingId,
    name, type,
    leadership: ld2, martial: mr2, intelligence: it2, politics: po2,
    total_score: total, rating,
    identity: document.getElementById('cgIdentity').value,
    faction: document.getElementById('cgFaction').value,
    avatarId: cgSelectedAvatar,
  };
  generals.push(entry);
  try {
    const r = await fetch('/api/characters/custom/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({generals})
    });
    const res = await r.json();
    if (res.ok) {
      showToast(`✓ 已保存武将「${name}」`);
      // Update preview with final id
      updateCgPreview();
    }
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function listCustomGenerals() {
  openEditor();
  document.getElementById('mainMenu').style.display = 'none';
  try {
    const r = await fetch('/api/characters/custom');
    const d = await r.json();
    const list = d.generals || [];
    if (list.length === 0) {
      showToast('暂无自建武将，请先创建');
      document.getElementById('mainMenu').style.display = 'flex';
      return;
    }
    // Show a simple selection overlay (reuse existing overlay approach)
    const ov = document.getElementById('editorOverlay');
    ov.classList.add('show');
    const grid = document.getElementById('editorGrid');
    grid.innerHTML = `<div style="font-size:12px;color:#888;padding:4px 8px">点击武将进行编辑</div>`;
    grid.innerHTML += list.map(g => {
      const total = (g.leadership||0)+(g.martial||0)+(g.intelligence||0)+(g.politics||0);
      return `<div class="ec-card" style="cursor:pointer" onclick="openCustomEditor(${g.id})">
        <div class="ec-id">#${g.id}</div>
        <div class="ec-avatar-row"><img class="ec-avatar" src="${generateAvatar({id:g.avatarId||g.id,name:g.name,rating:g.rating||'C',type:g.type||'全能'}, 48)}"></div>
        <div class="ec-name-static">${escHtml(g.name)}</div>
        <div class="ec-field"><span class="ec-label">类</span><span>${g.type||'全能'}</span></div>
        <div class="ec-field"><span class="ec-label">身份</span><span style="color:#f5a623">${g.identity||'非大名'}</span></div>
        <div class="ec-field"><span class="ec-label">评</span><span style="color:${RATING_COLORS[g.rating]||'#ccc'}">${g.rating||'C'}</span></div>
        <div style="font-size:10px;color:#888;margin-top:4px">统${g.leadership} 武${g.martial} 智${g.intelligence} 政${g.politics}</div>
        <div style="font-size:9px;color:#4fc3f7">总分 ${total}</div>
      </div>`;
    }).join('');
    // Add a close button to the editor header
    const hdr = document.querySelector('#editorOverlay .editor-hdr');
    hdr.innerHTML = `<h2>📝 编辑自建武将</h2>
      <div class="editor-hdr-btns">
        <button class="btn btn-outline btn-small" onclick="closeCharEditor()">返回</button>
      </div>`;
  } catch (e) {
    showToast('加载失败: ' + e.message, 'error');
  }
}

function showToast(msg, type) {
  if (!window._toast) { window._toast = document.createElement('div'); window._toast.className = 'toast-msg'; document.body.appendChild(window._toast); }
  window._toast.style.background = type === 'error' ? 'rgba(233,69,96,.9)' : 'rgba(46,204,113,.9)';
  window._toast.textContent = msg;
  window._toast.classList.add('show');
  setTimeout(() => window._toast.classList.remove('show'), 2500);
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const ov = document.getElementById('settingsOverlay');
    if (ov.classList.contains('show')) ov.classList.remove('show');
  }
});

// ==================== INIT (no-op; game starts via menu) ====================
