# Run locally to enter your ngrok authtoken privately and open the test backend over HTTPS.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$ngrokExecutable = Join-Path $projectRoot '.local\tools\ngrok.exe'
if (!(Test-Path -LiteralPath $ngrokExecutable)) {
    $ngrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
    $storeAlias = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\ngrok.exe'
    if ($ngrokCommand) { $ngrokExecutable = $ngrokCommand.Source }
    elseif (Test-Path -LiteralPath $storeAlias) { $ngrokExecutable = $storeAlias }
    else {
        $storePackage = Get-AppxPackage '*ngrok*' | Select-Object -First 1
        if ($storePackage) {
            $storeExecutable = Get-ChildItem -LiteralPath $storePackage.InstallLocation -Filter ngrok.exe -Recurse | Select-Object -First 1
            if ($storeExecutable) { $ngrokExecutable = $storeExecutable.FullName }
        }
    }
}
$ngrokConfig = Join-Path $projectRoot '.local\ngrok.yml'
$ngrokLog = Join-Path $projectRoot '.local\ngrok-agent.log'
if (!(Test-Path -LiteralPath $ngrokExecutable)) { throw 'ngrok belum terpasang. Install ngrok melalui Microsoft Store, lalu jalankan script ini lagi.' }
$backend = Invoke-RestMethod 'http://127.0.0.1:8000/local-test/info' -TimeoutSec 5
if ($backend.mode -ne 'local-test') { throw 'Jalankan backend uji pada port 8000 terlebih dahulu.' }

if (!(Test-Path -LiteralPath $ngrokConfig)) {
    Write-Host 'Buka https://dashboard.ngrok.com/get-started/your-authtoken'
    Write-Host 'Salin authtoken akun Anda, lalu tempel di prompt tersembunyi berikut.'
    $secureToken = Read-Host 'Authtoken ngrok (tidak ditampilkan)' -AsSecureString
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $tokenValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer).Trim()
        if ($tokenValue -notmatch '^[A-Za-z0-9_\-]{20,}$') { throw 'Authtoken tidak sesuai format. Salin authtoken dari dashboard ngrok.' }
        $configContent = "version: '2'`nauthtoken: '$tokenValue'`n"
        [IO.File]::WriteAllText($ngrokConfig, $configContent, (New-Object Text.UTF8Encoding($false)))
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
        $tokenValue = $null
        $configContent = $null
        $secureToken.Dispose()
    }
}

function Get-SmartlockTunnel {
    try {
        $tunnels = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
        return $tunnels.tunnels | Where-Object { $_.proto -eq 'https' -and $_.config.addr -eq 'http://127.0.0.1:8000' } | Select-Object -First 1
    } catch { return $null }
}
$tunnel = Get-SmartlockTunnel
if (!$tunnel) {
    $agentProcess = Start-Process -FilePath $ngrokExecutable -ArgumentList @('http','http://127.0.0.1:8000','--config',('"' + $ngrokConfig + '"'),'--inspect=false','--log',('"' + $ngrokLog + '"'),'--log-format=json') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Milliseconds 800
        $tunnel = Get-SmartlockTunnel
        if ($tunnel) { break }
        $agentProcess.Refresh()
        if ($agentProcess.HasExited) { throw 'ngrok berhenti. Periksa .local\ngrok-agent.log untuk penyebabnya; jangan bagikan token konfigurasi.' }
    }
}
if (!$tunnel) { throw 'Alamat HTTPS belum tersedia. Periksa koneksi internet dan .local\ngrok-agent.log.' }
$dashboardUrl = $tunnel.public_url.TrimEnd('/') + '/dashboard'
[IO.File]::WriteAllText((Join-Path $projectRoot '.local\ngrok-dashboard-url.txt'), $dashboardUrl)
Write-Host ''
Write-Host 'Buka di browser HP:'
Write-Host $dashboardUrl
Write-Host 'Login lalu izinkan kamera dan lokasi. Komputer serta backend harus tetap menyala.'
