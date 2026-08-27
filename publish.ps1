# HD-Icons 一键发布脚本
# 用法：把新图标放入 inbox/ 对应子文件夹后，双击 publish.bat（或运行本脚本）
# 可选参数：.\publish.ps1 -Message "自定义提交说明"

param([string]$Message = "")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 定位 git（git 不在 PATH 时使用常见安装路径）
$git = "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $fallback = "C:\Program Files\Git\cmd\git.exe"
    if (Test-Path $fallback) { $git = $fallback } else {
        Write-Host "[错误] 未找到 git，请安装 Git 或将其加入 PATH" -ForegroundColor Red
        exit 1
    }
}

# 检查 inbox 是否有新文件
$inboxStatus = & $git status --porcelain -- inbox
if (-not $inboxStatus) {
    Write-Host "inbox 中没有新图标，无需发布。" -ForegroundColor Yellow
    exit 0
}

# 从文件名自动生成提交说明
$names = @($inboxStatus | ForEach-Object {
    $_.Substring(3).Trim() -replace '^inbox/', ''
} | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_) -replace '-\d+$', '' } | Sort-Object -Unique)
$prefixes = ($names | Select-Object -First 8) -join ", "
if ($names.Count -gt 8) { $prefixes += " 等" }
$fileCount = ($inboxStatus | Measure-Object).Count
if (-not $Message) {
    $Message = "新增 $fileCount 个图标：$prefixes"
}

Write-Host "本次发布：$Message" -ForegroundColor Cyan
& $git add -A
& $git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 提交失败" -ForegroundColor Red
    exit 1
}
& $git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 推送失败，请检查网络或凭据" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "已推送到 GitHub，Actions 将自动完成压缩、入库、索引、README 与预览图更新。" -ForegroundColor Green
Write-Host "进度查看：https://github.com/xushier/HD-Icons/actions"
