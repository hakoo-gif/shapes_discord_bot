## WARNING: DISCORD MAY BAN YOU SINCE SHAPES API GOT BANNED FROM THEIR PLATFORM, MAKE SURE YOU LEFT NO HINT OF THE BOT IN YOUR MAIN ACCOUNT (YOU CAN CREATE BOT ON AN ALT ACC AND USE HOSTING SERVICE)

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- A Discord bot token (create one at https://discord.com/developers/applications)
- A Shapes API key and Shape username (obtain from https://shapes.inc)

### Installation Steps

1. Clone or download this repository to your local machine.

2. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with the following content:
   ```
   #=========REQUIRED=========
   ## Discord Bot Configuration
   BOT_TOKEN=              # your discord bot TOKEN

   ## Shapes API Configuration
   SHAPES_API_KEY=         # your shapes API key
   SHAPES_USERNAME=         # your shape username (the vanity name after https://shapes.inc/)

   #=========CUSTOMIZE=========
   ## Discord Bot Configuration
   BOT_OWNER=              # your user ID, used for permission to block bot responding to someone
   REPLY_STYLE=            # reply style configuration (1=reply with ping, 2=reply no ping, 3=direct message)

   ## Shapes Bot Configuration
   TRIGGER_WORDS=          # list of words that trigger the bot to respond (comma-separated)
   ERROR_MESSAGE=          # custom error message when bot fail to get AI response

   ## Bot Activity Configuration
   STATUS=online           # online, idle, dnd, invisible
   ACTIVITY_TYPE=none      # playing, streaming, listening, watching, competing, custom, none
   ACTIVITY_MESSAGE=       # text displayed in the bot's activity status
   ```

4. Replace the placeholder values with your actual Discord token, User ID, Shapes API key, and Shape username.

5. Run the bot:
   ```
   python main.py
   ```

## Get Shapes API Key

1. Go to https://shapes.inc/developer
2. Generate API Key
3. Copy API Key and paste to .env

## Get SHAPE_USERNAME

1. Go to https://shapes.inc/explore
2. Select the shape
3. SHAPES_USERNAME is the vanity name after https://shapes.inc/ (eg: SHAPE_USERNAME of https://shapes.inc/tenshi is tenshi)

## Discord Bot Setup

1. Go to https://discord.com/developers/applications
2. Create a new application and set up a bot
3. Enable the following Privileged Gateway Intents:
   - Server Members Intent
   - Message Content Intent
4. Generate an invite link with the following permissions:
   - Read Messages/View Channels
   - Send Messages
   - Send Messages in Threads
   - Read Message History
   - Attach Files
   - Embed Links
5. Invite the bot to your server using the generated link

## Usage

### Basic Interaction
- Send a direct message to the bot to start a private conversation
- Mention the bot (@BotName) in a server channel to get a response
- Reply to one of the bot's messages to continue a conversation

### Slash Commands
The bot provides slash commands:
  
- `/auth <option: action>` - Authenticate with Shapes API or remove authentication
  - Action: Authenticate/Remove Authentication

- `/activate <enable: True/False>` - Make the bot respond to all messages in the channel

- `/blacklist` and `/whitelist` - Manage whitelist/blacklist channels: blacklist channels = bot ignore those channels, whitelist channels = bot only respond in those channels
  - Mode Conflict: Using `blacklist` will auto clear `whitelist` and vice versa

- `/block <user> <action: Block/Unblock>` - Make the bot respond to all messages in the channel
  
- `/permission <action: Add/Remove/List> <command_name> <option: role>` - Add or remove roles that can use specific bot commands

- `/revivechat <action: enable/disable/status> <option: channel> <option: role> <option: interval>` - Revive chat with scheduled messages
  
- `/trigger <action: Add/Remove/List> <option: word>` - Server-specific trigger word management

### Prefix Commands
The bot using Shapes API prefix commands

!help      - Display a list of available commands and their descriptions.
!wack      - Reset conversation history with the shape.
!reset     - Completely reset the shape's memory and conversation history.
!sleep     - Save your conversation to long-term memory.
!info      - Display debug information about the shape.
!dashboard - Get a link to edit your shape on the dashboard.
!imagine   - Generate an image based on your description.
!web       - Include results from Internet search in the response.

### Capabilities
- AI chat: Responds to messages using Shapes Inc
- Contextual Replies
- Image & Voice process (include sticker)
- Channel Modes
- Trigger Words: The bot will respond to messages containing trigger words defined in the `.env` file (global) or using `/trigger` (server-specific)
- Custom Bot Status, Reply Style, Error Message

## Troubleshooting

- **Bot not responding**: Ensure you've set up the correct permissions and intents
- **API errors**: Check your Shapes API key and username
- **Rate limiting**: The bot will inform you if it's being rate limited by the API
- **Logging**: Check the logs directory for detailed information about any errors
