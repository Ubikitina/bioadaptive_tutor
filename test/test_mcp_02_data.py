import urllib.request
import json
import threading
import time

SERVER_URL = "http://localhost:8000"
SSE_ENDPOINT = f"{SERVER_URL}/sse"

def sse_listener(ready_event, result_container, stop_event):
    print(f"👂 [SSE] Conectando...")
    try:
        with urllib.request.urlopen(SSE_ENDPOINT, timeout=60) as response:
            for line in response:
                if stop_event.is_set(): break
                decoded = line.decode('utf-8').strip()
                if not decoded: continue
                
                # 1. Capturar ID de sesión
                if decoded.startswith("data:") and "/messages/" in decoded:
                    result_container['endpoint'] = decoded.split("data:")[1].strip()
                    ready_event.set()

                # 2. Capturar cualquier respuesta JSON-RPC
                if decoded.startswith("data:") and '{"jsonrpc"' in decoded:
                    msg = json.loads(decoded[5:].strip())
                    # Si es la respuesta a nuestro recurso (id=2)
                    if msg.get('id') == 2:
                        print("\n✨ ¡DATOS RECIBIDOS!")
                        print("==================================")
                        print(msg['result']['contents'][0]['text'])
                        print("==================================")
                        result_container['success'] = True
                        stop_event.set()
                        return
                    # Si es la respuesta a la inicialización (id=1), avisamos para pedir el recurso
                    if msg.get('id') == 1:
                        result_container['initialized'] = True

    except Exception as e:
        if not stop_event.is_set(): print(f"❌ Error SSE: {e}")

def send_mcp(endpoint, method, params, msg_id):
    data = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": msg_id})
    req = urllib.request.Request(f"{SERVER_URL}{endpoint}", data=data.encode(), headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req)

if __name__ == "__main__":
    ready_to_init = threading.Event()
    stop_all = threading.Event()
    shared = {'initialized': False, 'success': False}

    t = threading.Thread(target=sse_listener, args=(ready_to_init, shared, stop_all))
    t.daemon = True
    t.start()

    if ready_to_init.wait(timeout=5):
        # PASO 1: Inicializar
        print("🛠️  Enviando 'initialize'...")
        send_mcp(shared['endpoint'], "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }, 1)
        
        # Esperar a que el servidor confirme inicialización
        for _ in range(10):
            if shared['initialized']: break
            time.sleep(0.5)

        if shared['initialized']:
            # PASO 2: Pedir recurso
            print("📨 Pidiendo recurso 'user://state'...")
            send_mcp(shared['endpoint'], "resources/read", {"uri": "user://state"}, 2)
            stop_all.wait(timeout=5)
        else:
            print("❌ El servidor no respondió a la inicialización.")
    
    if not shared['success']: print("⚠️ No se recibió el dato final.")
    stop_all.set()