# vLLM v0.29.0 multi-platform manifest.
FROM vllm/vllm-openai@sha256:c2914767605584b6d8f45686b82de173ecc99e781897aa3d0a66dacd72c51ae1
WORKDIR /workspace
COPY src/radar /workspace/src/radar
COPY experiments/glm47-mtp /workspace/experiments/glm47-mtp
ENV PYTHONPATH=/workspace/src
ENV HF_HOME=/models
ENTRYPOINT ["python", "-m", "radar.validation"]
CMD ["check", "experiments/glm47-mtp/plan.json"]
