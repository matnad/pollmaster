# Setting up Pollmaster

## Requirements

These steps have been tested on Ubuntu 19.04 with miniconda for Python 3.7 and Docker  
[Miniconda3](https://docs.conda.io/en/latest/miniconda.html)  
[Docker Engine: Community](https://docs.docker.com/install/linux/docker-ce/ubuntu/)

## Installation

Execute the following commands from a terminal window:
```sh
conda create --name pollmaster
conda activate pollmaster
git clone https://github.com/matnad/pollmaster.git
cd pollmaster
conda install pip
~/miniconda3/envs/pollmaster/bin/pip install -r requirements.txt
```
##  Setup app and bot in Discord 

- Setup an app and a bot using [Creating a Bot Account](https://discordpy.readthedocs.io/en/latest/discord.html#creating-a-bot-account)

## Running the application

- start a mongodb container using docker run -it -d -p 27017:27017 --name mongodb mongo
- Create a secrets.py in essentials folder in the project. You can use the following template

```python
class Secrets:
    def __init__(self):
        self.dbl_token = ''  # DBL token (only needed for public bot)
        self.mongo_db = 'mongodb://localhost:27017/pollmaster'
        self.bot_token = '' # official discord bot token
        self.mode = 'development' # or production

SECRETS = Secrets()
```

- Run the application using python pollmaster.py
- You can see the following :
```
AsyncIOMotorDatabase(Database(MongoClient(host=['localhost:27017'], document_class=dict, tz_aware=False, connect=False, driver=DriverInfo(name='Motor', version='2.0.0', platform=None)), 'pollmaster'))
Servers verified. Bot running.
```
##  Invite the bot in Discord 

- Generate url to invite the bot using [Inviting Your Bot](https://discordpy.readthedocs.io/en/latest/discord.html#inviting-your-bot)
- Specify permissions by using the following bit format of the bot permissions appended to the bot invitation url and paste the url in browser and follow the instructions as given in the above url 

> &permissions=1073867840

- Now you will see the bot in your Discord channel
- Try commands like pm!help and pm!new

## Log files

- You can view the log file pollmaster.log in the pollmaster directory