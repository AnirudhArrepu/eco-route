$ErrorActionPreference = "Stop"

$secureKey = Read-Host "Enter the Bedrock Mantle OPENAI_API_KEY (input is hidden)" -AsSecureString
if ($secureKey.Length -eq 0) {
    throw "A non-empty Mantle API key is required."
}

$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    Remove-Variable secureKey, keyPointer -ErrorAction SilentlyContinue
}

$env:OPENAI_BASE_URL = "https://bedrock-mantle.ap-south-1.api.aws/v1"
$env:OPENAI_PROJECT_ID = "default"
$env:BEDROCK_MODEL_ID = "openai.gpt-oss-safeguard-20b"
$env:AWS_REGION = "ap-south-1"
$env:AWS_INTEGRATIONS_ENABLED = "true"
$env:DATABASE_SECRET_ARN = "arn:aws:secretsmanager:ap-south-1:265134560414:secret:rds!db-c3715b2e-a906-44a8-821e-a88a09fe0b0d-deFchF"
$env:DATABASE_HOST = "127.0.0.1"
$env:DATABASE_PORT = "15432"
$env:LOCATION_INDEX_NAME = "ecoroute-places-286936"
$env:LOCATION_ROUTE_CALCULATOR_NAME = "ecoroute-routes-286936"
$env:STEP_FUNCTIONS_ENABLED = "false"
$env:STRANDS_AGENT_ENABLED = "false"
$env:AUTH_REQUIRED = "false"
$env:ENVIRONMENT = "development"
$env:AUTO_MIGRATE = "false"

Set-Location (Split-Path -Parent $PSScriptRoot)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
