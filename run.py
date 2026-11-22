
import subprocess
import sys


def main():
    # Start FastAPI
    api = subprocess.Popen([
        sys.executable,
        "-m",
        "uvicorn",
        "app.api:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ])

    try:
        # Start Streamlit
        subprocess.run([
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/streamlit_app.py",
            "--server.port", "8501"
        ], check=False)

    except KeyboardInterrupt:
        print("Shutting down applications...")

    finally:
        api.terminate()
        api.wait()


if __name__ == "__main__":
    main()
