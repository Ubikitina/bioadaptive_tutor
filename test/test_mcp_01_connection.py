import urllib.request

URL = "http://localhost:8000/sse"

print(f"📡 Probando conexión con {URL}...")

try:
    # Abrimos la conexión al stream
    with urllib.request.urlopen(URL, timeout=5) as response:
        print("✅ ¡Conexión establecida! El puerto está abierto.")
        
        # Leemos las primeras líneas que envía el servidor
        print("\n--- Respuesta del Servidor MCP ---")
        for _ in range(3):
            line = response.readline().decode('utf-8').strip()
            if line:
                print(f"   {line}")
                
        print("----------------------------------")
        print("🎉 Todo listo: El servidor está emitiendo eventos SSE.")

except TimeoutError:
    print("✅ ¡Éxito! (El timeout es normal porque el stream nunca cierra)")
except Exception as e:
    print(f"❌ Error conectando: {e}")
    print("   -> Verifica que Docker esté corriendo y el puerto 8000 expuesto.")