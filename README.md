# 💗 生活小管家 · Love Meal Bot

在飞书群里点一下，决定下一顿。原生交互卡片，无需跳转网页。

![餐桌插图](assets/meal-card-hero.png)

## 功能

- 50 道菜随机抽签，尽量避免重复；支持确认、收藏、最近选择。
- 群内共享忌口设置，可从全部菜品或收藏夹抽取。
- 玫瑰色主按钮、原地表单及清晰的操作反馈。
- 早餐及抹药提醒；同步指定群的 AI 日报，前三条速览，群内展开全文。
- SQLite 持久化、事件去重、成员白名单、过期按钮检查和失败回滚。

本仓库仅包含飞书原生机器人，不包含网页应用、私人聊天记录、生产配置或数据库。当前没有抹药打卡或 AI 问答；抹药内容只是固定提醒。

## 环境

Python 3.9+，仅使用标准库。另需安装并登录 `lark-cli`，支持以下命令：

- `im +messages-send` / `im +chat-messages-list`
- `api` / `event consume card.action.trigger`

应用机器人应加入目标群，并具有发送消息和接收卡片回调的权限。读取日报需用户身份有权访问来源群。提醒及日报使用群自定义机器人的 webhook；两个机器人可设置相同名称和头像。CLI 安装、登录和飞书应用权限需自行配置。

## 配置和运行

```sh
cp config.example.json config.json
```

在配置中填写 `chat_id`（目标群）、`member_ids`（可操作卡片的成员 open ID 数组）、`webhook`（提醒机器人）以及 `source_chat`（日报来源群）。不要提交真实配置或凭据。

可选环境变量：`LOVE_MEAL_CONFIG` 指定配置文件，`LOVE_MEAL_DATA_DIR` 指定数据目录，`LARK_CLI` 指定 CLI 路径。默认数据存储在 `data/`。

先保持一个监听进程运行：

```sh
python3 meal_card.py listen
```

另开终端发送推送：

```sh
python3 life_bot.py morning
python3 life_bot.py lunch
python3 life_bot.py dinner
```

用外部调度器每天北京时间 09:00、12:00、18:00 分别执行这三个命令。本程序不自动注册定时任务；主机需保持在线，关机后的补发由调度器决定。监听和推送须使用相同配置与数据目录。

同日同类推送按本地状态去重，日报按来源消息 ID 去重，保留来源日期。不要并发执行推送；发送成功后、状态写入前若意外退出，仍可能重复发送。建议备份 `data/`，不要清除去重状态。

日报解析匹配消息内的「AI 每日精选」和「📊」结构，不是通用 RSS 抓取器；来源格式变化需调整 `life_bot.py`。

可选插图：上传 `assets/meal-card-hero.png` 为飞书图片，将返回的 image key 写入数据目录的 `meal-hero-key.txt`。未配置也可运行。头像素材为 `assets/life-bot-avatar.png`。

## 测试

```sh
python3 -m unittest -v test_meal_card
python3 meal_card.py preview
```

测试使用临时数据库及模拟 API，不发消息。覆盖抽签、确认、收藏、忌口、白名单、迁移、去重及失败回滚。

## 结构

- `meal_card.py`：卡片、交互回调及数据库。
- `push_ui.py`：共用视觉组件、提醒及日报布局。
- `life_bot.py`：推送入口与日报同步。
- `card-menu.json`：50 道菜及食材。
- `test_meal_card.py`：隔离回归测试。

公开版将原部署的个人路径、群及成员 ID 改为本地配置，现有机器人部署不受影响。
