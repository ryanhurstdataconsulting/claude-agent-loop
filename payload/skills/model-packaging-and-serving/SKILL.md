---
name: model-packaging-and-serving
description: Use when a trained model needs to go behind an API, a batch job, or a streaming consumer — choosing batch vs. online vs. streaming serving, writing a Dockerfile for the model, validating its input signature, and smoke-testing it before deployment. Triggers on requests like "containerize this model," "put this model behind an endpoint," "add input validation to the model server," or "write a smoke test for the deployed model," and on symptoms like a model server crashing on malformed input or a serving latency regression.
---

# model-packaging-and-serving

## Overview
Takes a trained model artifact from experiment tracking to a deployable
serving surface — picks the serving mode, scaffolds the container, enforces
an input-signature contract, and smoke-tests the result before it takes
traffic. Owns "make this trained model safely callable," distinct from
training the model or monitoring it once live.

## When to use
- A trained model needs to be exposed behind an API endpoint, a batch job,
  or a streaming consumer for the first time.
- An existing model server lacks input validation and is crashing or
  silently mispredicting on malformed input.
- A model needs to move from a data scientist's local environment into a
  container that a deployment pipeline can run.
- A task asks for a smoke test to run before a model rollout.

## Workflow

1. **Choose the serving mode by latency and throughput requirement, not by
   default habit:**

   | Serving mode | Fits when | Typical shape |
   |---|---|---|
   | Batch | Predictions consumed on a schedule, latency in minutes/hours is fine | A scheduled job reads a table, scores it, writes results |
   | Online (request/response) | A caller needs a prediction within a request's lifetime (milliseconds–seconds) | A containerized model behind a REST/gRPC endpoint |
   | Streaming | Predictions attach to an event stream as it flows | A consumer that scores each message and republishes or triggers an action |

   Do not default to online serving because it is the most familiar
   pattern — a batch job is simpler to operate, cheaper, and sufficient
   for most non-interactive use cases.

2. **Pin the model's input signature and validate it at the boundary.**
   Define the expected schema (feature names, types, allowed ranges,
   nullability) once, and reject malformed input at the server boundary
   rather than letting it reach the model:
   ```python
   from pydantic import BaseModel, Field

   class PredictionRequest(BaseModel):
       user_purchase_count_7d: int = Field(ge=0)
       user_avg_order_value_30d: float = Field(ge=0)
       account_age_days: int = Field(ge=0)

   @app.post("/predict")
   def predict(req: PredictionRequest):
       features = req.model_dump()
       return {"score": model.predict(features)}
   ```
   A model that silently accepts a missing or out-of-range feature and
   returns a confident-looking number is a worse failure mode than one
   that returns a clear 4xx error.

3. **Write a minimal, reproducible Dockerfile** — pin the base image and
   dependency versions, copy only what serving needs (not training code or
   raw data), and run as a non-root user:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements-serving.txt .
   RUN pip install --no-cache-dir -r requirements-serving.txt
   COPY model_artifact/ ./model_artifact/
   COPY serve.py .
   RUN useradd -m modeluser && chown -R modeluser /app
   USER modeluser
   EXPOSE 8080
   CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
   ```
   Tag the image with the tracked experiment run ID or model version, not
   `latest`, so a deployed container is traceable back to the run that
   produced it.

4. **Smoke-test before the model takes real traffic.** At minimum: the
   container starts and passes a health check, a known-good input returns
   the expected prediction within tolerance, and a malformed input returns
   a validation error rather than a crash or a silent wrong answer.

5. **Decide the rollout strategy before the first deploy**, not after an
   incident: shadow traffic (score in parallel, don't act on it), canary
   (small percentage of live traffic), or blue-green — matched to how
   costly a bad prediction is for this particular model.

## Checklist / quality gate
- [ ] Serving mode (batch/online/streaming) is chosen deliberately against
      the actual latency and throughput requirement.
- [ ] Input schema is defined explicitly and validated at the server
      boundary before reaching the model.
- [ ] The container image is tagged with a traceable model/run version, not
      `latest`.
- [ ] A smoke test exercises: startup/health check, a known-good prediction,
      and a malformed-input rejection.
- [ ] The container runs as a non-root user and includes only what serving
      needs, not training code or raw training data.
- [ ] A rollout strategy (shadow, canary, or blue-green) is chosen and
      matches the cost of a bad prediction for this model.

## References
- "Machine Learning Engineer Skills" (containerizing a model with Docker,
  running it on Kubernetes): https://doit.software/blog/machine-learning-engineer-skills
- Indeed Machine Learning Engineer job description (serving and deployment
  competencies): https://www.indeed.com/hire/job-description/machine-learning-engineer

## Composition
- Consumes the output of **model-training-experiment-scaffold** — package
  the specific tracked run/artifact selected for promotion, not an
  untracked local file.
- Should pass **eval-harness** gating criteria before packaging begins;
  packaging an artifact that has not cleared its evaluation thresholds
  just moves the failure downstream.
- Hands off to an MLOps CI/CD pipeline (train → eval-gate → register →
  deploy) once the container and smoke test are in place — this skill
  produces the deployable artifact the pipeline promotes.
- Hands off to model-drift-monitoring once the model is live, to catch
  degradation this skill's one-time smoke test cannot.
