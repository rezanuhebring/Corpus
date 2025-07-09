# /tika.Dockerfile
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
ADD https://archive.apache.org/dist/tika/2.9.1/tika-server-standard-2.9.1.jar /tika-server.jar
CMD ["java", "-jar", "/tika-server.jar", "--host=0.0.0.0"]