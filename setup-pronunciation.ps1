param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FfmpegTarget = Join-Path $Root "ffmpeg"
$EspeakTarget = Join-Path $Root "espeak-ng"

$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$EspeakUrl = "https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi"

function Download-File {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$OutFile
    )
    Write-Host "Descargando $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

$ffmpegReady = Test-Path (Join-Path $FfmpegTarget "bin\ffmpeg.exe")
$espeakReady =
    (Test-Path (Join-Path $EspeakTarget "libespeak-ng.dll")) -and
    (Test-Path (Join-Path $EspeakTarget "espeak-ng.exe")) -and
    (Test-Path (Join-Path $EspeakTarget "espeak-ng-data"))

if (-not $Force -and $ffmpegReady -and $espeakReady) {
    Write-Host "FFmpeg y eSpeak NG ya estan preparados en el proyecto."
    exit 0
}

$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("libreria-ingles-pronunciation-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Temp | Out-Null

try {
    if ($Force -or -not $ffmpegReady) {
        $ffmpegZip = Join-Path $Temp "ffmpeg.zip"
        $ffmpegExtract = Join-Path $Temp "ffmpeg"
        Download-File -Url $FfmpegUrl -OutFile $ffmpegZip
        Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force

        $ffmpegExe = Get-ChildItem $ffmpegExtract -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
        if (-not $ffmpegExe) {
            throw "No se encontro ffmpeg.exe dentro del paquete descargado."
        }

        $sourceBin = $ffmpegExe.Directory.FullName
        if (Test-Path $FfmpegTarget) {
            Remove-Item $FfmpegTarget -Recurse -Force
        }
        New-Item -ItemType Directory -Path (Join-Path $FfmpegTarget "bin") -Force | Out-Null
        Copy-Item (Join-Path $sourceBin "*") (Join-Path $FfmpegTarget "bin") -Recurse -Force
        Write-Host "FFmpeg listo en root\ffmpeg\bin."
    }

    if ($Force -or -not $espeakReady) {
        $espeakMsi = Join-Path $Temp "espeak-ng.msi"
        $espeakExtract = Join-Path $Temp "espeak"
        New-Item -ItemType Directory -Path $espeakExtract | Out-Null
        Download-File -Url $EspeakUrl -OutFile $espeakMsi

        Write-Host "Extrayendo eSpeak NG..."
        & msiexec.exe /a $espeakMsi /qn "TARGETDIR=$espeakExtract"
        if ($LASTEXITCODE -ne 0) {
            throw "msiexec fallo al extraer eSpeak NG (codigo $LASTEXITCODE)."
        }

        $espeakDll = Get-ChildItem $espeakExtract -Recurse -Filter "libespeak-ng.dll" -File | Select-Object -First 1
        if (-not $espeakDll) {
            throw "No se encontro libespeak-ng.dll dentro del MSI extraido."
        }

        $sourceEspeak = $espeakDll.Directory.FullName
        if (-not (Test-Path (Join-Path $sourceEspeak "espeak-ng.exe"))) {
            throw "No se encontro espeak-ng.exe junto a libespeak-ng.dll."
        }
        if (-not (Test-Path (Join-Path $sourceEspeak "espeak-ng-data"))) {
            throw "No se encontro espeak-ng-data junto a libespeak-ng.dll."
        }

        if (Test-Path $EspeakTarget) {
            Remove-Item $EspeakTarget -Recurse -Force
        }
        New-Item -ItemType Directory -Path $EspeakTarget -Force | Out-Null
        Copy-Item (Join-Path $sourceEspeak "*") $EspeakTarget -Recurse -Force
        Write-Host "eSpeak NG listo en root\espeak-ng."
    }

    Write-Host ""
    Write-Host "Dependencias de pronunciacion preparadas correctamente."
    Write-Host "FFmpeg:  $FfmpegTarget\bin\ffmpeg.exe"
    Write-Host "eSpeak:  $EspeakTarget\libespeak-ng.dll"
}
finally {
    if (Test-Path $Temp) {
        Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
