FROM python:3.11-slim

# Install FFmpeg and other system dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY davinci_https_server.py .

# Railway uses PORT env variable
ENV PORT=8443

# Expose port
EXPOSE 8443

# Run the server
CMD ["python", "davinci_https_server.py"]
