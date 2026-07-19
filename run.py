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

    # 3. Build Frontend
    log("Building Frontend Assets")
    if not run_command("npm run build", cwd=frontend_dir):
        sys.exit(1)

    # 4. Start Integrated Server
    log("Starting FastAPI Backend (serving frontend at http://localhost:8000)")
    backend_dir = os.path.join(root_dir, "backend")
    
    # Run uvicorn via python -m to ensure the venv paths are clean across all platforms
    uvicorn_cmd = (
        f'"{venv_python}" -m uvicorn app.main:app '
        "--host 127.0.0.1 --port 8000 --reload"
    )

    # We use subprocess.Popen to let uvicorn take over the console output
    process = subprocess.Popen(
        uvicorn_cmd,
        cwd=backend_dir,
        shell=True
    )
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        process.terminate()


if __name__ == "__main__":
    main()

