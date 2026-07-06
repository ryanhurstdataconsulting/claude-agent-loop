# MiniStack — reference

Free, MIT-licensed local AWS emulator (Python 3.12). ~56 services on `http://localhost:4566`, a small footprint, and — its standout trait — **real backing containers** for stateful services. Drop-in replacement for LocalStack Community. Repo: [github.com/ministackorg/ministack](https://github.com/ministackorg/ministack); PyPI `ministack`; Docker `ministackorg/ministack`.

## Install & run

```bash
pip install ministack && ministack                      # serves :4566 (change port with GATEWAY_PORT=XXXX)
docker run -p 4566:4566 ministackorg/ministack          # standard image
docker run -p 4566:4566 -v /var/run/docker.sock:/var/run/docker.sock ministackorg/ministack   # real infra (RDS/ElastiCache/ECS/Lambda containers)
docker run -p 4566:4566 ministackorg/ministack:full     # ':full' adds DuckDB (Athena), psycopg2, pymysql, aws-sam-translator
git clone https://github.com/ministackorg/ministack && cd ministack && docker compose up -d
curl http://localhost:4566/_ministack/health            # verify it is up
```

## Wiring AWS tools

Dummy creds; **a 12-digit `AWS_ACCESS_KEY_ID` becomes the account ID** (else `000000000000`). Startup overrides: `MINISTACK_REGION`, `MINISTACK_ACCOUNT_ID`. Optional `S3_PERSIST=1`.

- **CLI:** `aws --endpoint-url=http://localhost:4566 …` with `AWS_ACCESS_KEY_ID/SECRET=test` + a region. ⚠️ MiniStack's `awslocal` is a **repo-local script** (`bin/awslocal`, present only after cloning) — it is **not** a pip-installable global like LocalStack's. Prefer `--endpoint-url` or exported `AWS_*` env vars.
- **boto3:** `boto3.client("s3", endpoint_url="http://localhost:4566", aws_access_key_id="test", aws_secret_access_key="test", region_name="us-east-1")`.
- **Node v3:** `new S3Client({ endpoint:"http://localhost:4566", region:"us-east-1", credentials:{accessKeyId:"test", secretAccessKey:"test"} })`.
- **Terraform:** MiniStack **does** document a provider `endpoints{}` block:
  ```hcl
  provider "aws" {
    access_key = "test"   # or a 12-digit number for account isolation
    secret_key = "test"
    region     = "us-east-1"
    endpoints { s3 = "http://localhost:4566"  dynamodb = "http://localhost:4566"  # … }
  }
  ```
  Also set `skip_credentials_validation` / `skip_requesting_account_id` / `skip_metadata_api_check`. CDK and Pulumi are listed as compatible.

## Test-automation API (`/_ministack/*`)

- `GET /_ministack/health` — status + edition (lean/full).
- `POST /_ministack/reset` — wipe ALL state (call in `setUp`/`beforeEach` for a clean env without restarting).
- `POST /_ministack/reset?init=1` — reset **and** re-run init scripts (`boot.d` + `ready.d`) to restore seed resources.
- `POST /_ministack/config` — change service settings at runtime (e.g. `lambda_svc.LAMBDA_EXECUTOR` = `local|docker`, `athena.ATHENA_ENGINE` = `duckdb|mock`, `stepfunctions._SFN_WAIT_SCALE` = `0` to skip waits).
- `GET /_ministack/ses/messages` — inspect email SES "sent" (stored, never delivered); filter `?account=…`.
- `GET /_ministack/sqs/messages` — inspect every queue's messages (Body, MessageId, ReceiveCount, visibility, FIFO group/dedup); filter `?account=…&QueueUrl=…`.

LocalStack-compatible `/_localstack/health` and `/health` are also served. These SQS/SES inspection endpoints make MiniStack handy for asserting on a pipeline without standing up receivers.

## Real backing services (need the Docker socket)

RDS → **real** Postgres/MySQL container with a live `host:port`; ElastiCache → real Redis/Memcached; ECS → real Docker via `RunTask` (injects Task Metadata V4 + container creds + `AWS_ENDPOINT_URL` so in-task SDKs route back); Lambda → warm worker pool + Docker RIE for image/other runtimes; Athena → real DuckDB SQL (`:full`); Glue → subprocess / PySpark image. Without `-v /var/run/docker.sock` these cannot start real containers.

## Coverage & limitations

- **Service count is inconsistent** across the project's own sources (README "56+", repo description "55+", homepage "60+/56+") — treat as **~56**, unverified rounding.
- **Image size is inconsistent** too: install docs say ~110 MB (standard) / ~360 MB (`:full`), while the homepage claims ~270 MB. Do not quote a single authoritative size.
- **Stub / control-plane only (do not trust for behavior):** EC2 keeps in-memory state with **no real VMs**; EMR is control-plane only; Amazon MQ has no real container; Backup completes instantly; CloudFront Functions are API stubs; SES **stores** mail (via the inspection endpoint) rather than sending it.
- Athena real SQL and SAM expansion require the `:full` image.
- Some services implement a subset of operations; unsupported CloudFormation resource types fail loudly (`CREATE_FAILED`).
- Footprint/perf claims (~270 MB, ~30 MB RAM, <2 s startup, "2,400+ tests") are self-reported, not independently benchmarked.
- Strengths worth using: zero-config multi-tenancy (12-digit key), real Postgres/MySQL/Redis fidelity, and the purpose-built reset + message-inspection API. Frees some LocalStack-Pro-gated services (EBS/EFS/EMR available free).

## Sources
Repo README (via `gh api repos/ministackorg/ministack/readme`), repo metadata, and [ministack.org](https://ministack.org).
