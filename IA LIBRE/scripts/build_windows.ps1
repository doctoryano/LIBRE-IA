param([string]$entry="server.py",[string]$name="ia-libre-server")
Write-Host "Make sure virtualenv activated and pyinstaller installed"
$add = @("--add-data","web;web","--add-data","data;data","--add-data","app;app")
$addStr = $add -join " "
$cmd = "pyinstaller --onefile --noconsole --name $name $entry $addStr"
Write-Host $cmd
Invoke-Expression $cmd
Write-Host "Result: dist\$name.exe"