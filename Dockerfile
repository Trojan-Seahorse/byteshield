FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-warm HanLP model so first request doesn't stall
RUN python -c "from argus_redact import redact_pseudonym_llm; redact_pseudonym_llm('预热', lang='zh')"

COPY main.py .
COPY location_names.txt .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
