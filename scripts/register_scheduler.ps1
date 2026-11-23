$ErrorActionPreference = "Stop"

$TaskName = "GoyangAbleJobsDaily"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VbsPath = Join-Path $ScriptDir "run_daily_hidden.vbs"

if (-not (Test-Path $VbsPath)) {
    throw "run_daily_hidden.vbs 를 찾을 수 없습니다: $VbsPath"
}

Write-Host "=== Windows 작업 스케줄러 등록: $TaskName ===" -ForegroundColor Cyan
Write-Host "실행 파일: $VbsPath"

$Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$VbsPath`""

# 트리거 1: 로그인 시 2분 뒤 실행 (PC 켰을 때, 부팅 버벅임 방지 + 인터넷 연결 대기)
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$TriggerLogon.Delay = "PT2M"

# 트리거 2: 매일 오전 9시 (PC가 계속 켜져 있을 때도 하루 1회 실행)
$TriggerDaily = New-ScheduledTaskTrigger -Daily -At 9:00AM

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($TriggerLogon, $TriggerDaily) `
    -Settings $Settings `
    -Description "고양시·서울·경기·재택 장애인 채용공고 하루 1회 자동 수집 (OpenCode DeepSeek 4.1)" `
    -Force | Out-Null

Write-Host "✅ 등록 완료!" -ForegroundColor Green
Write-Host " - 컴퓨터 로그인 2분 후 및 매일 오전 9시에 자동 체크합니다."
Write-Host " - 하루에 PC를 여러 번 켜도 state/state.json 가드로 '하루 딱 1번'만 수집합니다."
Write-Host " - 수집 시작/완료 시 Windows 우측 하단 토스트 알림이 뜹니다."
Write-Host " - 해제하려면: powershell -ExecutionPolicy Bypass -File scripts\unregister_scheduler.ps1"
