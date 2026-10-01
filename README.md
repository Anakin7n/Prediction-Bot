# 影片落位预测 Bot

飞书群聊机器人，用户在群里按流程输入预测日期、影片及累计新增占比、大盘场次，Bot 自动从猫眼实时票房抓取排片数据，计算落位占比并生成 Excel 回传。

WebSocket 长连接模式，无需公网 IP，不依赖飞书官方 SDK。

## 项目结构

```
Prediction-Bot/
├── main.py                  # Bot 入口 (WS 客户端 + 事件分发 + 消息发送)
├── config.py                # 配置 (.env 读取)
├── requirements.txt         # 6 个依赖
├── install.bat              # 一键安装 (创建 venv + pip install + playwright 浏览器)
├── install_playwright.bat   # 依赖修复 (pip 损坏时用内置 wheel 修复 + 重装 Playwright)
├── start.bat                # 启动 (Windows Terminal)
├── start.ps1                # 启动脚本 (自动识别 venv / 系统 Python，退出后 5s 自动重启)
├── start.vbs                # 后台静默启动
├── .env.example             # 飞书凭证模板
├── .gitignore
├── tests/
│   ├── test_parsers.py       # 解析函数单元测试
│   ├── test_protobuf.py      # Protobuf 编解码测试
│   └── test_excel.py         # Excel 公式生成测试
├── scraper/
│   └── maoyan.py            # 猫眼数据 (requests 读排片页 + Playwright 拦截大盘接口 + 字体解码)
├── bot/
│   ├── handlers.py          # 交互状态机 (3 步流程)
│   └── cards.py             # 文本消息模板
└── excel/
    └── generator.py         # Excel 生成 (openpyxl 写公式)
```

## 环境要求

- Windows 10+
- Python 3.12+
- 飞书应用（需开启机器人能力，订阅 `im.message.receive_v1` 事件）

## 快速开始

1. 复制整个 `Prediction-Bot\` 文件夹到目标设备
2. 安装 Python 3.12+（勾选"Add Python to PATH"）
3. 双击 `install.bat`，自动完成：虚拟环境创建 → 依赖安装 → Playwright 浏览器 → `.env` 模板生成
4. 编辑 `.env` 填入飞书凭证
5. 双击 `start.bat` 或 `start.vbs` 启动

> 如果不想用虚拟环境，可跳过第 3 步，直接 `pip install -r requirements.txt && playwright install chromium`。启动脚本会自动识别。
>
> 启动后若报 Playwright / pip 相关错误，双击 `install_playwright.bat`：pip 损坏时先用 Python 内置 wheel 修复，再重装 Playwright。
> `start.ps1` 带自动重启守护（进程退出后 5 秒重启，关闭窗口即停止）。

## 飞书应用配置

1. 飞书开放平台 → 创建应用 → 开启**机器人**能力
2. 权限管理添加以下权限：

| 权限 | 说明 |
|------|------|
| `im:message` | 获取消息 |
| `im:message.group_msg` | 获取群组中所有消息（敏感权限，需审核） |
| `im:message.p2p_msg:readonly` | 读取用户发给机器人的单聊消息 |
| `im:message:send_as_bot` | 以应用的身份发消息 |
| `im:resource` | 获取与上传图片或文件资源 |

3. 事件订阅添加 `im.message.receive_v1`（WebSocket 模式**无需配置回调地址**）
4. 发布应用并通过审核

## 交互流程

```
用户: /start
  ← Bot: "请输入预测日期 (如 6.15)"
用户: 6.15
  ← Bot: "请输入影片及累计新增占比 (如 排球少年:0.176, 狗阵:0.147)"
用户: 消失的人:0.176, 狗阵:0.147
  ← Bot: "请输入 6.15 的大盘场次(D)"
用户: 420000
  ← Bot: "收到，正在查询猫眼排片数据"
  ← [Bot 爬取猫眼 → 匹配影片排片数据 → 计算所有公式 → 生成 Excel]
  ← Bot: "✅ 预测 Excel 已生成" + Excel 文件
  ← Bot: 落位汇总 ("周X落位：片名：xx.x%")
