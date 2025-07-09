# /ollama.Dockerfile
# A custom Ollama image with the model pre-baked.

FROM ollama/ollama

# This RUN command executes when the image is built.
# It starts Ollama, pulls the model, and then stops.
# The final container will start with the model already cached.
RUN /bin/sh -c "ollama serve & sleep 5 && ollama pull tinyllama && pkill ollama"

# The default CMD from the base image will be used to start the server at runtime.