#!/usr/bin/env python3

import web3
import json
import time
import requests
from web3 import Web3
from setup import WS_ARBITRUM_ALCHEMY, WS_MAINNET_INFURA, MY_TELEGRAM_ID, send_message, BONDING_MANAGER_PROXY, BONDING_MANAGER_ABI, ROUND_MANAGER_PROXY, ROUND_MANAGER_ABI, TICKET_BROKER_PROXY

w3 = Web3(Web3.WebsocketProvider(WS_ARBITRUM_ALCHEMY))
w3m = Web3(Web3.WebsocketProvider(WS_MAINNET_INFURA))

###
# Variables
###

poll_interval = 300

###
# Contracts, Filters & Classes
###

bonding_manager_proxy = w3.eth.contract(address=BONDING_MANAGER_PROXY, abi=json.loads(BONDING_MANAGER_ABI))
round_manager_proxy = w3.eth.contract(address=ROUND_MANAGER_PROXY, abi=json.loads(ROUND_MANAGER_ABI))

class Transcoder:
    # Class Attributes, defaults to true in case script crashes -> no invalid warnings
    rewardCalled = True
    isActive = True

    def __init__(self, address, subscriber=[]):
        self.address = address
        self.subscriber = subscriber

class ErrorMessage:
    # For debugging purposes - avoid sending a telegram message of the error for every poll_interval
    ErrorSent = False


###
# Functions
###

def update_transcoder_instances():
    """Reads the subscription file and updates the transcoder dict.
    """
    with open("transcoder_subscriptions.json", "r") as f: 
        ts = json.load(f)
    # Without resetting the dict (and losing updated variables like .rewardCalled), remove the transcoders that are no longer in the subscriber list
    noLongerInList = list(set(transcoder.keys()).difference(ts.keys()))
    for addr in noLongerInList:
        del transcoder[addr]
    for address, subscriber in ts.items():
        if address not in transcoder.keys():
            transcoder[address] = Transcoder(address, subscriber)
        else:
            setattr(transcoder[address], "subscriber", subscriber)

def get_active_transcoders():
    """Gets all the active transcoders in the Livepeer Pool
    """
    first = bonding_manager_proxy.functions.getFirstTranscoderInPool().call()
    transcoderPoolSize = bonding_manager_proxy.functions.getTranscoderPoolSize().call()
    activeTranscoders = [first]
    for i in range(0, transcoderPoolSize-1):
        activeTranscoders.append(bonding_manager_proxy.functions.getNextTranscoderInPool(activeTranscoders[i]).call())
    return activeTranscoders

def process_round():
    """After a new round has begun, check for missed reward calls.
    
    Also checks if the transcoder became active/inactive.
    """
    activeTranscoders = get_active_transcoders()
    for address in transcoder:
        if (transcoder[address].rewardCalled == False and transcoder[address].isActive == True):
            for chat_id in transcoder[address].subscriber:
                send_message("NO REWARDS CLAIMED - Orchestrator {} did not claim the rewards in the last round! You did not get any rewards for your stake.".format(address[:8]+"..."), chat_id)
                time.sleep(1.5)
        transcoder[address].rewardCalled = False
        if address not in activeTranscoders:
            transcoder[address].isActive = False
            for chat_id in transcoder[address].subscriber:
                send_message("WARNING - Orchestrator {} is no longer in the active orchestrator set! You will no longer receive rewards for your stake.".format(address[:8]+"..."), chat_id)
                time.sleep(1.5)
        elif transcoder[address].isActive == False and address in activeTranscoders:
            transcoder[address].isActive = True
            for chat_id in transcoder[address].subscriber:
                send_message("Orchestrator {} is back in the active orchestrator set! You will get notified if and when rewards are called.".format(address[:8]+"..."), chat_id)
                time.sleep(1.5)

