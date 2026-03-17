FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y ffmpeg yt-dlp && \
    apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads

EXPOSE 5000

CMD ["python", "app.py"]
