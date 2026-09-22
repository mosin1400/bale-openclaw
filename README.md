# Bale AI Bot (OpenClaw-based)

A Telegram/Bale bot based on OpenClaw that enables conversations with various AI models.

## 📋 Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Bot Commands](#bot-commands)
- [Thinking Levels](#thinking-levels)
- [File Structure](#file-structure)
- [How It Works](#how-it-works)
- [Models Cache](#models-cache)
- [Limitations](#limitations)
- [Security Notes](#security-notes)
- [Sample Conversation](#sample-conversation)
- [License](#license)

## ✨ Features

- **Multi-Model Support**: Choose from various OpenAI and other provider models
- **Chat History Management**: Save and retrieve previous conversations
- **Thinking Level Control**: Adjust model reasoning depth (light, medium, extra, high, max)
- **Message Deletion**: Delete sent messages in Bale for privacy
- **Token Monitoring**: Graphical display of remaining token usage
- **Persistent Storage**: Maintain user state even after bot restart
- **Models Caching**: Reduce repeated requests to OpenClaw server

## 🛠 Prerequisites

- Python 3.8 or higher
- Access to OpenClaw service (running on `http://127.0.0.1:18789`)
- Bale bot token (get from [@BotFather](https://t.me/BotFather) or Bale equivalent)
- Python libraries (listed in `requirements.txt`)

## 📥 Installation & Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <project-directory>
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Bot Token

Edit `config.py` and add your bot token:

```python
BALE_TOKEN="YOUR_BOT_TOKEN_HERE"
OPENCLAW_URL="http://127.0.0.1:18789"
```

> ⚠️ **Security Warning**: Never commit `config.py` to public GitHub repositories.

### 4. Run the Bot

```bash
python main.py
```

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BALE_TOKEN` | Bale bot token | - |
| `OPENCLAW_URL` | OpenClaw server URL | `http://127.0.0.1:18789` |
| `MAX_HISTORY_PER_USER` | Max chats stored per user | 30 |
| `MAX_RECENT_CHATS_SHOWN` | Max chats shown in list | 8 |
| `MODELS_CACHE_TTL_SECONDS` | Models cache TTL (seconds) | 120 |
| `MAX_MODEL_LIST` | Max models displayed | 12 |

## 📜 Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Start bot and show welcome message | `/start` |
| `/help` | Show full command list | `/help` |
| `/newchat` or `/new` | Create new chat and archive current one | `/newchat` |
| `/end` or `/exit` | Stop conversation and save to history | `/end` |
| `/recentchats` | Show recent chat history | `/recentchats` |
| `/continuechat <index>` | Continue a chat from history | `/continuechat 2` |
| `/clear` | Delete all chat messages in Bale + reset history | `/clear` |
| `/deletehistory <all\|index>` | Delete one or all history items | `/deletehistory all` |
| `/models` | Show OpenAI models list | `/models` |
| `/models all` | Show all available models | `/models all` |
| `/models <index>` | Select model by number | `/models 3` |
| `/models <model_id>` | Select model directly by ID | `/models openai/gpt-4` |
| `/model` | Show current model | `/model` |
| `/reasoning` or `/thinking` | Show current thinking level | `/reasoning` |
| `/reasoning <level>` | Set thinking level | `/reasoning medium` |
| `/remainingusage` | Show remaining tokens graphically | `/remainingusage` |

## 🧠 Thinking Levels

| Value | Display | Description |
|-------|---------|-------------|
| `off` | Off | Disable thinking |
| `minimal` | Minimal | Minimum thinking |
| `light` or `low` | light | Light thinking |
| `medium` or `med` | medium | Medium thinking |
| `high` | high | High thinking |
| `extra` or `xhigh` | extra | Extra high thinking |
| `max` | max | Maximum thinking |

### Changing Thinking Level Examples

```
/reasoning light    # Light thinking
/reasoning medium   # Medium thinking
/reasoning extra    # Extra high thinking
/reasoning max      # Maximum thinking
/reasoning off      # Disable thinking
```

## 📁 File Structure

```
.
├── main.py              # Main bot code
├── config.py            # Configuration file (tokens & URLs)
├── requirements.txt     # Python dependencies
├── history.json         # Persistent user state storage
└── README.md            # This readme file
```

## 🔧 How It Works

### Chat Lifecycle

1. **Start**: User sends `/start`
2. **Select Model**: User chooses model via `/models`
3. **Set Thinking**: User adjusts thinking level with `/reasoning`
4. **Send Message**: User sends their message
5. **Processing**: Bot sends message to OpenClaw and receives response
6. **Storage**: User and bot messages are saved in `history.json`
7. **End**: User ends chat with `/end` or `/newchat`

### User State Management

- User state is maintained in memory (`user_states`)
- State is periodically saved to `history.json` and on important changes
- On bot restart, states are restored from the file

## 🗄 Models Cache

To reduce repeated requests to OpenClaw server, models are cached:

- **TTL**: 120 seconds (configurable via `MODELS_CACHE_TTL_SECONDS`)
- **Cache Keys**: 
  - `openai`: OpenAI provider models
  - `all`: All available models

## ⚠️ Limitations

- Requires running OpenClaw server
- Maximum 30 recent chats stored per user
- Maximum 12 models displayed in list
- Message deletion in Bale may not always succeed (depends on API)

## 🔒 Security Notes

1. **Protect Token**: Add `config.py` to `.gitignore`
2. **No Git Upload**: Never upload tokens to public repositories
3. **Use Environment Variables**: In production, use environment variables
4. **Restrict Access**: Limit access to OpenClaw server

### Sample `.gitignore`

```gitignore
config.py
history.json
__pycache__/
*.pyc
.env
```

## 💬 Sample Conversation

```
User: /start
Bot: 👋 Hello! AI Bot is ready.

User: /models
Bot: 📡 OpenAI Models:
     1. ● openai/gpt-4
     2. ● openai/gpt-3.5-turbo ✅
     3. ○ openai/gpt-3.5

User: /models 1
Bot: ✅ Current model set to: openai/gpt-4

User: /reasoning medium
Bot: ✅ thinking set to medium.

User: What is the capital of Iran?
Bot: The capital of Iran is Tehran.

User: /end
Bot: Conversation saved.
```

## 📄 License

This project is published without a specific license. For commercial use or distribution, please contact the developer.

## 🆘 Support

For bug reports or feature requests, please create an issue or contact the developer.

---

**Developed with ❤️ for the Bale platform**