✅ 完成
```

## Excel 数据流

| 列 | 名称 | 来源 | 说明 |
|----|------|------|------|
| A | 日期 | 用户输入 | 如 `6.15` |
| B | 影片名称 | 用户输入 → 猫眼匹配 | |
| C | 累计新增占比 | 用户输入 | 小数格式 |
| D | 大盘场次 | 用户输入 | |
| E | 目前大盘场次 | 猫眼 | 今日取排片页 `totalCount`，非今日取 `showCountDesc` ≈ 36万 |
| F | 剩余场次 | 公式 `=D−E` | |
| G | 剩余可开场次 | 公式 `=F×C` | |
| H | 目前场次 | 猫眼 | 今日优先取排片页普通数字，其他情况取字体解码后的场次 |
| I | 影片总场次 | 公式 `=G+H` | |
| J | 落位占比 | 公式 `=ROUNDDOWN(I/D,3)` | 向下取整到 3 位小数 |

## 猫眼数据

- 查询今天时，先用 requests 读取今日排片页（`piaofang.maoyan.com/session` 的 `pageData.movieRankList` / `totalCount`）；
  所需影片齐全时直接使用普通数字的场次与总场次，不启动浏览器、不推断字体。影片场次须为非负整数，总场次须大于 0
- 查询其他日期，或今日排片页缺少所需影片时，使用 Playwright 浏览器（375×812 模拟移动端）打开 `piaofang.maoyan.com/i/dashboard/movie?date=YYYY-MM-DD`，拦截
  `/i/api/encrypt/dashboard-ajax/movie` 响应取影片列表与场次（不再 requests 直调 dashboard-ajax）
- 大盘响应中的 `showCount` 使用自定义字体混淆，需解码：用今日排片页的已知场次与今日大盘响应中的字形做加权匹配，解出字形→数字映射；
  非今日日期再下载 woff 字体、canvas 渲染字形位图与今日模板比对（距离阈值校验，失败即报错而非猜数）
- 今日排片与大盘数字映射不可靠时，每次重新获取两份数据；最多获取 3 次（失败后间隔 1 秒重试，最多重试 2 次）。
  日志记录冲突字形、候选数字和支持/冲突票数；连续失败后报错，不放宽校验，也不将获取失败的场次填为 0
- 关键字段: `movieName`（电影名）、`showCount`（加密场次）、`movieList.nationBoxInfo.showCountDesc`（总场次，如 `42.5万` / `3963场`）
- 目前大盘场次：今日取排片页 `totalCount`，非今日取 `showCountDesc`；今日单部影片优先用排片页场次
- 浏览器启动依次尝试 Playwright Chromium → 系统 Chrome → Edge，均失败则报错
- 进入大盘抓取流程后，影片不在猫眼所查询日期的大盘列表中会直接报错，不再回退侧边栏/详情页查找

## 技术选型

| 决策 | 方案 | 原因 |
|------|------|------|
| 连接方式 | WebSocket 长连接 | 无需公网 IP，启动 < 1 秒 |
| 依赖 | `websockets` + `requests` + `playwright` + `openpyxl` + `python-dotenv` | 不依赖 lark-oapi SDK，极简 |
| 消息去重 | message_id 持久化 | 防 WS 重推 / 重启回放 |
| Protobuf | 专用二进制帧编解码 | 仅解析 frame type 和 payload，不引入大库 |
| Excel 生成 | openpyxl 写原生公式 | 用户打开后可独立重算 |

## 运行测试

```bash
pytest tests/
```

## 注意事项

- 日期年份默认使用当前年份，无需输入（如 `6.15` 会解析为今年的 6 月 15 日）
- 影片名称需与猫眼对应数据源中的名称**精确匹配**（今日优先匹配排片页，进入大盘流程时匹配所查询日期的大盘列表）；未匹配会直接报错并终止本次预测，不再回退侧边栏查找或记 0 场
- 累计新增占比支持百分比自动转换（输入 `17.6` 自动变为 `0.176`）
- 大盘场次支持 `42万` / `42.5万` 等中文数字格式
- 密钥走 `.env`，不硬编码，不提交 git
- 日志自动轮转（单文件 5MB，保留 3 个备份）
