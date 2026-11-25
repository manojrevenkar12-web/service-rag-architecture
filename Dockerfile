FROM python:3.13-slim
WORKDIR /app
ENV SRA_ROOT=/app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
COPY reports/reranker.json ./reports/reranker.json
RUN useradd -m app
USER app
EXPOSE 8000
CMD ["sra", "serve"]
