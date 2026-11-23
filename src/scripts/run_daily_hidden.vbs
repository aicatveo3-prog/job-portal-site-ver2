Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
srcDir = fso.GetParentFolderName(scriptDir)
rootDir = fso.GetParentFolderName(srcDir)
cmd = "cmd /c cd /d """ & rootDir & """ && set PYTHONDONTWRITEBYTECODE=1 && python src\scripts\run_daily.py"
' 0 = 창 숨김 (까만 콘솔 창 안 뜸), False = 비동기 실행
WshShell.Run cmd, 0, False
