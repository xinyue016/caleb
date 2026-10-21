# 夏以昼 AI 对话系统

一个可本地运行、可部署到公网、可接入微信官方公众号或 QQ 官方机器人的夏以昼人设对话系统。

项目核心：

- Web 聊天界面，电脑和手机浏览器都可使用
- 用户注册与密码登录
- 服务器 Cookie 会话，180 天内重新打开会自动恢复
- SQLite 多用户对话记忆与账号隔离
- 夏以昼专属人设与安全边界
- 支持 mock、OpenAI Responses API、OpenAI 兼容接口、Ollama
- 微信官方公众号回调接口
- QQ 官方机器人 Webhook 与主动回复接口
- Python 标准库即可启动，核心功能没有强制第三方依赖

> 不支持个人微信、个人 QQ 的自动登录或挂机机器人。这类方案违反平台规则，也存在封号风险。

## 1. 目录结构

    caleb-ai-chat/
    ├─ server.py              # Web 服务与 API
    ├─ persona.py             # 夏以昼人设和系统提示词
    ├─ chat_service.py        # 对话流程
    ├─ llm_client.py          # 模型提供方适配
    ├─ storage.py             # SQLite 记忆
    ├─ integrations.py        # 微信/QQ 官方接口
    ├─ static/                # 手机端和电脑端聊天界面
    ├─ data/                  # 自动生成 chat.db
    ├─ .env.example
    ├─ requirements.txt
    ├─ start.bat
    └─ start.ps1

## 2. 本地启动

在本目录打开 PowerShell：

    Copy-Item .env.example .env
    python server.py

也可以双击 start.bat。

默认地址：

    http://127.0.0.1:8787

手机与电脑在同一个 Wi-Fi 时，打开启动日志中的：

    http://你的电脑局域网IP:8787

如果 Windows 防火墙拦截，请允许 Python 使用专用网络。

## 3. 配置 AI 模型

编辑 .env 后重新启动服务器。

### 3.1 不配置模型，直接演示

    CALEB_PROVIDER=mock

系统使用内置人设规则回复，适合先测试界面、微信或 QQ 接线。此模式没有真正的大模型推理能力，所以不适合作为长期聊天语气；要获得自然、连续、非重复的对话，必须切换到 OpenAI、OpenAI 兼容接口或 Ollama。

### 3.2 OpenAI Responses API

    CALEB_PROVIDER=openai
    CALEB_MODEL=gpt-5.1
    OPENAI_API_KEY=你的APIKey
    CALEB_BASE_URL=https://api.openai.com/v1

### 3.3 OpenAI 兼容接口

用于支持 /chat/completions 的兼容服务：

    CALEB_PROVIDER=openai_compatible
    CALEB_MODEL=你的模型名
    OPENAI_API_KEY=你的APIKey
    CALEB_BASE_URL=https://你的服务地址/v1

### 3.4 Ollama

先在本机运行 Ollama 并拉取模型，例如：

    ollama pull qwen3:8b

然后：

    CALEB_PROVIDER=ollama
    CALEB_MODEL=qwen3:8b
    CALEB_BASE_URL=http://127.0.0.1:11434

## 4. 多用户账号系统

网页不再给所有访客共用同一个聊天记录。

- 用户打开网页先进入登录页
- 没有账号时可以点击“注册新账号”
- 登录成功后由服务器写入 HttpOnly Cookie
- 下一次打开同一网址会自动登录并恢复自己的聊天页面
- 每个账号的聊天记录、记忆和清空操作互相独立
- 密码使用 PBKDF2-SHA256 加盐哈希后保存，不保存明文
- 账号和会话默认保存在 data/chat.db

如果需要重置全部账号数据，停止服务器后删除 data/chat.db，再次启动即可。

## 5. 接入微信官方公众号

这不是个人微信机器人，而是微信公众平台的服务器回调。

1. 准备一个已认证或测试用的微信官方公众号。
2. 将本项目部署到有 HTTPS 公网域名的服务器。
3. 在 .env 设置：

       WECHAT_TOKEN=你自定义的Token
       WECHAT_PLAIN_MODE=true

4. 微信公众平台进入：
   设置与开发 -> 基本配置 -> 服务器配置
5. 填写：

   - URL：https://你的域名/webhooks/wechat
   - Token：与 WECHAT_TOKEN 完全一致
   - 消息加解密方式：先使用明文模式或兼容模式

6. 点击提交，服务器会完成 signature/timestamp/nonce/echostr 校验。
7. 用户给公众号发送文字后，消息会进入系统并由夏以昼回复。

生产环境若使用安全模式，需要继续加入微信 AES 消息解密和客服消息异步回复。当前项目已实现明文/兼容模式的同步文本回复，适合测试号和基础部署。

## 6. 接入 QQ 官方机器人

1. 在 QQ 开放平台创建官方机器人应用。
2. 记下 AppID、ClientSecret、Ed25519 私钥和公钥。
3. 安装可选依赖：

       pip install -r requirements.txt

4. 在 .env 设置：

       QQ_BOT_APP_ID=你的AppID
       QQ_BOT_CLIENT_SECRET=你的ClientSecret
       QQ_BOT_PRIVATE_KEY=Ed25519私钥Hex
       QQ_BOT_PUBLIC_KEY=Ed25519公钥Hex

5. 在 QQ 开放平台填写回调地址：

       https://你的域名/webhooks/qq

6. 平台发送 op=13 校验事件时，系统会使用私钥签名并返回验证结果。
7. 收到单聊或群聊 @机器人 消息后，系统会通过 QQ 官方 OpenAPI 回复。

QQ 官方接口的权限、沙箱环境、群聊权限和审核状态由 QQ 开放平台决定。

## 7. 部署到公网

可以使用 Render、Railway、Zeabur、云服务器等支持 Python Web Service 的平台。

通用设置：

- Build Command：pip install -r requirements.txt
- Start Command：python server.py
- 环境变量：参考 .env.example
- 端口：平台通常通过 PORT 环境变量提供，项目会自动读取

部署成功后，把平台给出的 HTTPS 域名填入微信或 QQ 后台。

## 8. 修改夏以昼人设

主要修改 persona.py 中的：

- PERSONA_FACTS：已确认的人物事实
- SYSTEM_PROMPT：说话风格、关系方式和安全规则

注意：不要写“不知道就随便编”。系统已经明确要求未知剧情要询问或承认记不清。

## 9. 数据与隐私

- 聊天记录保存在 data/chat.db
- 删除该文件会清空所有用户的全部记录
- 网页中的“清空当前对话”只删除当前浏览器用户的记录
- 部署到公网后，建议加入访问密码、限流和数据库备份
- 不要把 .env 上传到 GitHub

## 10. 常用接口

    GET  /api/health
    GET  /api/me
    POST /api/register
    POST /api/login
    POST /api/logout
    GET  /api/history
    POST /api/chat
    POST /api/reset
    GET  /webhooks/wechat
    POST /webhooks/wechat
    POST /webhooks/qq

网页调用 /api/chat 的示例：

    {
      "message": "你今天回不回家？",
      "platform": "web"
    }

## 11. 当前边界

- 已实现聊天、记忆、Web、微信明文/兼容模式和 QQ 官方 Webhook。
- 微信安全模式加密、客服消息异步推送尚未实现。
- QQ 接口需要官方平台的实际权限。
- 网页聊天必须登录账号，聊天接口会验证服务器会话。
- 公网部署仍建议增加限流、邮箱验证和管理后台。
