[CmdletBinding()]
param(
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$expectedOrigin = 'https://github.com/glutfeste/buyu-haepari-dogam.git'
$targetGit = Join-Path $workspace '.git'

if (Test-Path -LiteralPath $targetGit) {
    throw "작업 폴더에 이미 Git 메타데이터가 있다: $targetGit"
}

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
$tempRepository = Join-Path $tempRoot ('buyu-haepari-git-recovery-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRepository -Force | Out-Null

try {
    $cloneOutput = & git clone --no-checkout $expectedOrigin $tempRepository 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "원격 저장소를 임시로 내려받지 못했다:`n$($cloneOutput | Out-String)"
    }

    $sourceGit = Join-Path $tempRepository '.git'
    if (-not (Test-Path -LiteralPath $sourceGit)) {
        throw "임시 clone에서 Git 메타데이터를 찾지 못했다: $sourceGit"
    }
    if (Test-Path -LiteralPath $targetGit) {
        throw "복구 중 작업 폴더에 Git 메타데이터가 새로 생겼다: $targetGit"
    }

    Copy-Item -LiteralPath $sourceGit -Destination $targetGit -Recurse -Force
    $resetOutput = & git -C $workspace reset --mixed HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "복구한 Git index를 구성하지 못했다:`n$($resetOutput | Out-String)"
    }

    $identity = & git -C $workspace log -1 --format='%an%x09%ae' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "복구한 저장소의 기존 커밋 작성자를 읽지 못했다:`n$($identity | Out-String)"
    }
    $identityParts = (($identity | Out-String).Trim()) -split "`t", 2
    if ($identityParts.Count -ne 2 -or [String]::IsNullOrWhiteSpace($identityParts[0]) -or [String]::IsNullOrWhiteSpace($identityParts[1])) {
        throw "복구한 저장소에 커밋 작성자 정보가 없다. user.name과 user.email을 직접 설정한다."
    }
    & git -C $workspace config --local user.name $identityParts[0]
    if ($LASTEXITCODE -ne 0) {
        throw "복구한 저장소에 user.name을 설정하지 못했다."
    }
    & git -C $workspace config --local user.email $identityParts[1]
    if ($LASTEXITCODE -ne 0) {
        throw "복구한 저장소에 user.email을 설정하지 못했다."
    }

    Write-Output "Git 메타데이터를 origin/main에서 복구했다. 기존 커밋의 작성자 정보를 이 저장소에 설정했다. 작업 파일은 덮어쓰지 않았다."
    & git -C $workspace remote -v
    & git -C $workspace status --short
}
finally {
    $resolvedTempRepository = [IO.Path]::GetFullPath($tempRepository)
    if ($resolvedTempRepository.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedTempRepository)) {
        Remove-Item -LiteralPath $resolvedTempRepository -Recurse -Force
    }
}
