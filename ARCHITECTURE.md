# Legacy Modernization Factory — Target Architecture

## Purpose

The Legacy Modernization Factory converts a legacy application description and data-source metadata into a reviewed AWS sandbox deployment plan. It supports an explicit human decision point before deployment and provides a common TACS lookup endpoint for demonstrating migrated records.

## Current demonstrator

```text
PowerShell / JSON intake
          |
          v
  sanitize -> analyze -> propose -> validate -> approve
                                             |
                                             v
                                      AWS sandbox adapters
                                  /         |          \
                               S3      DynamoDB       Aurora RDS
                                \         |          /
                                 +--> common API <---+
                                      /api/data
```

Verified flows:

- S3 private JSON object → AWS SDK → endpoint → TACS filter.
- DynamoDB table with `tacs-index` → AWS SDK → endpoint → TACS filter.
- Aurora PostgreSQL Serverless v2 through the RDS Data API → endpoint → TACS filter.

The current local endpoint is a demonstration adapter. It is not yet a production API gateway or production data plane.

## Configurable data model

Configuration is centralized in `modernization_factory/config.py` and overridden with environment variables. Current common fields are:

| Field | Purpose |
|---|---|
| `id` | Stable source record identifier |
| `tacs` | Lookup/business key |
| `handset` | Handset identifier; optional during migration |
| `cell` | Cell/site identifier; optional during migration |
| `name` | Display/business name |
| `status` | Source lifecycle state |
| `payload` | JSON extension point for future columns |
| `tags` | S3/DynamoDB metadata for filtering and test data |

For the normalized RDS target, the demonstrator now creates two tables:

```text
handset_details(handset_id PK, tacs, cell_id FK, handset_model, status, payload)
cells(cell_id PK, cell_name, technology, status, payload)
```

The endpoint joins `handset_details` to `cells` by `cell_id`. If handset movement history is required, add a future `handset_cell_history` association table rather than overwriting the current relationship.

Future fields should be added to the canonical mapping contract first, then mapped per target. RDS migrations should use additive, backward-compatible schema changes. S3 and DynamoDB can carry additional fields without changing the transport contract.

## Synthetic load testing

`scripts/populate_test_data.py` generates deterministic synthetic data and supports 1 to 1,000,000 records:

```powershell
python .\scripts\populate_test_data.py --target dynamodb --count 100
python .\scripts\populate_test_data.py --target s3 --count 100000
python .\scripts\populate_test_data.py --target rds --count 100000 --tacs 8888
```

The generator uses DynamoDB batch writes, one compressed-in-memory-safe S3 upload through a temporary JSON file, and RDS Data API batches of 100 parameter sets. Use a dedicated sandbox table/object/database and synthetic data only. One million RDS Data API records can take significant time and incur cost; measure smaller loads first.

## Production target state

### Intake and governance

1. Receive a sanitized application description or metadata-only collector output.
2. Classify data and interfaces; redact secrets before persistence.
3. Generate proposed mappings with confidence, assumptions, and open questions.
4. Run policy, security, network, resilience, and cost validation.
5. Require an auditable human approval before deployment.
6. Produce immutable versioned artifacts and a rollback plan.

### Runtime services

- API Gateway plus a versioned Lambda or ECS service for the read endpoint.
- Step Functions or an orchestrated migration workflow for extract, transform, validate, reconcile, and publish stages.
- S3 as immutable landing/archive storage with SSE-KMS, lifecycle policies, and object versioning.
- DynamoDB for high-volume keyed lookups with provisioned capacity/autoscaling and a carefully designed partition key.
- Aurora PostgreSQL for relational queries, constraints, and reporting workloads.
- MSK or Amazon MQ adapters for Kafka/RabbitMQ events.
- AWS DataSync, Storage Gateway, or a controlled transfer service for SMB file ingestion.
- CloudWatch metrics/logs/traces and centralized audit events.

### Security baseline

- IAM roles with least privilege and separate deploy/runtime/migration roles.
- KMS customer-managed keys where required by classification.
- Private subnets, VPC endpoints, security-group allow lists, and no public database endpoints.
- Secrets Manager for database secrets; never place credentials in environment files or source control.
- Macie/GuardDuty/CloudTrail integration as required by the organization.
- Encryption in transit and at rest, retention controls, masking, and deletion workflows.

### Reliability and operations

- Idempotent migration keys and checkpoints.
- Dead-letter handling and replay for Kafka/RabbitMQ/SMB failures.
- Source-to-target reconciliation counts and checksums.
- Contract, unit, integration, load, security, and disaster-recovery tests.
- SLOs for endpoint latency, availability, freshness, and migration completion.
- Blue/green or canary deployment, automated rollback, and change approval.

## Decisions required before production

- Confirm the canonical record schema and ownership of `tacs`, handset, and cell identifiers.
- Decide whether S3 is an archive/landing store only or whether Athena/Iceberg/S3 Tables are needed for query workloads.
- Set expected record volume, write rate, query patterns, retention, and RTO/RPO.
- Select the production network/account boundary and approved AWS services.
- Define data quality thresholds and reconciliation acceptance criteria.
- Confirm IAM, KMS, audit, privacy, and operational support requirements.

## Known limitations of the demonstrator

- The local HTTP server has no authentication, rate limiting, pagination, or API Gateway integration.
- S3 reads the JSON object into memory; production should use partitioned objects and query/metadata services for large data.
- DynamoDB scans are suitable only for the demo; production access must use modeled keys and pagination.
- RDS Data API batching is useful for the sandbox but should be replaced or complemented by a managed migration path for very large loads.
- AWS resources are sandbox resources and must be cost-monitored and cleaned up after testing.
