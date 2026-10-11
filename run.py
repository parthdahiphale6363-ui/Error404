"""Single-command runner for Corporate Risk Radar.

Starts both FastAPI backend and Vite frontend concurrently.
Handles graceful shutdown of both processes on Ctrl+C.

Usage:
    python run.py
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def main():
    print("=" * 65)
    print("  Corporate Risk Radar (Fintech PS 01) - Single Runner")
    print("=" * 65)
    print("  [Backend]  Starting FastAPI on http://localhost:8000...")
    print("  [Frontend] Starting Vite on    http://localhost:3000...")
    print("  [Docs]     Swagger API docs on http://localhost:8000/docs")
    print("=" * 65)
    print("  Press Ctrl+C to stop all services.\n")

    # Start FastAPI backend process
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
    ]
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=ROOT_DIR,
    )

    # Start Vite frontend dev server
    # Use shell=True on Windows for npm execution
    npm_cmd = "npm run dev"
    frontend_proc = subprocess.Popen(
        npm_cmd,
        cwd=FRONTEND_DIR,
        shell=True,
    )

    def shutdown(signum=None, frame=None):
        print("\n\nStopping Corporate Risk Radar services...")
        try:
            if backend_proc.poll() is None:
                backend_proc.terminate()
                backend_proc.wait(timeout=3)
        except Exception:
            backend_proc.kill()

        try:
            if frontend_proc.poll() is None:
                if sys.platform == "win32":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(frontend_proc.pid)])
                else:
                    frontend_proc.terminate()
                frontend_proc.wait(timeout=3)
        except Exception:
            frontend_proc.kill()

        print("All services stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            # Check if either process crashed
            b_code = backend_proc.poll()
            f_code = frontend_proc.poll()

            if b_code is not None:
                print(f"\n[Warning] Backend process exited with code {b_code}")
                shutdown()
            if f_code is not None:
                print(f"\n[Warning] Frontend process exited with code {f_code}")
                shutdown()

            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
