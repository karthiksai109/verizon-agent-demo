FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir streamlit requests
COPY services/ui ./services/ui
EXPOSE 8514
CMD ["streamlit", "run", "services/ui/app.py", "--server.port", "8514", "--server.address", "0.0.0.0"]
