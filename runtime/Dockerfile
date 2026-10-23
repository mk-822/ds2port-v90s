FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake python3 ca-certificates pkg-config \
    libasound2-dev libx11-dev libxext-dev libegl-dev libgles-dev libxtst6 libxcursor1 libxfixes3 \
    xvfb x11-utils xkb-data timgm6mb-soundfont \
    gcc-mingw-w64-i686-posix gcc-x86-64-linux-gnu libc6-dev-amd64-cross \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
