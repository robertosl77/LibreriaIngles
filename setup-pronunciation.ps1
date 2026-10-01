param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FfmpegTarget = Join-Path $Root "ffmpeg"
$EspeakTarget = Join-Path $Root "espeak-ng"

$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$EspeakReleaseBase = "https://github.com/thewh1teagle/espeakng-loader/releases/download/v0.1.0"
$EspeakDataUrl = "$EspeakReleaseBase/espeak-ng-data.tar.gz"

$architecture = $env:PROCESSOR_ARCHITECTURE
if ($architecture -eq "ARM64") {
    $EspeakLibArchive = "espeak-ng-libs-windows-arm64.tar.gz"
}
else {
    $EspeakLibArchive = "espeak-ng-libs-windows-x86_64.tar.gz"
}
$EspeakLibUrl = "$EspeakReleaseBase/$EspeakLibArchive"

$ProjectPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (Test-Path $ProjectPython) {
    $PythonExe = $ProjectPython
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "No se encontro Python. Se esperaba backend\.venv\Scripts\python.exe o python en PATH."
    }
    $PythonExe = $pythonCommand.Source
}

function Download-File {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$OutFile
    )
    Write-Host "Descargando $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Expand-TarGz {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    # Evitamos tar.exe de Windows: en algunos equipos corporativos falla con
    # rutas extendidas (\\?\...) aun cuando la ruta real no sea demasiado larga.
    & $PythonExe -c "import sys, tarfile; a=tarfile.open(sys.argv[1], 'r:gz'); a.extractall(sys.argv[2]); a.close()" $Archive $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "Python no pudo extraer $Archive (codigo $LASTEXITCODE)."
    }
}

$ffmpegReady = Test-Path (Join-Path $FfmpegTarget "bin\ffmpeg.exe")
$espeakReady =
    (Test-Path (Join-Path $EspeakTarget "libespeak-ng.dll")) -and
    (Test-Path (Join-Path $EspeakTarget "espeak-ng-data"))

if (-not $Force -and $ffmpegReady -and $espeakReady) {
    Write-Host "FFmpeg y eSpeak NG ya estan preparados en el proyecto."
    exit 0
}

# Usamos una ruta temporal corta dentro del repo para evitar limitaciones de
# longitud/rutas extendidas de herramientas de Windows.
$Temp = Join-Path $Root ".pronunciation-tmp"
if (Test-Path $Temp) {
    Remove-Item $Temp -Recurse -Force
}
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
        $espeakLibs = Join-Path $Temp $EspeakLibArchive
        $espeakDataArchive = Join-Path $Temp "espeak-ng-data.tar.gz"
        $espeakExtract = Join-Path $Temp "espeak"
        New-Item -ItemType Directory -Path $espeakExtract | Out-Null

        Download-File -Url $EspeakLibUrl -OutFile $espeakLibs
        Download-File -Url $EspeakDataUrl -OutFile $espeakDataArchive

        Write-Host "Extrayendo eSpeak NG portable..."
        Expand-TarGz -Archive $espeakLibs -Destination $espeakExtract
        Expand-TarGz -Archive $espeakDataArchive -Destination $espeakExtract

        $espeakDll = Get-ChildItem $espeakExtract -Recurse -File |
            Where-Object { $_.Name -in @("libespeak-ng.dll", "espeak-ng.dll") } |
            Select-Object -First 1
        if (-not $espeakDll) {
            throw "No se encontro la DLL de eSpeak NG dentro del paquete portable."
        }

        $espeakData = Get-ChildItem $espeakExtract -Recurse -Directory -Filter "espeak-ng-data" |
            Select-Object -First 1
        if (-not $espeakData) {
            throw "No se encontro espeak-ng-data dentro del paquete portable."
        }

        if (Test-Path $EspeakTarget) {
            Remove-Item $EspeakTarget -Recurse -Force
        }
        New-Item -ItemType Directory -Path $EspeakTarget -Force | Out-Null

        Get-ChildItem $espeakDll.Directory.FullName -Filter "*.dll" -File |
            Copy-Item -Destination $EspeakTarget -Force
        Copy-Item $espeakDll.FullName (Join-Path $EspeakTarget "libespeak-ng.dll") -Force
        Copy-Item $espeakData.FullName (Join-Path $EspeakTarget "espeak-ng-data") -Recurse -Force

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
