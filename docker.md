# Setting up Pollmaster for Docker Development

## Purpose

These instructions are intended to help configure a development environment. They have not been designed or written with considerations for security, and are therefore not appropriate to run in a production environment.

## Requirements

These steps have been tested on Ubuntu 20.04

[Docker Engine: Community](https://docs.docker.com/install/linux/docker-ce/ubuntu/)

## Installation

Execute the following commands from a terminal window:
```sh
git clone https://github.com/matnad/pollmaster.git
cd pollmaster
```
##  Setup app and bot in Discord 

- Setup an app and a bot using [Creating a Bot Account](https://discordpy.readthedocs.io/en/latest/discord.html#creating-a-bot-account)

## Running the application

- Create a secrets.py in essentials folder in the project. You can use the following template

```python
class Secrets:
    def __init__(self):
        self.dbl_token = ''  # DBL token (only needed for public bot)
        self.mongo_db = 'mongodb://username:password@db:27017/pollmaster' # Replace with credentials in mongo-init.js
        self.bot_token = '' # official discord bot token
        self.mode = 'development' # or production

SECRETS = Secrets()
```

- Update essentials/settings.py ; set the owner\_id to the developer's User ID in Discord
- Run the following commands from a terminal window, within the pollmaster working directory:
```sh
docker-compose build
docker-compose up -d
```
- When making changes to the Python code, run these commands to restart the bot:
```sh
docker stop pollmaster_bot_1
docker start pollmaster_bot_1
```

##  Invite the bot in Discord 

- Generate url to invite the bot using [Inviting Your Bot](https://discordpy.readthedocs.io/en/latest/discord.html#inviting-your-bot)
- Specify permissions by using the following bit format of the bot permissions appended to the bot invitation url and paste the url in browser and follow the instructions as given in the above url 

> &permissions=1073867840

- Now you will see the bot in your Discord channel
- Try commands like pm!help and pm!new

## Log files

- You can view the log file pollmaster.log in the pollmaster directory
- These commands will also output anything from the two docker containers:
```sh
docker logs pollmaster_bot_1
docker logs pollmaster_mongodb_1
```

## Cleanup

When finished development work, run this command from the pollmaster working copy to remove the docker containers:
```sh
docker-compose down
```

If you would like to clear the MongoDB database files, remove the data/ directory as well.

