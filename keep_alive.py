import subprocess
import sys
import time
import os
import signal

BOT_SCRIPT = "main.py"
LOG_FILE = "bot.log"


def main():
    print(f"Starting bot manager for {BOT_SCRIPT}")
    print(f"Logs: {LOG_FILE}")
    print("Press Ctrl+C to stop.")
    print("-" * 40)

    while True:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"\n--- Bot started at {time.ctime()} ---\n")

            process = subprocess.Popen(
                [sys.executable, "-u", BOT_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in iter(process.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    print(line)
                    with open(LOG_FILE, "a", encoding="utf-8") as log:
                        log.write(line + "\n")

            process.wait()
            print(f"\nBot exited with code {process.returncode}. Restarting in 3s...")
            time.sleep(3)

        except KeyboardInterrupt:
            print("\nShutting down...")
            process.terminate()
            process.wait(timeout=5)
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
