"""Launch the operational paper-session dashboard."""
import os, sys, uvicorn
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == "__main__":
    uvicorn.run("src.monitoring.paper_dashboard:app", host="127.0.0.1", port=8777,
                log_level="warning")
