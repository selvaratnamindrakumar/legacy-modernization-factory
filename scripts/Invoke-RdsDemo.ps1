param(
    [switch]$Execute,
    [string]$Profile = "sandbox",
    [string]$Region = "us-east-1",
    [string]$VpcId = "vpc-060d6b7b",
    [string]$SubnetA = "subnet-3b9ad05d",
    [string]$SubnetB = "subnet-910454b0"
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""
$cluster = "legacy-modernization-aurora"
$instance = "legacy-modernization-aurora-1"
$subnetGroup = "legacy-modernization-db-subnets"
$securityGroupName = "legacy-modernization-rds-sg"
$database = "legacydb"
$handsetTable = "handset_details"
$cellTable = "cells"

if (-not $Execute) {
    Write-Host "DRY RUN: no AWS resources will be created or modified." -ForegroundColor Yellow
    Write-Host "Review this script, then rerun with -Execute to create the sandbox Aurora demo."
    exit 0
}

function Invoke-Aws([string[]]$Arguments) {
    & aws @Arguments
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI command failed with exit code $LASTEXITCODE" }
}

function Get-AwsText([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $result = & aws @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return "" }
        return (($result -join "`n").Trim())
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Write-Host "Creating or reusing subnet group..."
try {
    Invoke-Aws @("rds", "describe-db-subnet-groups", "--profile", $Profile, "--region", $Region, "--db-subnet-group-name", $subnetGroup, "--output", "json")
} catch {
    Invoke-Aws @("rds", "create-db-subnet-group", "--profile", $Profile, "--region", $Region, "--db-subnet-group-name", $subnetGroup, "--db-subnet-group-description", "Legacy modernization sandbox Aurora subnets", "--subnet-ids", $SubnetA, $SubnetB)
}

$sgId = Get-AwsText @("ec2", "describe-security-groups", "--profile", $Profile, "--region", $Region, "--filters", "Name=vpc-id,Values=$VpcId", "Name=group-name,Values=$securityGroupName", "--query", "SecurityGroups[0].GroupId", "--output", "text")
if (-not $sgId -or $sgId -eq "None") {
    $sgId = Get-AwsText @("ec2", "create-security-group", "--profile", $Profile, "--region", $Region, "--group-name", $securityGroupName, "--description", "Legacy modernization sandbox RDS Data API", "--vpc-id", $VpcId, "--query", "GroupId", "--output", "text")
}

$existing = Get-AwsText @("rds", "describe-db-clusters", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster, "--query", "DBClusters[0].DBClusterIdentifier", "--output", "text")
if ($existing -ne $cluster) {
    Invoke-Aws @("rds", "create-db-cluster", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster, "--engine", "aurora-postgresql", "--engine-version", "17.7", "--database-name", $database, "--master-username", "appadmin", "--manage-master-user-password", "--storage-encrypted", "--enable-http-endpoint", "--serverless-v2-scaling-configuration", "MinCapacity=0.5,MaxCapacity=1", "--db-subnet-group-name", $subnetGroup, "--vpc-security-group-ids", $sgId, "--backup-retention-period", "1", "--copy-tags-to-snapshot", "--tags", "Key=Project,Value=legacy-modernization", "Key=Environment,Value=sandbox")
}

$clusterStatus = Get-AwsText @("rds", "describe-db-clusters", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster, "--query", "DBClusters[0].Status", "--output", "text")
if ($clusterStatus -ne "available") {
    Invoke-Aws @("rds", "wait", "db-cluster-available", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster)
}

$scaling = Get-AwsText @("rds", "describe-db-clusters", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster, "--query", "DBClusters[0].ServerlessV2ScalingConfiguration", "--output", "json")
if (-not $scaling -or $scaling -eq "null") {
    Invoke-Aws @("rds", "modify-db-cluster", "--profile", $Profile, "--region", $Region, "--db-cluster-identifier", $cluster, "--serverless-v2-scaling-configuration", "MinCapacity=0.5,MaxCapacity=1", "--apply-immediately")
}

$existingInstance = Get-AwsText @("rds", "describe-db-instances", "--profile", $Profile, "--region", $Region, "--db-instance-identifier", $instance, "--query", "DBInstances[0].DBInstanceIdentifier", "--output", "text")
if ($existingInstance -ne $instance) {
    Invoke-Aws @("rds", "create-db-instance", "--profile", $Profile, "--region", $Region, "--db-instance-identifier", $instance, "--db-cluster-identifier", $cluster, "--engine", "aurora-postgresql", "--db-instance-class", "db.serverless")
}

Invoke-Aws @("rds", "wait", "db-instance-available", "--profile", $Profile, "--region", $Region, "--db-instance-identifier", $instance)

$resourceArn = aws rds describe-db-clusters --profile $Profile --region $Region --db-cluster-identifier $cluster --query "DBClusters[0].DBClusterArn" --output text
$secretArn = aws rds describe-db-clusters --profile $Profile --region $Region --db-cluster-identifier $cluster --query "DBClusters[0].MasterUserSecret.SecretArn" --output text
if (-not $resourceArn -or $resourceArn -eq "None" -or -not $secretArn -or $secretArn -eq "None") { throw "Cluster ARN or managed secret ARN is missing." }

function Execute-Sql([string]$Sql, [array]$Parameters = @()) {
    $request = @{ resourceArn = $resourceArn; secretArn = $secretArn; database = $database; sql = $Sql }
    if ($Parameters.Count -gt 0) { $request.parameters = $Parameters }
    $path = Join-Path $PSScriptRoot ("rds-request-" + [Guid]::NewGuid().ToString() + ".json")
    try {
        $request | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii $path
        Invoke-Aws @("rds-data", "execute-statement", "--profile", $Profile, "--region", $Region, "--cli-input-json", "file://$path")
    } finally {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
}

Execute-Sql "CREATE TABLE IF NOT EXISTS cells (cell_id VARCHAR(100) PRIMARY KEY, cell_name VARCHAR(200) NOT NULL, technology VARCHAR(50), status VARCHAR(50) NOT NULL, payload JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
Execute-Sql "CREATE TABLE IF NOT EXISTS handset_details (handset_id VARCHAR(100) PRIMARY KEY, tacs VARCHAR(50) NOT NULL, cell_id VARCHAR(100) REFERENCES cells(cell_id), handset_model VARCHAR(100), status VARCHAR(50) NOT NULL, payload JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
Execute-Sql "CREATE INDEX IF NOT EXISTS idx_handset_details_tacs ON handset_details (tacs)"
$rows = @(
    @{ id = "rds-8888"; tacs = "8888"; handset = "HS-8888"; cell = "CELL-8888"; name = "RDS customer 8888"; status = "ACTIVE" },
    @{ id = "rds-7777"; tacs = "7777"; handset = "HS-7777"; cell = "CELL-7777"; name = "RDS customer 7777"; status = "READY" }
)
foreach ($row in $rows) {
    $cellParameters = @(
        @{ name = "cell_id"; value = @{ stringValue = $row.cell } },
        @{ name = "cell_name"; value = @{ stringValue = "Cell site $($row.cell)" } },
        @{ name = "technology"; value = @{ stringValue = "5G" } },
        @{ name = "status"; value = @{ stringValue = $row.status } },
        @{ name = "payload"; value = @{ stringValue = '{"origin":"accumulo","mapping":"cell"}' } }
    )
    Execute-Sql "INSERT INTO cells (cell_id,cell_name,technology,status,payload) VALUES (:cell_id,:cell_name,:technology,:status,CAST(:payload AS JSONB)) ON CONFLICT (cell_id) DO UPDATE SET cell_name=EXCLUDED.cell_name,technology=EXCLUDED.technology,status=EXCLUDED.status,payload=EXCLUDED.payload" $cellParameters
    $handsetParameters = @(
        @{ name = "handset_id"; value = @{ stringValue = $row.handset } },
        @{ name = "tacs"; value = @{ stringValue = $row.tacs } },
        @{ name = "cell_id"; value = @{ stringValue = $row.cell } },
        @{ name = "handset_model"; value = @{ stringValue = $row.name } },
        @{ name = "status"; value = @{ stringValue = $row.status } },
        @{ name = "payload"; value = @{ stringValue = '{"origin":"accumulo","mapping":"handset"}' } }
    )
    Execute-Sql "INSERT INTO handset_details (handset_id,tacs,cell_id,handset_model,status,payload) VALUES (:handset_id,:tacs,:cell_id,:handset_model,:status,CAST(:payload AS JSONB)) ON CONFLICT (handset_id) DO UPDATE SET tacs=EXCLUDED.tacs,cell_id=EXCLUDED.cell_id,handset_model=EXCLUDED.handset_model,status=EXCLUDED.status,payload=EXCLUDED.payload" $handsetParameters
}

Write-Host "RDS demo is ready." -ForegroundColor Green
Write-Host "RDS_RESOURCE_ARN=$resourceArn"
Write-Host "RDS_SECRET_ARN=$secretArn"
Write-Host "Set these values in the endpoint PowerShell window before starting the server."
