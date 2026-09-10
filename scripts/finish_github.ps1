$ErrorActionPreference = "Continue"
$tok = (Get-Content "D:\AIWorkSpace\.githubtoken" -Raw).Trim()
$hdr = @{ Authorization = "Bearer $tok"; Accept = "application/vnd.github+json" }
$old = "SamXiaBing/cockpit-hmi-notes"
$newName = "samxiabing-open-context"
$desc = "SamXiaBing's open context - public writing corpus of a cockpit 3D HMI engineer: car paint rendering, scene materials, performance, stability, framework, localization, SR. Chinese deep-dives, CC BY-NC-ND 4.0."

# 1. push with retry
$pushed = $false
for ($i = 0; $i -lt 40; $i++) {
    git -C "D:\AIWorkSpace\articles-corpus" push 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "[$i] push OK"; $pushed = $true; break }
    Write-Host "[$i] push failed, retry in 120s"
    Start-Sleep -Seconds 120
}
if (-not $pushed) { Write-Host "FATAL: push failed after all retries"; exit 1 }

# 2. rename + EN description
for ($i = 0; $i -lt 20; $i++) {
    try {
        $body = @{ name = $newName; description = $desc } | ConvertTo-Json
        $r = Invoke-RestMethod -Method Patch -Uri "https://api.github.com/repos/$old" -Headers $hdr -ContentType "application/json" -Body $body
        Write-Host "renamed: $($r.html_url)"
        break
    } catch {
        Write-Host "[$i] rename failed: $($_.Exception.Message)"
        Start-Sleep -Seconds 120
    }
}

# 3. update remote, verify
git -C "D:\AIWorkSpace\articles-corpus" remote set-url origin "https://github.com/SamXiaBing/$newName.git"
git -C "D:\AIWorkSpace\articles-corpus" fetch origin 2>&1 | Out-Null
$tip = git -C "D:\AIWorkSpace\articles-corpus" log origin/main -1 --format="%h %s"
Write-Host "FINAL: remote=SamXiaBing/$newName tip=$tip"
