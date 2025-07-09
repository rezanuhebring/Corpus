#!/bin/sh
# /chroma-entrypoint.sh

# This is the permissions fix. It changes ownership of the mounted volume.
echo "Fixing permissions for /chroma directory..."
chown -R chroma:chroma /chroma

# This is the crucial part.
# `exec "$@"` passes control to the command specified in the Dockerfile
# or the 'command' section of the docker-compose.yml.
# It allows us to ADD functionality without BREAKING the original startup.
exec "$@"