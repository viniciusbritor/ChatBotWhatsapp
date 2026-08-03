# Loop Harness - ChatBotWhatsapp
# Helper para rodar testes com timeout rigoroso e reportar status.
# Uso:
#   . ./scripts/loop_helper.ps1
#   Run-Test-Safe "cd agents_runtime; python -m pytest -q tests/test_x.py" 30 "descricao"

function Run-Test-Safe {
    param(
        [string]$Command,
        [int]$TimeoutSec = 60,
        [string]$Description = "test"
    )

    $startTime = Get-Date
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] START: $Description" -ForegroundColor Cyan
    Write-Host "  CMD: $Command" -ForegroundColor DarkGray

    $job = Start-Job -ScriptBlock {
        param($cmd)
        Set-Location $using:WORKDIR
        Invoke-Expression $cmd 2>&1
    } -ArgumentList $Command

    $completed = Wait-Job -Job $job -Timeout $TimeoutSec

    if (-not $completed) {
        Write-Host "  [TIMEOUT $TimeoutSec s] matando processo..." -ForegroundColor Red
        Stop-Job -Job $job -Force
        Remove-Job -Job $job -Force
        Get-Process | Where-Object { $_.CommandLine -like "*pytest*" } | Stop-Process -Force -ErrorAction SilentlyContinue
        return @{ Status = "TIMEOUT"; Duration = $TimeoutSec; Output = "" }
    }

    $output = Receive-Job -Job $job
    Remove-Job -Job $job -Force

    $duration = (Get-Date) - $startTime

    # Detectar padroes de erro/sucesso
    $passed = ($output | Select-String -Pattern "passed").Count -gt 0
    $failed = ($output | Select-String -Pattern "FAILED|failed").Count -gt 0
    $error = ($output | Select-String -Pattern "Error|error|Exception").Count -gt 0

    if ($passed -and -not $failed) {
        Write-Host "  [OK] $([math]::Round($duration.TotalSeconds,1))s" -ForegroundColor Green
    } elseif ($failed) {
        Write-Host "  [FAIL] $([math]::Round($duration.TotalSeconds,1))s" -ForegroundColor Red
    } elseif ($error) {
        Write-Host "  [ERR] $([math]::Round($duration.TotalSeconds,1))s" -ForegroundColor Yellow
    } else {
        Write-Host "  [DONE] $([math]::Round($duration.TotalSeconds,1))s" -ForegroundColor Gray
    }

    return @{
        Status = if ($passed -and -not $failed) { "PASS" } elseif ($failed) { "FAIL" } else { "UNKNOWN" }
        Duration = $duration.TotalSeconds
        Output = $output
    }
}

function Show-Loop-Status {
    param([string]$Title = "Loop Status")

    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Magenta
    Write-Host "  $Title" -ForegroundColor Magenta
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Magenta
    $todos = Get-TodoList 2>$null
    if ($todos) {
        foreach ($t in $todos) {
            $icon = switch ($t.Status) {
                "completed" { "[OK]" }
                "in_progress" { "[..]" }
                "pending" { "[  ]" }
                default { "[??]" }
            }
            $color = switch ($t.Status) {
                "completed" { "Green" }
                "in_progress" { "Yellow" }
                default { "Gray" }
            }
            Write-Host "  $icon $($t.Content)" -ForegroundColor $color
        }
    }
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Magenta
    Write-Host ""
}

Export-ModuleMember -Function Run-Test-Safe, Show-Loop-Status