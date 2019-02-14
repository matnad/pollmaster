import discord

from essentials.secrets import SECRETS


class Settings:
    def __init__(self):
        self.color = discord.Colour(int('7289da', 16))
        self.title_icon = "https://i.imgur.com/vtLsAl8.jpg" #PM
        self.author_icon = "https://i.imgur.com/TYbBtwB.jpg" #tag
        self.report_icon = "https://i.imgur.com/YksGRLN.png" #report
        self.owner_id = 117687652278468610
        self.msg_errors = False
        self.log_errors = True
        self.invite_link = \
            'https://discordapp.com/api/oauth2/authorize?client_id=444831720659877889&permissions=126016&scope=bot'

        self.load_secrets()

    def load_secrets(self):
        # secret
        self.dbl_token = SECRETS.dbl_token
        self.mongo_db = SECRETS.mongo_db
        self.bot_token = SECRETS.bot_token


SETTINGS = Settings()
