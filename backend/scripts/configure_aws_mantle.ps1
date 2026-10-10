$ErrorActionPreference = "Stop"

$region = "ap-south-1"
$secureKey = $null
$keyPointer = [IntPtr]::Zero
$temporaryConfig = Join-Path $env:TEMP "ecoroute-lambda-environment-$([guid]::NewGuid().ToString('N')).json"
try {
    if ($env:OPENAI_API_KEY) {
        $apiKey = $env:OPENAI_API_KEY
    }
    else {
        $secureKey = Read-Host "Enter the Bedrock Mantle OPENAI_API_KEY (input is hidden)" -AsSecureString
        if ($secureKey.Length -eq 0) {
            throw "A non-empty Mantle API key is required."
        }
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    }
    foreach ($functionName in @("ecoroute-api-286936", "ecoroute-workflow-286936")) {
        $variablesJson = aws lambda get-function-configuration `
            --region $region `
            --function-name $functionName `
            --query "Environment.Variables" `
            --output json `
            --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read configuration for $functionName."
        }

        $variablesObject = $variablesJson | ConvertFrom-Json
        $variables = @{}
        if ($variablesObject) {
            foreach ($property in $variablesObject.PSObject.Properties) {
                $variables[$property.Name] = [string]$property.Value
            }
        }

        $variables["OPENAI_API_KEY"] = $apiKey
        $variables["BEDROCK_MODEL_ID"] = "openai.gpt-oss-safeguard-20b"
        $variables["OPENAI_BASE_URL"] = "https://bedrock-mantle.ap-south-1.api.aws/v1"
        $variables["OPENAI_PROJECT_ID"] = "default"
        $variables["STRANDS_AGENT_ENABLED"] = "false"
        if ($functionName -eq "ecoroute-api-286936") {
            $variables["STEP_FUNCTIONS_ENABLED"] = "true"
        }

        @{ Variables = $variables } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporaryConfig -Encoding ascii
        aws lambda update-function-configuration `
            --region $region `
            --function-name $functionName `
            --environment "file://$temporaryConfig" `
            --query "{FunctionName:FunctionName,LastUpdateStatus:LastUpdateStatus}" `
            --output json `
            --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "Could not update configuration for $functionName."
        }
        aws lambda wait function-updated --region $region --function-name $functionName
        if ($LASTEXITCODE -ne 0) {
            throw "Configuration update did not finish for $functionName."
        }
    }
    Write-Output "Mantle is configured on the API and workflow Lambdas. Step Functions is enabled on the API."
}
finally {
    if ($keyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    Remove-Item -LiteralPath $temporaryConfig -Force -ErrorAction SilentlyContinue
    Remove-Variable apiKey, secureKey, keyPointer -ErrorAction SilentlyContinue
}
