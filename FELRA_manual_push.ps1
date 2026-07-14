param(
    [string]$ProjectPath = (Join-Path $PSScriptRoot "FELRA"),
    [string]$RemoteUrl = "https://github.com/kakon77777-commits/FELRA.git"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "找不到 Git。請先安裝 Git for Windows，並重新開啟 PowerShell。"
}

if (-not (Test-Path $ProjectPath)) {
    throw "找不到專案資料夾：$ProjectPath。請先解壓縮 FELRA_clean_source.zip。"
}

Set-Location $ProjectPath

if (-not (Test-Path ".git")) {
    git init
}

git branch -M main
git add .

$hasHead = $true
try {
    git rev-parse --verify HEAD *> $null
} catch {
    $hasHead = $false
}

if (-not $hasHead) {
    git commit -m "feat: initialize FELRA Python-first research workbench"
} else {
    $changes = git status --porcelain
    if ($changes) {
        git commit -m "chore: synchronize FELRA project"
    }
}

$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    git remote set-url origin $RemoteUrl
} else {
    git remote add origin $RemoteUrl
}

git push -u origin main

Write-Host "`nFELRA 已推送到 $RemoteUrl" -ForegroundColor Green
