![image description](https://github.com/Muhammadsaid2oo6/AnonimVaqtiBot/blob/master/cover.jpg)
# AnonimVaqti Bot

Telegram bot for anonymous messaging.

## Features

- Anonymous messaging
- Voice messages support
- Photo messages support
- Message statistics
- User blocking system
- Reply chain support
- Command menu interface

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token
MONGODB_URI=your_mongodb_uri
```

3. Run the bot:
```bash
python bot.py
```

## Deployment

### Prerequisites
- Python 3.9+
- MongoDB database
- Telegram Bot Token

### Cloud Deployment Steps

1. Clone the repository
2. Set up environment variables on your cloud platform:
   - `TELEGRAM_BOT_TOKEN`
   - `MONGODB_URI`
3. Deploy using the provided Procfile

## Commands

- `/start` - Start the bot
- `/mystats` - View your statistics
- `/url` - Create a new anonymous message link
- `/blacklist` - Clear your block list
- `/issue` - Send feedback or report issues 
