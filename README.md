# 影片落位预测 Bot

飞书群聊机器人，用户在群里按流程输入预测日期、影片及累计新增占比、大盘场次，Bot 自动从猫眼实时票房抓取排片数据，计算落位占比并生成 Excel 回传。

WebSocket 长连接模式，无需公网 IP，不依赖飞书官方 SDK。

## 项目结构

```
Prediction-Bot/
├── main.py                  # Bot 入口 (WS 客户端 + 事件分发 + 消息发送)
├── config.py                # 配置 (.env 读取)
├── requirements.txt         # 4 个轻量依赖
├── install.bat              # 首次安装 (创建 venv + pip install)
├── start.bat                # 启动 (Windows Terminal + PowerShell)
├── .env.example             # 飞书凭证模板
├── .gitignore
├── scraper/
│   └── maoyan.py            # 猫眼 API 封装 (requests 调用 dashboard-ajax)
├── bot/
│   ├── handlers.py          # 交互状态机 (4 步流程)
│   └── cards.py             # 文本消息模板
├── excel/
│   └── generator.py         # Excel 生成 (openpyxl 写公式)
└── 影片落位预测.xlsx         # 原始 Excel 模板
```

## 环境要求

- Windows 10+
- Python 3.12+
- 飞书应用（需开启机器人能力，订阅 `im.message.receive_v1` 事件）

## 快速开始

1. 双击 `install.bat` 创建虚拟环境并安装依赖
2. 创建 `.env`，填入飞书凭证：
   ```
   FEISHU_APP_ID=cli_xxxxxxxx
   FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
   ```
3. 双击 `start.bat` 启动

## 飞书应用配置

1. 飞书开放平台 → 创建应用 → 开启**机器人**能力
2. 权限管理添加：
   - `im:message` — 读取消息
   - `im:message:send_as_bot` — 发送消息
3. 事件订阅添加 `im.message.receive_v1`（WebSocket 模式**无需配置回调地址**）
4. 发布应用并通过审核

## 交互流程

```
用户: /start
  ← Bot: "请输入预测日期 (如 6.15)"
用户: 6.15
  ← Bot: "请输入影片及累计新增占比 (如 排球少年:0.176, 狗阵:0.147)"
用户: 消失的人:0.176, 狗阵:0.147
  ← [Bot 爬取猫眼 API → 匹配影片排片数据]
  ← Bot: "请提供大盘场次" (附带匹配结果)
用户: 420000
  ← [Bot 计算所有公式 → 生成 Excel → 发送文件]
✅ 完成
```

## Excel 数据流

| 列 | 名称 | 来源 | 说明 |
|----|------|------|------|
| A | 日期 | 用户输入 | 如 `6.15` |
| B | 影片名称 | 用户输入 → 猫眼匹配 | |
| C | 累计新增占比 | 用户输入 | 小数格式 |
| D | 大盘场次 | 用户输入 | |
| E | 目前大盘场次 | 猫眼 API | sum(showCount) ≈ 36万 |
| F | 剩余场次 | 公式 `=D−E` | |
| G | 剩余可开场次 | 公式 `=F×C` | |
| H | 目前场次 | 猫眼 API | 每个影片的 `showCount` |
| I | 影片总场次 | 公式 `=G+H` | |
| J | 落位占比 | 公式 `=I/D` | |

## 猫眼 API

- 接口: `https://piaofang.maoyan.com/dashboard-ajax`
- 响应: JSON，包含完整榜单（约 60+ 部电影）
- 关键字段: `movieInfo.movieName`（电影名）、`showCount`（排片场次，纯整数）
- 目前大盘场次 = 所有电影 `showCount` 之和

## 技术选型

| 决策 | 方案 | 原因 |
|------|------|------|
| 连接方式 | WebSocket 长连接 | 无需公网 IP，启动 < 1 秒 |
| 依赖 | `websockets` + `requests`（4 个包） | 不依赖 lark-oapi SDK，极简 |
| 消息去重 | message_id 持久化 + 内容哈希 | 防 WS 重推 / 重启回放 |
| Protobuf | 自写轻量编解码 | 仅需 ping 帧，无需引入大库 |
| Excel 生成 | openpyxl 写原生公式 | 用户打开后可独立重算 |

## 注意事项

- 影片名称需与猫眼榜单**精确匹配**，否则场次填 0
- 累计新增占比支持百分比自动转换（输入 `17.6` 自动变为 `0.176`）
- 大盘场次支持 `42万` / `42.5万` 等中文数字格式
- 密钥走 `.env`，不硬编码，不提交 git
- 日志输出到 `bot.log`，不自动清理
