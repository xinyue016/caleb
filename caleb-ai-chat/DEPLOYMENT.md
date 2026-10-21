# 导出与部署说明

## 一、这个导出包里有什么

- 夏以昼多用户 AI 网页
- 注册、登录、服务器会话
- 每个账号独立的聊天记录
- SQLite 持久化数据库
- 夏以昼双层人格设定
- 微信官方公众号回调接口
- QQ 官方机器人接口
- VS Code 本地运行和端口转发支持
- Render / Railway 部署配置

## 二、用 VS Code 打开

1. 解压压缩包。
2. 用 VS Code 打开解压后的 caleb-ai-chat 文件夹。
3. 打开终端。
4. 执行：

    Copy-Item .env.example .env
    python server.py

5. 浏览器打开：

    http://127.0.0.1:8787

第一次进入需要注册账号。

## 三、通过 VS Code 给手机临时访问

1. 保持 python server.py 运行。
2. 在 VS Code 底部打开 PORTS / 端口。
3. 转发端口 8787。
4. 将端口可见性设置为 Public / 公开。
5. 复制类似的 Forwarded Address：

    https://xxxxxxxx-8787.devtunnels.ms

该网址可由手机流量访问。VS Code 和电脑关闭后，临时网址会失效，但 SQLite 中的用户数据不会丢失。

## 四、通过 GitHub + Render 长期部署

1. 在 GitHub 创建公开仓库。
2. 将本项目文件推送到仓库。
3. 登录 Render，选择 New Web Service。
4. 连接该 GitHub 仓库。
5. Build Command：

    pip install -r requirements.txt

6. Start Command：

    python server.py

7. 添加环境变量。至少设置：

    HOST=0.0.0.0
    CALEB_PROVIDER=mock

8. 部署完成后，Render 会提供固定 HTTPS 地址。

## 五、接入真实 AI 模型

MOCK 模式只用于测试界面和机器人接线，不是真正的大模型。

推荐使用 OpenAI 兼容接口：

    CALEB_PROVIDER=openai_compatible
    CALEB_MODEL=服务商提供的模型名
    OPENAI_API_KEY=你的APIKey
    CALEB_BASE_URL=服务商提供的兼容接口地址

也支持：

    CALEB_PROVIDER=openai

以及本地 Ollama：

    CALEB_PROVIDER=ollama
    CALEB_MODEL=qwen3:8b
    CALEB_BASE_URL=http://127.0.0.1:11434

## 六、微信接入

仅支持微信官方公众号或测试号，不支持个人微信自动机器人。

回调地址：

    https://你的域名/webhooks/wechat

在 .env 设置：

    WECHAT_TOKEN=你的Token
    WECHAT_PLAIN_MODE=true

消息加解密方式先使用明文模式或兼容模式。

## 七、数据保存

默认数据库位置：

    data/chat.db

删除该文件会删除全部账号和聊天记录。备份时直接复制该文件即可。

## 八、Git

本项目已经包含 Git 提交历史。GitHub 可访问时可以直接推送。如果 GitHub 当前网络不可用，可先使用 VS Code 端口转发，或者把导出包发送到其他可运行 Python 的服务器。
