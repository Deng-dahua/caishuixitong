# ============================================================================
#  把 8001 服务注册为 Windows 任务计划（登录即启动 / 无窗口 / 崩溃自愈）
#
#  为什么需要它（2026-10-21 实测事故）
#  -----------------------------------
#  旧方案 = 启动文件夹 → autostart_server.bat → 以**可见窗口**启动 start8001.bat。
#  而 start8001.bat 的文件头自己写着：
#      Keep this window OPEN while using the app.
#      Closing the window (or Ctrl+C) stops the server.
#  实测：16:58 电脑重启 → 16:59:18 启动项确实拉起了进程 → 该实例**随后静默消失**
#  （日志里连 uvicorn 的 "Started server process" 都没有，stdout 未 flush 即被杀），
#  且**守护器一并死亡** ⇒ 用户看到"服务器进不去"。
#  根因是结构性的：**服务跑在可见控制台窗口里，窗口被关 = 全灭**。
#
#  本方案
#  ------
#  ① 触发器：登录时（AtLogOn）
#  ② 执行  ：pythonw.exe scripts\serve_supervisor.py
#            （pythonw = 无控制台版 Python ⇒ 没有任何窗口可被误关）
#  ③ 设置  ：崩溃自动重启、允电池运行、已在跑则不重复启动（IgnoreNew）
#            —— serve_supervisor.py 自带端口守卫，已有实例时直接退出，**不会双开**
#
#  用法（**需要管理员权限**：注册任务计划是系统级操作）
#  ----------------------------------------------------------
#    安装： powershell -ExecutionPolicy Bypass -File scripts\install_server_task.ps1
#    卸载： powershell -ExecutionPolicy Bypass -File scripts\install_server_task.ps1 -Uninstall
#    查看： powershell -ExecutionPolicy Bypass -File scripts\install_server_task.ps1 -Status
#
#  ★ 本脚本只注册任务计划，**不动**启动文件夹里的旧文件（见安装后提示）。
# ============================================================================

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

$TaskName = 'caishuixitong-server'
$Project  = Split-Path -Parent $PSScriptRoot
$PythonW  = Join-Path $Project '.venv\Scripts\pythonw.exe'
$Script   = Join-Path $Project 'scripts\serve_supervisor.py'
$StartupBat = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\caishuixitong-server.bat'

function Write-Head($t) {
    Write-Host ''
    Write-Host ('=' * 70)
    Write-Host "  $t"
    Write-Host ('=' * 70)
}

# ---------------------------------------------------------------- 状态查询
if ($Status) {
    Write-Head '任务计划状态'
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Write-Host "  任务名称 : $TaskName"
        Write-Host "  状态     : $($t.State)"
        $t.Actions | ForEach-Object { Write-Host "  执行     : $($_.Execute) $($_.Arguments)" }
        $t.Triggers | ForEach-Object { Write-Host "  触发器   : $($_.CimClass.CimClassName)" }
    } else {
        Write-Host '  （未注册）'
    }
    Write-Host ''
    Write-Host "  旧启动项 : $(if (Test-Path $StartupBat) { '仍存在（' + $StartupBat + '）' } else { '不存在' })"
    Write-Host "  8001 监听: $(if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) { '有' } else { '无' })"
    exit 0
}

# ---------------------------------------------------------------- 卸载
if ($Uninstall) {
    Write-Head "卸载任务计划：$TaskName"
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host '  ✓ 已删除任务计划'
    } else {
        Write-Host '  （任务计划本就不存在，无需删除）'
    }
    Write-Host ''
    Write-Host '  提示：如需一并停用旧方案，请手动删除：'
    Write-Host "    $StartupBat"
    exit 0
}

# ---------------------------------------------------------------- 安装
Write-Head "安装任务计划：$TaskName"

# 前置检查：文件必须真实存在（否则任务会静默失败）
$missing = @()
foreach ($p in @($PythonW, $Script)) {
    if (-not (Test-Path $p)) { $missing += $p }
}
if ($missing.Count -gt 0) {
    Write-Host '  ✘ 前置检查未通过，以下文件缺失：' -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "      $_" }
    exit 1
}
Write-Host '  ✓ 前置检查通过（pythonw.exe 与 serve_supervisor.py 均在）'

# 管理员权限检查（注册任务计划必须提权）
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host ''
    Write-Host '  ✘ 需要管理员权限（注册任务计划是系统级操作）。' -ForegroundColor Red
    Write-Host '     请右键「开始」→「终端(管理员)」或「PowerShell(管理员)」，再执行本脚本。'
    exit 1
}
Write-Host '  ✓ 已获得管理员权限'

# 动作：无控制台窗口运行守护器
$action = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument ('"' + $Script + '"') `
    -WorkingDirectory $Project

# 触发器：登录时启动（含开机后首次登录）
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# 设置：崩溃自愈 + 允许电池 + 不重复启动
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)      # 0 = 不限时（常驻服务不得被超时杀掉）

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited                            # 不需要最高权限，普通用户级即可

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'caishuixitong 8001 服务：登录即启动、无窗口、崩溃自愈（2026-10-21 建立）' `
    -Force | Out-Null

Write-Host '  ✓ 任务计划已注册'
Write-Host ''
Write-Host '  任务定义：'
Write-Host "    名称     : $TaskName"
Write-Host "    执行     : $PythonW"
Write-Host "    参数     : $Script"
Write-Host "    工作目录 : $Project"
Write-Host '    触发器   : 登录时'
Write-Host '    设置     : 崩溃自动重启 3 次 / 不限时 / 已在跑则不重复启动'

# 立即启动一次（若服务未在跑，可省去手动双击）
Write-Host ''
Write-Host '  正在启动服务（若已有实例在跑，守护器的端口守卫会直接退出，不会双开）…'
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 6
$listening = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host '  ✓ 8001 已在监听' -ForegroundColor Green
} else {
    Write-Host '  … 8001 暂未监听（服务可能仍在启动，请稍候几秒再试）' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '  ⚠ 旧方案仍在生效（启动文件夹）：'
Write-Host "      $StartupBat"
Write-Host '    它与本任务计划**不会冲突**（守护器有端口守卫，不会双开）。'
Write-Host '    若想彻底切到新方案，可删除上面那个 .bat（也可保留，双保险）。'
Write-Host ''
Write-Host '  完成。以后电脑重启/重新登录，服务会自动起来，且没有任何窗口可被误关。'