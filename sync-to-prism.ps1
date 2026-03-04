# sync-to-prism.ps1
# Watches for changes in the resource pack and syncs to PrismLauncher

$source = $PSScriptRoot
$destination = "C:\Users\gabec\AppData\Roaming\PrismLauncher\instances\1.21.11\minecraft\resourcepacks\SummitMCRP"

Write-Host "Source:      $source"
Write-Host "Destination: $destination"
Write-Host ""

# Initial full sync
Write-Host "Performing initial sync..." -ForegroundColor Cyan
robocopy $source $destination /MIR /XD ".git" /XF "sync-to-prism.ps1" /NP /NFL /NDL
Write-Host "Initial sync complete." -ForegroundColor Green
Write-Host ""
Write-Host "Watching for changes... Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $source
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor
                        [System.IO.NotifyFilters]::DirectoryName -bor
                        [System.IO.NotifyFilters]::LastWrite

$debounceTimer = $null
$pendingSync = $false

$onChange = {
    $global:pendingSync = $true
}

Register-ObjectEvent $watcher Changed -Action $onChange | Out-Null
Register-ObjectEvent $watcher Created -Action $onChange | Out-Null
Register-ObjectEvent $watcher Deleted -Action $onChange | Out-Null
Register-ObjectEvent $watcher Renamed -Action $onChange | Out-Null

try {
    while ($true) {
        Start-Sleep -Milliseconds 500

        if ($global:pendingSync) {
            $global:pendingSync = $false
            $timestamp = Get-Date -Format "HH:mm:ss"
            Write-Host "[$timestamp] Change detected, syncing..." -ForegroundColor Cyan
            robocopy $source $destination /MIR /XD ".git" /XF "sync-to-prism.ps1" /NP /NFL /NDL
            Write-Host "[$timestamp] Sync complete." -ForegroundColor Green
        }
    }
}
finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Get-EventSubscriber | Unregister-Event
    Write-Host "Watcher stopped." -ForegroundColor Red
}