def check_rewardCut_changes(fromBlock, toBlock):
    """Checks for changes in the reward & fee cut values between fromBlock and toBlock.
    
    If an event exists, get the caller of the event and check if it is in the subscription list.
    Get the new and old fee and reward cut values and check if either one changed.
    Send notification to the subscribers.
    """
    
    rewardCut_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": BONDING_MANAGER_PROXY,
    "topics": ['0x7346854431dbb3eb8e373c604abf89e90f4865b8447e1e2834d7b3e4677bf544'],
    })
    for event in rewardCut_filter.get_all_entries():
        caller = w3.toChecksumAddress("0x" + event["topics"][1].hex()[26:])
        if caller in transcoder.keys():
            rewardCut = w3.toInt(hexstr=event["data"][2:][:64])
            feeShare = w3.toInt(hexstr=event["data"][2:][64:])
            roundNr = round_manager_proxy.functions.currentRound().call()
            previousData = bonding_manager_proxy.functions.getTranscoderEarningsPoolForRound(caller, roundNr).call()
            pRewardCut = previousData[1]
            pFeeShare = previousData[2]
            tx = event["transactionHash"].hex()
            if rewardCut != pRewardCut or feeShare != pFeeShare:     
                message = "REWARD AND/OR FEE CUT CHANGE - for Orchestrator {caller}!\n\n" \
                    "New values:\nReward cut = {rewardCut} (old: {pRewardCut})\n" \
                    "Fee cut = {feeCut} (old: {pFeeCut})\n" \
                    "[Transaction link](https://arbiscan.io/tx/{tx})".format(
                        caller = caller[:8]+"...", rewardCut = str(rewardCut/10**4)+"%",
                        pRewardCut = str(pRewardCut/10**4)+"%", feeCut = str(100-(feeShare/10**4))+"%", 
                        pFeeCut = str(100-(pFeeShare/10**4))+"%", tx = tx)
                for chat_id in transcoder[caller].subscriber:
                    send_message(message, chat_id)
                    time.sleep(1.5)

def check_rewardCall(fromBlock, toBlock):
    """Checks for reward transactions between blockOld and block.
    
    If an event exists, get the caller of the event and check if it is in the subscription list.
    Sends notification to the subscribers and sets the rewardCalled attribute for the caller to true.
    """

    rewardCall_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": BONDING_MANAGER_PROXY,
    "topics": ['0x619caafabdd75649b302ba8419e48cccf64f37f1983ac4727cfb38b57703ffc9'],
    })
    for event in rewardCall_filter.get_all_entries():
        caller = w3.toChecksumAddress("0x" + event["topics"][1].hex()[26:])
        if caller in transcoder.keys() and transcoder[caller].rewardCalled == False:
            tokens = round(w3.toInt(hexstr=event["data"])/10**18,2)
            roundNr = round_manager_proxy.functions.currentRound().call()
            data = bonding_manager_proxy.functions.getTranscoderEarningsPoolForRound(caller, roundNr).call()
            totalStake = round(data[0]/10**18)
            rewardCut = data[1]/10**4
            rewardCutTokens = round(tokens*(rewardCut/10**2),2)
            tx = event["transactionHash"].hex()
            message = "Rewards claimed for round {roundNr} -> Orchestrator {caller} received {tokens} LPT " \
                "for a total stake of {totalStake} LPT (keeping {rewardCutTokens} LPT due to its {rewardCut} reward cut)\n" \
                "[Transaction link](https://arbiscan.io/tx/{tx})".format(
                roundNr = roundNr, caller = caller[:8]+"...", tokens = tokens, totalStake = totalStake,
                rewardCutTokens = rewardCutTokens, rewardCut = str(rewardCut)+"%", tx = tx)
            for chat_id in transcoder[caller].subscriber:
                send_message(message, chat_id)
                time.sleep(1.5)
            transcoder[caller].rewardCalled = True

def check_rewardCall_status(block):
    """Sends a notification if a transcoder didn't call reward yet but is in the active set
    """
    for address in transcoder.keys():
        if transcoder[address].rewardCalled == False and transcoder[address].isActive == True:
            for chat_id in transcoder[address].subscriber:
                send_message("WARNING - Orchestrator {} did not yet claim rewards at block {} of 5760 in the current round!".format(address[:8]+"...", str(block%5760)), chat_id)
                time.sleep(1.5)

def check_ticketRedemption(fromBlock, toBlock):
    """Checks for ticket redemptions between blockOld and block.
    
    If an event exists, get the caller of the event and check if it is in the subscription list.
    Sends notification to the subscribers.
    """
    ticket_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": TICKET_BROKER_PROXY,
    "topics": ['0x8b87351a208c06e3ceee59d80725fd77a23b4129e1b51ca231fc89b40712649c']})
    for event in ticket_filter.get_all_entries():
        caller = w3.toChecksumAddress("0x" + event["topics"][2].hex()[26:])
        if caller in transcoder.keys():
            ticketValue = round(w3.toInt(hexstr=event["data"])/10**18, 4)
            feeShare = bonding_manager_proxy.functions.getTranscoder(caller).call()[2]/10**6
            ticketShare = round(ticketValue*feeShare, 4)
            with open("winning_tickets.json") as f:
                wt = json.load(f)
            if wt.get(caller):
                wt[caller]["value"].append(ticketValue)
                wt[caller]["share"].append(ticketShare)
            else:
                wt[caller] = {'value': [ticketValue], 'share': [ticketShare]}
            stake = round(bonding_manager_proxy.functions.transcoderTotalStake(caller).call()/10**18,-5)
            roundedStake = round(stake, -5)
            if roundedStake == 0:
                LIMIT = 0.01
            elif roundedStake >= 1000000:
                LIMIT = 0.1
            else:
                LIMIT = roundedStake/10**7
            if sum(wt[caller]["value"]) > LIMIT:
                message = "Since the last payout notification, Orchestrator {caller_short} earned {ticketValue} ETH for transcoding!\n" \
                "Out of those, its delegators share {ticketShare} ETH. The Orchestrator's current fee cut is {feeCut}%\n" \
                "[Check arbiscan for the txs](https://arbiscan.io/address/{caller})".format(
                    caller_short = caller[:8]+"...", ticketValue = round(sum(wt[caller]["value"]), 3), 
                    ticketShare = round(sum(wt[caller]["share"]), 3), feeCut = round((1-feeShare)*100), caller = caller)
                for chat_id in transcoder[caller].subscriber:
                    send_message(message, chat_id)
                    time.sleep(1.5)
                #delete values if messages were sent
                wt[caller]["value"], wt[caller]["share"] = [], []
            #save file
            with open("winning_tickets.json", "w") as f:
                json.dump(wt, f, indent=1)

