Option Explicit

Const PROJECT_DIR = "C:\Users\piard\Desktop\Begonya00"
Const BATCH_FILE = "C:\Users\piard\Desktop\Begonya00\BASLAT_BEGONYA00.bat"

Function IsBegonyaOrchestratorRunning()
    Dim wmi, processes, process, commandLine
    IsBegonyaOrchestratorRunning = False

    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = wmi.ExecQuery( _
        "SELECT CommandLine FROM Win32_Process " & _
        "WHERE Name='python.exe' OR Name='pythonw.exe'" _
    )

    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If

    For Each process In processes
        commandLine = LCase("" & process.CommandLine)
        If InStr(commandLine, "orchestrator\start_begonya.py") > 0 Then
            IsBegonyaOrchestratorRunning = True
            Exit For
        End If
    Next
    On Error GoTo 0
End Function

If IsBegonyaOrchestratorRunning() Then
    WScript.Quit 0
End If

Dim shell, command
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = PROJECT_DIR
command = "cmd.exe /d /c """ & BATCH_FILE & """ --watchdog"
shell.Run command, 0, False
