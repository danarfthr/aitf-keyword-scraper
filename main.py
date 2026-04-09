"""
main.py
=======
Launches FastAPI + Streamlit side-by-side.

Usage:
    uv run python main.py
"""
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    print("Starting Keyword Scraper MVP...")
    print("FastAPI docs: http://localhost:8000/docs")
    print("Streamlit UI: http://localhost:8501")

    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )

    st_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "Scrape_Keywords.py", "--server.port", "8501"],
    )

    try:
        api_process.wait()
        st_process.wait()
    except KeyboardInterrupt:
        api_process.terminate()
        st_process.terminate()

if __name__ == "__main__":
    main()
