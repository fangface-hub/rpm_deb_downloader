param(
    [string]$PublisherCN,
    [string]$IdentityName = "Local.RpmDebDownloader",
    [string]$PublisherName = $env:USERNAME,
    [string]$CertPassword,
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot

try {
    if (-not $PublisherCN) {
        $PublisherCN = "CN=" + [guid]::NewGuid().ToString().ToUpper()
    } elseif ($PublisherCN -notmatch "^CN=") {
        $PublisherCN = "CN=$PublisherCN"
    }

    if (-not $CertPassword) {
        $CertPassword = -join ((65..90) + (97..122) + (48..57) |
            Get-Random -Count 32 |
            ForEach-Object { [char]$_ })
    }

    if (-not $SkipBuild) {
        powershell -ExecutionPolicy Bypass -File .\build_nuitka.ps1
    }

    $exePath = Join-Path $repoRoot "dist\RpmDebDownloader.exe"
    if (-not (Test-Path $exePath)) {
        throw "Missing artifact: $exePath"
    }

    $workDir = Join-Path $repoRoot "build\msix-local"
    $payloadDir = Join-Path $workDir "payload"
    $appDir = Join-Path $payloadDir "RpmDebDownloader"
    $msixPath = Join-Path $repoRoot "dist\RpmDebDownloader.msix"
    $pfxPath = Join-Path $repoRoot "dist\RpmDebDownloader.pfx"
    $cerPath = Join-Path $repoRoot "dist\RpmDebDownloader.cer"

    if (Test-Path $workDir) {
        Remove-Item $workDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null

    [xml]$manifest = Get-Content (Join-Path $repoRoot "AppxManifest.xml")
    $manifest.Package.Identity.Publisher = $PublisherCN
    $manifest.Package.Identity.Name = $IdentityName
    $manifest.Package.Properties.PublisherDisplayName = $PublisherName
    $manifest.Save((Join-Path $payloadDir "AppxManifest.xml"))

    Copy-Item $exePath (Join-Path $appDir "RpmDebDownloader.exe") -Force
    Copy-Item (Join-Path $repoRoot "Square150x150Logo.png") $payloadDir -Force
    Copy-Item (Join-Path $repoRoot "Square44x44Logo.png") $payloadDir -Force

    $kitsRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    $versions = Get-ChildItem $kitsRoot |
        Where-Object { $_.Name -match "^\d+\.\d+\.\d+\.\d+$" } |
        Sort-Object Name -Descending
    if (-not $versions) {
        throw "Windows SDK tools not found: $kitsRoot"
    }
    $latest = $versions[0].FullName
    $makeappx = Join-Path $latest "x64\makeappx.exe"
    $signtool = Join-Path $latest "x64\signtool.exe"

    & $makeappx pack /d $payloadDir /p $msixPath /o

    $certArgs = @{
        Type = "Custom"
        Subject = $PublisherCN
        KeyUsage = "DigitalSignature"
        FriendlyName = "RpmDebDownloader Local Test Certificate"
        CertStoreLocation = "Cert:\CurrentUser\My"
        TextExtension = @(
            "2.5.29.37={text}1.3.6.1.5.5.7.3.3",
            "2.5.29.19={text}"
        )
    }
    $cert = New-SelfSignedCertificate @certArgs

    $securePassword = ConvertTo-SecureString -String $CertPassword -AsPlainText -Force
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $securePassword | Out-Null
    Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

    & $signtool sign /fd SHA256 /a /f $pfxPath /p $CertPassword $msixPath

    if (Test-Path $pfxPath) {
        Remove-Item $pfxPath -Force
    }

    Write-Host "MSIX package: $msixPath"
    Write-Host "Certificate (public): $cerPath"
    Write-Host "Install cert (CurrentUser\\Root): Import-Certificate -FilePath '$cerPath' -CertStoreLocation Cert:\CurrentUser\Root"
    Write-Host "Install package: Add-AppxPackage -Path '$msixPath'"
}
finally {
    Pop-Location
}