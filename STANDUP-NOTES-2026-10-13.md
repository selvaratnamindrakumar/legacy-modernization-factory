# Stand-up Notes — 13 October 2026

## Completed

- Built the local Legacy Modernization Factory MVP for governed legacy-to-AWS sandbox planning.
- Added a plan display endpoint and health endpoint.
- Added AWS-mode data access for DynamoDB and Aurora PostgreSQL RDS.
- Created the sandbox Aurora PostgreSQL Serverless v2 demo with the RDS Data API.
- Created the `legacy_records` table and inserted demonstration records for TACS `8888` and `7777`.
- Added an automated PowerShell setup script with a dry-run mode and explicit `-Execute` mode.
- Added the AWS sandbox runbook, including Zscaler CA setup, AWS login, provisioning, testing, and cleanup.
- Verified the live local endpoint returned the real RDS record:
  `rds-8888`, TACS `8888`, status `ACTIVE`.
- Pushed the implementation and documentation to GitHub.

## Demo command

Start the endpoint with AWS-mode variables set, then call:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8090/api/data?source=rds&tacs=8888" |
  ConvertTo-Json -Depth 10
```

Expected result includes:

```text
id: rds-8888
tacs: 8888
source: RDS
```

## Key implementation points

- The endpoint uses the RDS Data API; the database is not exposed directly to the laptop on port 5432.
- AWS credentials use the `sandbox` profile and the corporate Zscaler CA bundle.
- The RDS automation uses Aurora Serverless v2 because the original `db.t4g.medium` class did not support the Data API HTTP endpoint.
- The script is safe to preview without AWS changes:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\Invoke-RdsDemo.ps1
```

## Next steps

- Confirm the intended target architecture and IAM least-privilege policy for a shared team demo.
- Add the S3 provider and demonstrate the same TACS lookup contract.
- Add Kafka, RabbitMQ, and SMB migration adapters as reviewed intermediate steps.
- Add automated integration tests using mocks or an isolated AWS test account.
- Stop/delete the Aurora demo resources when no longer required to avoid sandbox cost.

## Risks / decisions needed

- Confirm whether Aurora Serverless v2 is the approved RDS target for the sandbox.
- Confirm data classification, retention, and masking requirements for migrated Accumulo data.
- Confirm who approves the final modernization plan before deployment beyond the sandbox.
