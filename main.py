"""
main.py
=======
Launches FastAPI + Streamlit side-by-side.

Usage:
    uv run python main.py
"""
import subprocess
import sys

def main():
    print("Starting Keyword Scraper MVP...")
    print("FastAPI docs: http://localhost:8000/docs")
    print("Streamlit UI: http://localhost:8501")

    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd="/Users/user/aitf/keyword-scraper/.worktrees/feat-mvp",
    )

    st_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "pages/1_Scrape.py", "--server.port", "8501"],
        cwd="/Users/user/aitf/keyword-scraper/.worktrees/feat-mvp",
    )

    try:
        api_process.wait()
        st_process.wait()
    except KeyboardInterrupt:
        api_process.terminate()
        st_process.terminate()

if __name__ == "__main__":
    main()
