# 信长之野望-战国夺旗 v0.1.0

基于日本战国历史的回合制策略棋盘游戏 + WebSocket 实时多人对战。

---

## 快速开始

```bash
# 安装依赖
pip install -r server/requirements.txt

# 启动服务器
python -m server.src.main

# 浏览器访问 http://127.0.0.1:8000
```

## 特性

- **100 名战国武将** — 统、武、智、政四维属性，S+/S/A/B/C/D 评级
- **14 个势力 + 多势力系统** — 同势力友军邻接时兵力加成，敌对势力邻接时削弱
- **类型加成系统** — 全能/文臣/武将/特才四种类型，开局自动增幅属性
- **三选一招募** — 每回合从随机武将中选择 1 名加入麾下
- **旗本系统** — 大名武将作为旗本，阵亡掉落旗印可被友军拾取
- **武将编辑器** — 编辑现有武将属性，支持保存/恢复
- **自建武将** — 20 个头像位，支持新建/编辑/保存自定义武将
- **背景音乐系统** — 菜单/部署/战斗/结算自动切换
- **自动战斗** — 近战/远程/侧击/夹击/争夺，全自动结算
- **结算画面** — MVP 展示、排名榜
- **多人异步对战** — 房间系统 + WebSocket 实时对战协议
- **地形系统** — 天王山、长篠等特殊战场
- **列队前进** — 前排推进时后排自动补位，保持阵型

## 游戏规则

- **棋盘**: 8×8 网格，玩家控制下半区（4-7行），AI 控制上半区（0-3行）
- **卡牌招募**: 每回合从 3 张随机武将中选择 1 张
- **旗本抽取**: 第一轮抽牌完成后，双方从抽牌堆中抽取 3 名大名作为旗本候补
- **部署**: 每回合在本方区域部署最多 5 个单位，分配兵力
- **战斗**: 双方部署完成后自动结算，支持近战、远程、侧击、夹击
- **胜利条件**:
  1. 达阵 — 任意单位进入敌方底线
  2. 全歼 — 消灭所有敌方单位
  3. 旗本溃散 3 次 — 敌方旗本武将阵亡 3 次

## 武将系统

### 四维属性

| 属性 | 作用 |
|---|---|
| **统率** (leadership) | 提升战力、增益邻接友军、决定兵力上限 |
| **武力** (martial) | 主要伤害来源 |
| **智力** (intelligence) | 远程伤害系数、削弱正面敌方 |
| **政治** (politics) | 减少战损、战后恢复、收入加成 |

旗本武将获得 1.1× 属性倍率。

### 武将类型

| 类型 | 效果 |
|---|---|
| **全能** | 四维全 × 1.05 |
| **文臣** | 智力、政治 × 1.07 |
| **武将** | 统率、武力 × 1.07 |
| **特才** | 最高单项属性 × 1.10 |

### 评级系统

| 评级 | 条件 |
|------|------|
| **S+** | 任意属性 = 100 |
| **S** | 剩余武将中总分前 ~9% |
| **A** | 接下来 ~18% |
| **B** | 接下来 ~18% |
| **C** | 接下来 ~27% |
| **D** | 末尾 ~27% |

## 网络架构 (v0.1.0)

四层实时对战协议，输入同步 + 服务端验证：

```
┌─────────────────────────────────────────────────┐
│  Layer 4  Business    backend/state.py          │
│            游戏规则验证、resolve_rt_melee()       │
├─────────────────────────────────────────────────┤
│  Layer 3  Logic        network/session.py       │
│            10Hz tick 循环、输入队列、差值同步     │
├─────────────────────────────────────────────────┤
│  Layer 2  Protocol     network/protocol.py      │
│            JSON 帧 {t,seq,ts,tick,d}、seq 窗口   │
│            结构校验、delta 计算                   │
├─────────────────────────────────────────────────┤
│  Layer 1  Transport    main.py / connection.py  │
│            WebSocket + 异步发送队列、心跳         │
│            握手鉴权、速率限制、背压控制            │
└─────────────────────────────────────────────────┘
```

### 协议帧格式

```json
{"t": 4, "seq": 42, "ts": 1718000000000, "tick": 15, "d": {"type": "move", "unit_uid": 1, "to_cell": 32}}
```

### 消息类型

| 方向 | 类型 | 值 | 说明 |
|------|------|----|------|
| C→S | HEARTBEAT | 1 | 心跳 |
| C→S | JOIN_BATTLE | 2 | 加入实时战斗 |
| C→S | LEAVE | 3 | 离开 |
| C→S | INPUT | 4 | 操作输入 (move/attack/hold) |
| C→S | PING | 5 | 延迟测试 |
| C→S | SNAPSHOT_REQ | 6 | 重连状态请求 |
| S→C | HEARTBEAT | 129 | 心跳回复 |
| S→C | STATE | 130 | 全量/差值状态同步 |
| S→C | ACK | 131 | 输入确认 |
| S→C | ERROR | 132 | 错误通知 |
| S→C | PHASE | 133 | 阶段切换 |
| S→C | EVENT | 134 | 战斗事件 |
| S→C | PONG | 135 | PING 回复 |
| S→C | SNAPSHOT_RES | 136 | 重连状态回复 |
| S→C | FLOW_CONTROL | 137 | 背压控制 |

