# Stage 1: compile Tailwind CSS with the standalone binary
# (no Node in the final image; the binary is a self-contained executable)
FROM debian:bookworm-slim AS tailwind

ARG TAILWIND_VERSION=v3.4.17

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Pick the right binary for the build architecture (amd64 or arm64)
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
        amd64) PLATFORM=linux-x64;; \
        arm64) PLATFORM=linux-arm64;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1;; \
    esac \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-${PLATFORM}" \
    && chmod +x /usr/local/bin/tailwindcss

COPY tailwind.config.js ./
COPY tailwind/input.css ./input.css
# The config scans the template tree, so the templates are part of the build input
COPY finance/templates ./finance/templates
COPY finance/static/finance ./finance/static/finance

RUN tailwindcss -c tailwind.config.js -i input.css -o tailwind.css --minify

# Stage 2: the runtime image
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Drop in the compiled Tailwind CSS from the build stage
COPY --from=tailwind /build/tailwind.css /app/finance/static/finance/tailwind.css

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

# Make user-site console scripts (e.g. pytest, ruff from requirements-dev) resolvable
ENV PATH="/home/appuser/.local/bin:${PATH}"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
