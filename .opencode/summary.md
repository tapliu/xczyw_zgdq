# Current Objective
所有地图以石头剪刀布开场决定先手抽卡顺序；普通模式放兵限制在己方半场（前端+后端）；修复普通模式棋盘显示。

## Completed Changes

### 1. 所有地图以RPS开场
- `state.py:reset_game` — 无论地形，开局 `game_phase = 'rps'`
- `state.py:_resolve_rps` — 根据地形分支：
  - `tennozan` → `rps_pick_flag` 选旗本，然后分配给AI
  - `normal` → 直接进入 `_init_draw_sequence()`
- `state.py:_init_draw_sequence` — 第0回合根据 `rps_winner` 决定先手（player/ai，多人为host/guest）
- `game/js/main.js:329` — RPS阶段文字改为通用"决定先手抽卡顺序"
- `game/index.html` — RPS弹窗描述改为"赢家优先抽卡"

### 2. 放兵限制在己方半场
- 新增 `VISUAL_AI_CELLS`, `VISUAL_PLAYER_CELLS` 数组（仅含玩家/电脑可见半场格子，不含前方空白区域）
- 每个地形各自一套坐标（`_switch_board` 时切换）
- **后端** `place_unit` / `place_unit_guest`：由 `HEX_DEPTH` 改为检查 `cell not in PLAYER_FLAG_CELLS and cell not in VISUAL_PLAYER_CELLS`
- **前端** `onCellClick`：同理改为 zone-based 检查
- `_auto_place_side` 及其调用处：传参由 `depth` 改为使用 `VISUAL_*_CELLS`

### 3. 修复普通模式棋盘
- `AI_FLAG_CELLS` 修正为 `[4,5,6,7,8]`（之前错误偏移一格）
- `main.js` 和 `state.py` 均修复

### 4. 天王山模式（已完成，不受影响）
- RPS → 选秀吉/光秀 → 旗本分配 → 缩略抽卡序列（每方2轮旗本+1轮普通）
- 双棋盘 `_switch_board`
- 前端弹窗 `showTennozanFlagPickModal`

### 5. 基础RPS流程
- RPS弹窗、API路由、单人/多人自动模式
- 平局重开、auto-play跳过
- `rps_winner` 字段存储胜者

## Key Files Modified
- **`server/src/backend/state.py`** — reset_game, _resolve_rps, _init_draw_sequence, place_unit, place_unit_guest, BOARD_DEFS, VISUAL_CELLS, flag cells
- **`game/js/main.js`** — onCellClick, applyStateFromServer, RPS phase text
- **`game/index.html`** — RPS modal description

## Next Steps
- 多人模式下测试RPS抽卡顺序
- 验证auto-play在普通模式下从RPS到放兵的完整流程
- 如有bug，修复抽卡阶段卡住或其他边缘情况
