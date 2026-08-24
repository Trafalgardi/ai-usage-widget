' Запуск v2 виджета без окна консоли
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
sh.Run "pythonw """ & dir & "\widget_v2.py""", 0, False
