# Start local Postgres (Docker) and run Alembic migrations.
# Usage: .\scripts\dev_db_postgres.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Resolve-DockerCli {
    # Cursor/CI shells often start before Docker Desktop updates PATH — refresh first.
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($machinePath -or $userPath) {
        $env:Path = ($machinePath, $userPath -join ";").Trim(";")
    }

    $cmd = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "docker\.ps1$") {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe",
        "$env:LocalAppData\Programs\Docker\Docker\resources\bin\docker.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$DockerExe = Resolve-DockerCli
if (-not $DockerExe) {
    Write-Error @"
Docker CLI not found in PATH or default install locations.
Install Docker Desktop, restart the terminal, then rerun:
  .\scripts\dev_db_postgres.ps1
"@
}

Write-Host "==> Using Docker: $DockerExe"
& $DockerExe version --format "{{.Server.Version}}" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is installed but the daemon is not running. Start Docker Desktop, then rerun this script."
}

Write-Host "==> Starting Postgres container..."
& $DockerExe compose up -d postgres
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed (exit $LASTEXITCODE)."
}

Write-Host "==> Waiting for database..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    $status = & $DockerExe inspect -f "{{.State.Health.Status}}" ai-interview-bot-db 2>$null
    if ($status -eq "healthy") {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Error "Postgres did not become healthy in time. Check: docker compose logs postgres"
}

$env:DATABASE_URL = "postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot"
Write-Host "==> Bootstrapping database schema..."
python scripts/bootstrap_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Database bootstrap failed (exit $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Postgres is ready."
Write-Host "Ensure your .env has exactly one DATABASE_URL line:"
Write-Host "DATABASE_URL=postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot"
