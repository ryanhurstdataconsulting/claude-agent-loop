# Floci — reference

Free, MIT-licensed local AWS (and Azure) emulator. Java/Quarkus native image; Docker image `floci/floci:latest`; every service on one endpoint, `http://localhost:4566`. Pitched as the drop-in successor to LocalStack Community (which required auth tokens and froze security updates in March 2026). Repo: [github.com/floci-io/floci](https://github.com/floci-io/floci); CLI: [github.com/floci-io/floci-cli](https://github.com/floci-io/floci-cli).

## Install & run

```bash
# CLI (recommended)
brew install floci-io/floci/floci            # macOS/Linux; or: curl -fsSL https://floci.io/install.sh | sh
floci start                                  # start emulator on :4566 (needs Docker/Podman)
eval "$(floci env)"                          # export AWS_ENDPOINT_URL + dummy creds + region into the shell
floci wait                                   # block until ready (CI); also: status, logs, doctor, services
floci stop                                   # 'floci stop --remove' deletes the container
floci snapshot save|load|list|delete         # save/restore known states

# Start variants
floci start --port 4599 | --services s3,dynamodb | --persist ./data | --detach

# Docker Compose (compose.yaml)
#   services: { floci: { image: floci/floci:latest, ports: ["4566:4566"] } }
docker compose up

# Plain docker WITH the Docker socket (required for container-backed services)
docker run -d --name floci -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock -u root floci/floci:latest
```

Image tags: `latest` (standard), `latest-compat` (bundles AWS CLI + boto3 for init scripts), pinned (e.g. `1.5.x`), `nightly`. Azure mode: `floci az start` / `eval "$(floci az env)"` on port 4577.

## Wiring AWS tools

`floci env` sets `AWS_ENDPOINT_URL`, `AWS_DEFAULT_REGION`, and dummy `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Any non-empty creds work; a **12-digit access key becomes the account ID** (multi-account isolation), else it falls back to `000000000000`.

- **CLI:** `eval "$(floci env)"` then use `aws` normally, or `aws --endpoint-url http://localhost:4566 …`.
- **boto3:** `boto3.client("s3", endpoint_url="http://localhost:4566", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")`.
- **Node v3:** `new S3Client({ endpoint: "http://localhost:4566", region: "us-east-1", credentials: {accessKeyId:"test", secretAccessKey:"test"}, forcePathStyle: true })`.
- **Terraform / OpenTofu / CDK:** **env-var wiring only** — set `AWS_ENDPOINT_URL` + dummy creds and the AWS provider (v5+, which honors `AWS_ENDPOINT_URL`) targets Floci; also set `skip_credentials_validation` / `skip_requesting_account_id` / `skip_metadata_api_check`. ⚠️ The Floci sources ship **no verbatim `endpoints{}` HCL block** — do not invent one (that pattern belongs to MiniStack/LocalStack).

S3: use path-style. `floci env` defaults the host to `http://localhost.floci.io:4566` (resolves to 127.0.0.1) to enable virtual-hosted-style buckets; plain `http://localhost:4566` also works.

## Test isolation

- **Reset endpoint** (verified in source): `POST /_floci/state/reset` (alias `POST /_localstack/state/reset`, and `/state/nuke`) clears every resettable service + storage, returns `{"status":"OK"}`. Also serves `GET /health`, `/init`, `/info`, `/diagnose`, `/config` under the `_floci|_localstack` prefix.
- **Testcontainers** (isolated container per test lifecycle): Java `io.floci:testcontainers-floci` (mature: 1.4.0, or 2.5.0 for Testcontainers 2.x/Spring Boot 4) — `@Container static FlociContainer floci = new FlociContainer();`; Node `@floci/testcontainers` 0.1.0; Python `testcontainers-floci` 0.1.1 — `with FlociContainer() as floci:` then build clients from `floci.get_endpoint()/get_region()/get_access_key()/get_secret_key()`. ⚠️ **Only Java is mature; Node and Python modules are pre-1.0; Go is not yet released.** Because Floci emits a LocalStack-style `Ready.` log line and serves `/_localstack/health`, Testcontainers' built-in `LocalStackContainer` also works unchanged.

## Persistence (`FLOCI_STORAGE_MODE`, default `memory`)

`memory` (RAM, lost on stop — best for CI) · `persistent` (flush on every write) · `hybrid` (in-memory speed + async flush every 5s — best for local dev) · `wal` (write-ahead log, highest durability). Path via `FLOCI_STORAGE_PERSISTENT_PATH` (default `./data`) or `floci start --persist ./data`.

## Coverage

README states **68 AWS services** (⚠️ a vendor headline — category tables overlap and third-party write-ups cite ~66; verify per-operation coverage before depending on any one). Real Docker-backed (need the socket): Lambda, RDS (Postgres/MySQL/MariaDB), ElastiCache/MemoryDB (Valkey), Neptune (Gremlin/Neo4j), DocumentDB (Mongo), MSK (Redpanda), Amazon MQ (RabbitMQ), EC2, ECS, EKS (k3s), OpenSearch, ECR, CodeBuild; Athena via a DuckDB sidecar.

## Limitations & caveats

- **Stub-only (do not trust for behavior):** Bedrock Runtime, Textract, Transcribe return dummy/immediate results.
- **Container-backed services need `-v /var/run/docker.sock` (+ `-u root`)** and pull heavy real images (postgres, mysql, k3s, redpanda, mongo…).
- Multi-container Compose: set `FLOCI_HOSTNAME` so returned URLs (e.g. SQS `QueueUrl`) resolve from other containers.
- **Provenance/supply-chain note:** advertised coordinates are `io.floci` but the source package is still `io.github.hectorvent.floci`; `/health` reports edition `community` / `floci-always-free`; the old `hectorvent/floci` image is deprecated. Reads as a rebrand/fork lineage, not a clean-room project.
- Performance figures (~24 ms startup, ~13 MiB idle, "2,506 tests") are self-reported, not independently benchmarked.

## Sources
Repo README (via `gh api repos/floci-io/floci/readme`), floci-cli README, `docs/testcontainers/*.md`, `src/main/java/io/github/hectorvent/floci/lifecycle/EmulatorInfoController.java`, and [floci.io/floci](https://floci.io/floci/). LocalStack sunset per the Floci-cited [LocalStack blog](https://blog.localstack.cloud/the-road-ahead-for-localstack/).
