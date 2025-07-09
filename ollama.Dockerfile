# /ollama.Dockerfile
FROM ollama/ollama
# This RUN command downloads the model when the image is built.
RUN /bin/sh -c "ollama serve & sleep 5 && ollama pull tinyllama && pkill ollama"