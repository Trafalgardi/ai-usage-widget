' Start the v2 Control Center without a console window.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
venvPython = dir & "\.venv\Scripts\pythonw.exe"
If fso.FileExists(venvPython) Then
  sh.Run """" & venvPython & """ """ & dir & "\widget_v2.py""", 0, False
Else
  sh.Run "pyw -3.12 """ & dir & "\widget_v2.py""", 0, False
End If
