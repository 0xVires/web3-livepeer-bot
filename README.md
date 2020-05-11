# web3-livepeer-bot
Sends telegram notifications about activities of the Livepeer contracts on the Ethereum blockchain.

**Link to the Telegram bot**

https://t.me/OrchestratorWatcherBot

**Setup**

Adjust the setup.py file accordingly - You will need to specify your web3 websocket, your telegram ID (for error messages) and the telegram bot token.
The block_records.txt and telegram-subscriptions.json files are just examples. Those files will be populated while running the scripts. 

**What does the bot do?**

By writing “/start”, the bot will give you an introduction and informs about the available commands:

* subscribe <orchestrator address>
* remove <orchestrator address>
* subscriptions

If you subscribe to an orchestrator (or multiple, there is no limit), you will get notified about the following events:

* reward calls
* delayed reward calls
* missed reward calls
* when the reward/fee cut changes
* orchestrator becomes active/inactive

Whenever possible, the transaction link is inclueded so that you can be sure that no incorrect information is sent. Please note that it’s always possible that there is an error in the script.

A note on the wording regarding "orchestrator"/"transcoder":
Originally, only transcoders existed in the livepeer protocol. This changed with an update and the correct wording would now be "orchestrators". However, since the contract calls still use "transcoder", only the outgoing messages have been adjusted.

More information here: https://forum.livepeer.org/t/telegram-bot-transcoder-watcher/
