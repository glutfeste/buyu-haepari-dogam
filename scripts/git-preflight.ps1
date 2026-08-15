[CmdletBinding()]
param(
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-ExistingDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )

    $item = Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) {
        throw "디렉터리가 아니다: $LiteralPath"
    }
    return $item.FullName
}

function ConvertTo-NormalizedPath {
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )

    $item = Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
    return $item.FullName.TrimEnd([char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar))
}

function ConvertTo-NormalizedRemote {
    param(
        [Parameter(Mandatory)]
        [string]$Url
    )

    $normalized = $Url.Trim()
    if ($normalized -match '^git@github\.com:(?<path>.+)$') {
        $normalized = "https://github.com/$($Matches['path'])"
    }
    elseif ($normalized -match '^ssh://git@github\.com/(?<path>.+)$') {
        $normalized = "https://github.com/$($Matches['path'])"
    }

    $normalized = $normalized.TrimEnd('/')
    if ($normalized.EndsWith('.git', [StringComparison]::OrdinalIgnoreCase)) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }

    return $normalized.ToLowerInvariant()
}

$workspace = Resolve-ExistingDirectory (Join-Path -Path $PSScriptRoot -ChildPath '..')
$expectedOrigin = 'https://github.com/glutfeste/buyu-haepari-dogam'

function Invoke-GitText {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $stdout = @(& git -C $workspace @Arguments 2> $stderrPath)
        $exitCode = $LASTEXITCODE

        $stderrRaw = if (Test-Path -LiteralPath $stderrPath) {
            Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
        }
        else {
            $null
        }
        $stderr = if ($null -eq $stderrRaw) { '' } else { ([string]$stderrRaw).Trim() }

        $stdoutText = if ($null -eq $stdout) {
            ''
        }
        else {
            (($stdout | ForEach-Object { [string]$_ }) -join [Environment]::NewLine).Trim()
        }

        if ($exitCode -ne 0) {
            $details = @($stdoutText, $stderr) | Where-Object { -not [String]::IsNullOrWhiteSpace($_) }
            throw "Git 점검 명령이 실패했다: git $($Arguments -join ' ')`n$($details -join [Environment]::NewLine)"
        }

        return [string]$stdoutText
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$gitDirectory = Join-Path -Path $workspace -ChildPath '.git'
if (-not (Test-Path -LiteralPath $gitDirectory)) {
    throw "Git 메타데이터가 없다: $gitDirectory`n먼저 .\scripts\restore-git-metadata.ps1을 실행한다."
}

$repositoryRootText = [string](Invoke-GitText @('rev-parse', '--show-toplevel'))
if ([String]::IsNullOrWhiteSpace($repositoryRootText)) {
    throw 'Git 저장소 루트를 읽지 못했다.'
}

$repositoryRootLine = @($repositoryRootText -split "`r?`n") |
    ForEach-Object { $_.Trim() } |
    Where-Object { -not [String]::IsNullOrWhiteSpace($_) } |
    Select-Object -Last 1

$repositoryRoot = ConvertTo-NormalizedPath $repositoryRootLine
$normalizedWorkspace = ConvertTo-NormalizedPath $workspace
if (-not [String]::Equals($repositoryRoot, $normalizedWorkspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Git 저장소 루트가 작업 폴더와 다르다.`n작업 폴더: $normalizedWorkspace`n저장소 루트: $repositoryRoot"
}

$origin = [string](Invoke-GitText @('remote', 'get-url', 'origin'))
$normalizedOrigin = ConvertTo-NormalizedRemote $origin
$normalizedExpectedOrigin = ConvertTo-NormalizedRemote $expectedOrigin
if (-not [String]::Equals($normalizedOrigin, $normalizedExpectedOrigin, [StringComparison]::OrdinalIgnoreCase)) {
    throw "origin이 예상 저장소와 다르다.`n예상: $expectedOrigin`n현재: $origin"
}

$branch = [string](Invoke-GitText @('branch', '--show-current'))
if ($branch -ne 'main') {
    throw "현재 브랜치가 main이 아니다: $branch"
}

$userName = [string](Invoke-GitText @('config', '--get', 'user.name'))
$userEmail = [string](Invoke-GitText @('config', '--get', 'user.email'))
$userName = $userName.Trim()
$userEmail = $userEmail.Trim()
if ([String]::IsNullOrWhiteSpace($userName) -or [String]::IsNullOrWhiteSpace($userEmail)) {
    throw 'Git 커밋 작성자 설정이 없다. 복구 스크립트를 실행하거나 이 저장소에 user.name과 user.email을 설정한다.'
}

$head = [string](Invoke-GitText @('rev-parse', '--verify', 'HEAD'))
$statusText = [string](Invoke-GitText @('status', '--short'))

[PSCustomObject]@{
    Repository = $repositoryRoot
    Origin     = $origin
    Branch     = $branch
    User       = "$userName <$userEmail>"
    HEAD       = $head
    Worktree   = if ([String]::IsNullOrWhiteSpace($statusText)) { 'clean' } else { 'changes present' }
    Changes    = $statusText
}
