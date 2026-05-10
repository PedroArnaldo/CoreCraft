import zmq
import threading

def start_zmq_listener(event_store):
    def loop():
        ctx = zmq.Context()
        sock = ctx.socket(zmq.SUB)
        sock.connect("tcp://127.0.0.1:28332")  # hashblock
        sock.connect("tcp://127.0.0.1:28333")  # hashtx
        sock.setsockopt(zmq.SUBSCRIBE, b"hashblock")
        sock.setsockopt(zmq.SUBSCRIBE, b"hashtx")
        
        while True:
            try:
                topic, body, _seq = sock.recv_multipart()
                if topic == b"hashblock":
                    event_store.add_block(body.hex())
                elif topic == b"hashtx":
                    event_store.add_tx(body.hex())
            except Exception as e:
                print(f"[zmq] erro: {e}")
    
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread