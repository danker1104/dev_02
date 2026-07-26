param(
	[switch]$BackendOnly,
	[switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendRoot = Join-Path $projectRoot "web"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
	throw "python is not available on PATH."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
	throw "npm is not available on PATH."
}

$backendCommand = @(
	"Set-Location '$projectRoot'"
	"if (-not `$env:REPOSITORY_KIND) { `$env:REPOSITORY_KIND = 'inmemory' }"
	"if (-not `$env:OCR_API_KEY) { `$env:OCR_API_KEY = 'K88457281188957' }"
	"if (-not `$env:OCR_API_URL) { `$env:OCR_API_URL = 'https://ocr.space' }"
	"if (-not `$env:OCR_ENGINE) { `$env:OCR_ENGINE = '3' }"
	"if (-not `$env:OCR_LANGUAGE) { `$env:OCR_LANGUAGE = 'kor' }"
	"python -m uvicorn app.main:app --reload"
) -join "; "

$frontendCommand = @(
	"Set-Location '$frontendRoot'"
	"npm run dev"
) -join "; "

if (-not $FrontendOnly) {
	Start-Process -FilePath "pwsh" -WorkingDirectory $projectRoot -ArgumentList @(
		"-NoExit"
		"-Command"
		$backendCommand
	) | Out-Null
	Write-Host "Started backend: http://127.0.0.1:8000"
}

if (-not $BackendOnly) {
	Start-Process -FilePath "pwsh" -WorkingDirectory $frontendRoot -ArgumentList @(
		"-NoExit"
		"-Command"
		$frontendCommand
	) | Out-Null
	Write-Host "Started frontend: http://127.0.0.1:3000"
}

Write-Host "Done."
