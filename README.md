# * SHAPES API HAS BEEN DISABLED SO THIS PROJECT WILL NOT WORKING ANYMORE

# WARNING: SHAPES API IS BANNED FROM DISCORD, YOUR ACCOUNT MAY BE AT RISK IF DISCORD DETECTS THAT YOUR BOT IS USING SHAPES API

# Setup Instructions

## Prerequisites

- Python 3.8 or higher
- A Discord bot token (create one at https://discord.com/developers/applications)
- A Shapes API key and Shape username (obtain from https://shapes.inc)

## Installation Steps

1. Clone or download this repository to your local machine.

2. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file (or rename the `.env.example` file) in the root directory with the following content:
   ```
   #=========REQUIRED=========
   ## Discord Bot Configuration
   BOT_TOKEN=              # your discord bot TOKEN

   ## Shapes API Configuration
   SHAPES_API_KEY=         # your shapes API key
   SHAPES_USERNAME=        # your shape username (the vanity name after https://shapes.inc/)

   #=========CUSTOMIZE=========
   ## Discord Bot Configuration
   BOT_OWNER=              # your user ID, used for permission to block bot responding to someone
   REPLY_STYLE=            # reply style configuration (1=reply with ping, 2=reply no ping, 3=direct message to channel)

   ## Shapes Bot Configuration
   TRIGGER_WORDS=          # list of words that trigger the bot to respond (comma-separated)
   ERROR_MESSAGE=          # custom error message when bot fail to get AI response

   ## Bot Activity Configuration
   STATUS=online           # online, idle, dnd, invisible
   ACTIVITY_TYPE=none      # playing, streaming, listening, watching, competing, custom, none
   ACTIVITY_MESSAGE=       # text displayed in the bot's activity status
   ```

4. Replace the placeholder values with your actual Discord Bot token, Shapes API key, and Shape username.

5. Run the bot:
   ```
   python main.py
   ```
   
### You can host the Bot for free on [sillydev](https://panel.sillydev.co.uk) if you don't want to run it on your local machine.

1. Create a server
   - In **Server Software Type** select `Coding Languages`
   - In **Server Software** select `Python`

2. Upload the code project on your server

3. In the **Startup ►** tab
   - Edit **App py file** from `app.py` to `main.py`
   - If your `main.py` is not in `/home/container/`, make sure to move code project there or update the path accordingly

## Get Shapes API Key

1. Go to https://shapes.inc/developer
2. Generate API Key
3. Copy API Key and paste to .env

## Get SHAPES_USERNAME

1. Go to https://shapes.inc/explore
2. Select the shape
3. SHAPES_USERNAME is the vanity name after https://shapes.inc/ (eg: SHAPES_USERNAME of https://shapes.inc/tenshi is tenshi)

## Discord Bot Setup

1. Go to https://discord.com/developers/applications
2. Create a new application and set up a bot
3. Enable the following Privileged Gateway Intents:
   - Server Members Intent
   - Message Content Intent
4. Generate an invite link with the following permissions:
   - View Channels
   - Send Messages
   - Send Messages in Threads
   - Read Message History
   - Attach Files
   - Embed Links
   - Mention @everyone, @here and All Roles (for revival chat function)
5. Invite the bot to your server using the generated link

# Usage

## Basic Interaction
- Send a direct message to the bot to start a private conversation
- Mention the bot (@BotName) in a server channel to get a response
- Reply to one of the bot's messages to continue a conversation

## Slash Commands
The bot provides slash commands:
  
- `/auth <option: action>` - Authenticate with Shapes API or remove authentication
  - Action: Authenticate/Remove Authentication

- `/activate <enable: True/False>` - Make the bot respond to all messages in the channel

- `/blacklist` and `/whitelist` - Manage whitelist/blacklist channels: blacklist channels = bot ignore those channels, whitelist channels = bot only respond in those channels
  - Mode Conflict: Using `blacklist` will auto clear `whitelist` and vice versa

- `/block <user> <action: Block/Unblock>` - Block or unlock a user from chatting with the bot in server

- `/botchat <enable: True/False>` - Enable or disable bot-to-bot conversations in the channel
  
- `/permission <action: Add/Remove/List> <command_name> <option: role>` - Add or remove roles that can use specific bot commands

- `/revivechat <action: enable/disable/status> <option: channel> <option: role> <option: interval>` - Revive chat with scheduled messages

- `/say <message> <option: channel>` - Make the bot say a message
  
- `/trigger <action: Add/Remove/List> <option: word>` - Server-specific trigger word management

- `/welcome <channel> <status: Enable/Disable>` - Select ⁠channel to send welcome message when new members join

## Prefix Commands
The bot using Shapes API prefix commands
```
!help      - Display a list of available commands and their descriptions.
!wack      - Reset conversation history with the shape.
!reset     - Completely reset the shape's memory and conversation history.
!sleep     - Save your conversation to long-term memory.
!info      - Display debug information about the shape.
!dashboard - Get a link to edit your shape on the dashboard.
!voice     - Force voice generation for the next response (one-time override).
!imagine   - Generate an image based on your description.
!web       - Include results from Internet search in the response.
```

## Capabilities
- AI chat: Responds to messages using Shapes Inc
- Contextual Replies
- Auth to link user personal/memories
- Image, sticker & Voice process
- Channel Modes
- Bot talks to Bot
- Trigger Words: The bot will respond to messages containing trigger words defined in the `.env` file (global) or using `/trigger` (server-specific)
- Revival chat & Welcomer chat

## Troubleshooting

- **Bot not responding**: Ensure you've set up the correct permissions and intents
- **API errors**: Check your Shapes API key and username
- **Rate limiting**: The bot will inform you if it's being rate limited by the API
- **Logging**: Check the logs for detailed information about any errors

