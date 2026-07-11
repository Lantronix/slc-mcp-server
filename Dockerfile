FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY run_server.py ./
RUN pip install --no-cache-dir --no-deps .

ENV SLC_CREDENTIAL_PROVIDER=env
ENV SLC_VERIFY_SSL=true

ENTRYPOINT ["python3", "run_server.py"]
