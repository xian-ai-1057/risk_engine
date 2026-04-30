# risk_analysis.exe smoke test (Windows/PowerShell).
#
# 用法:
#   .\scripts\smoke_test.ps1 -Exe .\dist\risk_analysis.exe -Sample .\build\sample
#
# Sample 目錄必須包含：
#   indicators_config.json, risk_user_prompt.txt,
#   narrative_user_prompt.txt, f1.html..f4.html
param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(Mandatory=$true)][string]$Sample,
    [string]$Industry = "7大指標"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Exe))   { throw "exe 不存在: $Exe" }
if (-not (Test-Path $Sample)) { throw "sample 目錄不存在: $Sample" }

$exeDir = Split-Path -Parent (Resolve-Path $Exe)
foreach ($f in @(
    "indicators_config.json","risk_user_prompt.txt",
    "narrative_user_prompt.txt","tag_table.csv"
)) {
    $src = Join-Path $Sample $f
    if (Test-Path $src) { Copy-Item $src $exeDir -Force }
}

$html = @()
foreach ($n in 1..4) {
    $p = Join-Path $Sample "f$n.html"
    if (-not (Test-Path $p)) { throw "找不到 $p" }
    $html += $p
}

# 1. 單次呼叫
Write-Host "== 測試 1: 單次呼叫契約 =="
$out = & $Exe @html "--industry" $Industry "--request-id" "smoke-1" "--stdout"
$obj = $out | ConvertFrom-Json
if ($obj.schema_version -ne "1.0") { throw "schema_version 不是 1.0: $($obj.schema_version)" }
if (-not $obj.risk_prompt)         { throw "risk_prompt 為空" }
if (-not $obj.narrative_prompt)    { throw "narrative_prompt 為空" }
if ($obj.risk_prompt -match '\{\{risk_results_\d\}\}') {
    throw "risk_prompt 殘留未替換 placeholder"
}
Write-Host "[OK] 契約欄位齊備"

# 2. INVALID_ARGS
Write-Host "== 測試 2: INVALID_ARGS =="
$err = & $Exe @html "--request-id" "smoke-2" "--stdout" 2>$null
$errObj = $err | ConvertFrom-Json
if ($errObj.error_code -ne "INVALID_ARGS") {
    throw "期待 INVALID_ARGS 實際 $($errObj.error_code)"
}
Write-Host "[OK] error_code=INVALID_ARGS"

# 3. 併發 5 次
Write-Host "== 測試 3: 併發 5 次 =="
$jobs = @()
$tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ([guid]::NewGuid()))
foreach ($i in 1..5) {
    $jobs += Start-Job -ArgumentList $Exe,$html,$Industry,$i,$tmp.FullName -ScriptBlock {
        param($Exe,$html,$Industry,$i,$tmp)
        & $Exe @html "--industry" $Industry "--request-id" "smoke-c$i" "--stdout" |
            Set-Content (Join-Path $tmp "out_$i.json") -Encoding utf8
    }
}
$jobs | Wait-Job | Out-Null
foreach ($i in 1..5) {
    $obj = (Get-Content (Join-Path $tmp "out_$i.json")) | ConvertFrom-Json
    if ($obj.request_id -ne "smoke-c$i") {
        throw "第 $i 份 request_id 不一致: $($obj.request_id)"
    }
}
Write-Host "[OK] 5 份併發各自獨立"

Write-Host "OK"
