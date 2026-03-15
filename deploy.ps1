Write-Host "Step 1: Building..."
sam build --no-cached

Write-Host "Step 2: Zipping..."
Compress-Archive -Path ".aws-sam\build\MaterialProcessorFunction\*" -DestinationPath "lambda_deploy.zip" -Force

Write-Host "Step 3: Updating material-processor..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-material-processor --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 4: Updating qa-engine..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-qa-engine --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 5: Updating quiz-generator..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-quiz-generator --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 6: Updating gap-detector..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-gap-detector --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 7: Updating explanation-engine..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-explanation-engine --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 8: Updating session-manager..."
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-code --function-name study-assistant-session-manager --zip-file fileb://lambda_deploy.zip --region ap-south-1

Write-Host "Step 9: Updating env vars on all functions..."
$envVars = "Variables={TABLE_NAME=study-assistant,BUCKET_NAME=study-assistant-materials-690167396999-ap-south-1,BEDROCK_MODEL_ID=amazon.nova-micro-v1:0}"
$functions = @(
    "study-assistant-material-processor",
    "study-assistant-qa-engine",
    "study-assistant-quiz-generator",
    "study-assistant-gap-detector",
    "study-assistant-explanation-engine",
    "study-assistant-session-manager"
)
foreach ($fn in $functions) {
    Write-Host "  Updating env: $fn"
    & "C:\Program Files\Amazon\AWSCLIV2\aws.exe" lambda update-function-configuration --function-name $fn --environment $envVars --region ap-south-1 | Out-Null
}

Write-Host "Done! All 6 functions updated with new model."
