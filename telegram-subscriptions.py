import json 
import requests
import time
from web3 import Web3
from setup import WS_GETH, WS_INFURA, TEL_URL, MY_TELEGRAM_ID, send_message, BONDING_MANAGER_PROXY, BONDING_MANAGER_ABI

w3 = Web3(Web3.WebsocketProvider(WS_GETH))

bonding_manager_proxy = w3.eth.contract(address=BONDING_MANAGER_PROXY, abi=json.loads(BONDING_MANAGER_ABI))

def get_json_from_url(url):
    content = requests.get(url).content.decode("utf8")
    js = json.loads(content)
    return js

def get_updates(offset=None):
    getUpdatesURL = TEL_URL + "getUpdates?timeout=60"
    if offset:
        getUpdatesURL += "&offset={}".format(offset)
    js = get_json_from_url(getUpdatesURL)
    return js

def get_last_update_id(updates):
    last_id = updates["result"][-1]["update_id"]
    return last_id

def handleSubscription(subscriptions, chat_id, transcoderChecksum):
    """Handles adding a subscription
    Cases: 
    1) transcoder & chat_id is already in subscriptions: do nothing
    2) t is in subscriptions but not c: append c to t
    3) t is not in subscriptions: add t & c
    """
    if subscriptions.get(transcoderChecksum):
        if chat_id in subscriptions[transcoderChecksum]:
            send_message("You are already subscribed to this address", chat_id)
            return
        else:
            subscriptions[transcoderChecksum].append(chat_id)
    else:
        subscriptions[transcoderChecksum] = [chat_id]
    with open("transcoder_subscriptions.json", "w") as f:
        json.dump(subscriptions, f, indent=1)
    send_message("Subscription added, you will now be notified about events of {}".format(transcoderChecksum), chat_id)

def handleUnsubscribe(subscriptions, chat_id, transcoderChecksum):
    """Handles subscription removal

    Check if the chat_id is subscribed to the transcoder.
    If true: delete chat_id from transcoder. 
    If the transcoder has no subscribers, remove the transcoder.
    """
    if chat_id in subscriptions[transcoderChecksum]:
        subscriptions[transcoderChecksum].remove(chat_id)
        if not subscriptions[transcoderChecksum]:
            del subscriptions[transcoderChecksum]
        with open("transcoder_subscriptions.json", "w") as f:
            json.dump(subscriptions, f, indent=1)
        send_message("You are now unsubscribed from orchestrator {}".format(transcoderChecksum), chat_id)
    else:
        send_message("You are not subscribed to this orchestrator", chat_id)


def getTranscoder_IfValid(message, chat_id):
    transcoderAddr = message[message.find("0x"):message.find("0x")+42]
    if w3.isAddress(transcoderAddr):
        transcoderChecksum = w3.toChecksumAddress(transcoderAddr)
        if bonding_manager_proxy.functions.isRegisteredTranscoder(transcoderChecksum).call():
            return transcoderChecksum
        else:
            send_message("The entered address is not a registered orchestrator. Please try again", chat_id)
    else:
        send_message("The entered address is not valid. Please try again", chat_id)

def getTranscoder(message):
    transcoderChecksum = w3.toChecksumAddress(message[message.find("0x"):message.find("0x")+42])
    return transcoderChecksum

def displaySubscriptions(chat_id):
    with open("transcoder_subscriptions.json", "r") as f:
        subscriptions = json.load(f)
    message = [t for t, cid in subscriptions.items() if chat_id in cid]
    send_message("You are subscribed to the following orchestrators:\n" + "\n".join(message), chat_id)

def checkMessage(updates):
    for update in updates["result"]:
        try:
            message = update["message"]["text"]
            chat_id = update["message"]["chat"]["id"]
            if message == "/start":
                send_message("Welcome to the Orchestrator-Watcher bot!\n\nThis bot is provided by the " \
                    "[0x525-Transcoder](https://forum.livepeer.org/t/transcoder-campaign-0x525-with-telegram-bot/588), " \
                    "Discord: vires-in-numeris. Tips to 0x525419FF5707190389bfb5C87c375D710F5fCb0E are appreciated, thank you!\n\n" \
                    "The following commands are available:\n - *subscribe* <orchestrator address>\n - *remove* <orchestrator address>\n - " \
                    "*subscriptions*\n\nPlease enter *subscribe* followed by the orchestrator address " \
                    "(e.g. 'subscribe 0x525419FF5707190389bfb5C87c375D710F5fCb0E') to get notified about the following events:\n - " \
                    "reward calls\n - missed reward calls\n - when the reward/fee cut changes\n - orchestrator becomes inactive\n\n" \
                    "If you no longer want to be notified, enter *remove* followed the orchestrator address.\n\n" \
                    "If you want to check your subscriptions, enter *subscriptions*.", chat_id)
            elif "subscribe" in message.lower() and "0x" in message:
                transcoderChecksum = getTranscoder_IfValid(message, chat_id)
                if transcoderChecksum:
                    with open("transcoder_subscriptions.json", "r") as f:
                        subscriptions = json.load(f)
                    handleSubscription(subscriptions, chat_id, transcoderChecksum)
            elif "remove" in message.lower() and "0x" in message:
                transcoderChecksum = getTranscoder_IfValid(message, chat_id)
                if transcoderChecksum:
                    with open("transcoder_subscriptions.json", "r") as f:
                        subscriptions = json.load(f)
                    handleUnsubscribe(subscriptions, chat_id, transcoderChecksum)
            elif "subscriptions" in message.lower():
                displaySubscriptions(chat_id)
            else:
                send_message("The following commands are available:\n - *subscribe* <orchestrator address>\n - *remove* <orchestrator address>\n - *subscriptions*", chat_id)
        except Exception as ex:
            print(ex)
            send_message(ex, MY_TELEGRAM_ID)

def main():
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        if updates.get("result"):
            last_update_id = get_last_update_id(updates) + 1
            checkMessage(updates)
        time.sleep(1)

if __name__ == '__main__':
    main()

