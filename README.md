# 📸 GIF Maker — Convert YouTube, Uploaded, or Local Videos into GIFs

GIF Maker is a lightweight, self‑hosted web app that creates GIFs from:

- YouTube videos
- Uploaded files (MP4, MOV, WebM, etc.)
- Locally hosted media already on your server

It runs anywhere via Docker and requires no external services beyond yt-dlp and ffmpeg. Perfect for homelabs, Raspberry Pis, and anyone who wants a simple, fast way to generate GIFs.

## 🚀 Features

- Multiple input sources  
  Create GIFs from YouTube URLs, uploaded video files, or local media stored on your server.

- Precise trimming controls  
  Select exact start and end timestamps to capture the perfect moment.

- Automatic GIF output directory  
  All generated GIFs are saved to a dedicated folder you can mount anywhere.

- Mobile‑first UI  
  Designed for smooth use on phones, tablets, and desktops.

- Lightweight + homelab‑friendly  
  Runs great on Raspberry Pi, low‑power servers, or full x86 systems.

- Zero external dependencies  
  Everything runs locally using yt-dlp and ffmpeg.

- Dockerized for easy deployment  
  One command and you're up and running.

## 🐳 Running with Docker (Recommended)

The easiest way to run GIF Maker is with Docker Compose.

### docker-compose.yml

services:
  gifmaker:
    image: thomasdev/gifmaker:latest
    container_name: gifmaker
    ports:
      - "5000:5000"
    volumes:
      - /path/to/media:/videos
      - /path/to/media/gifs:/gifs
    restart: unless-stopped

### Start the app

docker compose up -d

Then open:

http://localhost:5000

## 📁 Volume Mapping

| Host Path             | Container Path | Purpose                     |
|-----------------------|----------------|-----------------------------|
| /path/to/media        | /videos        | Temporary video downloads   |
| /path/to/media/gifs   | /gifs          | Final GIF output directory  |

You can point these to any directory on your system.

## 🧪 Development Setup

If you want to modify the app, use the development override file.

### docker-compose.dev.yml

services:
  gifmaker:
    build:
      context: .
      dockerfile: Dockerfile
    image: gifmaker-dev
    container_name: gifmaker-dev
    ports:
      - "5000:5000"
    volumes:
      - .:/app
      - /path/to/media:/videos
      - /path/to/media/gifs:/gifs
    environment:
      - FLASK_ENV=development

### Start in development mode

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

This gives you:

- local image builds
- live code editing (.:/app)
- identical behavior to production

## 🏗️ Building the Image Manually

If you want to build the image yourself:

docker build -t gifmaker .

Or tag it for Docker Hub:

docker build -t thomasdev/gifmaker:latest .
docker push thomasdev/gifmaker:latest

## 🔧 Environment Variables

| Variable    | Description              | Default      |
|-------------|--------------------------|--------------|
| FLASK_ENV   | development/production   | production   |

## 📜 License

MIT License — free to use, modify, and self‑host.

## 🙌 Contributing

Pull requests are welcome. If you build something cool with it, share it.
