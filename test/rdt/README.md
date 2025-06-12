Feel free to reach me on Discord @**ozymandiasthegreat** in case you need assistance.
# How to implement multi-accounting?
Modify ```accounts.json``` and add as many accounts as you need.<br><br>
Example#1:
```
[
    {
        "username":"user1",
        "password":"pass1"
    }
]
```
If your ```accounts.json``` file looks like the above, the bot will only use one account ```user1:pass1```. To add new accounts, the structure of ```accounts.json``` should look like this:
<br><br>

Example#2:
```
[
    {
        "username":"user1",
        "password":"pass2"
    },
    {
        "username":"user2",
        "password":"pass2"
    },
    {
        "username":"user3",
        "password":"pass3"
    }
]
```
In the above example of ```accounts.json``` the bot will loop between three accounts ```user1:pass1```, ```user2:pass2``` and ```user3:pass3```. The bot will use the first account to send a DM and immediately switch to the second account to prevent the first account from being detected and shadowbanned; when the bot reaches the last available account ```user3:pass3``` and finds no more accounts to send DMs, it just loops through the accounts again.