### 鉴权流程

```
客户端 ws://host/ws/{game_id}/{role}?token=xxx
  │
  ├─ 1. 参数校验 + 游戏存在检查       4001/4004
  ├─ 2. validate_ws_token()           4003
  ├─ 3. register_connection() 防重复   4002
  └─ 4. ws.accept() ───→ 正常通信
```

Token 由房间系统生成（uuid4），多人游戏开始时存入 `GameState.host_token` / `GameState.guest_token`。单机游戏无 Token，无法通过 WS 鉴权。

### 背压控制

双重限流：硬性速率上限 (30 msg/s) + 动态拥塞控制：

```
input_queue 深度 < 100  → 正常发送 (30/s)
             100–300    → 线性降至 2/s，下发 FLOW_CONTROL
             ≥ 300      → 丢弃新输入，客户端重试
```

### 状态同步

- 每 5 tick（0.5s）发全量快照
- 中间 tick 发差值 `compute_delta(old, new)`
- 客户端 `_handleState()` 合并差值到本地快照
- 重连时通过 `SNAPSHOT_REQ` 获取历史快照（保留最近 60 帧 = 6s）

### 视图过滤

`filter_state_for_role()` 按身份裁剪状态：
- Host 侧去除 AI 方的 `is_new_placement` 标记
- Guest 侧去除 Player 方的 `is_new_placement` 标记
- 保持自身侧数据完整

## 项目结构

```
├── game/                       # 前端静态文件
│   ├── index.html              # 主界面
│   ├── js/
│   │   ├── main.js             # 核心逻辑 & UI
│   │   ├── api.js              # API 客户端
│   │   ├── net.js              # WebSocket 协议 (Client)
│   │   └── data.js             # 武将数据
│   ├── characters.json
│   └── portraits/
├── server/src/
│   ├── main.py                 # FastAPI 入口 + WS 端点
│   ├── network/                # 实时网络协议栈
│   │   ├── protocol.py         # 协议帧 / 类型 / delta
│   │   ├── connection.py       # 连接管理 / 心跳 / 队列
│   │   ├── session.py          # 对局会话 / tick 循环
│   │   ├── auth_service.py     # 握手鉴权
│   │   └── tests/              # 单元测试 (84 tests)
│   ├── routes/
│   │   ├── game.py             # HTTP 游戏 API
│   │   └── room.py             # 房间 API
│   └── backend/
│       ├── state.py            # 游戏状态 & 战斗引擎
│       ├── combat.py           # 战斗计算
│       ├── ai.py               # AI
│       ├── room.py             # 房间管理
│       └── constants.py        # 常量
└── server/requirements.txt
```

## API 端点

### HTTP

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/game/new` | 新建游戏 |
| GET | `/api/game/{id}` | 获取游戏状态 |
| POST | `/api/game/{id}/draw-options` | 抽卡选项 |
| POST | `/api/game/{id}/pick-card` | 选择武将 |
| POST | `/api/game/{id}/place` | 部署单位 |
| POST | `/api/game/{id}/end-turn` | 结束部署 |
| POST | `/api/game/{id}/auto-place` | 托管部署 |
| POST | `/api/game/{id}/reset` | 重置游戏 |
| POST | `/api/room/create` | 创建房间 |
| POST | `/api/room/join` | 加入房间 |
| POST | `/api/room/leave` | 离开房间 |
| POST | `/api/room/start` | 开始游戏 |
| POST | `/api/room/ready` | 准备/取消准备 |
| POST | `/api/room/status` | 房间状态 |
| GET | `/api/room/list` | 房间列表 |
| POST | `/api/characters/save` | 保存武将编辑 |
| POST | `/api/characters/custom/save` | 保存自建武将 |

### WebSocket

| 路径 | 参数 | 说明 |
|---|---|---|
| `/ws/{game_id}/{role}` | `?token=` | 实时对战连接 |

API 文档（运行时）：`http://127.0.0.1:8000/docs`

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Pydantic / Uvicorn |
| 前端 | 原生 HTML5 + CSS3 + JavaScript（无框架） |
| 实时通信 | WebSocket + 自定义 JSON 协议 |
| 测试 | pytest + pytest-asyncio |

## 测试

```bash
cd server && python -m pytest src/network/tests/ -v
```

## 版本历史

- **v0.1.0** — WebSocket 实时对战协议、握手鉴权、背压控制、4 层网络架构、84 项单元测试
- **v0.0.8** — 多人房间系统、天王山/长篠地形、列队前进、自建武将
- v0.0.7 — 武将编辑器、势力关系、类型加成
- v0.0.6 — 旗本系统、MVP 结算
- v0.0.5 — 背景音乐系统
- v0.0.4 — 自动战斗引擎
- v0.0.3 — 三选一招募
- v0.0.2 — 基础部署
- v0.0.1 — 初始版本

## 致谢

- 武将数据、头像及势力关系参考自光荣《信长之野望》系列
