import random
from .constants import (
    BOARD_COLS, BOARD_ROWS, PLACE_PER_ROUND, MAX_TROOPS_PER_UNIT
)
from .combat import is_behind_enemy_line, is_on_cooldown


def shuffle(arr):
    for i in range(len(arr) - 1, 0, -1):
        j = random.randint(0, i)
        arr[i], arr[j] = arr[j], arr[i]


def auto_place_side(side, collection, rows, is_player, max_place=PLACE_PER_ROUND,
                    player_board=None, ai_board=None, unit_id_counter_ref=None,
                    uid_char_map=None, uid_side_map=None, max_units_func=None):
    if max_place is None:
        max_place = PLACE_PER_ROUND

    rating_order = {'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5}

    avail = [
        c for c in collection
        if not any(u is not None and u['char']['id'] == c['id'] for u in player_board)
        and not any(u is not None and u['char']['id'] == c['id'] for u in ai_board)
        and not is_on_cooldown(c['id'], is_player)
        and not False  # isDead - handled outside
    ]

    avail.sort(key=lambda c: rating_order.get(c['rating'], 9))

    max_units = max_units_func() if max_units_func else 16
    remain_slots = max_units - len([u for u in side['board'] if u is not None])
    to_place = min(max_place, len(avail), remain_slots)
    if to_place <= 0:
        return

    front_cut = 6 if is_player else 2
    front_cells = []
    back_cells = []
    for r in rows:
        for c in range(BOARD_COLS):
            i = r * BOARD_COLS + c
            if side['board'][i] is not None or is_behind_enemy_line(i, is_player, player_board, ai_board):
                continue
            if (is_player and r < front_cut) or (not is_player and r >= front_cut):
                front_cells.append(i)
            else:
                back_cells.append(i)

    shuffle(front_cells)
    shuffle(back_cells)

    dir_val = -1 if is_player else 1
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
                behind = row_of(cell) + dir_val
                if 0 <= behind < 8:
                    bi = behind * BOARD_COLS + col_of(cell)
                    support_preferred.append(bi)
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
                if side['board'][c] is None and c in back_cells:
                    cell = c
                    found = True
                    back_cells.remove(c)
                    break
            if not found and back_cells:
                cell = back_cells.pop()
            elif not found and front_cells:
                cell = front_cells.pop()
            elif not found:
                break

        max_t = min(MAX_TROOPS_PER_UNIT, ch['leadership'] * 100, side['troops'])
        t = max(500, min(max_t, round(ch['martial'] * 60 + ch['leadership'] * 40)))
        nuid = unit_id_counter_ref['counter'] + 1
        unit_id_counter_ref['counter'] = nuid
        side['board'][cell] = {'char': ch, 'troops': t, 'uid': nuid, 'pinned': False}
        if uid_char_map is not None:
            uid_char_map[nuid] = ch
        if uid_side_map is not None:
            uid_side_map[nuid] = 'player' if is_player else 'ai'

        side['troops'] = max(0, side['troops'] - t)
        placed += 1


def row_of(i):
    return i // BOARD_COLS


def col_of(i):
    return i % BOARD_COLS


def is_on_cooldown(char_id, is_player):
    return False  # stub - real check from state


def try_recruit_ai(ai, spectator_pool, surviving_count_fn):
    if surviving_count_fn('ai') >= 10 or len(spectator_pool) == 0:
        return
    rating_order = {'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5}
    best = min(spectator_pool, key=lambda c: rating_order.get(c['rating'], 9))
    spectator_pool.remove(best)
    ai['collection'].append(best)
    return best
