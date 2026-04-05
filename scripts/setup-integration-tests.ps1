param(
    [string]$ComposeFile = "deploy/docker-compose.yml",
    [string]$PostgresService = "postgres",
    [string]$RedisService = "redis",
    [string]$DbUser = "nexus",
    [string]$DbPassword = "nexus_dev_2024",
    [string]$DbName = "nexus_notebook_11_test"
)

$ErrorActionPreference = "Stop"

function Assert-DockerDaemon {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not running. Start Docker Desktop and retry."
    }
}

function Wait-ForPostgres {
    param(
        [int]$Retries = 40,
        [int]$SleepSeconds = 2
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        docker compose -f $ComposeFile exec -T $PostgresService `
            pg_isready -U $DbUser -d postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds $SleepSeconds
    }

    throw "Postgres did not become ready in time."
}

Assert-DockerDaemon

Write-Host "Starting integration dependencies: $PostgresService, $RedisService"
docker compose -f $ComposeFile up -d $PostgresService $RedisService
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Host "Waiting for Postgres readiness..."
Wait-ForPostgres

Write-Host "Creating test database (if missing)..."
$exists = docker compose -f $ComposeFile exec -T $PostgresService `
    psql -U $DbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query pg_database"
}
if (-not ($exists -match "1")) {
    docker compose -f $ComposeFile exec -T $PostgresService `
        psql -U $DbUser -d postgres -c "CREATE DATABASE $DbName"
    if ($LASTEXITCODE -ne 0) {
        throw "CREATE DATABASE failed"
    }
}

Write-Host "Applying schema to $DbName (safe on empty DB; re-run may error if tables exist)..."
docker compose -f $ComposeFile exec -T $PostgresService `
    psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/001_initial.sql
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Schema apply failed — if the test DB already has tables, recreate the DB or drop volumes."
    throw "Schema apply failed"
}

Write-Host ""
Write-Host "Integration test stack ready."
Write-Host "Run tests with:"
Write-Host "  `$env:ENVIRONMENT='testing'"
Write-Host "  `$env:DATABASE_URL='postgresql+asyncpg://${DbUser}:${DbPassword}@localhost:5432/${DbName}'"
Write-Host "  `$env:REDIS_URL='redis://localhost:6379/1'"
Write-Host "  pytest tests/integration -v --tb=short"
