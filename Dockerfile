# DocMind - Law Firm Knowledge Assistant
# Base image: Official Python 3.13 slim
FROM python:3.13-slim

# Create non-root user with UID 1000 (standard requirement for Hugging Face Spaces)
RUN useradd -m -u 1000 user

# Set environment variables
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DEMO_MODE=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_PORT=7860 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    CHROMA_DIR=/home/user/chroma_db \
    ANALYTICS_DB_PATH=/home/user/data/analytics.db \
    DEMO_LIMITS_DB_PATH=/home/user/data/demo_limits.db

# Set working directory
WORKDIR /home/user/app

# Copy dependency specifications first to leverage Docker layer caching
COPY --chown=user:user requirements.txt .

# Install dependencies as non-root user
RUN pip install --no-cache-dir --user -r requirements.txt

# Create writable runtime data and Chroma directories
RUN mkdir -p /home/user/data /home/user/chroma_db && \
    chown -R user:user /home/user/data /home/user/chroma_db /home/user/app

# Copy application source code
COPY --chown=user:user . .

# Expose standard Hugging Face Spaces port
EXPOSE 7860

# Launch Streamlit server with iframe and CORS protection flags disabled for Spaces
CMD ["streamlit", "run", "app.py", \
     "--server.port", "7860", \
     "--server.address", "0.0.0.0", \
     "--server.enableCORS", "false", \
     "--server.enableXsrfProtection", "false"]
