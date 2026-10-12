# AWS Sandbox DynamoDB Runbook

This runbook documents the successful local integration test for the Legacy Modernization Factory using a real DynamoDB table in the AWS sandbox.

It is written for Windows PowerShell and can be reused on a laptop or desktop.

## What this runbook creates

| Item | Value |
|---|---|
| AWS account | `356724906763` |
| AWS region | `us-east-1` |
| AWS CLI profile | `sandbox` |
| DynamoDB table | `legacy-modernization-demo` |
| DynamoDB primary key | `id` (String) |
| DynamoDB index | `tacs-index` with partition key `tacs` (String) |
| Billing | On-demand / `PAY_PER_REQUEST` |
| Local endpoint | `http://127.0.0.1:8090` |

The endpoint is read-only in AWS mode. It queries DynamoDB using the `tacs-index`.

## 1. Open the project

Use PowerShell commands, not Command Prompt commands:

```powershell
Set-Location "C:\Users\selva.indrakumar\Documents\Codex\2026-10-07\we-2"
```

PowerShell uses:

```powershell
Set-Location "C:\path\to\project"
```

Command Prompt uses:

```cmd
cd /d "C:\path\to\project"
```

Do not mix the two syntaxes.

## 2. Verify AWS CLI

```powershell
aws --version
aws configure list-profiles
```

The AWS CLI profile used by this runbook is `sandbox`.

## 3. Generate the Zscaler CA certificate

The AWS CLI may fail with this error when the corporate network performs HTTPS inspection:

```text
SSL validation failed
CERTIFICATE_VERIFY_FAILED
unable to get local issuer certificate
```

The fix is to export the corporate Zscaler root certificate and tell the AWS CLI to trust it. Export only the public certificate; never export a private key.

### Export using Microsoft Edge

1. Open Edge and visit:

   ```text
   https://us-east-1.signin.aws.amazon.com
   ```

2. Select the lock icon in the address bar.
3. Select **Connection is secure**.
4. Select **Certificate is valid**.
5. Open the **Certification Path** tab.
6. Select the Zscaler/company root certificate, not the AWS website certificate.
7. Select **View Certificate**.
8. Open **Details** and select **Copy to File**.
9. Choose:

   ```text
   Base-64 encoded X.509 (.CER)
   ```

10. Save it as:

    ```text
    C:\Users\<username>\zscaler-root.cer
    ```

Check the file:

```powershell
Test-Path "$env:USERPROFILE\zscaler-root.cer"
Get-Content "$env:USERPROFILE\zscaler-root.cer" -First 2
```

The file should contain certificate markers similar to:

```text
-----BEGIN CERTIFICATE-----
```

If the exported certificate is binary instead of Base-64 text, convert it:

```powershell
certutil -encode `
  "$env:USERPROFILE\zscaler-root.cer" `
  "$env:USERPROFILE\zscaler-root.pem"
```

Then use the `.pem` path instead of the `.cer` path.

### Configure the AWS CLI to use the certificate

```powershell
aws configure set ca_bundle `
  "$env:USERPROFILE\zscaler-root.cer" `
  --profile sandbox
```

If the file was converted, use:

```powershell
aws configure set ca_bundle `
  "$env:USERPROFILE\zscaler-root.pem" `
  --profile sandbox
```

This profile configuration persists across new PowerShell windows.

## 4. Log in to AWS

This flow uses the AWS CLI console-login flow. It does not require copying credentials from another computer.

```powershell
aws login --profile sandbox --region us-east-1
```

Complete the browser login. Then verify access:

```powershell
aws sts get-caller-identity `
  --profile sandbox `
  --region us-east-1
```

The response should contain the expected account and an assumed SSO role.

If the AWS CLI reports an SSL error, confirm the CA bundle:

```powershell
aws configure get ca_bundle --profile sandbox
```

Do not use `--no-verify-ssl`. That disables certificate verification.

## 5. Install Python dependencies

Install the AWS SDK and the CRT dependency required by credentials created through `aws login`:

```powershell
python -m pip install boto3
python -m pip install "botocore[crt]"
```

Verify the CRT module:

```powershell
python -c "import botocore.crt; print('AWS CRT ready')"
```

## 6. Create the DynamoDB table

PowerShell can remove quotes from inline JSON passed to the AWS CLI. Store the JSON in an ASCII file instead. ASCII encoding also avoids the UTF-8 BOM problem.

Create the GSI definition:

```powershell
@'
[
  {
    "IndexName": "tacs-index",
    "KeySchema": [
      {
        "AttributeName": "tacs",
        "KeyType": "HASH"
      }
    ],
    "Projection": {
      "ProjectionType": "ALL"
    }
  }
]
'@ | Set-Content -Encoding ascii .\tacs-index.json
```

