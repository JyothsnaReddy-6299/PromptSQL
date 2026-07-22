import os
import subprocess
import sys
import platform


def log(msg):
    print(f"\n[RUN.PY] === {msg} ===\n")


def run_command(command, cwd=None, shell=True):
    print(f"Running command: {command} (cwd={cwd})")
    result = subprocess.run(
        command,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    if result.returncode != 0:
        print(result.stdout)
        print(f"Error executing command: {command}")
        return False
    print(result.stdout)
    return True


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    is_windows = platform.system().lower() == "windows"

    # Define path to the virtual environment python executable based on OS
    if is_windows:
        venv_python = os.path.join(root_dir, "venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(root_dir, "venv", "bin", "python")

    # Auto-create virtual environment if it doesn't exist
    if not os.path.exists(venv_python):
        log("Virtual environment not found. Creating 'venv'...")
        venv_cmd = f'"{sys.executable}" -m venv venv'
        if not run_command(venv_cmd, cwd=root_dir):
            print("Failed to automatically create virtual environment.")
            print("Please create virtual environment manually using: python -m venv venv")
            sys.exit(1)

    # 1. Install Backend Dependencies
    log("Installing Backend Dependencies from requirements.txt")
    requirements_path = os.path.join(root_dir, "backend", "requirements.txt")
    pip_cmd = f'"{venv_python}" -m pip install -r "{requirements_path}"'
    if not run_command(pip_cmd):
        sys.exit(1)

    # 2. Install Frontend Dependencies
    log("Installing Frontend Dependencies")
    frontend_dir = os.path.join(root_dir, "frontend")
    if not run_command("npm install", cwd=frontend_dir):
        sys.exit(1)

    # 3. Choose running mode
    print("\n=============================================")
    print("      PROMPTSQL RUNNER MODE CHOOSER          ")
    print("=============================================")
    print(" [1] Developer Mode (Backend + Frontend live reloading side-by-side)")
    print(" [2] Production Mode (Compiles Frontend and serves on single port http://localhost:8000)")
    print("=============================================")
    
    choice = input("Select running mode (default=1): ").strip()
    if choice not in ["1", "2"]:
        choice = "1"

    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")
    
    uvicorn_cmd = f'"{venv_python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload'

    if choice == "2":
        # Build Frontend
        log("Building Frontend Assets")
        if not run_command("npm run build", cwd=frontend_dir):
            sys.exit(1)
            
        log("Starting FastAPI Backend in Production (serving frontend at http://localhost:8000)")
        process = subprocess.Popen(uvicorn_cmd, cwd=backend_dir, shell=True)
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            process.terminate()
    else:
        # Dev Mode
        import time
        log("Starting Developer Mode (Concurrent Live Servers)")
        print("- FastAPI running at: http://localhost:8000")
        print("- React/Vite running at: http://localhost:5173 (Hot Reload Active)")
        
        # Start both concurrently
        backend_proc = subprocess.Popen(uvicorn_cmd, cwd=backend_dir, shell=True)
        frontend_proc = subprocess.Popen("npm run dev", cwd=frontend_dir, shell=True)
        
        try:
            # Poll loop to keep console open and monitor status
            while True:
                if backend_proc.poll() is not None:
                    print("\n[RUN.PY] Backend server terminated unexpectedly.")
                    break
                if frontend_proc.poll() is not None:
                    print("\n[RUN.PY] Frontend server terminated unexpectedly.")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down developer servers...")
        finally:
            # Clean exit
            backend_proc.terminate()
            frontend_proc.terminate()


if __name__ == "__main__":
    main()
