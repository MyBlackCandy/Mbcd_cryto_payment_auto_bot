import requests
from decimal import Decimal
import os

ETHERSCAN_API = os.getenv("ETHERSCAN_API")

def get_price(symbol):
    if symbol in ["USDT-TRC20", "USDT-ERC20"]:
        return Decimal(1)

    ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana"
    }

    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ids[symbol], "vs_currencies": "usd"},
        timeout=10
    ).json()

    return Decimal(r[ids[symbol]]["usd"])


def get_latest_tx(chain, address):

    if chain == "BTC":
        r = requests.get(
            f"https://api.blockcypher.com/v1/btc/main/addrs/{address}",
            timeout=10
        ).json()
        tx = r.get("txrefs", [None])[0]
        if tx:
            return tx["tx_hash"], Decimal(tx["value"]) / Decimal(1e8)

    if chain in ["ETH", "USDT-ERC20"]:

    action = "tokentx" if chain == "USDT-ERC20" else "txlist"

    r = requests.get(
        "https://api.etherscan.io/api",
        params={
            "module": "account",
            "action": action,
            "address": address,
            "sort": "desc",
            "apikey": ETHERSCAN_API
        },
        timeout=10
    ).json()

    # ✅ ตรวจสอบให้แน่ใจว่า result เป็น list
    if r.get("status") == "1" and isinstance(r.get("result"), list) and r["result"]:
        tx = r["result"][0]

        value = Decimal(tx["value"])

        if chain == "ETH":
            amount = value / Decimal(1e18)
        else:
            amount = value / Decimal(1e6)

        return tx["hash"], amount

    else:
        print("ETH API ERROR:", r)
        return None, None

    if chain == "SOL":
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, {"limit": 1}]
        }
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json=payload,
            timeout=10
        ).json()

        result = r.get("result")
        if result:
            return result[0]["signature"], Decimal(0)

    if chain == "USDT-TRC20":
        r = requests.get(
            f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=1",
            timeout=10
        ).json()

        tx = r.get("data", [None])[0]
        if tx:
            decimals = int(tx["token_info"]["decimals"])
            amount = Decimal(tx["value"]) / Decimal(10 ** decimals)
            return tx["transaction_id"], amount

    return None, None
