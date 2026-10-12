param(
    [switch]$Execute,
    [string]$Profile = "sandbox",
    [string]$Region = "us-east-1",
    [string]$Bucket = "legacy-modernization-s3-356724906763",
    [string]$Key = "legacy-records.json"
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""
$records = @(
    @{ id = "s3-8888"; tacs = "8888"; name = "S3 customer 8888"; status = "ACTIVE"; tags = @("8888", "customer") },
    @{ id = "s3-7777"; tacs = "7777"; name = "S3 customer 7777"; status = "READY"; tags = @("7777", "customer") }
)

if (-not $Execute) {
    Write-Host "DRY RUN: no S3 resources or objects will be created or modified." -ForegroundColor Yellow
    Write-Host "Review this script, then rerun with -Execute to create the private S3 demo object."
    exit 0
}

$jsonPath = Join-Path $PSScriptRoot "s3-legacy-records.json"
$encryptionPath = Join-Path $PSScriptRoot "s3-encryption.json"
try {
    $records | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii $jsonPath
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' | Set-Content -Encoding ascii $encryptionPath
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        aws s3api head-bucket --profile $Profile --region $Region --bucket $Bucket 2>$null
        $headExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($headExitCode -ne 0) {
        if ($Region -eq "us-east-1") {
            aws s3api create-bucket --profile $Profile --region $Region --bucket $Bucket
        } else {
            aws s3api create-bucket --profile $Profile --region $Region --bucket $Bucket --create-bucket-configuration LocationConstraint=$Region
        }
        if ($LASTEXITCODE -ne 0) { throw "Unable to create S3 bucket $Bucket" }
    }
    aws s3api put-public-access-block --profile $Profile --region $Region --bucket $Bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    aws s3api put-bucket-encryption --profile $Profile --region $Region --bucket $Bucket --server-side-encryption-configuration file://$encryptionPath
    if ($LASTEXITCODE -ne 0) { throw "Unable to enable default S3 encryption" }
    aws s3api put-object --profile $Profile --region $Region --bucket $Bucket --key $Key --body $jsonPath --content-type application/json --server-side-encryption AES256
    if ($LASTEXITCODE -ne 0) { throw "Unable to upload S3 object" }
    Write-Host "S3 demo is ready." -ForegroundColor Green
    Write-Host "S3_BUCKET=$Bucket"
    Write-Host "S3_KEY=$Key"
} finally {
    Remove-Item -LiteralPath $jsonPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $encryptionPath -Force -ErrorAction SilentlyContinue
}
