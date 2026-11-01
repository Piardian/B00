$ErrorActionPreference='Stop'
$seasonDir=$PSScriptRoot
$seasonRepo=[System.IO.Path]::GetFullPath((Join-Path $seasonDir '..\..'))
$seasonExe='C:\Program Files\Five Percent Online MetaTrader 5\terminal64.exe'
$seasonPrior=@(Get-CimInstance Win32_Process -Filter "name='terminal64.exe'" | Where-Object ExecutablePath -eq $seasonExe)
if ($seasonPrior.Count -gt 1) { throw 'Multiple matching terminals; ambiguous session.' }
if ((Get-PSDrive C).Free -lt 2GB) { throw 'Need2GiB before warm-cache extraction.' }
$seasonConfig=Join-Path $seasonDir 'readonly.ini'
$seasonOwn=$seasonPrior.Count -eq 0
if ($seasonOwn) {
    $seasonTerminal=Start-Process -FilePath $seasonExe -ArgumentList ('/config:"'+$seasonConfig+'"') -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 8
} else { $seasonTerminal=Get-Process -Id $seasonPrior[0].ProcessId }
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class SeasonGuard { [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid); [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr process); [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle); }'
$seasonPython=(Get-Command python).Source
$seasonWorker=Start-Process -FilePath $seasonPython -ArgumentList @('-u','research/london-gold-seasonal-extension-2026-10-24/study.py','collect') -WorkingDirectory $seasonRepo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $seasonDir 'collect.log') -RedirectStandardError (Join-Path $seasonDir 'collect_errors.log')
while (-not $seasonWorker.HasExited) {
    if ((Get-PSDrive C).Free -lt 1GB) {
        $seasonIdentity=Get-CimInstance Win32_Process -Filter "ProcessId=$($seasonTerminal.Id)"
        if ($null -ne $seasonIdentity -and $seasonIdentity.ExecutablePath -eq $seasonExe) {
            $seasonHandle=[SeasonGuard]::OpenProcess(0x0800,$false,[int]$seasonTerminal.Id)
            if ($seasonHandle -eq [IntPtr]::Zero) { throw 'Cannot suspend own terminal.' }
            $seasonStatus=[SeasonGuard]::NtSuspendProcess($seasonHandle)
            [void][SeasonGuard]::CloseHandle($seasonHandle)
            @{status='suspended';pid=$seasonTerminal.Id;code=$seasonStatus;free_bytes=(Get-PSDrive C).Free} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $seasonDir 'disk_emergency.json')
        }
        Stop-Process -Id $seasonWorker.Id
        throw 'Disk emergency: owned terminal suspended; preserve partial outputs.'
    }
    Start-Sleep -Milliseconds 500
    $seasonWorker.Refresh()
}
$seasonWorker.Refresh()
$seasonExit=$seasonWorker.ExitCode
if ($seasonOwn -and -not $seasonTerminal.HasExited) {
    [void]$seasonTerminal.CloseMainWindow()
    if (-not $seasonTerminal.WaitForExit(10000)) { throw 'Collector ended but own terminal did not close normally.' }
}
if ($seasonExit -ne 0) { throw "Read-only collector failed: $seasonExit" }
"COLLECTION_COMPLETE own_terminal_closed=$seasonOwn"
