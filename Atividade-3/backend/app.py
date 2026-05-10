import os
import re
import time
from flask import Flask, jsonify, request, send_from_directory
from rpc import BitcoinRPC, BitcoinRPCError, wallet_state
from utils import summarize_mempool
from event_store import EventStore
from zmq_listener import start_zmq_listener

TXID_RE = re.compile(r"[0-9a-fA-F]{64}")

app = Flask(__name__)
rpc = BitcoinRPC()
event_store = EventStore()
start_zmq_listener(event_store)  # inicia o listener de eventos em background

# ---------- utilitários ----------

def ok(data):
    return jsonify({"ok": True, "data": data})

def fail(message, details=None, code=400):
    payload = {"ok": False, "error": {"message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), code

def interpret_transaction(txid, wallet, send_time=None):
    now = int(time.time())
    
    # Tenta achar na wallet
    try:
        tx = rpc.call("gettransaction", [txid], wallet=wallet)
        confirmations = tx.get("confirmations", 0)
        block_hash = tx.get("blockhash")
        tx_time = tx.get("time", now)
        age_seconds = now - tx_time
        
        if confirmations >= 1:
            return {
                "txid": txid,
                "wallet": wallet,
                "status": "confirmed",
                "confirmed": True,
                "confirmations": confirmations,
                "block_hash": block_hash,
                "age_seconds": age_seconds,
                "message": "Transação confirmada em bloco."
            }
        
        # confirmations == 0 → ou está na mempool, ou em rejeitado
        # Verifica na mempool
        try:
            rpc.call("getmempoolentry", [txid])
            in_mempool = True
        except Exception:
            in_mempool = False
        
        if in_mempool:
            result = {
                "txid": txid,
                "wallet": wallet,
                "status": "mempool",
                "confirmed": False,
                "confirmations": 0,
                "block_hash": None,
                "age_seconds": age_seconds,
                "message": "Transação aceita na mempool, aguardando inclusão em bloco."
            }
            if age_seconds > 120:
                result["warning"] = "Transação está na mempool há mais de 2 minutos."
            return result
        
        # Nem confirmada nem na mempool → broadcast recente?
        if age_seconds < 30:
            return {
                "txid": txid,
                "wallet": wallet,
                "status": "broadcast",
                "confirmed": False,
                "confirmations": 0,
                "block_hash": None,
                "age_seconds": age_seconds,
                "message": "Transação enviada ao node, aguardando aceitação na mempool."
            }
        
        return {
            "txid": txid,
            "wallet": wallet,
            "status": "unknown",
            "confirmed": False,
            "confirmations": 0,
            "block_hash": None,
            "age_seconds": age_seconds,
            "warning": "Transação não localizada na mempool nem em bloco."
        }
    
    except Exception:
        return {
            "txid": txid,
            "wallet": wallet,
            "status": "unknown",
            "warning": "Transação não localizada na wallet selecionada."
        }


# ---------- endpoints API ----------

@app.get("/api/node")
def api_node():
    """
    Node snapshot:
    - getblockchaininfo (chain, blocks, headers, difficulty, bestblockhash)
    - getmempoolinfo (size, bytes, usage)
    - getnetworkinfo (subversion, connections)
    """
    try:
        bc = rpc.call("getblockchaininfo")
        mp = rpc.call("getmempoolinfo")
        nw = rpc.call("getnetworkinfo")

        data = {
            "chain": bc.get("chain"),
            "blocks": bc.get("blocks"),
            "headers": bc.get("headers"),
            "difficulty": bc.get("difficulty"),
            "bestblockhash": bc.get("bestblockhash"),
            "mempool": {
                "txcount": mp.get("size"),
                "bytes": mp.get("bytes"),
                "usage": mp.get("usage"),
                "maxmempool": mp.get("maxmempool"),
                "mempoolminfee": mp.get("mempoolminfee"),
            },
            "network": {
                "subversion": nw.get("subversion"),
                "connections": nw.get("connections"),
                "version": nw.get("version"),
            }
        }
        return ok(data)
    except BitcoinRPCError as e:
        return fail("Falha ao consultar estado do node via RPC.", details=str(e), code=502)


@app.get("/api/blocks/recent")
def api_blocks_recent():
    """
    Lista N blocos recentes com estatísticas simples.
    Usa:
      - getblockcount
      - getblockhash(height)
      - getblockheader(hash)  (leve)
      - getblockstats(hash)   (stats úteis)
    """
    n = int(request.args.get("n", 10))
    n = max(1, min(n, 25))  # limite didático

    try:
        tip = rpc.call("getblockcount")
        blocks = []
        for h in range(tip, max(tip - n, -1), -1):
            bh = rpc.call("getblockhash", [h])
            header = rpc.call("getblockheader", [bh])
            stats = rpc.call("getblockstats", [bh])

            blocks.append({
                "height": h,
                "hash": bh,
                "time": header.get("time"),
                "mediantime": header.get("mediantime"),
                "txs": stats.get("txs"),
                "totalfee": stats.get("totalfee"),
                "avgfee": stats.get("avgfee"),
                "feerate_percentiles": stats.get("feerate_percentiles"),
                "avgfeerate": stats.get("avgfeerate"),
                "avg_tx_size": stats.get("avgtxsize"),
                "total_size": stats.get("total_size"),
            })

        return ok({"tip": tip, "items": blocks})
    except BitcoinRPCError as e:
        return fail("Falha ao consultar blocos recentes via RPC.", details=str(e), code=502)


@app.get("/api/block/<blockhash>")
def api_block(blockhash):
    """
    Resumo de um bloco por hash.
    Usa getblock(hash, verbosity=1) para evitar payload gigante.
    """
    try:
        blk = rpc.call("getblock", [blockhash, 1])

        data = {
            "hash": blk.get("hash"),
            "height": blk.get("height"),
            "confirmations": blk.get("confirmations"),
            "time": blk.get("time"),
            "nTx": blk.get("nTx"),
            "size": blk.get("size"),
            "weight": blk.get("weight"),
            "version": blk.get("version"),
            "previousblockhash": blk.get("previousblockhash"),
            "nextblockhash": blk.get("nextblockhash"),
            "tx": blk.get("tx")[:20],  # mostra só 20 txids por segurança/UX
        }
        return ok(data)
    except BitcoinRPCError as e:
        return fail("Falha ao consultar bloco.", details=str(e), code=502)

@app.get("/api/mempool/summary")
def mempool_summary():
    """
    Resumo da mempool.
    Usa getrawmempool (verbose=False) para pegar só txids, e getmempoolentry para detalhes.
    """
    try:
        print(summarize_mempool())
        return ok(summarize_mempool())
    except BitcoinRPCError as e:
        return fail("Falha ao consultar mempool.", details=str(e), code=502)

@app.get("/api/blockchain/lag")
def blockchain_lag():
    """
    Diferença de tempo entre o bloco mais recente e o bloco anterior.
    Usa getblockchaininfo para pegar o timestamp do último bloco.
    """
    try:
        bc = rpc.call("getblockchaininfo")
        block = bc.get("blocks")
        headers = bc.get("headers")
        data = {
            "block": block,
            "headers": headers,
            "lag": block - headers
        }
        return ok(data)
    except BitcoinRPCError as e:
        return fail("Falha ao consultar blockchain lag.", details=str(e), code=502)

@app.get("/api/events/summary")
def api_events_summary():
    """
    Resumo de eventos recentes (exemplo didático).
    Usa ZeroMQ para receber notificações de novos blocos e transações.
    """
    snap = event_store.snapshot()
    blocks = snap["blocks"]
    txs = snap["txs"]
    
    # tx por segundo: número de txs / janela de tempo
    if len(txs) >= 2:
        window = txs[-1]["ts"] - txs[0]["ts"]
        tx_per_second = round(len(txs) / window, 2) if window > 0 else 0
    else:
        tx_per_second = 0
    
    last_ts = 0
    if blocks:
        last_ts = max(last_ts, blocks[-1]["ts"])
    if txs:
        last_ts = max(last_ts, txs[-1]["ts"])
    
    return jsonify({
        "blocks_observed": len(blocks),
        "tx_observed": len(txs),
        "last_event_time": last_ts,
        "tx_per_second": tx_per_second
    })

@app.route("/api/events/latest")
def events_latest():
    snap = event_store.snapshot()
    return jsonify({
        "blocks": list(snap["blocks"]),
        "txs": list(snap["txs"])
    })

@app.route("/api/events/state-comparison")
def state_comparison():
    snap = event_store.snapshot()
    last_seen = snap["blocks"][-1]["hash"] if snap["blocks"] else None
    best_block = rpc.call("getbestblockhash")
    
    return jsonify({
        "best_block": best_block,
        "last_seen_block": last_seen,
        "divergence": last_seen != best_block
    })

@app.route("/api/wallets", methods=["GET"])
def list_wallets():
    # Wallets no disco
    wallet_dir = rpc.call("listwalletdir")
    available = [w["name"] for w in wallet_dir["wallets"]]
    
    # Wallets carregadas
    loaded = rpc.call("listwallets")
    
    return jsonify({
        "available_wallets": available,
        "loaded_wallets": loaded,
        "selected_wallet": wallet_state.get()
    })

@app.route("/api/wallet/select", methods=["POST"])
def select_wallet():
    body = request.get_json()
    name = body.get("wallet")
    
    if not name:
        return jsonify({"error": "campo 'wallet' obrigatório"}), 400
    
    # 1. Verifica se existe no disco
    wallet_dir = rpc.call("listwalletdir")
    available = [w["name"] for w in wallet_dir["wallets"]]
    if name not in available:
        return jsonify({"error": f"wallet '{name}' não existe"}), 404
    
    # 2. Carrega se ainda não estiver carregada
    loaded = rpc.call("listwallets")
    if name not in loaded:
        try:
            rpc.call("loadwallet", [name])
        except Exception as e:
            return jsonify({"error": f"erro ao carregar wallet: {e}"}), 500
    
    # 3. Define como ativa
    wallet_state.set(name)
    
    # 4. Retorna info
    info = rpc.call("getwalletinfo", wallet=name)
    balances = rpc.call("getbalances", wallet=name)

    print(jsonify(info))
    return jsonify({
    "selected_wallet": name,
    "wallet_info": {
        "walletname": info.get("walletname", name),
        "balance": balances.get("mine", {}).get("trusted", 0)
                 + balances.get("watchonly", {}).get("trusted", 0),
        "txcount": info.get("txcount", 0),
    }
})

@app.route("/api/wallet/status", methods=["GET"])
def wallet_status():
    name = wallet_state.get()
    if not name:
        return jsonify({"error": "nenhuma wallet selecionada"}), 400
    
    balances = rpc.call("getbalances", wallet=name)
    utxos = rpc.call("listunspent", wallet=name)

    balance = (
        balances.get("mine", {}).get("trusted", 0)
        + balances.get("watchonly", {}).get("trusted", 0)
    )

    return jsonify({
        "wallet": name,
        "balance": balance,
        "utxos": len(utxos)
    })

@app.route("/api/tx/<txid>", methods=["GET"])
def get_tx(txid):
    if not TXID_RE.fullmatch(txid):
        return fail("txid inválido: precisa ser hex de 64 caracteres.", code=400)

    wallet = wallet_state.get()
    if not wallet:
        return jsonify({"error": "nenhuma wallet selecionada"}), 400

    return jsonify(interpret_transaction(txid, wallet))

# ---------- servir frontend (opcional) ----------
# Vamos servir o frontend por Flask para facilitar (um único comando pra rodar tudo).
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.get("/app.js")
def frontend_js():
    return send_from_directory(FRONTEND_DIR, "app.js")

@app.get("/styles.css")
def frontend_css():
    return send_from_directory(FRONTEND_DIR, "styles.css")


if __name__ == "__main__":
    # Dica: debug=True só em ambiente local
    app.run(host="127.0.0.1", port=8080, debug=True)

