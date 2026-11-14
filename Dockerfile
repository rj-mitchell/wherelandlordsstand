# syntax=docker/dockerfile:1
# Where Landlords Stand: the website, its small API and the data tools in one image. The data lives in /data.
FROM python:3.12.16-slim
# security fixes published since the base image was built
RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.32
# the site runs as its own user, not root (the same number as the charity's other sites)
RUN groupadd --system --gid 10001 landlords \
 && useradd --system --uid 10001 --gid landlords --home-dir /home/landlords --create-home landlords \
 && mkdir -p /data /backups && chown landlords:landlords /data /backups
WORKDIR /app
# uv's downloads are kept in a build cache on the server, not in the image; files are copied out of it
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
# The libraries first, in a layer of their own: it is rebuilt only when pyproject.toml or uv.lock changes, so a
# change to the code, wording or data_static/ rebuilds in seconds (the family's server audit, R11)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# Then the site itself, installed in place (editable): the build fingerprints src/, config/ and data_static/ here
COPY README.md LICENSE ./
COPY src ./src
COPY config ./config
COPY data_static ./data_static
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
# the code is read-only here: the refreshed name register goes in the data folder (src/landlords/register.py)
ENV LANDLORDS_DATA_DIR=/data \
    LANDLORDS_REGISTER_DIR=/data/register \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER landlords
EXPOSE 8000
CMD ["landlords", "serve", "--host", "0.0.0.0", "--port", "8000", "--behind-proxy"]
