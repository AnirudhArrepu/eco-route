param(
    [string]$Region = "ap-south-1",
    [string]$ExpectedAccount = "265134560414",
    [string]$Profile = "",
    [string]$FunctionName = "",
    [string[]]$FunctionNames = @()
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packageRoot = Join-Path $env:TEMP "ecoroute-deploy-$([guid]::NewGuid().ToString('N'))"
$archivePath = Join-Path $env:TEMP "ecoroute-deploy-$([guid]::NewGuid().ToString('N')).zip"
$requirementsPath = Join-Path $backendRoot "infra\lambda-requirements.txt"
$awsPrefix = @()
$targetFunctions = @("ecoroute-api-286936", "ecoroute-workflow-286936")
if ($FunctionName) {
    $targetFunctions = @($FunctionName)
}
elseif ($FunctionNames.Count -gt 0) {
    $targetFunctions = $FunctionNames
}
if ($Profile) {
    $awsPrefix = @("--profile", $Profile)
}

try {
    if (-not (Test-Path -LiteralPath $requirementsPath)) {
        throw "Lambda requirements file not found: $requirementsPath"
    }

    $account = & aws @awsPrefix sts get-caller-identity --query Account --output text --no-cli-pager
    if ($LASTEXITCODE -ne 0) {
        throw "AWS identity check failed. Confirm your AWS CLI credentials and retry."
    }
    if ($ExpectedAccount -and $account.Trim() -ne $ExpectedAccount) {
        throw "Refusing to deploy to account $($account.Trim()); expected $ExpectedAccount."
    }
    Write-Output "AWS account verified: $($account.Trim())"

    foreach ($targetFunction in $targetFunctions) {
        $configurationJson = & aws @awsPrefix lambda get-function-configuration `
            --region $Region `
            --function-name $targetFunction `
            --query "{Runtime:Runtime,Architectures:Architectures,State:State,LastUpdateStatus:LastUpdateStatus}" `
            --output json `
            --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read the target Lambda configuration for $targetFunction."
        }
        $configuration = $configurationJson | ConvertFrom-Json
        if ($configuration.Runtime -ne "python3.12" -or $configuration.Architectures -notcontains "x86_64") {
            throw "$targetFunction does not match this package's Python 3.12 x86_64 target."
        }
        if ($configuration.State -ne "Active" -or $configuration.LastUpdateStatus -eq "InProgress") {
            throw "$targetFunction is not ready for a code update (state=$($configuration.State), update=$($configuration.LastUpdateStatus))."
        }
    }

    New-Item -ItemType Directory -Path $packageRoot | Out-Null
    Write-Output "Installing Python 3.12 Lambda dependencies..."
    & python -m pip install --quiet --disable-pip-version-check --only-binary=:all: `
        --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --abi cp312 `
        --target $packageRoot --requirement $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the Lambda dependency package."
    }

    Copy-Item -LiteralPath (Join-Path $backendRoot "app") -Destination $packageRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $backendRoot "migrations") -Destination $packageRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $backendRoot "alembic.ini") -Destination $packageRoot
    Get-ChildItem -LiteralPath $packageRoot -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
    Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal

    $archiveSizeMb = [math]::Round((Get-Item -LiteralPath $archivePath).Length / 1MB, 2)
    if ($archiveSizeMb -gt 50) {
        throw "Deployment archive is $archiveSizeMb MB. Direct Lambda uploads must be 50 MB or less."
    }
    Write-Output "Deployment archive ready: $archiveSizeMb MB"

    foreach ($targetFunction in $targetFunctions) {
        & aws @awsPrefix lambda update-function-code `
            --region $Region `
            --function-name $targetFunction `
            --zip-file "fileb://$archivePath" `
            --query "{FunctionName:FunctionName,LastModified:LastModified,CodeSha256:CodeSha256}" `
            --output json `
            --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "Lambda code update failed for $targetFunction."
        }

        & aws @awsPrefix lambda wait function-updated --region $Region --function-name $targetFunction
        if ($LASTEXITCODE -ne 0) {
            throw "$targetFunction did not finish updating. Check its LastUpdateStatus before retrying."
        }

        $status = & aws @awsPrefix lambda get-function-configuration `
            --region $Region `
            --function-name $targetFunction `
            --query "{FunctionName:FunctionName,State:State,LastUpdateStatus:LastUpdateStatus,LastModified:LastModified}" `
            --output json `
            --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "Could not verify the updated Lambda configuration for $targetFunction."
        }
        Write-Output $status
    }
    Write-Output "Deployment complete:"
}
finally {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
}