Create the table:

```powershell
aws dynamodb create-table `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo `
  --attribute-definitions AttributeName=id,AttributeType=S AttributeName=tacs,AttributeType=S `
  --key-schema AttributeName=id,KeyType=HASH `
  --global-secondary-indexes file://tacs-index.json `
  --billing-mode PAY_PER_REQUEST `
  --tags Key=Project,Value=legacy-modernization Key=Environment,Value=sandbox
```

Wait until the table is active:

```powershell
aws dynamodb wait table-exists `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo
```

Verify:

```powershell
aws dynamodb describe-table `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo `
  --query "Table.{Name:TableName,Status:TableStatus,Indexes:GlobalSecondaryIndexes[].IndexName}" `
  --output table
```

Expected status:

```text
legacy-modernization-demo | ACTIVE
```

## 7. Insert test records

Create a record for `tacs=8888`:

```powershell
@'
{
  "id": {
    "S": "record-8888-001"
  },
  "tacs": {
    "S": "8888"
  },
  "name": {
    "S": "Demo record 8888"
  },
  "status": {
    "S": "ACTIVE"
  }
}
'@ | Set-Content -Encoding ascii .\record-8888.json
```

Insert it:

```powershell
aws dynamodb put-item `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo `
  --item file://record-8888.json
```

Create a record for `tacs=7777`:

```powershell
@'
{
  "id": {
    "S": "record-7777-001"
  },
  "tacs": {
    "S": "7777"
  },
  "name": {
    "S": "Demo record 7777"
  },
  "status": {
    "S": "READY"
  }
}
'@ | Set-Content -Encoding ascii .\record-7777.json
```

Insert it:

```powershell
aws dynamodb put-item `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo `
  --item file://record-7777.json
```

## 8. Query DynamoDB directly

Create an expression-value file:

```powershell
@'
{
  ":t": {
    "S": "8888"
  }
}
'@ | Set-Content -Encoding ascii .\tacs-8888.json
```

Query the GSI:

```powershell
aws dynamodb query `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo `
  --index-name tacs-index `
  --key-condition-expression "tacs = :t" `
  --expression-attribute-values file://tacs-8888.json
```

Repeat with `7777` by changing the value in the expression file.

## 9. Start the local endpoint in AWS mode

Set the environment variables in the same PowerShell window that starts the server:

```powershell
$env:AWS_PROFILE = "sandbox"
$env:AWS_REGION = "us-east-1"
$env:AWS_CA_BUNDLE = "$env:USERPROFILE\zscaler-root.cer"
$env:MODERNIZATION_DATA_MODE = "aws"
$env:DYNAMODB_TABLE = "legacy-modernization-demo"
$env:DYNAMODB_INDEX = "tacs-index"
```

Start the endpoint:

```powershell
python -m modernization_factory.server `
  --plan .\sandbox-output\plan.json `
  --port 8090
```

Leave this window running. Use a second PowerShell window for testing.

## 10. Test the endpoint

Health check:

```powershell
Invoke-RestMethod "http://127.0.0.1:8090/health"
```

Read DynamoDB data by `tacs`:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8090/api/data?source=dynamodb&tacs=8888"
```

Test the second record:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8090/api/data?source=dynamodb&tacs=7777"
```

The expected response includes:

```json
{
  "source": "dynamodb",
  "tag": "8888",
  "count": 1
}
```

The browser URL must use a normal ampersand:

```text
http://127.0.0.1:8090/api/data?source=dynamodb&tacs=8888
```

## Troubleshooting

### `NoCredentials`

Run:

```powershell
aws login --profile sandbox --region us-east-1
aws sts get-caller-identity --profile sandbox --region us-east-1
```

### `CERTIFICATE_VERIFY_FAILED`

Reapply the CA bundle:

```powershell
$env:AWS_CA_BUNDLE = "$env:USERPROFILE\zscaler-root.cer"
aws configure set ca_bundle "$env:USERPROFILE\zscaler-root.cer" --profile sandbox
```

### `MissingDependencyException` mentioning `botocore[crt]`

```powershell
python -m pip install "botocore[crt]"
```

Stop and restart the endpoint after installation.

### `Invalid JSON` with `ï»¿` or missing quotes

PowerShell wrote a UTF-8 BOM or stripped inline JSON quotes. Recreate JSON files with:

```powershell
Set-Content -Encoding ascii .\file.json
```

Use `file://file.json` with the AWS CLI.

### Endpoint returns `404`

Stop the old server with `Ctrl+C` and restart it from the project directory. The DynamoDB endpoint requires the updated `modernization_factory.server` code.

