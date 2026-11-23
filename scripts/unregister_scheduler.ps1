$TaskName = "GoyangAbleJobsDaily"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ 작업 스케줄러($TaskName)가 삭제되었습니다." -ForegroundColor Green
} else {
    Write-Host "등록된 작업($TaskName)이 없습니다." -ForegroundColor Yellow
}
