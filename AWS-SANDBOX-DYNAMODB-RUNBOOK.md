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

## Security notes

- Never commit access keys, passwords, tokens, or AWS credential caches.
- Use `aws login` or IAM Identity Center instead of static credentials.
- Keep the DynamoDB table private and use least-privilege IAM permissions.
- Do not use `--no-verify-ssl`.
- Treat `zscaler-root.cer` as organizational infrastructure material and protect it appropriately.
