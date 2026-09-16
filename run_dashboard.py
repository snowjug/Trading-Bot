"""
Quick launcher for the Apex Quant Real-Time Performance Dashboard.
Starts the FastAPI web server on port 8000 and opens the browser automatically.
"""
import sys
import webbrowser
import threading
import time
import uvicorn

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("⚡ APEX QUANT — STARTING LIVE PERFORMANCE DASHBOARD")
    print("Local URL: http://localhost:8000")
    print("Press CTRL+C to stop the dashboard server.")
    print("="*70 + "\n")
    
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("src.monitoring.dashboard:app", host="127.0.0.1", port=8000, log_level="info")