### Endpoint returns `502`

Inspect the server window. Common causes are missing `boto3`, missing `botocore[crt]`, expired AWS login, or incorrect table/index environment variables.

## Cleanup

Delete the demo table when it is no longer needed:

```powershell
aws dynamodb delete-table `
  --profile sandbox `
  --region us-east-1 `
  --table-name legacy-modernization-demo
```

Do not delete existing sandbox tables unless their owner has approved it.

## Aurora PostgreSQL RDS demo

The existing `database-1` cluster is available but has no DB instance, subnet group, or security groups, so it cannot accept SQL connections. Create a separate encrypted Aurora cluster for this demo. Aurora is billable; run these commands only in the sandbox and delete the resources when finished.

### 1. Create a subnet group and security group

```powershell
$profile = "sandbox"
$region = "us-east-1"
$vpcId = "vpc-060d6b7b"
$subnetA = "subnet-3b9ad05d" # us-east-1a
$subnetB = "subnet-910454b0" # us-east-1b

aws rds create-db-subnet-group `
  --profile $profile `
  --region $region `
  --db-subnet-group-name legacy-modernization-db-subnets `
  --db-subnet-group-description "Legacy modernization sandbox Aurora subnets" `
  --subnet-ids $subnetA $subnetB

$sgId = aws ec2 create-security-group `
  --profile $profile `
  --region $region `
  --group-name legacy-modernization-rds-sg `
  --description "Legacy modernization sandbox RDS Data API" `
  --vpc-id $vpcId `
  --query GroupId `
  --output text
```

The security group intentionally has no inbound rule. The RDS Data API is used by the local endpoint, so the database does not need to be exposed to your laptop.

### 2. Create the Aurora cluster and writer

```powershell
aws rds create-db-cluster `
  --profile $profile `
  --region $region `
  --db-cluster-identifier legacy-modernization-aurora `
  --engine aurora-postgresql `
  --engine-version 17.7 `
  --database-name legacydb `
  --master-username appadmin `
  --manage-master-user-password `
  --storage-encrypted `
  --enable-http-endpoint `
  --db-subnet-group-name legacy-modernization-db-subnets `
  --vpc-security-group-ids $sgId `
  --backup-retention-period 1 `
  --copy-tags-to-snapshot `
  --tags Key=Project,Value=legacy-modernization Key=Environment,Value=sandbox

aws rds create-db-instance `
  --profile $profile `
  --region $region `
  --db-instance-identifier legacy-modernization-aurora-1 `
  --db-cluster-identifier legacy-modernization-aurora `
  --engine aurora-postgresql `
  --db-instance-class db.t4g.medium

aws rds wait db-instance-available `
  --profile $profile `
  --region $region `
  --db-instance-identifier legacy-modernization-aurora-1
```

If `--enable-http-endpoint` is rejected, the account/engine does not support Data API for this cluster. Stop at that point and use the error to choose an approved Aurora configuration; do not expose port 5432 publicly as a workaround.

### 3. Capture the Data API identifiers

```powershell
$resourceArn = aws rds describe-db-clusters `
  --profile $profile `
  --region $region `
  --db-cluster-identifier legacy-modernization-aurora `
  --query "DBClusters[0].DBClusterArn" `
  --output text

$secretArn = aws rds describe-db-clusters `
  --profile $profile `
  --region $region `
  --db-cluster-identifier legacy-modernization-aurora `
  --query "DBClusters[0].MasterUserSecret.SecretArn" `
  --output text

aws rds describe-db-clusters `
  --profile $profile `
  --region $region `
  --db-cluster-identifier legacy-modernization-aurora `
  --query "DBClusters[0].{Status:Status,Arn:DBClusterArn,Secret:MasterUserSecret.SecretArn,DataApi:HttpEndpointEnabled}" `
  --output table
```

The cluster must be `available`, the secret ARN must be present, and `DataApi` must be `True`.

### 4. Create the table and insert records

Use PowerShell objects and `ConvertTo-Json` so JSON quoting and BOM issues do not corrupt AWS CLI arguments.

