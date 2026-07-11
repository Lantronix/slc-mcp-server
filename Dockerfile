FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY run_server.py ./
RUN pip install --no-cache-dir --no-deps .

RUN groupadd --system appuser \
    && useradd --system --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

ENV SLC_CREDENTIAL_PROVIDER=env
ENV SLC_VERIFY_SSL=true

USER appuser

ENTRYPOINT ["python3", "run_server.py"]
