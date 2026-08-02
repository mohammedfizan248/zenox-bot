import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
AUTO_ROLE_ID = os.getenv("AUTO_ROLE_ID")
MOD_ROLE_NAME = os.getenv("MOD_ROLE_NAME", "Moderator")
MUSIC_VOLUME = int(os.getenv("MUSIC_VOLUME", 50))
SAMP_SERVER_HOST = os.getenv("SAMP_SERVER_HOST", "")
SAMP_SERVER_PORT = int(os.getenv("SAMP_SERVER_PORT", 7777))
SAMP_QUERY_TIMEOUT = int(os.getenv("SAMP_QUERY_TIMEOUT", 5))
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "s33_Xlrp")
