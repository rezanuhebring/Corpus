# /tika.Dockerfile
# A custom, stable Tika server image.

FROM debian:bookworm-slim

# Install Java and curl
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl && rm -rf /var/lib/apt/lists/*

# Download a stable Tika Server jar file
ADD https://archive.apache.org/dist/tika/2.9.1/tika-server-standard-2.9.1.jar /tika-server.jar

# The command to run when the container starts
CMD ["java", "-jar", "/tika-server.jar", "--host=0.0.0.0"]