#!/bin/bash
# Script to start SushBotSeller Telegram Bot

cd /opt/sushbotseller
source venv/bin/activate

# Start the bot
python -m bot.main

