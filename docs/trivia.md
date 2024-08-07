```plaintext
!trivia [number_of_questions] [answer_time] [start_delay]
```
The `!trivia` command initiates a trivia game in the channel, asking a specified number of questions and waiting a set amount of time before sharing the answers. Optionally, a delay before starting the game can be set. If a delay is set, an `@here` alert will be added to the message.

Submit your answer by selecting a reaction on the bot's message. Only select one answer, or you will be docked points.
### Defaults
- `number_of_questions`: 3
- `answer_time`: 30 seconds
- `start_delay`: 0 seconds