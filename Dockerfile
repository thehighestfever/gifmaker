FROM python:3.11-slim

# Install ffmpeg (required for clip generation)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure required directories exist
RUN mkdir -p media uploads

# Expose Flask port
EXPOSE 5000

# Run the app
CMD ["python", "app.py"]

