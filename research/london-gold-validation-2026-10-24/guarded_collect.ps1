param([switch]$PreflightOnly, [ValidateSet('collect','repair_missing')][string]$Mode = 'collect')
$ErrorActionPreference = 'Stop'
$goldStudyDir = $PSScriptRoot
$goldRepoDir = [System.IO.Path]::GetFullPath((Join-Path $goldStudyDir '..\..'))
$goldTerminalPath = 'C:\Program Files\Five Percent Online MetaTrader 5\terminal64.exe'
$goldRequiredFree = 2GB
$goldEmergencyFree = 1GB
$goldTerminal = @(Get-CimInstance Win32_Process -Filter "name = 'terminal64.exe'" | Where-Object { $_.ExecutablePath -eq $goldTerminalPath })
$goldFree = (Get-PSDrive C).Free
$goldPreflight = @{ terminal_running = ($goldTerminal.Count -eq 1); free_bytes = $goldFree; required_free_bytes = $goldRequiredFree; approved_to_start = ($goldTerminal.Count -eq 1 -and $goldFree -ge $goldRequiredFree); starts_terminal = $false }
$goldPreflight | ConvertTo-Json
if ($PreflightOnly -or -not $goldPreflight.approved_to_start) { return }
# This launcher never starts/restarts MT5. Its monitored collector may only
# connect to the terminal already identified above. An emergency suspension
# stops an in-terminal download even if terminating Python does not cancel it.
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class GoldDiskGuard { [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid); [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr process); [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle); }'
$goldPython = (Get-Command python).Source
$goldScriptArgs = if ($Mode -eq 'collect') { @('-u','research/london-gold-validation-2026-10-24/validate.py','collect') } else { @('-u','research/london-gold-2026-10-24/repair_missing.py') }
$goldCollector = Start-Process -FilePath $goldPython -ArgumentList $goldScriptArgs -WorkingDirectory $goldRepoDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $goldStudyDir ($Mode + '_guarded.log')) -RedirectStandardError (Join-Path $goldStudyDir ($Mode + '_guarded_errors.log'))
while (-not $goldCollector.HasExited) {
    if ((Get-PSDrive C).Free -lt $goldEmergencyFree) {
        $goldIdentity = Get-CimInstance Win32_Process -Filter "ProcessId = $($goldTerminal[0].ProcessId)"
        if ($null -ne $goldIdentity -and $goldIdentity.ExecutablePath -eq $goldTerminalPath) {
            $goldHandle = [GoldDiskGuard]::OpenProcess(0x0800, $false, [int]$goldIdentity.ProcessId)
            if ($goldHandle -eq [IntPtr]::Zero) { throw 'Cannot suspend identified terminal; manual intervention required.' }
            $goldSuspendStatus = [GoldDiskGuard]::NtSuspendProcess($goldHandle)
            [void][GoldDiskGuard]::CloseHandle($goldHandle)
            if ($goldSuspendStatus -ne 0) { throw "Cannot suspend identified terminal: $goldSuspendStatus" }
            @{ status = 'suspended'; pid = $goldIdentity.ProcessId; path = $goldIdentity.ExecutablePath; reason = 'external disk watchdog'; utc = [DateTime]::UtcNow.ToString('o'); free_bytes = (Get-PSDrive C).Free } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $goldStudyDir 'terminal_pause.json')
        }
        if (-not $goldCollector.HasExited) { Stop-Process -Id $goldCollector.Id }
        throw 'Disk guard stopped collection and suspended MT5. Do not resume before cancelling download safely.'
    }
    Start-Sleep -Milliseconds 500
    $goldCollector.Refresh()
}
if ($goldCollector.ExitCode -ne 0) { throw "Collector failed with code $($goldCollector.ExitCode); preserve partial manifest." }

