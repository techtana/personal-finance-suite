# A private model server for Cloud Run with a GPU: Ollama with one model baked into the image,
# so a cold start only has to load it, not download it.
FROM ollama/ollama:latest

ARG MODEL=qwen3.5:9b
ENV OLLAMA_HOST=0.0.0.0:8080 \
    OLLAMA_MODELS=/models \
    OLLAMA_KEEP_ALIVE=-1 \
    OLLAMA_NUM_PARALLEL=1

RUN ollama serve & sleep 5 && ollama pull "$MODEL"

EXPOSE 8080
ENTRYPOINT ["ollama", "serve"]
