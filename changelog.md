# Changelog for Version 2.5

## New features
- Emoji-Only polls are now supported, including custom, uploaded emojis!
- Documentation on how to host your own instance: `setup.md`

## Important note for self-hosted bots
- Update requirements: `pip install -r requirements.txt`
- Version 2.5 include breaking database changes.<br />
To ensure old polls are compatible with the newest version you need to run:<br />
`migrations/1_to2-5_migrate_votes.py`

## Changes and Fixes
- Most libraries updated and adjusted code. Migrated to tasks.loop
- Votes are now stored in a separated database table to speed up parallel access
- Refresh Queue and Blocking: Max. 1 refresh per ~5 seconds -> improved performance for large polls
- Polls with hidden votes now remove reactions
- Purge reactions for anonymous and hidden polls more rigorously
- Paperclip and ?-Emojis now reset after clicking
- Question from 200 to 400 max. characters
- Increased time until timeout when using the wizard
- Improved Error messages
- Lots of refactoring and minor improvements
# Changelog for Version 2.4

## New features
- Write in answers (survey flags) per option
- Option to hide vote count while the poll is running
- Copying polls now possible (pm!copy)
- The text messages to create a poll (spam) will now delete after the poll is created
- @mention command (prefix independent)
- Admin module with hot-reloading to make patching easier

## Changes and Fixes
- Split pm!new into pm!new (basic poll) and pm!advanced (all features)
- Polls should now activate and close properly
- Poll info shows current votes
- pm!cmd is enabled again! Hopefully it works this time...
- Channel selection in PM bug fixed


# Changelog for Version 2.2

## New features
- Polls will now automatically activate or close and post themselves to the specified channel
- Improved ❔ functionality: Now lists the current votes for each options
- pm!cmd feature is enabled again with more error logging
- Title and options now support most UTF-8 characters, meaning you can put emojis and special characters in your poll

## Changes and Fixes
- Improved performance and scalability. Should feel a lot more responsive now
- Fixed formatting issues for closed polls
- Export now shows server specific nickname is applicable
- Users can no longer create polls in channels where they don't have "send message" permissions


# Changelog for Version 2.1

## New features
- React to a poll with ❔ to get personalised info
- Added back the command line feature from version 1. Type *pm!cmd help* to get started
- Multiple choice is no longer a flag, but a number of how many options each voter can choose 

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