def check_round_change(fromBlock, toBlock):
    """Checks for round initilized txs between blockOld and block.
    
    If an event exists, get the blocknumber of this tx and the round number
    """
    round_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": ROUND_MANAGER_PROXY,
    "topics": ['0x22f2fc17c5daf07db2379b3a03a8ef20a183f761097a58fce219c8a14619e786'],
    })
    result = round_filter.get_all_entries()
    if result:
        return result[0]["blockNumber"], w3.toInt(result[0]["topics"][1])
    else:
        return None, None

###
# Loop
###


transcoder = {}
# Just for debugging: Avoid sending the same telegram exception message every polling interval
latestError = 0 

def main():
    global latestError
    # Mainnet
    with open('mainnet_block_records.txt', 'r') as fh:
        mainnetBlockOld = int(fh.readlines()[-1])
    # Arbitrum
    with open('arbitrum_block_records.txt', 'r') as fh:
        arbitrumBlockOld = int(fh.readlines()[-1])
    # Rounds
    with open('roundNr_records.txt', 'r') as fh:
        roundNrOld = int(fh.readlines()[-1])
    while True:
        try:
            arbitrumBlock = w3.eth.blockNumber
            mainnetBlock = w3m.eth.blockNumber
            update_transcoder_instances()
            roundStartBlock, roundNr = check_round_change(arbitrumBlockOld, arbitrumBlock)
            if roundStartBlock and roundNr > roundNrOld:
                # In this case, process the previous round from blockOld to the first block of the new round
                check_rewardCut_changes(arbitrumBlockOld, roundStartBlock)
                check_rewardCall(arbitrumBlockOld, roundStartBlock)
                check_ticketRedemption(arbitrumBlockOld, roundStartBlock)
                # Set the blockOld to last processed blocknumber
                mainnetBlockOld = roundNr*5760 # this can be caluclated based on the previous round
                arbitrumBlockOld = roundStartBlock
                roundNrOld = roundNr # otherwise we process the same round again and again due to the above assignment
                # Write to processed blocks to both files - in case we need to restart the script
                with open('mainnet_block_records.txt', 'a') as fh:
                    fh.write(str(mainnetBlockOld) + "\n")
                with open('arbitrum_block_records.txt', 'a') as fh:
                    fh.write(str(arbitrumBlockOld) + "\n")
                with open('roundNr_records.txt', 'a') as fh:
                    fh.write(str(roundNrOld) + "\n")
                process_round()
                print("processed round at block {}".format(str(arbitrumBlockOld)))
            # Run checks once there are at least 500 new blocks since last check
            if mainnetBlock > mainnetBlockOld + 500:
                check_rewardCut_changes(arbitrumBlockOld, arbitrumBlock)
                check_rewardCall(arbitrumBlockOld, arbitrumBlock)
                check_rewardCall_status(mainnetBlock) #we only use the block for the notification, no query necessary
                check_ticketRedemption(arbitrumBlockOld, arbitrumBlock)
                # Set the blockOld to last processed blocknumber
                mainnetBlockOld = mainnetBlock
                arbitrumBlockOld = arbitrumBlock
                # Write to processed blocks file
                with open('mainnet_block_records.txt', 'a') as fh:
                    fh.write(str(mainnetBlockOld) + "\n")
                with open('arbitrum_block_records.txt', 'a') as fh:
                    fh.write(str(arbitrumBlockOld) + "\n")
                print("Processed until: " + str(arbitrumBlockOld))
        except Exception as ex:
            print(ex)
            # Only send telegram message if its a different error
            if str(ex) != latestError:
                send_message(ex, MY_TELEGRAM_ID)
                latestError = str(ex)
        time.sleep(poll_interval)

if __name__ == '__main__':
    main()
