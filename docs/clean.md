# Bot Cleanup Command

This bot includes a command to clean up its own messages from a channel within a specified time frame.

## Command: `!clean`

### Description

The `!clean` command deletes all messages sent by the bot in the channel where the command is called. The messages are deleted based on a specified number of minutes to look back.

### Usage

```plaintext
!clean <number_of_minutes>
```