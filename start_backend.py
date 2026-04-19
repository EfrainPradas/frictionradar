import subprocess
import sys
import time

proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "50000",
    ],
    cwd="C:/Ubuntu/home/efraiprada/frictionradar/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
print(f"Started process {proc.pid}")
time.sleep(5)
print("Done")
