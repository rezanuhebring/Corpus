# /chroma.Dockerfile
FROM chromadb/chroma:0.4.24

# Copy our custom entrypoint script into the image
COPY chroma-entrypoint.sh /

# Set our script as the entrypoint
ENTRYPOINT ["/chroma-entrypoint.sh"]