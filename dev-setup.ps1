param(
    [switch]$Workers,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required for the local development environment."
}
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose v2 is required (the 'docker compose' command is unavailable)."
}

if (-not (Test-Path .env.local)) {
    Copy-Item .env.local.example .env.local
    $jwt = -join ((1..48) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
    $litellm = -join ((1..32) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
    (Get-Content .env.local) `
        -replace 'replace-with-a-random-local-jwt-secret', $jwt `
        -replace 'replace-with-a-random-local-litellm-key', "sk-local-$litellm" `
        -replace 'replace-with-a-local-root-password', "local-root-$litellm" `
        -replace 'replace-with-a-local-database-password', "local-db-$litellm" |
        Set-Content .env.local -Encoding utf8
    Write-Host "Created .env.local with generated local-only secrets." -ForegroundColor Green
}

$composeArgs = @("compose", "--env-file", ".env.local", "-f", "deploy/compose/dev/compose.yml")
if ($Workers) { $composeArgs += @("--profile", "workers") }
if ($Down) {
    & docker @composeArgs down
    if ($LASTEXITCODE -ne 0) {
        throw "Local development services failed to stop."
    }
} else {
    & docker @composeArgs up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "Local development services failed to start."
    }
    Write-Host "Dashboard: http://localhost:3000" -ForegroundColor Green
    Write-Host "API docs:  http://localhost:8000/docs" -ForegroundColor Green
}
