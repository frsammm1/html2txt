# Python 3.11 Slim (Lightweight)
FROM python:3.11-slim

# Set env variables to prevent .pyc files and buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies required for lxml
# --no-install-recommends helps keep image small
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Caching layer)
COPY requirements.txt .

# Install python libs
# --only-binary saves compilation time
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY main.py .

# Expose port for Render
EXPOSE 8080

# Command to run
CMD ["python", "main.py"]
