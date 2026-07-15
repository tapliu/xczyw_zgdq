import json
import random
import os
from copy import deepcopy

from . import relations

CHARACTERS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'game', 'characters.json')

HEX_RADIUS = 7
HEX_SIZE = 52
PLACE_PER_ROUND = 5
INIT_TROOPS = 50000
MAX_TROOPS_PER_UNIT = 10000
TROOP_INCOME = 10000
MAX_TOTAL_TROOPS = 300000
MAX_DRAW_PER_SIDE = 30

# Board shape: 14 rows (r = -6..7)
# Row counts: 5,6,7,8,8,7,6,5 (r=-4..3)
_HEX_ROW_COUNTS = {
    -4: 5, -3: 6, -2: 7, -1: 8,
    0: 8, 1: 7, 2: 6, 3: 5,
}
_HEX_ROW_Q_STARTS = {
    -2: -4,  # shifted left 1
    -1: -5,  # shifted left 1
    0: -6,   # shifted left 2
    1: -6,   # shifted left 3
    2: -6,   # shifted left 3
    3: -6,   # shifted left 4
}

HEX_AXIAL_IDX = {}
HEX_IDX_AXIAL = {}
_hex_idx = 0
_HEX_ROW_LIST = sorted(_HEX_ROW_COUNTS.keys())
for r in _HEX_ROW_LIST:
    count = _HEX_ROW_COUNTS[r]
    q_start = _HEX_ROW_Q_STARTS.get(r, -(count // 2))
    q_vals = list(range(q_start, q_start + count))
    for q in q_vals:
        HEX_AXIAL_IDX[(q, r)] = _hex_idx
        HEX_IDX_AXIAL[_hex_idx] = (q, r)
        _hex_idx += 1
assert _hex_idx == HEX_SIZE

# Flat-top hex neighbor directions (axial coords)
HEX_DIRS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]

# Player advances north (decreasing depth = 2r + q)
PLAYER_FORWARD_DIRS = [(-1, 0), (0, -1), (1, -1)]
# AI advances south (increasing depth)
AI_FORWARD_DIRS = [(1, 0), (0, 1), (-1, 1)]

# Placement zones by depth (2*r + q, visual y for flat-top hexes)
# Player places in south half (depth > 0)
# AI places in north half (depth < 0)
# depth=0 is the contested front line

# For terrain patterns (hex version): all active by default, terrain modes modify
def _make_hex_active():
    return [True] * HEX_SIZE

_hex_active_all = _make_hex_active()

def _hex_neighbors(idx):
    q, r = HEX_IDX_AXIAL[idx]
    result = []
    for dq, dr in HEX_DIRS:
        nq, nr = q + dq, r + dr
        ni = HEX_AXIAL_IDX.get((nq, nr))
        if ni is not None:
            result.append(ni)
    return result

def _hex_forward_indices(idx, is_player):
    q, r = HEX_IDX_AXIAL[idx]
    dirs = PLAYER_FORWARD_DIRS if is_player else AI_FORWARD_DIRS
    result = []
    for dq, dr in dirs:
        nq, nr = q + dq, r + dr
        ni = HEX_AXIAL_IDX.get((nq, nr))
        if ni is not None:
            result.append(ni)
    return result

# Precompute all cell properties
HEX_NEIGHBORS = [_hex_neighbors(i) for i in range(HEX_SIZE)]
HEX_PLAYER_FORWARD = [_hex_forward_indices(i, True) for i in range(HEX_SIZE)]
HEX_AI_FORWARD = [_hex_forward_indices(i, False) for i in range(HEX_SIZE)]
# Depth (visual y) = 2*r + q for flat-top hex orientation
HEX_DEPTH = [HEX_IDX_AXIAL[i][1] * 2 + HEX_IDX_AXIAL[i][0] for i in range(HEX_SIZE)]
HEX_PLAYER_CELLS = [i for i in range(HEX_SIZE) if HEX_DEPTH[i] > 0]
HEX_AI_CELLS = [i for i in range(HEX_SIZE) if HEX_DEPTH[i] < 0]
HEX_FRONT_CELLS = sorted([
    HEX_AXIAL_IDX[(1, -2)],
    HEX_AXIAL_IDX[(-1, -1)],
    HEX_AXIAL_IDX[(-3, 0)],
    HEX_AXIAL_IDX[(-5, 1)],
])
PLAYER_BASELINE_DEPTH = max(HEX_DEPTH)
AI_BASELINE_DEPTH = min(HEX_DEPTH)
HEX_PLAYER_BASELINE = [i for i in range(HEX_SIZE) if HEX_DEPTH[i] == PLAYER_BASELINE_DEPTH]
HEX_AI_BASELINE = [i for i in range(HEX_SIZE) if HEX_DEPTH[i] == AI_BASELINE_DEPTH]

AI_FLAG_CELLS = sorted([
    HEX_AXIAL_IDX[(-2, -4)], HEX_AXIAL_IDX[(-1, -4)], HEX_AXIAL_IDX[(0, -4)],
    HEX_AXIAL_IDX[(-3, -3)], HEX_AXIAL_IDX[(-2, -3)], HEX_AXIAL_IDX[(-1, -3)],
    HEX_AXIAL_IDX[(-4, -2)], HEX_AXIAL_IDX[(-3, -2)], HEX_AXIAL_IDX[(-2, -2)],
])

PLAYER_FLAG_CELLS = sorted([
    HEX_AXIAL_IDX[(-2, 1)], HEX_AXIAL_IDX[(-1, 1)], HEX_AXIAL_IDX[(0, 1)],
    HEX_AXIAL_IDX[(-3, 2)], HEX_AXIAL_IDX[(-2, 2)], HEX_AXIAL_IDX[(-1, 2)],
    HEX_AXIAL_IDX[(-4, 3)], HEX_AXIAL_IDX[(-3, 3)], HEX_AXIAL_IDX[(-2, 3)],
])

# Two-step forward lookup: for each cell, list of (first_step, second_step) per forward direction
def _hex_forward_line(idx, is_player):
    q, r = HEX_IDX_AXIAL[idx]
    dirs = PLAYER_FORWARD_DIRS if is_player else AI_FORWARD_DIRS
    result = []
    for dq, dr in dirs:
        f1 = HEX_AXIAL_IDX.get((q + dq, r + dr))
        f2 = HEX_AXIAL_IDX.get((q + 2*dq, r + 2*dr))
        result.append((f1, f2))
    return result

HEX_FORWARD_LINE_PLAYER = [_hex_forward_line(i, True) for i in range(HEX_SIZE)]
HEX_FORWARD_LINE_AI = [_hex_forward_line(i, False) for i in range(HEX_SIZE)]

RATING_ORDER = {'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5}
RATING_ORDER = {'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5}


def load_characters():
    with open(CHARACTERS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

edited_characters = {}  # char_id -> modified char dict (saved by editor, not persisted to disk)
custom_generals = {}    # char_id -> custom general dict


def shuffle(arr):
    random.shuffle(arr)


class Unit:
    def __init__(self, char, troops, uid, pinned=False, is_new_placement=False):
        self.char = deepcopy(char)
        self.troops = troops
        self.uid = uid
        self.pinned = pinned
        self.is_new_placement = is_new_placement

    def to_dict(self):
        return {
            'char': self.char,
            'troops': self.troops,
            'uid': self.uid,
            'pinned': self.pinned,
            'is_new_placement': self.is_new_placement,
        }


class SideState:
    def __init__(self):
        self.collection = []
        self.board = [None] * HEX_SIZE
        self.troops = INIT_TROOPS
        self.flag_idx = -1
        self.placed = 0
        self.flag_generals = []
        self.locked_flag_ids = []
        self.current_flag_char_id = None
        self.total_draws = 0

    def to_dict(self):
        return {
            'collection': self.collection,
            'board': [u.to_dict() if u else None for u in self.board],
            'troops': self.troops,
            'flag_idx': self.flag_idx,
            'placed': self.placed,
            'flag_generals': self.flag_generals,
            'locked_flag_ids': self.locked_flag_ids,
            'current_flag_char_id': self.current_flag_char_id,
            'total_draws': self.total_draws,
        }


class GameState:
    def __init__(self, game_id):
        self.game_id = game_id
        self.round = 0
        self.game_phase = 'idle'
        self.placed_this_turn = 0
        self.player = SideState()
        self.ai = SideState()
        self.draw_pile = []
        self.dead_list = []
        self.spectator_pool = []
        self.combat_stats = {}
        self.player_cooldowns = []
        self.ai_cooldowns = []
        self.flag_scatter_count = {'player': 0, 'ai': 0}
        self.unit_id_counter = 0
        self.terrain_mode = 'normal'
        self.battle_log = []
        self.winner = None
        self.scatter_debuff = {}
        self.uid_char_map = {}
        self.uid_side_map = {}
        self._pending_draw_options = None
        self.pending_picks = 0
        self.pending_flag_picks = 0
        self.multiplayer = False
        self.host_token = ''       # multiplayer auth — set when game starts from room
        self.guest_token = ''      # multiplayer auth — set when game starts from room
        self._draw_seq = []
        self._draw_seq_idx = 0
        self.host_placement_ready = False
        self.guest_placement_ready = False
        self.guest_placed_this_turn = 0
        self.first_scaler_uid = None
        self.first_scaler_round = None
        self.lone_brave_player = False
        self.lone_brave_ai = False
        self.lone_brave_round = None

    def _check_first_scaler(self, idx, is_player):
        """Set first_scaler_uid if unit at idx just entered opponent's flag zone."""
        if self.first_scaler_uid is not None:
            return
        if is_player and idx in AI_FLAG_CELLS:
            u = self.player.board[idx]
            if u:
                self.first_scaler_uid = u.uid
                self.first_scaler_round = self.round
        elif not is_player and idx in PLAYER_FLAG_CELLS:
            u = self.ai.board[idx]
            if u:
                self.first_scaler_uid = u.uid
                self.first_scaler_round = self.round

    def _log(self, msg, typ='info'):
        self.battle_log.append({'msg': msg, 'type': typ})

    def _is_active_cell(self, idx):
        return 0 <= idx < HEX_SIZE

    def _get_neighbor_indices(self, idx):
        return HEX_NEIGHBORS[idx]

    def _get_cone_indices(self, idx, is_player):
        return HEX_PLAYER_FORWARD[idx] if is_player else HEX_AI_FORWARD[idx]

    def _is_flag_unit(self, idx, is_player):
        return self.player.flag_idx == idx if is_player else self.ai.flag_idx == idx

    def _calc_power(self, index, is_player):
        my_board = self.player.board if is_player else self.ai.board
        en_board = self.ai.board if is_player else self.player.board
        side = self.player if is_player else self.ai
        u = my_board[index]
        if not u:
            return 0
        flag_mul = 1.1 if self._is_flag_unit(index, is_player) else 1
        power = u.char['martial'] * 2 * flag_mul
        power *= (1 + u.troops / 30000)
        u_factions = u.char.get('factions') or []
        if not u_factions:
            f = u.char.get('faction', '')
            if f:
                u_factions = [f]
        has_qunxiong = '群雄' in u_factions
        faction_bonus = 1.0
        for ni in self._get_neighbor_indices(index):
            nu = my_board[ni]
            if nu:
                power += nu.char['leadership'] * 0.05
                nf = nu.char.get('faction', '')
                if nf and nf in u_factions:
                    faction_bonus += 0.03 if has_qunxiong else 0.05
                elif nf and any(relations.is_hostile(uf, nf) for uf in u_factions):
                    faction_bonus -= 0.05
        power += u.char['leadership'] * flag_mul * 0.05
        for ei in range(HEX_SIZE):
            eu = en_board[ei]
            if not eu:
                continue
            cone = self._get_cone_indices(ei, not is_player)
            if index in cone:
                power -= eu.char['intelligence'] * 0.03
        power *= faction_bonus
        # Lord bonus: each same-faction ally on board adds 5%
        is_lord = u.char.get('lord_name') == u.char.get('name')
        if is_lord:
            faction_count = 0
            for i in range(HEX_SIZE):
                fu = my_board[i]
                if fu and fu is not u:
                    ff = fu.char.get('factions') or []
                    if not ff:
                        ff = [fu.char.get('faction', '')]
                    if any(f in u_factions for f in ff):
                        faction_count += 1
            power *= (1 + faction_count * 0.05)
        # No flag on board → all units fight at 80%
        if side.flag_idx == -1:
            power = round(power * 0.8)
        # 居高临下: unit in front zone → +5%
        if index in HEX_FRONT_CELLS:
            power = round(power * 1.05)
        # 先登: first to enter enemy flag zone → +10% (lasts 5 rounds)
        if u.uid == self.first_scaler_uid and self.round <= self.first_scaler_round + 5:
            power = round(power * 1.10)
        # 孤勇者: lone flag general → +50% (lasts 10 rounds)
        if self.lone_brave_round is not None and self.round <= self.lone_brave_round + 10:
            if is_player and self.lone_brave_player and self._is_flag_unit(index, is_player):
                power = round(power * 1.50)
            if not is_player and self.lone_brave_ai and self._is_flag_unit(index, is_player):
                power = round(power * 1.50)
        return max(1, round(power))

    def _calc_battle(self, p_unit, a_unit, p_power, a_power, ratio=1):
        p_comm = p_unit.troops * ratio
        a_comm = a_unit.troops * ratio
        p_pol = p_unit.char['politics'] * (1.1 if self._is_flag_unit(self.player.flag_idx, True) else 1)
        a_pol = a_unit.char['politics'] * (1.1 if self._is_flag_unit(self.ai.flag_idx, False) else 1)
        p_red = 1 - p_pol / 240
        a_red = 1 - a_pol / 240
        total = p_power + a_power
        p_loss = round(p_comm * (a_power / total) * 0.8 * p_red) if total > 0 else 0
        a_loss = round(a_comm * (p_power / total) * 0.8 * a_red) if total > 0 else 0
        return {
            'pLoss': p_loss, 'aLoss': a_loss,
            'pLossPct': p_loss / (p_unit.troops * ratio) if p_unit.troops * ratio > 0 else 0,
            'aLossPct': a_loss / (a_unit.troops * ratio) if a_unit.troops * ratio > 0 else 0,
        }

    def resolve_rt_melee(self, unit_uid, target_uid, is_player_attacker):
        """Real-time melee resolution for input-based combat (Layer 4 validation)."""
        side = self.player if is_player_attacker else self.ai
        opp = self.ai if is_player_attacker else self.player
        attacker = next((u for u in side.board if u and u.uid == unit_uid), None)
        target = next((u for u in opp.board if u and u.uid == target_uid), None)
        if not attacker or not target:
            return None

        a_cell = next(i for i, u in enumerate(side.board) if u and u.uid == unit_uid)
        t_cell = next(i for i, u in enumerate(opp.board) if u and u.uid == target_uid)

        a_power = self._calc_battle_power(a_cell, is_player_attacker)
        t_power = self._calc_battle_power(t_cell, not is_player_attacker)

        if is_player_attacker:
            result = self._calc_battle(attacker, target, a_power, t_power)
        else:
            result = self._calc_battle(target, attacker, t_power, a_power)

        attacker.troops = max(0, attacker.troops - result['pLoss'] if is_player_attacker else result['aLoss'])
        target.troops = max(0, target.troops - result['aLoss'] if is_player_attacker else result['pLoss'])

        return {
            'attacker_damage': result['pLoss'] if is_player_attacker else result['aLoss'],
            'target_damage': result['aLoss'] if is_player_attacker else result['pLoss'],
            'attacker_alive': attacker.troops > 0,
            'target_alive': target.troops > 0,
        }

    def _calc_ranged_damage(self, attacker, defender, atk_power, def_power):
        total = atk_power + def_power
        intel_factor = attacker.char['intelligence'] / 100
        dmg = round(attacker.troops * (atk_power / total) * intel_factor * 0.15) if total > 0 else 1
        return max(1, dmg)

    def _has_adjacent_enemy(self, idx, is_player):
        enemy = self.ai if is_player else self.player
        for ni in HEX_NEIGHBORS[idx]:
            if enemy.board[ni]:
                return True
        return False

    def _is_behind_enemy_line(self, idx, is_player):
        my_d = HEX_DEPTH[idx]
        en_board = self.ai.board if is_player else self.player.board
        for i in range(HEX_SIZE):
            if en_board[i] and ((is_player and HEX_DEPTH[i] > my_d) or (not is_player and HEX_DEPTH[i] < my_d)):
                return True
        return False

    def _is_in_front_of_friendly(self, idx, is_player):
        my_d = HEX_DEPTH[idx]
        board = self.player.board if is_player else self.ai.board
        for i in range(HEX_SIZE):
            if board[i] and ((is_player and HEX_DEPTH[i] > my_d) or (not is_player and HEX_DEPTH[i] < my_d)):
                return True
        return False

    def _pin_from_placement(self, idx, is_player):
        side = self.player if is_player else self.ai
        enemy = self.ai if is_player else self.player
        adjacent = False
        for ni in HEX_NEIGHBORS[idx]:
            if enemy.board[ni]:
                adjacent = True
                enemy.board[ni].pinned = True
        if adjacent:
            side.board[idx].pinned = True

    def _is_triple_surrounded(self, idx, is_player):
        en_board = self.ai.board if is_player else self.player.board
        count = sum(1 for ni in HEX_NEIGHBORS[idx] if en_board[ni])
        return count >= 3

    def _get_encirclement_power_mod(self, idx, is_player):
        for ni in HEX_NEIGHBORS[idx]:
            if self._is_triple_surrounded(ni, True) or self._is_triple_surrounded(ni, False):
                return 0.9
        return 1

    def _calc_battle_power(self, idx, is_player):
        return round(self._calc_power(idx, is_player) * self._get_encirclement_power_mod(idx, is_player))

    def _stat_slot(self, uid):
        if uid not in self.combat_stats:
            self.combat_stats[uid] = {'damage': 0, 'meleeDmg': 0, 'rangedDmg': 0, 'meleeHits': 0, 'rangedHits': 0,
                                      'kills': 0, 'retreatTriggers': 0, 'damage_to': {}, 'damage_from': {},
                                      'melee_hit_details': [], 'ranged_hit_details': []}
        return self.combat_stats[uid]

    def _record_melee(self, atk_uid, def_uid, dmg):
        s = self._stat_slot(atk_uid)
        s['damage'] += dmg
        s['meleeDmg'] += dmg
        s['meleeHits'] += 1
        sk = str(def_uid)
        s['damage_to'][sk] = s['damage_to'].get(sk, 0) + dmg
        s['melee_hit_details'].append({'target': sk, 'dmg': dmg})
        t = self._stat_slot(def_uid)
        t['damage_from'][str(atk_uid)] = t['damage_from'].get(str(atk_uid), 0) + dmg

    def _record_ranged(self, atk_uid, def_uid, dmg):
        s = self._stat_slot(atk_uid)
        s['damage'] += dmg
        s['rangedDmg'] += dmg
        s['rangedHits'] += 1
        sk = str(def_uid)
        s['damage_to'][sk] = s['damage_to'].get(sk, 0) + dmg
        s['ranged_hit_details'].append({'target': sk, 'dmg': dmg})
        t = self._stat_slot(def_uid)
        t['damage_from'][str(atk_uid)] = t['damage_from'].get(str(atk_uid), 0) + dmg

    def _record_kill(self, uid):
        self._stat_slot(uid)['kills'] += 1

    def _record_retreat(self, uid):
        self._stat_slot(uid)['retreatTriggers'] += 1

    def _is_on_cooldown(self, char_id, is_player):
        arr = self.player_cooldowns if is_player else self.ai_cooldowns
        return any(c['id'] == char_id and c['round'] + 4 >= self.round for c in arr)

    def _mark_cooldown(self, char_id, is_player, typ='defeat'):
        arr = self.player_cooldowns if is_player else self.ai_cooldowns
        existing = next((c for c in arr if c['id'] == char_id), None)
        if existing:
            existing['type'] = typ
        else:
            arr.append({'id': char_id, 'round': self.round, 'type': typ})

    def _expire_cooldowns(self):
        self.player_cooldowns = [c for c in self.player_cooldowns if c['round'] + 4 >= self.round]
        self.ai_cooldowns = [c for c in self.ai_cooldowns if c['round'] + 4 >= self.round]

    def _is_dead(self, char_id):
        return char_id in self.dead_list

    def _find_highest_troops_idx(self, board):
        bi, bt = -1, -1
        for i in range(HEX_SIZE):
            if board[i] and board[i].troops > bt:
                bt = board[i].troops
                bi = i
        return bi

    def _total_troops(self, side):
        return sum(u.troops for u in side.board if u)

    def _decay_income(self, side):
        board_t = self._total_troops(side)
        income = int(TROOP_INCOME * max(0, 1 - board_t / MAX_TOTAL_TROOPS))
        sum_pol = sum(u.char['politics'] for u in side.board if u)
        pol_mult = max(0.2, min(2.0, sum_pol * 0.001))
        income = int(income * pol_mult)
        max_add = MAX_TOTAL_TROOPS - board_t - side.troops
        return max(0, min(income, max_add))

    @staticmethod
    def _apply_type_bonus(c):
        typ = c.get('type', '')
        # Save original values for frontend display
        for k in ('leadership','martial','intelligence','politics'):
            c['orig_' + k] = c.get(k, 0)
        if typ == '全能':
            for k in ('leadership','martial','intelligence','politics'):
                c[k] = round(c.get(k,0) * 1.05)
        elif typ == '文臣':
            for k in ('intelligence','politics'):
                c[k] = round(c.get(k,0) * 1.07)
        elif typ == '武将':
            for k in ('leadership','martial'):
                c[k] = round(c.get(k,0) * 1.07)
        elif typ == '特才':
            best = max(('leadership','martial','intelligence','politics'), key=lambda k: c.get(k,0))
            c[best] = round(c.get(best,0) * 1.10)

    @staticmethod
    def _recalc_ratings(chars):
        splus = set()
        for c in chars:
            ld = c.get('orig_leadership') or c.get('leadership') or 0
            mr = c.get('orig_martial') or c.get('martial') or 0
            it = c.get('orig_intelligence') or c.get('intelligence') or 0
            po = c.get('orig_politics') or c.get('politics') or 0
            if ld == 100 or mr == 100 or it == 100 or po == 100:
                splus.add(c['id'])
        rest = [c for c in chars if c['id'] not in splus]
        rest.sort(key=lambda c: -((c.get('orig_leadership') or c.get('leadership') or 0)
                                 + (c.get('orig_martial') or c.get('martial') or 0)
                                 + (c.get('orig_intelligence') or c.get('intelligence') or 0)
                                 + (c.get('orig_politics') or c.get('politics') or 0)))
        n = len(rest)
        tiers = [(1/11, 'S'), (3/11, 'A'), (5/11, 'B'), (8/11, 'C'), (1, 'D')]
        for i, c in enumerate(rest):
            pct = i / n if n > 0 else 1
            c['rating'] = 'D'
            for thr, tier in tiers:
                if pct < thr:
                    c['rating'] = tier
                    break
        for c in chars:
            if c['id'] in splus:
                c['rating'] = 'S+'

    def reset_game(self, include_custom_generals=True):
        all_chars = load_characters()
        # Attach default faction info from relation data (before edits, so edits can override)
        for c in all_chars:
            name = c.get('name', '')
            cf = relations.get_faction(name)
            if cf:
                c['faction'] = cf
                c['factions'] = relations.get_factions(name)
            lord = relations.get_lord(cf) if cf else None
            if lord:
                c['lord_name'] = lord
        # Apply editor-saved modifications on top of original file data
        for c in all_chars:
            cid = c['id']
            if cid in edited_characters:
                c.update(edited_characters[cid])
        # Apply type-based stat multipliers
        for c in all_chars:
            self._apply_type_bonus(c)
        # Recalculate ratings so static data errors don't propagate into gameplay
        self._recalc_ratings(all_chars)
        # Add custom generals to the pool (if enabled)
        all_game_chars = list(all_chars)
        if include_custom_generals:
            for cg in custom_generals.values():
                cg_copy = deepcopy(cg)
                if 'faction' not in cg_copy:
                    cf = relations.get_faction(cg_copy.get('name', ''))
                    if cf:
                        cg_copy['faction'] = cf
                        cg_copy['factions'] = relations.get_factions(cg_copy.get('name', ''))
                    lord = relations.get_lord(cf) if cf else None
                    if lord:
                        cg_copy['lord_name'] = lord
                self._apply_type_bonus(cg_copy)
                all_game_chars.append(cg_copy)
        self._recalc_ratings(all_game_chars)
        self.draw_pile = []
        self.spectator_pool = [deepcopy(c) for c in all_game_chars]
        shuffle(self.spectator_pool)
        self.player = SideState()
        self.ai = SideState()
        self.round = 0
        self.game_phase = 'idle'
        self.placed_this_turn = 0
        self.dead_list = []
        self.combat_stats = {}
        self.player_cooldowns = []
        self.ai_cooldowns = []
        self.flag_scatter_count = {'player': 0, 'ai': 0}
        self.unit_id_counter = 0
        self.scatter_debuff = {}
        self.uid_char_map = {}
        self.uid_side_map = {}
        self.battle_log = []
        self.winner = None
        self._pending_draw_options = None
        self.pending_picks = 0
        self.pending_flag_picks = 0
        self.host_placement_ready = False
        self.guest_placement_ready = False
        self._init_draw_sequence()
        self._log('初始抽卡：先选旗本武将，再选普通武将', 'info')

    # ---- Unified draw sequence (single-player & multiplayer) ----
    def _init_draw_sequence(self):
        """Generate the draw sequence for the current round."""
        self._draw_seq = []
        self._draw_seq_idx = 0
        # Check if both sides have reached the draw limit
        if self.player.total_draws >= MAX_DRAW_PER_SIDE and self.ai.total_draws >= MAX_DRAW_PER_SIDE:
            if self.game_phase in ('draw', 'pick_card', 'multiplayer_draw_host', 'multiplayer_pick_host'):
                self.game_phase = 'place_player'
            return
        if self.round == 0:
            if self.multiplayer:
                slot_a, slot_b = 'host', 'guest'
            else:
                slot_a, slot_b = 'player', 'ai'
            self._draw_seq = [
                (slot_a, 1, 'flag'),
                (slot_b, 2, 'flag'),
                (slot_a, 2, 'flag'),
                (slot_b, 1, 'flag'),
                (slot_b, 1, 'regular'),
                (slot_a, 2, 'regular'),
                (slot_b, 2, 'regular'),
                (slot_a, 2, 'regular'),
                (slot_b, 2, 'regular'),
                (slot_a, 2, 'regular'),
                (slot_b, 2, 'regular'),
                (slot_a, 1, 'regular'),
            ]
        elif self.multiplayer:
            starter = 'host' if self.round % 2 == 1 else 'guest'
            other = 'guest' if starter == 'host' else 'host'
            self._draw_seq = [(starter, 1, 'regular'), (other, 2, 'regular'), (starter, 1, 'regular')]
        else:
            starter = 'player' if self.round % 2 == 1 else 'ai'
            other = 'ai' if starter == 'player' else 'player'
            self._draw_seq = [(starter, 1, 'regular'), (other, 2, 'regular'), (starter, 1, 'regular')]
        self._draw_seq_idx = 0
        while not self.multiplayer and self._draw_seq_idx < len(self._draw_seq) and self._draw_seq[self._draw_seq_idx][0] == 'ai':
            _, count, card_type = self._draw_seq[self._draw_seq_idx]
            self._perform_ai_draw(count, card_type)
            self._draw_seq_idx += 1
        if self._draw_seq_idx >= len(self._draw_seq):
            self._finish_draw_sequence()
            return
        self._apply_draw_step()
        first_side = self._draw_seq[self._draw_seq_idx][0]
        self._set_phase_for_side(first_side)

    def _apply_draw_step(self):
        """Set pending_picks/pending_flag_picks from current step."""
        if self._draw_seq_idx >= len(self._draw_seq):
            return
        _, count, card_type = self._draw_seq[self._draw_seq_idx]
        self.pending_picks = count
        self.pending_flag_picks = count if card_type == 'flag' else 0

    def _advance_draw_sequence(self):
        """Move to next step. Returns (side, count, card_type) or None if done."""
        self._draw_seq_idx += 1
        if self._draw_seq_idx >= len(self._draw_seq):
            return None
        side, count, card_type = self._draw_seq[self._draw_seq_idx]
        self.pending_picks = count
        self.pending_flag_picks = count if card_type == 'flag' else 0
        return side, count, card_type

    def _perform_ai_draw(self, count, card_type):
        """Draw `count` cards for AI from spectator_pool."""
        if card_type == 'flag':
            daimyo = [c for c in self.spectator_pool if c.get('identity') == '大名']
            to_pick = daimyo[:count]
            picked_ids = {c['id'] for c in to_pick}
            self.spectator_pool = [c for c in self.spectator_pool if c['id'] not in picked_ids]
            for c in to_pick:
                self.ai.flag_generals.append(deepcopy(c))
                self.ai.collection.append(c)
                self.ai.total_draws += 1
            if to_pick:
                self._log(f'电脑选择了旗本 {to_pick[0]["name"]}', 'info')
        else:
            to_pick = self.spectator_pool[:count]
            self.spectator_pool = self.spectator_pool[count:]
            for c in to_pick:
                self.ai.collection.append(c)
                self.ai.total_draws += 1
            if to_pick:
                self._log(f'电脑选择了{"、".join(c["name"] for c in to_pick)}', 'info')

    def _auto_draw_player(self, count, card_type):
        """Auto-draw `count` cards for the player from spectator_pool (no UI)."""
        if card_type == 'flag':
            daimyo = [c for c in self.spectator_pool if c.get('identity') == '大名']
            to_pick = daimyo[:count]
            picked_ids = {c['id'] for c in to_pick}
            self.spectator_pool = [c for c in self.spectator_pool if c['id'] not in picked_ids]
            for c in to_pick:
                self.player.flag_generals.append(deepcopy(c))
                self.player.collection.append(c)
                self.player.total_draws += 1
            if to_pick:
                self._log(f'自动选择旗本 {to_pick[0]["name"]}', 'info')
        else:
            to_pick = self.spectator_pool[:count]
            self.spectator_pool = self.spectator_pool[count:]
            for c in to_pick:
                self.player.collection.append(c)
                self.player.total_draws += 1
            if to_pick:
                self._log(f'自动选择{"、".join(c["name"] for c in to_pick)}', 'info')


    def _handle_step_complete(self):
        """Called when the current human-side drawing step is complete. Advances or finishes."""
        next_step = self._advance_draw_sequence()
        if next_step is None:
            self._finish_draw_sequence()
            return
        # Process consecutive AI steps in single-player
        while not self.multiplayer and next_step[0] == 'ai':
            self._perform_ai_draw(next_step[1], next_step[2])
            next_step = self._advance_draw_sequence()
            if next_step is None:
                self._finish_draw_sequence()
                return
        side = next_step[0]
        self._set_phase_for_side(side)

    def _set_phase_for_side(self, side):
        """Set game_phase based on who should draw next."""
        if side in ('player', 'host'):
            if self.multiplayer:
                self.game_phase = 'multiplayer_draw_host'
                self._log('等待房主抽卡', 'info')
            else:
                self.game_phase = 'draw'
                self._log('请抽卡', 'info')
        elif side in ('ai', 'guest'):
            if self.multiplayer:
                self.game_phase = 'multiplayer_draw_guest'
                self._log('等待对手抽卡', 'info')
            else:
                # Single-player AI draws are handled by _auto_draw_ai_step
                self._log('电脑自动抽卡', 'info')

    def _finish_draw_sequence(self):
        """Transition from draw phase to placement."""
        if self.round == 0:
            self.round = 1
            self.placed_this_turn = 0
            pi = self._decay_income(self.player)
            a_inc = self._decay_income(self.ai)
            self.player.troops += pi
            self.ai.troops += a_inc
            if self.multiplayer:
                self.host_placement_ready = False
                self.guest_placement_ready = False
                self.guest_placed_this_turn = 0
                for u in self.player.board:
                    if u: u.is_new_placement = False
                for u in self.ai.board:
                    if u: u.is_new_placement = False
                self.game_phase = 'multiplayer_place'
                self._log(f'第1回合 · 各获{pi}/{a_inc}兵力，请双方部署', 'info')
            else:
                self.game_phase = 'place_player'
                self._log(f'第1回合 · 各获{pi}/{a_inc}兵力，请部署', 'info')
        else:
            self.round += 1
            self.placed_this_turn = 0
            pi = a_inc = 0
            if self.round > 1:
                pi = self._decay_income(self.player)
                a_inc = self._decay_income(self.ai)
                self.player.troops += pi
                self.ai.troops += a_inc
            if self.multiplayer:
                self.host_placement_ready = False
                self.guest_placement_ready = False
                self.guest_placed_this_turn = 0
                for u in self.player.board:
                    if u: u.is_new_placement = False
                for u in self.ai.board:
                    if u: u.is_new_placement = False
                self.game_phase = 'multiplayer_place'
                income_str = f'，各获{pi}/{a_inc}兵力' if self.round > 1 else ''
                self._log(f'第{self.round}回合 · 抽牌完成{income_str}，请双方部署', 'info')
            else:
                self.game_phase = 'place_player'
                income_str = f'，各获{pi}/{a_inc}兵力' if self.round > 1 else ''
                self._log(f'第{self.round}回合 · 抽牌完成{income_str}，请部署', 'info')

    # ---- Draw options (human side: player / host) ----
    def draw_options(self):
        self._expire_cooldowns()
        if self.game_phase not in ('idle', 'draw', 'pick_card', 'multiplayer_draw_host', 'multiplayer_pick_host'):
            raise ValueError('不在抽卡阶段')
        # Reinitialize sequence for new rounds (after battle ends with phase='draw')
        if self._draw_seq_idx >= len(self._draw_seq):
            self._init_draw_sequence()
            # After cap is reached, _init_draw_sequence transitions phase to place_player.
            # Return gracefully with no options.
            if self.game_phase not in ('draw', 'pick_card', 'multiplayer_draw_host', 'multiplayer_pick_host'):
                self._pending_draw_options = None
                return
        if self._draw_seq_idx >= len(self._draw_seq):
            raise ValueError('抽卡序列已完成')
        side, count, card_type = self._draw_seq[self._draw_seq_idx]
        if side not in ('player', 'host'):
            raise ValueError('不是你的抽卡回合')
        # pending_picks / pending_flag_picks already set by _apply_draw_step
        if self.pending_picks <= 0 and card_type != 'flag':
            self.pending_picks = count
        if len(self.spectator_pool) <= 0:
            self.pending_picks = 0
            self.round += 1
            self.placed_this_turn = 0
            pi = a_inc = 0
            if self.round > 1:
                pi = self._decay_income(self.player)
                a_inc = self._decay_income(self.ai)
                self.player.troops += pi
                self.ai.troops += a_inc
            self.game_phase = 'place_player'
            income_str = f'（各获{pi}/{a_inc}兵力）' if self.round > 1 else ''
            self._log(f'第{self.round}回合 · 牌堆已空，直接放置{income_str}', 'info')
            return
        if self.pending_flag_picks > 0:
            daimyo = [c for c in self.spectator_pool if c.get('identity') == '大名']
            opts_count = min(3, len(daimyo))
            opts = daimyo[:opts_count]
            self._pending_draw_options = opts
            picked_ids = {c['id'] for c in opts}
            self.spectator_pool = [c for c in self.spectator_pool if c['id'] not in picked_ids]
        else:
            opts_count = min(3, len(self.spectator_pool))
            opts = self.spectator_pool[:opts_count]
            self.spectator_pool = self.spectator_pool[opts_count:]
            self._pending_draw_options = opts
        if self.multiplayer:
            self.game_phase = 'multiplayer_pick_host'
        else:
            self.game_phase = 'pick_card'

    def pick_card(self, char_id):
        if self.game_phase not in ('pick_card', 'multiplayer_pick_host'):
            raise ValueError('不在选卡阶段')
        opts = self._pending_draw_options or []
        selected = next((c for c in opts if c['id'] == char_id), None)
        if not selected:
            raise ValueError('无效选择')
        self._pending_draw_options = None
        side, _, _ = self._draw_seq[self._draw_seq_idx]
        assert side in ('player', 'host'), f'pick_card called but current side is {side}'
        self.player.collection.append(selected)
        if self.pending_flag_picks > 0:
            if selected.get('identity') != '大名':
                raise ValueError('旗本武将只能选择大名身份武将')
            self.player.flag_generals.append(deepcopy(selected))
            self.pending_flag_picks -= 1
            self._log(f'选择了旗本 {selected["name"]}（剩余{self.pending_flag_picks}名旗本待选）', 'win')
        else:
            self._log(f'选择了 {selected["name"]}', 'win')
        unchosen = [c for c in opts if c['id'] != char_id]
        self.spectator_pool.extend(unchosen)
        self.player.total_draws += 1
        self.pending_picks -= 1
        if self.pending_picks > 0:
            flag_hint = f'旗本{self.pending_flag_picks}名，' if self.pending_flag_picks > 0 else ''
            self.game_phase = 'multiplayer_pick_host' if self.multiplayer else 'pick_card'
            self._log(f'还需选择{flag_hint}{self.pending_picks}张', 'info')
            return
        self._handle_step_complete()

    def place_unit(self, char_id, cell, troops):
        if self.game_phase not in ('place_player', 'multiplayer_place'):
            raise ValueError('不在放置阶段')
        if self.placed_this_turn >= PLACE_PER_ROUND:
            raise ValueError('本回合放置次数已用完')
        if not (0 <= cell < HEX_SIZE):
            raise ValueError('无效格子')
        if HEX_DEPTH[cell] <= 0:
            raise ValueError('只能在己方区域放置')
        if not self._is_active_cell(cell):
            raise ValueError('此格不可用')
        if self.player.board[cell] or self.ai.board[cell]:
            raise ValueError('此格已有单位')
        if self._is_behind_enemy_line(cell, True):
            raise ValueError('不可放置在敌方棋子后方')
        if self.round > 1 and self._is_in_front_of_friendly(cell, True):
            raise ValueError('不可放置在友军前方')
        char = next((c for c in self.player.collection if c['id'] == char_id), None)
        if not char:
            raise ValueError('武将不在玩家卡组中')
        if any(u and u.char['id'] == char_id for u in self.player.board if u):
            raise ValueError('该武将已在棋盘上')
        if any(u and u.char['id'] == char_id for u in self.ai.board if u):
            raise ValueError('敌方已有该武将')
        if troops > self.player.troops:
            raise ValueError('兵力不足')
        if troops > min(MAX_TROOPS_PER_UNIT, char['leadership'] * 100):
            raise ValueError('兵力超出上限')

        # No flag on board → next placement must be a flag general
        if self.player.flag_idx == -1:
            unlocked_flags = [fg for fg in self.player.flag_generals if fg['id'] not in self.player.locked_flag_ids]
            if unlocked_flags:
                is_flag_gen = any(fg['id'] == char_id for fg in unlocked_flags)
                if not is_flag_gen:
                    raise ValueError('旗本不在场上，必须先放置旗本武将')
                elif cell not in PLAYER_FLAG_CELLS and not self.lone_brave_player:
                    raise ValueError('旗本武将只能在己方旗本区域放置')

        self.unit_id_counter += 1
        uid = self.unit_id_counter
        u = Unit(char, troops, uid, is_new_placement=True)
        self.player.board[cell] = u
        self.uid_char_map[uid] = char
        self.uid_side_map[uid] = 'player'
        self._pin_from_placement(cell, True)
        self.player.troops -= troops
        self.placed_this_turn += 1

        is_flag_gen = any(fg['id'] == char_id for fg in self.player.flag_generals)
        if is_flag_gen:
            if char_id in self.player.locked_flag_ids:
                raise ValueError('该旗本已被锁定，无法上场')
            if self.player.current_flag_char_id is not None and self.player.current_flag_char_id != char_id:
                raise ValueError('已有旗本在场上，只能同时放置一名旗本')
            self.player.current_flag_char_id = char_id
            self.player.flag_idx = cell
            self._log(f'放置旗本 {char["name"]} 🚩', 'win')
        else:
            self._log(f'放置 {char["name"]}', 'win')

    def end_placement(self):
        if self.game_phase not in ('place_player', 'multiplayer_place'):
            raise ValueError('不在放置阶段')
        if not any(self.player.board[i] and self.player.flag_idx == i for i in range(HEX_SIZE) if self.player.board[i]):
            unlocked = [fg for fg in self.player.flag_generals if fg['id'] not in self.player.locked_flag_ids]
            has_flag_unit = any(u and u.char['id'] == self.player.current_flag_char_id for u in self.player.board if u)
            if unlocked and not has_flag_unit and self.player.current_flag_char_id is not None:
                self.player.flag_idx = -1
            elif unlocked and not has_flag_unit:
                self.player.flag_idx = -1
                self._log('尚未放置旗本，旗手位置空缺', 'info')
            else:
                if not any(u for u in self.player.board if u):
                    raise ValueError('请至少放置一名武将')

        if self.multiplayer:
            if self.game_phase == 'multiplayer_place':
                self.host_placement_ready = True
                self._log('你已完成放置，等待对方...', 'info')
                if self.host_placement_ready and self.guest_placement_ready:
                    self._log('双方放置完成！', 'info')
                    self._advance_phase()
                return
            self.placed_this_turn = 0
            self.game_phase = 'place_guest'
            self._log('等待对手放置', 'info')
        else:
            self.game_phase = 'place_ai'
            self._ai_placement()
            self._end_ai_place()

    # ---- Multiplayer guest methods ----
    def draw_options_guest(self):
        """Guest draws cards (in multiplayer mode only)."""
        self._expire_cooldowns()
        if self.game_phase not in ('multiplayer_draw_guest', 'multiplayer_pick_guest'):
            raise ValueError('不在抽卡阶段')
        if self._draw_seq_idx >= len(self._draw_seq):
            self._init_draw_sequence()
            if self.game_phase not in ('multiplayer_draw_guest', 'multiplayer_pick_guest'):
                self._pending_draw_options = None
                return
        if self._draw_seq_idx >= len(self._draw_seq):
            raise ValueError('抽卡序列已完成')
        side, count, card_type = self._draw_seq[self._draw_seq_idx]
        if side != 'guest':
            raise ValueError('不是对手的抽卡回合')
        if self.pending_picks <= 0 and card_type != 'flag':
            self.pending_picks = count
        if len(self.spectator_pool) <= 0:
            self.pending_picks = 0
            self._finish_draw_sequence()
            return
        if self.pending_flag_picks > 0:
            daimyo = [c for c in self.spectator_pool if c.get('identity') == '大名']
            opts_count = min(3, len(daimyo))
            opts = daimyo[:opts_count]
            self._pending_draw_options = opts
            picked_ids = {c['id'] for c in opts}
            self.spectator_pool = [c for c in self.spectator_pool if c['id'] not in picked_ids]
        else:
            opts_count = min(3, len(self.spectator_pool))
            opts = self.spectator_pool[:opts_count]
            self.spectator_pool = self.spectator_pool[opts_count:]
            self._pending_draw_options = opts
        self.game_phase = 'multiplayer_pick_guest'

    def pick_card_guest(self, char_id):
        if self.game_phase != 'multiplayer_pick_guest':
            raise ValueError('不在选卡阶段')
        opts = self._pending_draw_options or []
        selected = next((c for c in opts if c['id'] == char_id), None)
        if not selected:
            raise ValueError('无效选择')
        self._pending_draw_options = None
        side, _, _ = self._draw_seq[self._draw_seq_idx]
        assert side == 'guest', f'pick_card_guest called but current side is {side}'
        self.ai.collection.append(selected)
        if self.pending_flag_picks > 0:
            if selected.get('identity') != '大名':
                raise ValueError('旗本武将只能选择大名身份武将')
            self.ai.flag_generals.append(deepcopy(selected))
            self.pending_flag_picks -= 1
            self._log(f'对手选择了旗本 {selected["name"]}（剩余{self.pending_flag_picks}名旗本待选）', 'info')
        else:
            self._log(f'对手选择了 {selected["name"]}', 'info')
        unchosen = [c for c in opts if c['id'] != char_id]
        self.spectator_pool.extend(unchosen)
        self.ai.total_draws += 1
        self.pending_picks -= 1
        if self.pending_picks > 0:
            flag_hint = f'旗本{self.pending_flag_picks}名，' if self.pending_flag_picks > 0 else ''
            self.game_phase = 'multiplayer_pick_guest'
            self._log(f'对手还需选择{flag_hint}{self.pending_picks}张', 'info')
            return
        # Step complete → advance
        next_step = self._advance_draw_sequence()
        if next_step is None:
            self._finish_draw_sequence()
            return
        next_side, _, _ = next_step
        if next_side == 'guest':
            # More guest draws (shouldn't happen in current patterns but handle gracefully)
            self.draw_options_guest()
            return
        self._set_phase_for_side(next_side)

    def place_unit_guest(self, char_id, cell, troops):
        """Player 2 places a unit on the ai side."""
        if self.game_phase not in ('place_guest', 'multiplayer_place'):
            raise ValueError('不在对手放置阶段')
        max_placed = PLACE_PER_ROUND - (self.placed_this_turn if self.game_phase == 'place_guest' else self.guest_placed_this_turn)
        if max_placed <= 0:
            raise ValueError('本回合放置次数已用完')
        if not (0 <= cell < HEX_SIZE):
            raise ValueError('无效格子')
        if HEX_DEPTH[cell] >= 0:
            raise ValueError('只能在己方区域放置')
        if not self._is_active_cell(cell):
            raise ValueError('此格不可用')
        if self.player.board[cell] or self.ai.board[cell]:
            raise ValueError('此格已有单位')
        if self._is_behind_enemy_line(cell, False):
            raise ValueError('不可放置在敌方棋子后方')
        if self.round > 1 and self._is_in_front_of_friendly(cell, False):
            raise ValueError('不可放置在友军前方')
        char = next((c for c in self.ai.collection if c['id'] == char_id), None)
        if not char:
            raise ValueError('武将不在卡组中')
        if any(u and u.char['id'] == char_id for u in self.ai.board if u):
            raise ValueError('该武将已在棋盘上')
        if any(u and u.char['id'] == char_id for u in self.player.board if u):
            raise ValueError('对方已有该武将')
        if troops > self.ai.troops:
            raise ValueError('兵力不足')
        if troops > min(MAX_TROOPS_PER_UNIT, char['leadership'] * 100):
            raise ValueError('兵力超出上限')

        if self.ai.flag_idx == -1:
            unlocked_flags = [fg for fg in self.ai.flag_generals if fg['id'] not in self.ai.locked_flag_ids]
            if unlocked_flags:
                is_flag_gen = any(fg['id'] == char_id for fg in unlocked_flags)
                if not is_flag_gen:
                    raise ValueError('旗本不在场上，必须先放置旗本武将')
                elif cell not in AI_FLAG_CELLS and not self.lone_brave_ai:
                    raise ValueError('旗本武将只能在己方旗本区域放置')

        self.unit_id_counter += 1
        uid = self.unit_id_counter
        unit = Unit(char, troops, uid, is_new_placement=True)
        self.ai.board[cell] = unit
        self.ai.troops -= troops
        if self.game_phase == 'multiplayer_place':
            self.guest_placed_this_turn += 1
        else:
            self.placed_this_turn += 1
        self.uid_char_map[uid] = deepcopy(char)
        self.uid_side_map[uid] = 'ai'

        if self.ai.flag_idx == -1:
            unlocked_flags = [fg for fg in self.ai.flag_generals if fg['id'] not in self.ai.locked_flag_ids]
            for fg in unlocked_flags:
                if fg['id'] == char_id:
                    self.ai.flag_idx = cell
                    self.ai.current_flag_char_id = char_id
                    self._log(f'对手旗帜部署至 {cell}', 'flag')
                    break

        self._pin_from_placement(cell, False)
        if self._is_adjacent_to_enemy(cell, False):
            self._log(f'对手 {char["name"]} 部署至 {cell}（与敌方邻接，被钉住）', 'info')
        else:
            self._log(f'对手 {char["name"]} 部署至 {cell}', 'info')

    def end_placement_guest(self):
        """Player 2 (guest) ends their placement phase, triggering battle."""
        if self.game_phase not in ('place_guest', 'multiplayer_place'):
            raise ValueError('不在放置阶段')
        if not any(self.ai.board[i] and self.ai.flag_idx == i for i in range(HEX_SIZE) if self.ai.board[i]):
            unlocked = [fg for fg in self.ai.flag_generals if fg['id'] not in self.ai.locked_flag_ids]
            has_flag_unit = any(u and u.char['id'] == self.ai.current_flag_char_id for u in self.ai.board if u)
            if unlocked and not has_flag_unit and self.ai.current_flag_char_id is not None:
                self.ai.flag_idx = -1
            elif unlocked and not has_flag_unit:
                self.ai.flag_idx = -1
                self._log('对手尚未放置旗本，旗手位置空缺', 'info')
            else:
                if not any(u for u in self.ai.board if u):
                    raise ValueError('请至少放置一名武将')

        if self.multiplayer and self.game_phase == 'multiplayer_place':
            self.guest_placement_ready = True
            self._log('你已完成放置，等待对方...', 'info')
            if self.host_placement_ready and self.guest_placement_ready:
                self._log('双方放置完成！', 'info')
                self._advance_phase()
            return
        self._end_ai_place()

    def _is_adjacent_to_enemy(self, cell, is_player):
        for ni in self._get_neighbor_indices(cell):
            if is_player:
                if self.ai.board[ni]:
                    return True
            else:
                if self.player.board[ni]:
                    return True
        return False

    def _auto_place_side(self, side, cells, is_player, max_place=None):
        if max_place is None:
            max_place = PLACE_PER_ROUND

        # Sort placement cells by |r| (front-most first)
        avail_cells = [i for i in cells if not side.board[i] and not (self.player.board[i] or self.ai.board[i])]
        avail_cells.sort(key=lambda i: abs(HEX_DEPTH[i]))

        # First, place unlocked flag generals if none is currently deployed
        if side.current_flag_char_id is None:
            unlocked_flags = [fg for fg in side.flag_generals
                              if fg['id'] not in side.locked_flag_ids
                              and not any(u and u.char['id'] == fg['id'] for u in self.player.board if u)
                              and not any(u and u.char['id'] == fg['id'] for u in self.ai.board if u)]
            if unlocked_flags and avail_cells:
                unlocked_flags.sort(key=lambda c: RATING_ORDER.get(c.get('rating', ''), 9))
                best_flag = unlocked_flags[0]
                lone_brave = (self.lone_brave_player if is_player else self.lone_brave_ai)
                flag_zone = PLAYER_FLAG_CELLS if is_player else AI_FLAG_CELLS
                flag_avail = [c for c in avail_cells if c in flag_zone] if not lone_brave else avail_cells
                if not flag_avail:
                    return
                cell = flag_avail[0]
                avail_cells.remove(cell)
                max_t = min(MAX_TROOPS_PER_UNIT, best_flag['leadership'] * 100, side.troops)
                t = max(500, min(max_t, round(best_flag['martial'] * 60 + best_flag['leadership'] * 40)))
                self.unit_id_counter += 1
                nuid = self.unit_id_counter
                u = Unit(best_flag, t, nuid, is_new_placement=True)
                side.board[cell] = u
                self.uid_char_map[nuid] = best_flag
                self.uid_side_map[nuid] = 'player' if is_player else 'ai'
                self._pin_from_placement(cell, is_player)
                side.troops = max(0, side.troops - t)
                side.current_flag_char_id = best_flag['id']
                side.flag_idx = cell
                max_place -= 1

        avail = [c for c in side.collection
                 if not any(u and u.char['id'] == c['id'] for u in self.player.board if u)
                 and not any(u and u.char['id'] == c['id'] for u in self.ai.board if u)
                 and not self._is_on_cooldown(c['id'], is_player)
                 and not self._is_dead(c['id'])]
        avail.sort(key=lambda c: RATING_ORDER.get(c.get('rating', ''), 9))

        max_units = 12
        remain_slots = max_units - len([u for u in side.board if u])
        to_place = min(max_place, len(avail), remain_slots, len(avail_cells))
        if to_place == 0:
            return

        # Front cells: closer to r=0, back cells: closer to max |r|
        mid = len(avail_cells) // 2
        front_cells = avail_cells[:mid]
        back_cells = avail_cells[mid:]
        shuffle(front_cells)
        shuffle(back_cells)

        support_preferred = []
        placed = 0

        for ch in avail:
            if placed >= to_place:
                break
            combat = ch['leadership'] + ch['martial']
            support = ch['intelligence'] + ch['politics']
            cell = None

            if combat >= support:
                if front_cells:
                    cell = front_cells.pop()
                elif support_preferred:
                    cell = support_preferred.pop(0)
                    if cell in back_cells:
                        back_cells.remove(cell)
                elif back_cells:
                    cell = back_cells.pop()
                else:
                    break
            else:
                found = False
                while support_preferred:
                    c = support_preferred.pop(0)
                    if not side.board[c] and c in back_cells:
                        cell = c
                        back_cells.remove(c)
                        found = True
                        break
                if not found and back_cells:
                    cell = back_cells.pop()
                elif not found and front_cells:
                    cell = front_cells.pop()
                elif not found:
                    break

            max_t = min(MAX_TROOPS_PER_UNIT, ch['leadership'] * 100, side.troops)
            t = max(500, min(max_t, round(ch['martial'] * 60 + ch['leadership'] * 40)))
            self.unit_id_counter += 1
            nuid = self.unit_id_counter
            u = Unit(ch, t, nuid, is_new_placement=True)
            side.board[cell] = u
            self.uid_char_map[nuid] = ch
            self.uid_side_map[nuid] = 'player' if is_player else 'ai'
            self._pin_from_placement(cell, is_player)
            side.troops = max(0, side.troops - t)
            placed += 1

    def _ai_placement(self):
        self._auto_place_side(self.ai, HEX_AI_CELLS, False)

    def _end_ai_place(self):
        if not any(self.ai.board[i] and self.ai.flag_idx == i for i in range(HEX_SIZE) if self.ai.board[i]):
            self.ai.flag_idx = -1
        self._log('敌方放置完成', 'info')
        self._advance_phase()

    def _try_recruit_ai(self):
        surviving = sum(1 for c in self.ai.collection if not self._is_dead(c['id']))
        if surviving >= 10 or len(self.spectator_pool) == 0:
            return
        best = min(self.spectator_pool, key=lambda c: RATING_ORDER.get(c.get('rating', ''), 9))
        self.spectator_pool.remove(best)
        self.ai.collection.append(best)
        self._log(f'敌方招募了 {best["name"]} 加入阵营', 'info')

    def _surviving_count(self, side):
        return sum(1 for c in side.collection if not self._is_dead(c['id']))

    def auto_place_my_side(self, is_host):
        if self.game_phase != 'multiplayer_place':
            raise ValueError('不在多人放置阶段')
        if is_host:
            prev = len([u for u in self.player.board if u])
            self._auto_place_side(self.player, HEX_PLAYER_CELLS, True, PLACE_PER_ROUND - self.placed_this_turn)
            placed = len([u for u in self.player.board if u]) - prev
            if placed > 0:
                self.placed_this_turn += placed
            self.host_placement_ready = True
            self._log(f'你已完成托管放置{placed}名武将，等待对方...', 'info')
        else:
            prev = len([u for u in self.ai.board if u])
            self._auto_place_side(self.ai, HEX_AI_CELLS, False, PLACE_PER_ROUND - self.guest_placed_this_turn)
            placed = len([u for u in self.ai.board if u]) - prev
            if placed > 0:
                self.guest_placed_this_turn += placed
            self.guest_placement_ready = True
            self._log(f'你已完成托管放置{placed}名武将，等待对方...', 'info')
        if self.host_placement_ready and self.guest_placement_ready:
            self._log('双方放置完成！', 'info')
            self._advance_phase()

    def auto_place_remaining(self):
        if self.game_phase not in ('place_player', 'multiplayer_place'):
            raise ValueError('不在放置阶段')
        prev_count = len([u for u in self.player.board if u])
        self._auto_place_side(self.player, HEX_PLAYER_CELLS, True, PLACE_PER_ROUND - self.placed_this_turn)
        placed = len([u for u in self.player.board if u]) - prev_count
        if placed > 0:
            self.placed_this_turn += placed
            self._log(f'自动放置{placed}名武将', 'info')
        if self.multiplayer:
            self._auto_place_side(self.ai, HEX_AI_CELLS, False, PLACE_PER_ROUND - self.guest_placed_this_turn)
            self.host_placement_ready = True
            self.guest_placement_ready = True
            self._log('双方托管放置完成', 'info')
            self._advance_phase()
            return
        self._ai_placement()
        self._end_ai_place()

    def _advance_phase(self):
        self.game_phase = 'battle'

        p_flag_unit = self.player.board[self.player.flag_idx] if self.player.flag_idx >= 0 else None
        a_flag_unit = self.ai.board[self.ai.flag_idx] if self.ai.flag_idx >= 0 else None

        for i in range(HEX_SIZE):
            if self.player.board[i] and self.player.board[i].pinned and not self._has_adjacent_enemy(i, True):
                self.player.board[i].pinned = False
            if self.ai.board[i] and self.ai.board[i].pinned and not self._has_adjacent_enemy(i, False):
                self.ai.board[i].pinned = False

        init_troops_by_uid = {}
        pre_board_units = {}
        for i in range(HEX_SIZE):
            if self.player.board[i]:
                init_troops_by_uid[self.player.board[i].uid] = self.player.board[i].troops
                pre_board_units[self.player.board[i].uid] = {
                    'name': self.player.board[i].char['name'],
                    'char_id': self.player.board[i].char['id'],
                    'side': '我方'
                }
            if self.ai.board[i]:
                init_troops_by_uid[self.ai.board[i].uid] = self.ai.board[i].troops
                pre_board_units[self.ai.board[i].uid] = {
                    'name': self.ai.board[i].char['name'],
                    'char_id': self.ai.board[i].char['id'],
                    'side': '敌方'
                }

        engaged_p = set()
        engaged_a = set()
        adj_pairs = []
        gap_battles = []
        ranged_attacks = []

        for i in range(HEX_SIZE):
            if self.player.board[i]:
                for fi, si in HEX_FORWARD_LINE_PLAYER[i]:
                    if fi is None:
                        continue
                    e1 = self.ai.board[fi]
                    if e1:
                        engaged_p.add(i)
                        adj_pairs.append({'pIdx': i, 'aIdx': fi})
                    elif self.player.board[fi]:
                        if si is not None and self.ai.board[si]:
                            engaged_p.add(i)
                            ranged_attacks.append({'attackerIdx': i, 'targetIdx': si, 'isPlayer': True})
                    else:
                        if si is not None and self.ai.board[si]:
                            engaged_p.add(i)
                            gap_battles.append({'pIdx': i, 'aIdx': si, 'gapIdx': fi})

            if self.ai.board[i]:
                for fi, si in HEX_FORWARD_LINE_AI[i]:
                    if fi is None:
                        continue
                    e1 = self.player.board[fi]
                    if e1:
                        engaged_a.add(i)
                        if not any(p['aIdx'] == i for p in adj_pairs):
                            adj_pairs.append({'pIdx': fi, 'aIdx': i})
                    elif self.ai.board[fi]:
                        if si is not None and self.player.board[si]:
                            engaged_a.add(i)
                            ranged_attacks.append({'attackerIdx': i, 'targetIdx': si, 'isPlayer': False})
                    else:
                        if si is not None and self.player.board[si]:
                            engaged_a.add(i)
                            if not any(g['aIdx'] == i for g in gap_battles):
                                gap_battles.append({'pIdx': si, 'aIdx': i, 'gapIdx': fi})

        for i in range(HEX_SIZE):
            if self.player.board[i] and self.player.board[i].pinned:
                engaged_p.add(i)
            if self.ai.board[i] and self.ai.board[i].pinned:
                engaged_a.add(i)

        p_desires = []
        a_desires = []
        for i in range(HEX_SIZE):
            if self.player.board[i] and i not in engaged_p:
                candidates = [fi for fi in HEX_PLAYER_FORWARD[i] if fi is not None and not self.player.board[fi] and not self.ai.board[fi] and self._is_active_cell(fi)]
                u = self.player.board[i]
                p_desires.append({'idx': i, 'unit': u, 'troops': u.troops, 'power': u.char['martial'] + u.char['leadership'], 'candidates': candidates})
            if self.ai.board[i] and i not in engaged_a:
                candidates = [fi for fi in HEX_AI_FORWARD[i] if fi is not None and not self.player.board[fi] and not self.ai.board[fi] and self._is_active_cell(fi)]
                u = self.ai.board[i]
                a_desires.append({'idx': i, 'unit': u, 'troops': u.troops, 'power': u.char['martial'] + u.char['leadership'], 'candidates': candidates})

        p_desires.sort(key=lambda d: (-d['troops'], -d['power']))
        a_desires.sort(key=lambda d: (-d['troops'], -d['power']))

        p_moves = []
        a_moves = []
        p_claimed = set()
        a_claimed = set()

        for d in p_desires:
            t = d['idx']
            for ci in d['candidates']:
                if ci not in p_claimed:
                    t = ci
                    p_claimed.add(ci)
                    break
            p_moves.append({'from': d['idx'], 'to': t, 'unit': d['unit']})

        for d in a_desires:
            t = d['idx']
            for ci in d['candidates']:
                if ci not in a_claimed:
                    t = ci
                    a_claimed.add(ci)
                    break
            a_moves.append({'from': d['idx'], 'to': t, 'unit': d['unit']})

        for i in range(HEX_SIZE):
            if self.player.board[i] and i in engaged_p:
                p_moves.append({'from': i, 'to': i, 'unit': self.player.board[i]})
            if self.ai.board[i] and i in engaged_a:
                a_moves.append({'from': i, 'to': i, 'unit': self.ai.board[i]})

        p_orig_targets = {m['to'] for m in p_moves if m['to'] != m['from']}
        a_orig_targets = {m['to'] for m in a_moves if m['to'] != m['from']}

        p_target_map = {}
        a_target_map = {}
        for m in p_moves:
            if m['to'] != m['from']:
                p_target_map[m['to']] = m
        for m in a_moves:
            if m['to'] != m['from']:
                a_target_map[m['to']] = m

        contested = [t for t in p_target_map if t in a_target_map]
        contested_info = []
        for cell in contested:
            pm = p_target_map[cell]
            am = a_target_map[cell]
            contested_info.append({
                'cell': cell, 'pm': pm, 'am': am,
                'pPower': self._calc_battle_power(pm['from'], True),
                'aPower': self._calc_battle_power(am['from'], False),
            })

        self.player.board = [None] * HEX_SIZE
        self.ai.board = [None] * HEX_SIZE

        all_res = []

        for m in p_moves:
            if m['to'] not in contested:
                self.player.board[m['to']] = m['unit']
                self._check_first_scaler(m['to'], True)
        for m in a_moves:
            if m['to'] not in contested:
                self.ai.board[m['to']] = m['unit']
                self._check_first_scaler(m['to'], False)

        front_done = set()
        for ci in contested_info:
            cell = ci['cell']
            pm = ci['pm']
            am = ci['am']
            pu = pm['unit']
            au = am['unit']
            p_power = ci['pPower']
            a_power = ci['aPower']
            pn = pu.char['name']
            an = au.char['name']
            result = self._calc_battle(pu, au, p_power, a_power, 1)
            p_loss = result['pLoss']
            a_loss = result['aLoss']
            p_loss_pct = result['pLossPct']
            a_loss_pct = result['aLossPct']
            pu.troops = max(0, pu.troops - p_loss)
            au.troops = max(0, au.troops - a_loss)

            if p_loss > 0:
                self._record_melee(au.uid, pu.uid, p_loss)
            if a_loss > 0:
                self._record_melee(pu.uid, au.uid, a_loss)

            p_alive = pu.troops > 0
            a_alive = au.troops > 0
            if not p_alive:
                self._mark_cooldown(pu.char['id'], True)
                self._record_kill(au.uid)
            if not a_alive:
                self._mark_cooldown(au.char['id'], False)
                self._record_kill(pu.uid)

            if p_alive and not a_alive:
                self.player.board[cell] = pu
                self._check_first_scaler(cell, True)
                self._log(f'⚔ 抢占！{pn} 击溃 {an}，进入阵地', 'win')
            elif not p_alive and a_alive:
                self.ai.board[cell] = au
                self._check_first_scaler(cell, False)
                self._log(f'⚔ 抢占！{an} 击溃 {pn}，进入阵地', 'lose')
            elif p_alive and a_alive:
                if p_loss_pct < a_loss_pct:
                    self.player.board[cell] = pu
                    self.ai.board[am['from']] = au
                    self._check_first_scaler(cell, True)
                    self._log(f'⚔ 争夺！{pn}({round(p_loss_pct * 100)}%) 胜 {an}({round(a_loss_pct * 100)}%)，{pn}前进', 'win')
                else:
                    self.ai.board[cell] = au
                    self.player.board[pm['from']] = pu
                    self._check_first_scaler(cell, False)
                    self._log(f'⚔ 争夺！{an}({round(a_loss_pct * 100)}%) 胜 {pn}({round(a_loss_pct * 100)}%)，{an}前进', 'lose')
            front_done.add(cell)

        for g in gap_battles:
            pu = self.player.board[g['pIdx']]
            au = self.ai.board[g['aIdx']]
            if not pu or not au:
                continue
            p_power = self._calc_battle_power(g['pIdx'], True)
            a_power = self._calc_battle_power(g['aIdx'], False)
            pn = pu.char['name']
            an = au.char['name']
            result = self._calc_battle(pu, au, p_power, a_power, 1)
            p_loss = result['pLoss']
            a_loss = result['aLoss']
            p_loss_pct = result['pLossPct']
            a_loss_pct = result['aLossPct']
            pu.troops = max(0, pu.troops - p_loss)
            au.troops = max(0, au.troops - a_loss)
            if p_loss > 0:
                self._record_melee(au.uid, pu.uid, p_loss)
            if a_loss > 0:
                self._record_melee(pu.uid, au.uid, a_loss)
            p_alive = pu.troops > 0
            a_alive = au.troops > 0
            if not p_alive:
                self._mark_cooldown(pu.char['id'], True)
                self._record_kill(au.uid)
            if not a_alive:
                self._mark_cooldown(au.char['id'], False)
                self._record_kill(pu.uid)

            adv = ''
            if self._is_active_cell(g['gapIdx']):
                if p_alive and not a_alive:
                    self.player.board[g['gapIdx']] = pu
                    self.player.board[g['pIdx']] = None
                    self._check_first_scaler(g['gapIdx'], True)
                    adv = pn
                elif not p_alive and a_alive:
                    self.ai.board[g['gapIdx']] = au
                    self.ai.board[g['aIdx']] = None
                    self._check_first_scaler(g['gapIdx'], False)
                    adv = an
                elif p_alive and a_alive:
                    if p_loss_pct < a_loss_pct:
                        self.player.board[g['gapIdx']] = pu
                        self.player.board[g['pIdx']] = None
                        self._check_first_scaler(g['gapIdx'], True)
                        adv = pn
                    elif a_loss_pct < p_loss_pct:
                        self.ai.board[g['gapIdx']] = au
                        self.ai.board[g['aIdx']] = None
                        self._check_first_scaler(g['gapIdx'], False)
                        adv = an
            front_done.add(g['pIdx'])
            front_done.add(g['aIdx'])
            p_tag = '优' if p_power > a_power else ('劣' if p_power < a_power else '均')
            a_tag = '优' if a_power > p_power else ('劣' if a_power < p_power else '均')
            all_res.append(f'[前激战] {pn if p_alive else "💀" + pn}({p_tag})(损{int(p_loss_pct * 100)}%) ⚔ {an if a_alive else "💀" + an}({a_tag})(损{int(a_loss_pct * 100)}%)' + (f' → {adv}推进' if adv else ' → 对峙'))

        for r in ranged_attacks:
            attacker = self.player.board[r['attackerIdx']] if r['isPlayer'] else self.ai.board[r['attackerIdx']]
            defender = self.ai.board[r['targetIdx']] if r['isPlayer'] else self.player.board[r['targetIdx']]
            if not attacker or not defender:
                continue
            a_power = self._calc_battle_power(r['attackerIdx'], r['isPlayer'])
            d_power = self._calc_battle_power(r['targetIdx'], not r['isPlayer'])
            an = attacker.char['name']
            dn = defender.char['name']
            a_full = attacker.troops
            d_full = defender.troops
            damage = self._calc_ranged_damage(attacker, defender, a_power, d_power)
            defender.troops = max(0, defender.troops - damage)
            if damage > 0:
                self._record_ranged(attacker.uid, defender.uid, damage)
            d_alive = defender.troops > 0
            if not d_alive:
                self._mark_cooldown(defender.char['id'], not r['isPlayer'])
                self._record_kill(attacker.uid)
            pct = round(damage / d_full * 100) if d_full > 0 else 0
            all_res.append(f'[远程] {an} → {dn} 射伤{damage}({pct}%){" 💀击毙" if not d_alive else ""}')

        for i in range(HEX_SIZE):
            pu = self.player.board[i]
            au = self.ai.board[i]
            if not pu or not au or i in front_done:
                continue
            p_power = self._calc_battle_power(i, True)
            a_power = self._calc_battle_power(i, False)
            pn = pu.char['name']
            an = au.char['name']
            p_full = pu.troops
            a_full = au.troops
            result = self._calc_battle(pu, au, p_power, a_power, 1)
            p_loss = result['pLoss']
            a_loss = result['aLoss']
            p_loss_pct = result['pLossPct']
            a_loss_pct = result['aLossPct']
            pu.troops = max(0, pu.troops - p_loss)
            au.troops = max(0, au.troops - a_loss)
            if p_loss > 0:
                self._record_melee(au.uid, pu.uid, p_loss)
            if a_loss > 0:
                self._record_melee(pu.uid, au.uid, a_loss)
            p_alive = pu.troops > 0
            a_alive = au.troops > 0
            if not p_alive:
                self._mark_cooldown(pu.char['id'], True)
                self._record_kill(au.uid)
            if not a_alive:
                self._mark_cooldown(au.char['id'], False)
                self._record_kill(pu.uid)
            if p_alive:
                self.player.board[i] = pu
            else:
                self.player.board[i] = None
            if a_alive:
                self.ai.board[i] = au
            else:
                self.ai.board[i] = None
            p_tag = '优' if p_power > a_power else ('劣' if p_power < a_power else '均')
            a_tag = '优' if a_power > p_power else ('劣' if a_power < p_power else '均')
            if p_alive and a_alive:
                if p_loss_pct < a_loss_pct:
                    self.player.board[i] = pu
                    self.ai.board[i] = None
                    for fi in HEX_AI_FORWARD[i]:
                        if fi is not None and self._is_active_cell(fi) and not self.player.board[fi] and not self.ai.board[fi]:
                            self.ai.board[fi] = au
                            au.pinned = True
                            break
                    else:
                        self.ai.board[i] = au
                        au.pinned = True
                    all_res.append(f'[前胜] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) 击退 {an}({a_tag})(损{int(a_loss_pct * 100)}%)')
                elif a_loss_pct < p_loss_pct:
                    self.ai.board[i] = au
                    self.player.board[i] = None
                    for fi in HEX_PLAYER_FORWARD[i]:
                        if fi is not None and self._is_active_cell(fi) and not self.player.board[fi] and not self.ai.board[fi]:
                            self.player.board[fi] = pu
                            pu.pinned = True
                            break
                    else:
                        self.player.board[i] = pu
                        pu.pinned = True
                    all_res.append(f'[前败] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) 被 {an}({a_tag})(损{int(a_loss_pct * 100)}%) 击退')
                else:
                    self.ai.board[i] = None
                    for fi in HEX_AI_FORWARD[i]:
                        if fi is not None and self._is_active_cell(fi) and not self.player.board[fi] and not self.ai.board[fi]:
                            self.ai.board[fi] = au
                            break
                    else:
                        self.ai.board[i] = au
                    self.player.board[i] = pu
                    all_res.append(f'[前对峙] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) ⚔ {an}({a_tag})(损{int(a_loss_pct * 100)}%)')
            elif p_alive and not a_alive:
                all_res.append(f'[前胜] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) 击败 💀{an}')
            elif not p_alive and a_alive:
                all_res.append(f'[前败] 💀{pn}({p_tag}) 被 {an}({a_tag})(损{int(a_loss_pct * 100)}%) 击败')
            else:
                all_res.append(f'[前同尽] 💀{pn} ⚔ 💀{an}')
            front_done.add(i)

        for i in range(HEX_SIZE):
            if i in front_done:
                continue
            pu = self.player.board[i]
            au = self.ai.board[i]
            if not pu or not au:
                continue
            p_power = self._calc_battle_power(i, True)
            a_power = self._calc_battle_power(i, False)
            pn = pu.char['name']
            an = au.char['name']
            p_full = pu.troops
            a_full = au.troops
            result = self._calc_battle(pu, au, p_power, a_power, 1)
            p_loss = result['pLoss']
            a_loss = result['aLoss']
            p_loss_pct = result['pLossPct']
            a_loss_pct = result['aLossPct']
            pu.troops = max(0, pu.troops - p_loss)
            au.troops = max(0, au.troops - a_loss)
            if p_loss > 0:
                self._record_melee(au.uid, pu.uid, p_loss)
            if a_loss > 0:
                self._record_melee(pu.uid, au.uid, a_loss)
            p_alive = pu.troops > 0
            a_alive = au.troops > 0
            if not p_alive:
                self._mark_cooldown(pu.char['id'], True)
                self._record_kill(au.uid)
            if not a_alive:
                self._mark_cooldown(au.char['id'], False)
                self._record_kill(pu.uid)
            if p_alive:
                self.player.board[i] = pu
            else:
                self.player.board[i] = None
            if a_alive:
                self.ai.board[i] = au
            else:
                self.ai.board[i] = None
            p_tag = '优' if p_power > a_power else ('劣' if p_power < a_power else '均')
            a_tag = '优' if a_power > p_power else ('劣' if a_power < p_power else '均')
            if p_alive and a_alive:
                pu.pinned = True
                au.pinned = True
                all_res.append(f'[前对峙] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) ⚔ {an}({a_tag})(损{int(a_loss_pct * 100)}%)')
            elif p_alive and not a_alive:
                all_res.append(f'[前胜] {pn}({p_tag})(损{int(p_loss_pct * 100)}%) 击败 💀{an}')
            elif not p_alive and a_alive:
                all_res.append(f'[前败] 💀{pn} 被 {an}({a_tag})(损{int(a_loss_pct * 100)}%) 击败')
            else:
                all_res.append(f'[前同尽] 💀{pn} ⚔ 💀{an}')
            front_done.add(i)

        # Flanking (side) battles: non-forward adjacent enemies
        sbattles = []
        side_done = set()
        for i in range(HEX_SIZE):
            if i in side_done:
                continue
            pu = self.player.board[i]
            if not pu:
                continue
            for ni in HEX_NEIGHBORS[i]:
                if ni in side_done:
                    continue
                au = self.ai.board[ni]
                if not au:
                    continue
                # Only non-forward-adjacent pairs (skip forward pairs already handled)
                if (is_player_forward := ni in HEX_PLAYER_FORWARD[i]):
                    continue
                sbattles.append({'pIdx': i, 'aIdx': ni, 'pUnit': pu, 'aUnit': au,
                                 'pPower': self._calc_battle_power(i, True),
                                 'aPower': self._calc_battle_power(ni, False)})
                side_done.add(i)
                side_done.add(ni)
                break

        for b in sbattles:
            self.player.board[b['pIdx']] = None
            self.ai.board[b['aIdx']] = None

        for b in sbattles:
            p_idx = b['pIdx']
            a_idx = b['aIdx']
            p_unit = b['pUnit']
            a_unit = b['aUnit']
            p_power = b['pPower']
            a_power = b['aPower']
            pn = p_unit.char['name']
            an = a_unit.char['name']
            p_full = p_unit.troops
            a_full = a_unit.troops
            p_comm = p_full * 0.5
            a_comm = a_full * 0.5
            p_pol2 = p_unit.char['politics'] * (1.1 if self._is_flag_unit(p_idx, True) else 1)
            a_pol2 = a_unit.char['politics'] * (1.1 if self._is_flag_unit(a_idx, False) else 1)
            p_red2 = 1 - p_pol2 / 240
            a_red2 = 1 - a_pol2 / 240
            if p_power > a_power:
                p_loss = round(p_comm * 0.34 * p_red2)
                a_loss = round(a_comm * 0.8 * a_red2)
            elif a_power > p_power:
                p_loss = round(p_comm * 0.8 * p_red2)
                a_loss = round(a_comm * 0.34 * a_red2)
            else:
                p_loss = round(p_comm * 0.57 * p_red2)
                a_loss = round(a_comm * 0.57 * a_red2)
            p_unit.troops = max(0, p_unit.troops - p_loss)
            a_unit.troops = max(0, a_unit.troops - a_loss)
            if p_loss > 0:
                self._record_melee(a_unit.uid, p_unit.uid, p_loss)
            if a_loss > 0:
                self._record_melee(p_unit.uid, a_unit.uid, a_loss)
            p_alive = p_unit.troops > 0
            a_alive = a_unit.troops > 0
            if p_alive:
                self.player.board[p_idx] = p_unit
            else:
                self._mark_cooldown(p_unit.char['id'], True)
                self._record_kill(a_unit.uid)
            if a_alive:
                self.ai.board[a_idx] = a_unit
            else:
                self._mark_cooldown(a_unit.char['id'], False)
                self._record_kill(p_unit.uid)
            w = '胜' if p_power > a_power else ('败' if a_power > p_power else '平')
            s_tag = '优' if p_power > a_power else ('劣' if p_power < a_power else '均')
            all_res.append(f'[侧{w}] {pn if p_alive else "💀" + pn}({s_tag})(战{p_power}) ⚔ {an if a_alive else "💀" + an}(战{a_power})')

        for r in all_res:
            self._log(f'⚔ {r}', 'info')
        if not all_res:
            self._log('⚔ 无接触，无战斗', 'info')

        for i in range(HEX_SIZE):
            if self._is_triple_surrounded(i, True) and self.player.board[i]:
                self._log(f'⚠ {self.player.board[i].char["name"]} 陷入三方包围，属性-10%', 'lose')
                for ni in HEX_NEIGHBORS[i]:
                    if self.ai.board[ni]:
                        self._record_retreat(self.ai.board[ni].uid)
            if self._is_triple_surrounded(i, False) and self.ai.board[i]:
                self._log(f'⚠ 敌方 {self.ai.board[i].char["name"]} 陷入三方包围，属性-10%', 'win')
                for ni in HEX_NEIGHBORS[i]:
                    if self.player.board[ni]:
                        self._record_retreat(self.player.board[ni].uid)

        if p_flag_unit and not any(u and u.uid == p_flag_unit.uid for u in self.player.board if u):
            self.flag_scatter_count['player'] += 1
            self._log(f'⚠ 旗手战死！({self.flag_scatter_count["player"]}/3)', 'lose')
            self.player.locked_flag_ids.append(p_flag_unit.char['id'])
            self.player.current_flag_char_id = None
            self.player.flag_idx = -1
        if a_flag_unit and not any(u and u.uid == a_flag_unit.uid for u in self.ai.board if u):
            self.flag_scatter_count['ai'] += 1
            self._log(f'⚠ 敌方旗手战死！({self.flag_scatter_count["ai"]}/3)', 'win')
            self.ai.locked_flag_ids.append(a_flag_unit.char['id'])
            self.ai.current_flag_char_id = None
            self.ai.flag_idx = -1

        for side_is_player in (True, False):
            brd = self.player.board if side_is_player else self.ai.board
            for i in range(HEX_SIZE):
                u = brd[i]
                if not u:
                    continue
                sum_pol = u.char['politics']
                for ni in self._get_neighbor_indices(i):
                    nu = brd[ni]
                    if nu:
                        sum_pol += nu.char['politics']
                loss = (init_troops_by_uid.get(u.uid, 0) or 0) - u.troops
                if loss > 0:
                    rate = min(sum_pol * 0.001, 0.6)
                    u.troops = min(u.troops + int(loss * rate), 10000)

        for side_is_player in (True, False):
            brd = self.player.board if side_is_player else self.ai.board
            for i in range(HEX_SIZE):
                u = brd[i]
                if u and u.troops < 100:
                    died = False
                    if self.scatter_debuff.get(u.char['id']):
                        if not self._is_dead(u.char['id']):
                            self.dead_list.append(u.char['id'])
                        died = True
                        self._log(f'{"敌方" if not side_is_player else ""}{u.char["name"]} 再次溃散，战死沙场！★', 'lose')
                    else:
                        self.scatter_debuff[u.char['id']] = True
                        u.char['leadership'] = int(u.char['leadership'] * 0.9)
                        u.char['martial'] = int(u.char['martial'] * 0.9)
                        u.char['intelligence'] = int(u.char['intelligence'] * 0.9)
                        u.char['politics'] = int(u.char['politics'] * 0.9)
                        self._mark_cooldown(u.char['id'], side_is_player, 'scatter')
                        self._log(f'{"敌方" if not side_is_player else ""}{u.char["name"]} 兵力不足100，溃散！(全属性-10%)', 'lose')

                    if p_flag_unit and u.uid == p_flag_unit.uid:
                        self.flag_scatter_count['player'] += 1
                        self._log(f'⚠ 旗手溃散！({self.flag_scatter_count["player"]}/3)', 'lose')
                        self.player.locked_flag_ids.append(u.char['id'])
                        self.player.current_flag_char_id = None
                        self.player.flag_idx = -1
                    if a_flag_unit and u.uid == a_flag_unit.uid:
                        self.flag_scatter_count['ai'] += 1
                        self._log(f'⚠ 敌方旗手溃散！({self.flag_scatter_count["ai"]}/3)', 'win')
                        self.ai.locked_flag_ids.append(u.char['id'])
                        self.ai.current_flag_char_id = None
                        self.ai.flag_idx = -1
                    brd[i] = None

        current_uids = set()
        for i in range(HEX_SIZE):
            if self.player.board[i]:
                current_uids.add(self.player.board[i].uid)
            if self.ai.board[i]:
                current_uids.add(self.ai.board[i].uid)
        for uid, info in pre_board_units.items():
            if uid not in current_uids:
                if info['char_id'] in self.dead_list:
                    reason = '被击杀'
                elif self.scatter_debuff.get(info['char_id']):
                    reason = '击溃'
                else:
                    reason = '被击败'
                self._log(f'[离场] {info["side"]}{info["name"]} - {reason}', 'lose')

        self._try_recruit_ai()

        def find_flag(board, pu):
            if not pu:
                return -1
            for i in range(HEX_SIZE):
                if board[i] and board[i].uid == pu.uid:
                    return i
            return -1

        np_idx = find_flag(self.player.board, p_flag_unit)
        self.player.flag_idx = np_idx if np_idx >= 0 else -1

        na_idx = find_flag(self.ai.board, a_flag_unit)
        self.ai.flag_idx = na_idx if na_idx >= 0 else -1

        # 孤勇者: only flag generals remain → buff for surviving flag units
        p_non_flag = [i for i, u in enumerate(self.player.board) if u and not (
            self.player.flag_idx >= 0 and u.uid == self.player.board[self.player.flag_idx].uid)]
        a_non_flag = [i for i, u in enumerate(self.ai.board) if u and not (
            self.ai.flag_idx >= 0 and u.uid == self.ai.board[self.ai.flag_idx].uid)]
        if not p_non_flag and not a_non_flag:
            if any(u for u in self.player.board if u):
                self.lone_brave_player = True
            if any(u for u in self.ai.board if u):
                self.lone_brave_ai = True
            if self.lone_brave_round is None:
                self.lone_brave_round = self.round

        p_any = any(u for u in self.player.board if u)
        a_any = any(u for u in self.ai.board if u)

        p_td = [u for i, u in enumerate(self.player.board) if u and HEX_DEPTH[i] == AI_BASELINE_DEPTH]
        a_td = [u for i, u in enumerate(self.ai.board) if u and HEX_DEPTH[i] == PLAYER_BASELINE_DEPTH]
        if p_td or a_td:
            p_troops = sum(u.troops for u in p_td)
            a_troops = sum(u.troops for u in a_td)
            if p_td and (not a_td or p_troops >= a_troops):
                self.game_phase = 'gameover'
                self.winner = True
                self._log('🎉 达阵！我方大胜！' + (f'（{p_troops} vs {a_troops}）' if a_td else ''), 'win')
                return
            if a_td and (not p_td or a_troops > p_troops):
                self.game_phase = 'gameover'
                self.winner = False
                self._log('💀 达阵！敌方大胜！' + (f'（{p_troops} vs {a_troops}）' if p_td else ''), 'lose')
                return
        if len(self.spectator_pool) == 0 and not p_any and a_any:
            self.game_phase = 'gameover'
            self.winner = False
            self._log('💀 我方覆灭', 'lose')
            return
        if len(self.spectator_pool) == 0 and p_any and not a_any:
            self.game_phase = 'gameover'
            self.winner = True
            self._log('🎉 敌方覆灭', 'win')
            return
        if self.flag_scatter_count['player'] >= 3:
            self.game_phase = 'gameover'
            self.winner = False
            self._log('💀 旗手溃散3次，我方战败！', 'lose')
            return
        if self.flag_scatter_count['ai'] >= 3:
            self.game_phase = 'gameover'
            self.winner = True
            self._log('🎉 敌方旗手溃散3次，我方胜利！', 'win')
            return

        if self.player.total_draws >= MAX_DRAW_PER_SIDE and self.ai.total_draws >= MAX_DRAW_PER_SIDE:
            self.round += 1
            self.placed_this_turn = 0
            pi = a_inc = 0
            if self.round > 1:
                pi = self._decay_income(self.player)
                a_inc = self._decay_income(self.ai)
                self.player.troops += pi
                self.ai.troops += a_inc
            if self.multiplayer:
                self.host_placement_ready = False
                self.guest_placement_ready = False
                self.guest_placed_this_turn = 0
                for u in self.player.board:
                    if u: u.is_new_placement = False
                for u in self.ai.board:
                    if u: u.is_new_placement = False
                self.game_phase = 'multiplayer_place'
                income_str = f'，各获{pi}/{a_inc}兵力' if self.round > 1 else ''
                self._log(f'第{self.round}回合 · 抽牌封顶{income_str}，请双方部署', 'info')
            else:
                self.game_phase = 'place_player'
                income_str = f'，各获{pi}/{a_inc}兵力' if self.round > 1 else ''
                self._log(f'第{self.round}回合 · 抽牌封顶{income_str}，请部署', 'info')
        else:
            self.game_phase = 'draw'
            self.placed_this_turn = 0
            self._log(f'第{self.round}回合结束 · 请抽卡', 'info')

    def set_terrain(self, mode):
        if mode not in ('normal', 'nagashino', 'tennozan'):
            raise ValueError(f'无效地形模式: {mode}')
        self.terrain_mode = mode

    def to_dict(self):
        # Strip hit_details from combat_stats during regular play to reduce payload
        is_gameover = self.game_phase == 'gameover'
        combat_stats_out = {}
        for k, v in self.combat_stats.items():
            entry = dict(v)
            if not is_gameover:
                entry.pop('melee_hit_details', None)
                entry.pop('ranged_hit_details', None)
            combat_stats_out[str(k)] = entry
        return {
            'game_id': self.game_id,
            'round': self.round,
            'game_phase': self.game_phase,
            'placed_this_turn': self.placed_this_turn,
            'player': self.player.to_dict(),
            'ai': self.ai.to_dict(),
            'draw_pile_count': len(self.spectator_pool),
            'flag_scatter_count': dict(self.flag_scatter_count),
            'dead_list': list(self.dead_list),
            'spectator_pool': self.spectator_pool,
            'combat_stats': combat_stats_out,
            'player_cooldowns': self.player_cooldowns,
            'ai_cooldowns': self.ai_cooldowns,
            'terrain_mode': self.terrain_mode,
            'uid_char_map': {str(k): v for k, v in self.uid_char_map.items()},
            'uid_side_map': {str(k): v for k, v in self.uid_side_map.items()},
            'battle_log': self.battle_log[-200:],
            'winner': self.winner,
            'unit_id_counter': self.unit_id_counter,
            'pending_flag_picks': self.pending_flag_picks,
            'multiplayer': self.multiplayer,
            'first_scaler_uid': self.first_scaler_uid,
            'first_scaler_round': self.first_scaler_round,
            'lone_brave_player': self.lone_brave_player,
            'lone_brave_ai': self.lone_brave_ai,
            'lone_brave_round': self.lone_brave_round,
            'pending_draw_options': self._pending_draw_options,
            'host_placement_ready': self.host_placement_ready,
            'guest_placement_ready': self.guest_placement_ready,
        }
