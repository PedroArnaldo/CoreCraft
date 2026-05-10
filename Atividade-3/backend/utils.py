from rpc import BitcoinRPC, BitcoinRPCError

rpc = BitcoinRPC()

def summarize_mempool():
    raw = rpc.call("getrawmempool", [True])
    info = rpc.call("getmempoolinfo")
    
    total_vsize = 0
    fee_rates = []
    distribution = {"low": 0, "medium": 0, "high": 0}
    
   # print(f"raw: {raw}")

    for txid, tx in raw.items():
        
        # Calcula fee rate
        fee_btc = tx["fees"]["base"]
        rate = (fee_btc * 100_000_000) / tx["vsize"]
        fee_rates.append(rate)
        
        # Classifica
        if rate < 10:
            distribution["low"] += 1
        elif rate <= 50:
            distribution["medium"] += 1
        else:
            distribution["high"] += 1
    
    tx_count = info["size"]
    total_vsize = info["bytes"]
    avg_fee_rate = round(sum(fee_rates) / tx_count, 2) if tx_count > 0 else 0
    min_fee_rate = round(min(fee_rates), 2) if fee_rates else 0
    max_fee_rate = round(max(fee_rates), 2) if fee_rates else 0


    return {
        "tx_count": tx_count,
        "total_vsize": total_vsize,
        "avg_fee_rate": avg_fee_rate,
        "min_fee_rate": min_fee_rate,
        "max_fee_rate": max_fee_rate,
        "fee_distribution": distribution,
    }