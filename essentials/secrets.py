import os
from dotenv import load_dotenv
load_dotenv(".env")

class Secrets:
    def __init__(self):
        self.dbl_token = ''  # DBL token (only needed for public bot)
        self.mongo_db =  os.getenv('MONGO_URL')
        self.bot_token = os.getenv('pollmaster_token') # official discord bot token
        self.mode = 'development' # or production

SECRETS = Secrets()