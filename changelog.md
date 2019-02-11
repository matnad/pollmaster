# Changelog for Version 2.0

## TL;DR
- Poll creation now interactive
- New prefix: **pm!** (can be customized)
- All commands and roles have been changed, check **pm!help**

## Complete Overhaul
- Voting is no longer done per text, but by using reactions
- Poll creation has been streamlined and is now interactive
- An exhaustive pm!help function

## New features
- Prepare polls in advance and schedule them or activate them on demand
- A quick poll function with default settings
- Multiple Choice as new settings (allow more than one answer)

## Full Private Message and Multi Server Support
- **Every command can be used in private messages with pollmaster**
- This works even if you are in many servers with the bot
- Context sensitive detection of which server(s) are affected
- Promt the user for a server if still ambiguous

## New Look
- Complete visual overhaul for every aspect
- New custom icons

## New Database
- Changed the way all the polls are stored
- Added server specific configurations 

## New Prefix
- **pm!** is the new default prefix
- Prefix can be customized for each server

## New roles and permissions
- Users with "Manage Server" permissions can now use all functions regardless of pollmaster specific permissions
- Two new type of roles: *polladmin* and *polluser*
- They can be set with *!polladmin role* and *!polluser role*
- More infos pm!help -> configuration
- The *pollmaster* role is deprecated

## Compability
- Most databases will be preserved and converted to the new format
- If your server lost data, please join the support server or contact the developer