import math
from .constants import BOARD_ROWS, BOARD_COLS, MAX_TOTAL_TROOPS, TROOP_INCOME


def idx(r, c):
    return r * BOARD_COLS + c


def row_of(i):
    return i // BOARD_COLS


def col_of(i):
    return i % BOARD_COLS


def in_range(r, c):
    return 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS


def get_neighbor_indices(i):
    r = row_of(i)
    c = col_of(i)
    res = []
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            if dr == 0 and dc == 0:
                continue
            nr = r + dr
            nc = c + dc
            if in_range(nr, nc):
                res.append(idx(nr, nc))
    return res


def get_cone_indices(i, is_player):
    r = row_of(i)
    c = col_of(i)
    dir_val = -1 if is_player else 1
    res = []
    for dc in range(-1, 2):
        nr = r + dir_val
        nc = c + dc
        if in_range(nr, nc):
            res.append(idx(nr, nc))
    for dc in range(-2, 3):
        nr = r + dir_val * 2
        nc = c + dc
        if in_range(nr, nc):
            res.append(idx(nr, nc))
    return res


def is_flag_unit(idx, is_player, player_board, ai_board):
    flag_idx = player_board.get('flag_idx', -1) if isinstance(player_board, dict) else -1
    if isinstance(player_board, dict):
        if is_player:
            return player_board.get('flag_idx', -1) == idx
        else:
            return ai_board.get('flag_idx', -1) == idx
    return False


def calc_power(index, is_player, player_board, ai_board):
    my_board = player_board if is_player else ai_board
    en_board = ai_board if is_player else player_board
    u = my_board[index]
    if u is None:
        return 0

    p_flag_idx = player_board.get('flag_idx', -1) if isinstance(player_board, dict) else -1
    a_flag_idx = ai_board.get('flag_idx', -1) if isinstance(ai_board, dict) else -1
    is_flag = (is_player and index == p_flag_idx) or (not is_player and index == a_flag_idx)
    flag_mul = 1.1 if is_flag else 1

    power = u['char']['martial'] * 2 * flag_mul
    power *= (1 + u['troops'] / 30000)

    for ni in get_neighbor_indices(index):
        nu = my_board[ni]
        if nu is not None:
            power += nu['char']['leadership'] * 0.05
    power += u['char']['leadership'] * flag_mul * 0.05

    for ei in range(64):
        eu = en_board[ei]
        if eu is None:
            continue
        cone = get_cone_indices(ei, not is_player)
        if index in cone:
            power -= eu['char']['intelligence'] * 0.03

    return max(1, round(power))


def calc_battle(p_unit, a_unit, p_power, a_power, ratio, p_flag_idx=-1, a_flag_idx=-1):
    p_comm = p_unit['troops'] * ratio
    a_comm = a_unit['troops'] * ratio

    p_pol_flag = 1.1 if p_flag_idx is not None and p_flag_idx >= 0 else 1
    a_pol_flag = 1.1 if a_flag_idx is not None and a_flag_idx >= 0 else 1

    p_pol = p_unit['char']['politics'] * \
        (1.1 if (p_flag_idx >= 0 and False) else 1)
    a_pol = a_unit['char']['politics'] * \
        (1.1 if (a_flag_idx >= 0 and False) else 1)

    is_flag_p = p_unit.get('uid') is not None and p_flag_idx is not None and any(
        False
    )
    is_flag_a = a_unit.get('uid') is not None and a_flag_idx is not None and any(
        False
    )

    p_pol = p_unit['char']['politics'] * (1.1 if p_flag_idx >= 0 else 1)
    a_pol = a_unit['char']['politics'] * (1.1 if a_flag_idx >= 0 else 1)

    p_red = 1 - p_pol / 240
    a_red = 1 - a_pol / 240
    total = p_power + a_power
    p_loss = round(p_comm * (a_power / total) * 0.8 * p_red)
    a_loss = round(a_comm * (p_power / total) * 0.8 * a_red)
    return {
        'pLoss': p_loss,
        'aLoss': a_loss,
        'pLossPct': p_loss / (p_unit['troops'] * ratio) if (p_unit['troops'] * ratio) > 0 else 0,
        'aLossPct': a_loss / (a_unit['troops'] * ratio) if (a_unit['troops'] * ratio) > 0 else 0
    }


