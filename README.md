# 信长之野望-战国夺旗 v0.0.3

基于日本战国历史的回合制策略棋盘游戏。玩家扮演一方大名，通过招募武将、部署军队、征战沙场，夺取敌阵旗帜。

## 特性

- **100 名战国武将** — 统、武、智、政四维属性，S+/S/A/B/C/D 评级
- **类型加成系统** — 全能/文臣/武将/特才四种类型，隐藏属性加成
- **三选一招募** — 每回合从随机武将中选择 1 名加入麾下
- **旗本系统** — 指定大名身份武将作为旗本，阵亡后掉落旗印可被友军拾取
- **武将编辑器** — 编辑现有武将属性，支持保存/恢复
- **自建武将** — 20 个头像位，支持新建/编辑/保存自定义武将，类型受属性比例约束
- **毛玻璃 UI** — 页脚毛玻璃框、编辑器悬浮预览等视觉效果
- **自动战斗** — 近战/远程/侧击/夹击/争夺，全自动结算
- **列队前进** — 前排推进时后排自动补位，保持阵型
- **地形系统** — 支持不同战场地形（天王山、长篠等）
- **武将头像** — WebP 格式武将画像，含 20 张自定义头像
- **阵容观战** — 可查看双方及观战席武将详情

## 游戏规则

- **棋盘**: 8×8 网格，玩家控制下半区（4-7行），AI 控制上半区（0-3行）
- **身份系统**: 武将分为大名（64人）与非大名（36人），仅大名可被选为旗本
- **卡牌招募**: 每回合从 3 张随机武将中选择 1 张加入麾下（三选一）
- **旗本抽取**: 第一轮抽牌完成后，双方从抽牌堆中抽取 3 名大名作为旗本候补
- **部署**: 每回合在本方区域部署最多 5 个单位，分配兵力
- **战斗**: 双方部署完成后自动结算，支持近战、远程、侧击、夹击
- **胜利条件**:
  1. 达阵 — 任意单位进入敌方底线
  2. 全歼 — 消灭所有敌方单位
  3. 旗本溃散 3 次 — 敌方旗本武将阵亡 3 次

## 快速开始

```bash
# 安装依赖
pip install -r server/requirements.txt

# 启动服务器
python -m server.src.main
# 或: uvicorn server.src.main:app --reload

# 浏览器访问
# http://127.0.0.1:8000
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Pydantic |
| 前端 | 原生 HTML5 + CSS3 + JavaScript（无框架） |
| 运行 | Uvicorn |

## 项目结构

```
├── game/                       # 前端静态文件
│   ├── index.html
│   ├── css/style.css
│   ├── js/api.js               # API 客户端
│   ├── js/main.js              # 核心逻辑 & UI
│   ├── js/editor.js            # 武将编辑器
│   ├── data.js                 # 武将数据
│   ├── characters.json         # 武将数据文件
│   └── portraits/              # 武将头像（webp）
├── server/src/                 # 后端
│   ├── main.py                 # FastAPI 入口
│   ├── data/characters.py      # 武将数据（Python）
│   ├── routes/game.py          # REST API 路由
│   └── backend/                # 游戏引擎
│       ├── state.py            # 游戏状态 & 战斗引擎
│       ├── combat.py           # 战斗计算
│       ├── ai.py               # AI 部署逻辑
│       └── constants.py        # 游戏常量
└── server/requirements.txt
```

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/game/new` | 新建游戏 |
| GET | `/api/game/{id}` | 获取状态 |
| POST | `/api/game/{id}/draw` | 抽牌阶段 |
| POST | `/api/game/{id}/draw-options` | 获取三选一选项 |
| POST | `/api/game/{id}/pick-card` | 选择武将 |
| POST | `/api/game/{id}/place` | 部署单位 |
| POST | `/api/game/{id}/end-turn` | 结束部署 |
| POST | `/api/game/{id}/auto-place` | 托管部署 |
| POST | `/api/game/{id}/reset` | 重置游戏 |
| POST | `/api/game/{id}/set-terrain` | 设置地形 |
| POST | `/api/characters/save` | 保存武将编辑 |
| POST | `/api/characters/custom/save` | 保存自建武将 |

API 文档（运行时）：`http://127.0.0.1:8000/docs`
