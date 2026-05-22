FROM python:3.10-slim

WORKDIR /workspace

# Prevent python from writing bytecode and buffer outputs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into container context
COPY . /workspace

EXPOSE 8501

# Start streamlit application binding to all interfaces on 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
