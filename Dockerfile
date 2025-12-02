FROM python:3.11-slim
# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy bot code
COPY bot.py .
# Set environment variables (example, override at runtime)
ENV BOT_TOKEN=your_bot_token_here
ENV ADMIN_ID=123456789
# Expose port for webhook (if used)
EXPOSE 8443
# Run the bot
CMD ["python", "bot.py"]
