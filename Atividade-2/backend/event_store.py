from collections import deque
from threading import Lock
import time

class EventStore:
    def __init__(self, max_blocks=20, max_txs=500):
        self.blocks = deque(maxlen=max_blocks)
        self.txs = deque(maxlen=max_txs)
        self.lock = Lock()  # pra leituras consistentes
    
    def add_block(self, block_hash):
        with self.lock:
            self.blocks.append({
                "hash": block_hash,
                "ts": int(time.time())
            })
    
    def add_tx(self, txid):
        with self.lock:
            self.txs.append({
                "txid": txid,
                "ts": int(time.time())
            })
    
    def snapshot(self):
        """Retorna uma cópia consistente para os endpoints lerem"""
        with self.lock:
            return {
                "blocks": list(self.blocks),
                "txs": list(self.txs)
            }