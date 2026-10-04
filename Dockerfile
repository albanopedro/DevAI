# DevAI's web interface in a container (D051).
# Run with: PROJECT=/path/to/project docker compose up --build
# The address with the token is printed in the logs: docker compose logs devai

# 1. Build the pages. Node is needed only here, never in the final image.
FROM node:22-alpine AS pages
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# 2. DevAI itself, with the [ai] and [web] extras.
FROM python:3.12-slim
# git: file listing and `devai review`. A mounted project belongs to another
# user, so git must be told to trust it (inside this container only).
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[ai,web]"
COPY --from=pages /web/dist /app/pages

# OpenCode's CLI isn't in the image: AI runs on Ollama on the host machine,
# and DevAI still asks before sending, since the data leaves the container.
ENV DEVAI_WEB_DIST=/app/pages \
    DEVAI_AI_PROVIDER=ollama \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home devai
USER devai
EXPOSE 8765
# --listen-all: inside the container only; compose publishes the port on the
# host's 127.0.0.1, so other machines still can't reach it.
CMD ["devai", "serve", "/project", "--port", "8765", "--listen-all", "--no-open"]
