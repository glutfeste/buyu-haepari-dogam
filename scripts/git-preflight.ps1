[CmdletBinding()]
param(
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$expectedOrigin = 'https://github.com/glutfeste/buyu-haepari-dogam.git'

function Get-GitValue {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $result = & git -C $workspace @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $message = ($result | Out-String).Trim()
        throw "Git 점검 명령이 실패했다: git $($Arguments -join ' ')`n$message"
    }
    return (($result | Out-String).Trim())
}

$gitDirectory = Join-Path $workspace '.git'
if (-not (Test-Path -LiteralPath $gitDirectory)) {
    throw "Git 메타데이터가 없다: $gitDirectory`n먼저 .\scripts\restore-git-metadata.ps1을 실행한다."
}

$repositoryRoot = [IO.Path]::GetFullPath((Get-GitValue @('rev-parse', '--show-toplevel')))
if (-not [String]::Equals($repositoryRoot, $workspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Git 저장소 루트가 작업 폴더와 다르다.`n작업 폴더: $workspace`n저장소 루트: $repositoryRoot"
}

$origin = (Get-GitValue @('remote', 'get-url', 'origin')).TrimEnd('/')
if (-not [String]::Equals($origin, $expectedOrigin.TrimEnd('/'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "origin이 예상 저장소와 다르다.`n예상: $expectedOrigin`n현재: $origin"
}

$branch = Get-GitValue @('branch', '--show-current')
if ($branch -ne 'main') {
    throw "현재 브랜치가 main이 아니다: $branch"
}

$userName = (& git -C $workspace config --get user.name 2>$null | Out-String).Trim()
$userEmail = (& git -C $workspace config --get user.email 2>$null | Out-String).Trim()
if ([String]::IsNullOrWhiteSpace($userName) -or [String]::IsNullOrWhiteSpace($userEmail)) {
    throw "Git 커밋 작성자 설정이 없다. 복구 스크립트를 실행하거나 이 저장소에 user.name과 user.email을 설정한다."
}

$head = Get-GitValue @('rev-parse', '--verify', 'HEAD')
$statusResult = & git -C $workspace status --short 2>&1
$statusExitCode = $LASTEXITCODE
if ($statusExitCode -ne 0) {
    throw "Git 상태 확인이 실패했다: $($statusResult | Out-String)"
}

$statusText = ($statusResult | Out-String).Trim()
[PSCustomObject]@{
    Repository = $repositoryRoot
    Origin     = $origin
    Branch     = $branch
    User       = "$userName <$userEmail>"
    HEAD       = $head
    Worktree   = if ([String]::IsNullOrWhiteSpace($statusText)) { 'clean' } else { 'changes present' }
}