```powershell
$createTable = @{
  resourceArn = $resourceArn
  secretArn = $secretArn
  database = "legacydb"
  sql = "CREATE TABLE IF NOT EXISTS legacy_records (id VARCHAR(100) PRIMARY KEY, tacs VARCHAR(50) NOT NULL, name VARCHAR(200) NOT NULL, status VARCHAR(50) NOT NULL, payload JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
} | ConvertTo-Json -Depth 10
$createTable | Set-Content -Encoding ascii .\rds-create-table.json
aws rds-data execute-statement --profile $profile --region $region --cli-input-json file://rds-create-table.json

$createIndex = @{
  resourceArn = $resourceArn
  secretArn = $secretArn
  database = "legacydb"
  sql = "CREATE INDEX IF NOT EXISTS idx_legacy_records_tacs ON legacy_records (tacs)"
} | ConvertTo-Json -Depth 10
$createIndex | Set-Content -Encoding ascii .\rds-create-index.json
aws rds-data execute-statement --profile $profile --region $region --cli-input-json file://rds-create-index.json

$insert = @{
  resourceArn = $resourceArn
  secretArn = $secretArn
  database = "legacydb"
  sql = "INSERT INTO legacy_records (id,tacs,name,status,payload) VALUES (:id,:tacs,:name,:status,CAST(:payload AS JSONB)) ON CONFLICT (id) DO UPDATE SET tacs=EXCLUDED.tacs,name=EXCLUDED.name,status=EXCLUDED.status,payload=EXCLUDED.payload"
  parameters = @(
    @{ name = "id"; value = @{ stringValue = "rds-8888" } },
    @{ name = "tacs"; value = @{ stringValue = "8888" } },
    @{ name = "name"; value = @{ stringValue = "RDS customer 8888" } },
    @{ name = "status"; value = @{ stringValue = "ACTIVE" } },
    @{ name = "payload"; value = @{ stringValue = '{"origin":"accumulo","mapping":"rds"}' } }
  )
} | ConvertTo-Json -Depth 10
$insert | Set-Content -Encoding ascii .\rds-insert-8888.json
aws rds-data execute-statement --profile $profile --region $region --cli-input-json file://rds-insert-8888.json
```

Repeat the insert with `rds-7777`, `7777`, and a second name/status if you want to demonstrate both successful queries. Verify directly with:

```powershell
$query = @{
  resourceArn = $resourceArn
  secretArn = $secretArn
  database = "legacydb"
  sql = "SELECT id,tacs,name,status FROM legacy_records WHERE tacs = :tacs ORDER BY id"
  parameters = @(@{ name = "tacs"; value = @{ stringValue = "8888" } })
  includeResultMetadata = $true
} | ConvertTo-Json -Depth 10
$query | Set-Content -Encoding ascii .\rds-query.json
aws rds-data execute-statement --profile $profile --region $region --cli-input-json file://rds-query.json
```

### 5. Start the local endpoint in AWS mode and test RDS

From the repository directory, keep the server in one PowerShell window:

```powershell
$env:AWS_PROFILE = "sandbox"
$env:AWS_REGION = "us-east-1"
$env:AWS_CA_BUNDLE = "$env:USERPROFILE\zscaler-root.cer"
$env:MODERNIZATION_DATA_MODE = "aws"
$env:RDS_RESOURCE_ARN = $resourceArn
$env:RDS_SECRET_ARN = $secretArn
$env:RDS_DATABASE = "legacydb"
python -m modernization_factory.server --plan .\sandbox-output\plan.json --port 8090
```

In a second window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8090/api/data?source=rds&tacs=8888" | ConvertTo-Json -Depth 10
```

Expected result: `source` is `rds`, `count` is `1`, and the record contains `tacs` equal to `8888`. A missing `RDS_RESOURCE_ARN` or `RDS_SECRET_ARN` returns HTTP 502 rather than silently reading demo data.

### RDS cleanup

After the demo, delete the writer first, then the cluster, subnet group, and security group. Confirm the identifiers before running:

```powershell
aws rds delete-db-instance --profile $profile --region $region --db-instance-identifier legacy-modernization-aurora-1 --skip-final-snapshot
aws rds wait db-instance-deleted --profile $profile --region $region --db-instance-identifier legacy-modernization-aurora-1
aws rds delete-db-cluster --profile $profile --region $region --db-cluster-identifier legacy-modernization-aurora --skip-final-snapshot
aws rds wait db-cluster-deleted --profile $profile --region $region --db-cluster-identifier legacy-modernization-aurora
aws rds delete-db-subnet-group --profile $profile --region $region --db-subnet-group-name legacy-modernization-db-subnets
aws ec2 delete-security-group --profile $profile --region $region --group-id $sgId
```

These cleanup commands do not touch the existing `database-1` cluster or any existing DynamoDB tables.

## Security notes

- Never commit access keys, passwords, tokens, or AWS credential caches.
- Use `aws login` or IAM Identity Center instead of static credentials.
- Keep the DynamoDB table private and use least-privilege IAM permissions.
- Do not use `--no-verify-ssl`.
- Treat `zscaler-root.cer` as organizational infrastructure material and protect it appropriately.
