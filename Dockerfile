FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# keep_alive.py supervises main.py and auto-restarts it if it crashes
CMD ["python", "-u", "keep_alive.py"]
