# Legacy Modernization Factory (local MVP)

This repository contains a local, dependency-free prototype for turning a legacy application description into a reviewed AWS sandbox deployment plan.

It intentionally does **not** connect to AWS, read production systems, or execute generated infrastructure. The `deploy` stage writes a sandbox manifest locally so the workflow can be tested safely before AWS adapters are added.

## Workflow

`intake -> analyze -> propose -> validate -> approve -> deploy -> test`

The workflow produces reviewable artefacts:

- sanitized intake
- application inventory
- target architecture and mapping decisions
- validation findings
- approval record
- local sandbox manifest
- test report

## Run

```powershell
python -m modernization_factory.cli demo --output-dir .\sandbox-output
python -m unittest discover -s tests -v
```

Start a browser/API demo endpoint:

```powershell
python -m modernization_factory.server --plan .\sandbox-output\plan.json
```

Open `http://127.0.0.1:8080/` in a browser. The JSON endpoint is
`http://127.0.0.1:8080/api/plan`, and the health endpoint is
`http://127.0.0.1:8080/health`.

Demo tagged data from the local S3/RDS simulator:

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/api/data?tags=8888"
Invoke-RestMethod "http://127.0.0.1:8080/api/data?source=s3&tags=8888"
Invoke-RestMethod "http://127.0.0.1:8080/api/data?source=rds&tags=8888"
```

The endpoint also accepts `tacs=8888` as an alias for the requested demo spelling. The current data is local test data, not a live AWS connection.

To use the real sandbox DynamoDB table, install the AWS SDK and set the AWS mode:

```powershell
python -m pip install boto3
$env:AWS_PROFILE = "sandbox"
$env:AWS_REGION = "us-east-1"
$env:MODERNIZATION_DATA_MODE = "aws"
$env:DYNAMODB_TABLE = "legacy-modernization-demo"
$env:DYNAMODB_INDEX = "tacs-index"
python -m modernization_factory.server --plan .\sandbox-output\plan.json --port 8090
```

Then query `http://127.0.0.1:8090/api/data?source=dynamodb&tacs=8888`.

Configuration defaults and environment overrides are defined in
`modernization_factory/config.py`. The configurable synthetic load generator
supports 1 to 1,000,000 records for DynamoDB, S3, or RDS:

```powershell
python .\scripts\populate_test_data.py --target dynamodb --count 100
python .\scripts\populate_test_data.py --target s3 --count 100000
python .\scripts\populate_test_data.py --target rds --count 100000 --tacs 8888
```

RDS load data is normalized into `handset_details` and `cells`; the endpoint returns the joined view. The RDS setup script creates and seeds both tables:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-RdsDemo.ps1 -Execute
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the presentation architecture,
production-readiness target, security baseline, and decisions required.

To create a private S3 JSON-backed record source, preview and then execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-S3Demo.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-S3Demo.ps1 -Execute
```

Set the returned values before starting the endpoint:

```powershell
$env:S3_BUCKET = "legacy-modernization-s3-356724906763"
$env:S3_KEY = "legacy-records.json"
$env:MODERNIZATION_DATA_MODE = "aws"
python -m modernization_factory.server --plan .\sandbox-output\plan.json --port 8090
```

Test with `http://127.0.0.1:8090/api/data?source=s3&tacs=8888`. S3 is represented as a private JSON object rather than a relational table; the endpoint filters the object records by TACS.

Use a custom description:

```powershell
python -m modernization_factory.cli plan .\examples\order-service.json --output-dir .\sandbox-output
```

Approve and deploy the generated plan:

```powershell
python -m modernization_factory.cli deploy .\sandbox-output\plan.json --approve --output-dir .\sandbox-output
```

## Safety boundaries

- Credentials, tokens, passwords, and private keys are redacted during intake.
- Deployment is local simulation only.
- The workflow blocks deployment when validation finds errors.
- A human approval flag is required before deployment.
- AWS service mappings are recommendations, not executable infrastructure.

## Next implementation steps

1. Replace the local deployer with a constrained AWS account adapter.
2. Add policy-as-code checks and cost estimation.
3. Add source collectors that emit metadata without exporting source or secrets.
4. Add Step Functions, S3, IAM, and Control Tower integrations behind interfaces.
