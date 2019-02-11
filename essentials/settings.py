import discord

from essentials.secrets import SECRETS


class Settings:
    def __init__(self):
        self.color = discord.Colour(int('7289da', 16))
        self.title_icon = "http://mnadler.ch/img/tag.png"
        self.author_icon = "http://mnadler.ch/img/tag.jpg"
        self.report_icon = "http://mnadler.ch/img/report.png"
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
