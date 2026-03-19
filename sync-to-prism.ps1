# sync-to-prism.ps1
# Syncs the exported resource pack zip to PrismLauncher

$sourceZip = Join-Path $PSScriptRoot "SummitMCRP.zip"
$destinationDir = "C:\Users\gabec\AppData\Roaming\PrismLauncher\instances\Summi-F2\minecraft\resourcepacks"

Write-Host "Source ZIP:  $sourceZip"
Write-Host "Destination: $destinationDir"
Write-Host ""

# Initial sync
Write-Host "Performing initial sync..." -ForegroundColor Cyan
if (Test-Path $sourceZip) {
    Copy-Item $sourceZip $destinationDir -Force
    Write-Host "Initial sync complete." -ForegroundColor Green
} else {
    Write-Host "Source ZIP not found: $sourceZip" -ForegroundColor Red
}
Write-Host ""
Write-Host "Watching for changes... Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $PSScriptRoot
$watcher.Filter = "SummitMCRP.zip"
$watcher.EnableRaisingEvents = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor
                        [System.IO.NotifyFilters]::LastWrite

$debounceTimer = $null
$pendingSync = $false

$onChange = {
    $global:pendingSync = $true
}

Register-ObjectEvent $watcher Changed -Action $onChange | Out-Null
Register-ObjectEvent $watcher Created -Action $onChange | Out-Null

try {
    while ($true) {
        Start-Sleep -Milliseconds 500

        if ($global:pendingSync) {
            $global:pendingSync = $false
            $timestamp = Get-Date -Format "HH:mm:ss"
            Write-Host "[$timestamp] Change detected, syncing..." -ForegroundColor Cyan
            if (Test-Path $sourceZip) {
                Copy-Item $sourceZip $destinationDir -Force
                Write-Host "[$timestamp] Sync complete." -ForegroundColor Green
            } else {
                Write-Host "[$timestamp] Source ZIP not found: $sourceZip" -ForegroundColor Red
            }
        }
    }
}
finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Get-EventSubscriber | Unregister-Event
    Write-Host "Watcher stopped." -ForegroundColor Red
}