def calc_ranged_damage(attacker, defender, atk_power, def_power):
    total = atk_power + def_power
    intel_factor = attacker['char']['intelligence'] / 100
    dmg = round(attacker['troops'] * (atk_power / total) * intel_factor * 0.25)
    return max(1, dmg)


def is_triple_surrounded(idx, is_player, player_board, ai_board):
    r = row_of(idx)
    c = col_of(idx)
    en_board = ai_board if is_player else player_board
    if is_player:
        has_front = r > 0 and en_board[(r - 1) * 8 + c] is not None
    else:
        has_front = r < 7 and en_board[(r + 1) * 8 + c] is not None
    has_left = c > 0 and en_board[r * 8 + (c - 1)] is not None
    has_right = c < 7 and en_board[r * 8 + (c + 1)] is not None
    return has_front and has_left and has_right


def get_encirclement_power_mod(idx, is_player, player_board, ai_board):
    r = row_of(idx)
    c = col_of(idx)
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            nr = r + dr
            nc = c + dc
            if nr < 0 or nr > 7 or nc < 0 or nc > 7:
                continue
            ni = nr * 8 + nc
            if is_triple_surrounded(ni, True, player_board, ai_board) or \
               is_triple_surrounded(ni, False, player_board, ai_board):
                return 0.9
    return 1


def calc_battle_power(idx, is_player, player_board, ai_board):
    return round(calc_power(idx, is_player, player_board, ai_board) *
                 get_encirclement_power_mod(idx, is_player, player_board, ai_board))


def total_troops(board):
    t = 0
    for i in range(64):
        if board[i] is not None:
            t += board[i]['troops']
    return t


def decay_income(side_board, side_troops):
    board_t = total_troops(side_board)
    income = math.floor(TROOP_INCOME * max(0, 1 - board_t / MAX_TOTAL_TROOPS))
    sum_pol = 0
    for i in range(64):
        if side_board[i] is not None:
            sum_pol += side_board[i]['char']['politics']
    pol_mult = max(0.2, min(2.0, sum_pol * 0.001))
    income = math.floor(income * pol_mult)
    max_add = MAX_TOTAL_TROOPS - board_t - side_troops
    return max(0, min(income, max_add))


def find_highest_troops_idx(board):
    bi = -1
    bt = -1
    for i in range(64):
        if board[i] is not None and board[i]['troops'] > bt:
            bt = board[i]['troops']
            bi = i
    return bi


def has_adjacent_enemy(idx, is_player, player_board, ai_board):
    r = row_of(idx)
    c = col_of(idx)
    enemy = ai_board if is_player else player_board
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            if dr == 0 and dc == 0:
                continue
            nr = r + dr
            nc = c + dc
            if nr < 0 or nr > 7 or nc < 0 or nc > 7:
                continue
            if enemy[nr * 8 + nc] is not None:
                return True
    return False


def is_behind_enemy_line(idx, is_player, player_board, ai_board):
    r = row_of(idx)
    c = col_of(idx)
    en_board = ai_board if is_player else player_board
    if is_player:
        for rr in range(r + 1, 8):
            if en_board[rr * 8 + c] is not None:
                return True
    else:
        for rr in range(r - 1, -1, -1):
            if en_board[rr * 8 + c] is not None:
                return True
    return False


def are_adjacent(i1, i2):
    if i1 < 0 or i2 < 0:
        return False
    r1 = row_of(i1)
    c1 = col_of(i1)
    r2 = row_of(i2)
    c2 = col_of(i2)
    return abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1 and not (r1 == r2 and c1 == c2)
