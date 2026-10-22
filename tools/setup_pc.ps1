<#
  Set up this PC for The Fourth Sheet. Safe to run again any time.

  Easiest: double-click "Set up this PC.cmd" in OneDrive (Projects\The Fourth Sheet).
  Or in PowerShell:  powershell -ExecutionPolicy Bypass -File "Set up this PC.ps1"
  Add -OneDrive "C:\path\to\The Fourth Sheet" to pin this PC to a particular OneDrive folder (otherwise the one found is pinned).

  What it does, in order (anything already done is skipped):
    1. checks OneDrive has the project folder (Projects\The Fourth Sheet)
    2. installs Python 3.12, Git and Google Chrome if they're missing (winget)
    3. downloads the website project to %USERPROFILE%\thefourthsheet (or updates it if it's already there)
    4. switches on Python's UTF-8 mode for good
    2b. installs VS Code and Claude Code if they're missing
    5. runs tools\setup\setup_machine.py: Python packages, Azure command line, git leak guard, OneDrive media sync,
       and brings over your Mac set-up (VS Code extensions and settings, Claude settings, memory, conversations)
       (Azure sign-in is left for later unless you add -Azure: wait until the business Microsoft 365 account exists)
    6. checks it works: lists the reports, then tests every page in a real browser
    7. puts "Preview The Fourth Sheet" on the desktop and opens the site
  A log is kept at %USERPROFILE%\fourthsheet-setup.log. If anything fails, send that file.
#>
param(
    [string]$Folder = "$env:USERPROFILE\thefourthsheet",
    [string]$OneDrive = "",
    [switch]$Azure,
    [switch]$SkipSiteCheck
)

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/nnbooth/thefourthsheet.git"
$Log = "$env:USERPROFILE\fourthsheet-setup.log"
Start-Transcript -Path $Log -Append | Out-Null

function Say($m)  { Write-Host ""; Write-Host "== $m" -ForegroundColor Green }
function Ok($m)   { Write-Host "   ok  $m" -ForegroundColor Gray }
function Warn($m) { Write-Host "   !!  $m" -ForegroundColor Yellow }
function Has($c)  { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Add-UserPath($dir) {
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($user -split ";") -notcontains $dir) { [Environment]::SetEnvironmentVariable("Path", ($user.TrimEnd(";") + ";" + $dir), "User") }
    if (($env:Path -split ";") -notcontains $dir) { $env:Path += ";$dir" }
}
function Run-Py {
    # runs Python with its output (errors too) going into the log; PowerShell 5.1 leaves it out otherwise
    $ErrorActionPreference = "Continue"
    & py.exe @args 2>&1 | ForEach-Object { "$_" } | Out-Host
}
function Install($id, $name) {
    if (-not (Has "winget")) {
        throw "winget (the Windows package installer) isn't available. Install 'App Installer' from the Microsoft Store, then run this again."
    }
    Write-Host "   installing $name (a window may ask for permission) ..."
    winget install -e --id $id --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Refresh-Path
}

try {
    Write-Host "Setting up $env:COMPUTERNAME for The Fourth Sheet" -ForegroundColor Cyan

    # 1. OneDrive ---------------------------------------------------------------------------------
    Say "1. OneDrive"
    if ($OneDrive) {
        if (-not (Test-Path (Join-Path $OneDrive "Data"))) { throw "-OneDrive '$OneDrive' isn't the 'The Fourth Sheet' folder (no Data folder in it), or it hasn't synced yet." }
        $project = $OneDrive
    } else {
    $bases = @($env:OneDriveConsumer, $env:OneDriveCommercial, $env:OneDrive) + @(Get-ChildItem $env:USERPROFILE -Directory -Filter "OneDrive*" -ErrorAction SilentlyContinue | ForEach-Object FullName)
    $project = $bases | Where-Object { $_ -and (Test-Path (Join-Path $_ "Projects\The Fourth Sheet")) } | Select-Object -First 1
    if (-not $project) {
        throw "Can't find 'Projects\The Fourth Sheet' in OneDrive. Open OneDrive, sign in with your Microsoft account, let the folder sync, then run this again."
    }
    $project = Join-Path $project "Projects\The Fourth Sheet"
    }
    Ok "project folder: $project (this PC is pinned to it; change with -OneDrive)"
    foreach ($sub in "Data", "Data documentation", "Business", "Media\site media") {
        if (Test-Path (Join-Path $project $sub)) { Ok $sub } else { Warn "$sub not synced yet (it will be fetched when needed)" }
    }

    # 2. Python, Git, Chrome ------------------------------------------------------------------------
    Say "2. Python, Git and Chrome"
    $hasPython = (Has "py") -and ((& py -3 --version 2>$null) -match "Python 3\.(1[0-9])")
    if (-not $hasPython) { Install "Python.Python.3.12" "Python 3.12" }
    if (-not ((& py -3 --version 2>$null) -match "Python 3")) {
        throw "Python didn't install properly. Install Python 3.12 from python.org (tick 'Add python.exe to PATH'), then run this again."
    }
    Ok (& py -3 --version)
    if (-not (Has "git")) { Install "Git.Git" "Git" }
    if (-not (Has "git")) { throw "Git didn't install properly. Install it from git-scm.com, then run this again." }
    Ok (& git --version)
    $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $chrome) {
        try { Install "Google.Chrome" "Google Chrome" } catch { Warn "Chrome didn't install; the PDFs will use Playwright's own browser instead" }
    } else { Ok "Google Chrome" }

    # 2b. VS Code and Claude Code -----------------------------------------------------------------------
    Say "2b. VS Code and Claude Code"
    if (-not ((Has "code") -or (Test-Path "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd"))) { Install "Microsoft.VisualStudioCode" "VS Code" }
    Ok "VS Code"
    if (-not (Has "claude")) {
        Write-Host "   installing Claude Code (Anthropic's official installer) ..."
        try { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression; Refresh-Path }
        catch { Warn "Claude Code didn't install: see docs.claude.com (Claude Code > Set up). Everything else carries on." }
    }
    if (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") { Add-UserPath "$env:USERPROFILE\.local\bin" }
    if (Has "claude") { Ok "Claude Code" }

    # 3. The project ----------------------------------------------------------------------------------
    Say "3. The website project"
    if ($Folder -like "*OneDrive*") { Warn "The project shouldn't live inside OneDrive (git and OneDrive fight over files). Using $env:USERPROFILE\thefourthsheet instead."; $Folder = "$env:USERPROFILE\thefourthsheet" }
    if (Test-Path (Join-Path $Folder ".git")) {
        git -C $Folder checkout -q main
        git -C $Folder pull -q --ff-only origin main
        Ok "updated: $Folder"
    } else {
        git clone -q $Repo $Folder
        Ok "downloaded to $Folder"
    }
    git -C $Folder config user.name "Nathan Booth"
    Ok ("version: " + (git -C $Folder log -1 --format="%h %ad %s" --date=short))

    # 4. UTF-8 ----------------------------------------------------------------------------------------
    Say "4. Python UTF-8 mode"
    if ([Environment]::GetEnvironmentVariable("PYTHONUTF8", "User") -ne "1") { [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User") }
    $env:PYTHONUTF8 = "1"
    Ok "on (the tools write characters like the cent sign and arrows)"

    # 5. The project's own setup -----------------------------------------------------------------------
    Say "5. Packages, Azure command line, git leak guard, media, and your set-up from the Mac"
    Push-Location $Folder
    $pyArgs = @("tools\setup\setup_machine.py", "--onedrive", $project)
    if (-not $Azure) { $pyArgs += "--no-azure" }
    Run-Py @pyArgs
    if ($LASTEXITCODE -ne 0) { throw "tools\setup\setup_machine.py reported a problem (see above)." }

    # 6. Check it works --------------------------------------------------------------------------------
    Say "6. Checking it works"
    Run-Py tools\3_publish_site\report.py --list
    if ($LASTEXITCODE -ne 0) { throw "The report builder didn't run (see above)." }
    if (-not $SkipSiteCheck) {
        Write-Host "   testing every page and report in a real browser (a few minutes) ..."
        Run-Py tools\3_publish_site\tests\site_check.py
        if ($LASTEXITCODE -ne 0) { Warn "The site check found problems (listed above). Everything else is set up; send me the log." }
    }
    Pop-Location

    # 7. Desktop shortcut and preview ------------------------------------------------------------------
    Say "7. Desktop shortcut"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcut = Join-Path $desktop "Preview The Fourth Sheet.cmd"
    $lines = @("@echo off", "rem Starts the local preview of the website and opens it. Close this window to stop it.",
               "cd /d `"$Folder`"", "start `"`" http://127.0.0.1:8765/", "py tools\3_publish_site\serve.py")
    Set-Content -Path $shortcut -Value $lines -Encoding ASCII
    Ok "double-click 'Preview The Fourth Sheet' on the desktop any time"
    Start-Process -FilePath $shortcut

    Say "Done. This PC is ready."
    Write-Host "   Project:   $Folder"
    Write-Host "   Data:      $project"
    Write-Host "   Next:      the checklist in OneDrive, Business\Microsoft 365, Azure and Fabric plan.md"
    Write-Host "   Everyday:  cd $Folder   then   py tools\1_build_data\sample_data.py  /  py tools\3_publish_site\report.py --list"
    Write-Host "   Before you start work each day:  git -C $Folder pull"
    Write-Host "   Claude:    open VS Code on $Folder, sign in to Claude Code, and pick '4th Sheet buildout' from its history"
    Write-Host "   Switching back to the Mac later:  py tools\setup\machine_profile.py export   (then on the Mac: python3 tools/setup/setup_machine.py)"
    if (-not $Azure) { Write-Host "   Azure:     once the business Microsoft 365 account exists, run this again with -Azure (or: az login)" }
}
catch {
    Write-Host ""
    Write-Host "STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Nothing is broken: fix that one thing and run this again (it skips whatever is already done)."
    Write-Host "The full log is $Log"
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
