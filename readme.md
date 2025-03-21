````
# Telegram 文件管理机器人

## 项目介绍

Telegram 文件管理机器人是一个专为管理和下载 Telegram 文件设计的机器人。它能够直接从 Telegram 消息或链接下载文件，并提供文件管理功能，如重命名、删除和列出已下载的文件。机器人使用 Docker 容器化部署，便于安装和维护。

## 主要功能

- 直接从 Telegram 消息下载文件
- 支持从 Telegram 链接下载文件
- 按日期自动整理文件 (YYYYMMDD/文件名)
- 文件重命名和删除功能
- 分页列出已下载文件
- 实时显示下载进度条、速度和预计完成时间
- 支持取消正在进行的下载
- 查看当前活动的下载
- 自动生成唯一文件名，防止覆盖同名文件
- 用户权限管理系统

## 文件结构

```
/
├── bot.py                    # 主机器人文件，包含命令处理程序
├── docker-compose.yml        # Docker 配置文件
├── Dockerfile                # Docker 构建文件
├── requirements.txt          # Python 依赖项
├── .env                      # 环境变量
└── utils/
    ├── __init__.py           # 包初始化文件
    ├── download_manager.py   # 下载管理器
    └── file_manager.py       # 文件管理器（列出、重命名、删除）
```

## 技术实现

- 使用 Telethon 库与 Telegram API 交互
- 异步设计，支持并行处理多个下载任务
- Docker 容器化部署
- 按日期自动组织文件 (YYYYMMDD)
- 实时下载进度跟踪，支持速度估算和完成时间预测
- 唯一文件 ID 系统，用于跟踪和取消下载
- 针对大文件优化的进度更新
- 自动处理文件名冲突，防止覆盖现有文件

## 安装指南

### 环境要求

- Docker 和 Docker Compose
- Telegram Bot Token
- Telegram API ID 和 API Hash

### 配置步骤

1. 克隆仓库到本地：

```bash
git clone <repository-url>
cd telegram-file-bot
```

2. 创建 `.env` 文件并添加以下内容：

```
BOT_TOKEN=<your_bot_token>
API_ID=<your_api_id>
API_HASH=<your_api_hash>
ALLOWED_USERS=<user_id1>,<user_id2>  # 可选，限制只有特定用户能使用机器人
```

3. 使用 Docker Compose 构建和启动容器：

```bash
docker compose build
docker compose up -d
```

## 使用说明

### 机器人命令

- `/start` - 显示帮助信息
- `/list [页码]` - 分页列出已下载文件
- `/rename <索引> <新名称>` - 重命名文件
- `/delete <索引>` - 删除文件
- `/cancel <下载ID>` - 取消正在进行的下载
- `/active` - 查看当前活动的下载

### BotFather设置机器人命令
start - Show help message
list - List files
rename - Rename a file, format: /rename index new_name
delete - Delete a file, format: /delete index
cancel - Cancel download, format: /cancel download_id
active - View active downloads

### 下载文件

有三种方式可以下载文件：

1. 直接发送文件给机器人
2. 转发包含文件的消息给机器人
3. 发送 Telegram 链接给机器人 (例如: t.me/channel/123)

文件将按日期（YYYYMMDD）保存在下载目录中。

### 管理下载

下载开始后，机器人会显示下载进度、速度和预计完成时间。如果需要取消下载，可以使用 `/cancel <下载ID>` 命令。

可以通过 `/active` 命令查看所有正在进行的下载。

## 代码架构

### bot.py

处理所有机器人命令和消息。主要功能包括：
- 命令处理（/start, /list, /rename, /delete, /cancel, /active）
- 消息处理（文件和链接）
- 用户认证

### download_manager.py

负责文件下载功能：
- 从 Telegram 下载文件
- 处理下载进度更新
- 支持取消下载
- 自动生成唯一文件名

### file_manager.py

处理文件管理功能：
- 列出已下载的文件
- 重命名文件
- 删除文件
- 文件缓存管理

## 注意事项

- 确保机器人在群组中有足够的权限
- 对于大文件，下载可能需要较长时间
- 文件保存在容器中的 `/app/downloads` 目录，此目录已映射到主机
- 要访问下载的文件，可在主机上查看 `./downloads` 目录

## 故障排除

### 常见问题

1. **机器人不响应** - 检查 BOT_TOKEN 是否正确
2. **下载速度慢** - 这通常取决于 Telegram 服务器和您的网络连接
3. **"文件不存在"错误** - 检查机器人是否有权访问该文件

### 日志查看

可以通过以下命令查看日志：

```bash
docker compose logs -f
```

## 贡献指南

欢迎贡献代码或提出改进建议。请遵循以下步骤：

1. Fork 仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

## 许可证

此项目采用 MIT 许可证 - 详情请参阅 LICENSE 文件。
````

