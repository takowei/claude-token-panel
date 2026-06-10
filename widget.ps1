# Claude Token Usage Widget - PowerShell WPF

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase

# ── Limits (anchored 2026-06-07: current week = 100%) ──────────────────────────
$H5_LIMIT = 1872102L     # 5-hour rolling limit
$WK_LIMIT = 3597011L     # weekly limit anchored at this week's actual usage (100%)

[xml]$xaml = @"
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Claude Token Usage"
    Width="290" Height="310"
    WindowStyle="None"
    AllowsTransparency="True"
    Background="Transparent"
    Topmost="True"
    ShowInTaskbar="False"
    ResizeMode="NoResize">
  <Border Background="#1a1a2e" CornerRadius="12" BorderBrush="#3a3a5e" BorderThickness="1">
    <Grid Margin="14,10,14,12">
      <Grid.RowDefinitions>
        <RowDefinition Height="22"/>
        <RowDefinition Height="*"/>
      </Grid.RowDefinitions>

      <!-- Title bar -->
      <Grid Grid.Row="0">
        <TextBlock Text="Claude Token Usage" Foreground="#e0e0e0" FontSize="11"
                   FontWeight="SemiBold" VerticalAlignment="Center"/>
        <Button x:Name="CloseBtn" Content="×" HorizontalAlignment="Right"
                VerticalAlignment="Center" Width="20" Height="20"
                Foreground="#888" Background="Transparent" BorderThickness="0"
                FontSize="14" Cursor="Hand" Padding="0"/>
      </Grid>

      <!-- Content -->
      <StackPanel Grid.Row="1" Margin="0,6,0,0">

        <!-- ── Last 5h ── -->
        <TextBlock Text="&#9201;  Last 5 Hours" Foreground="#9090b0"
                   FontSize="10" FontWeight="SemiBold" Margin="0,0,0,4"/>

        <!-- progress bar -->
        <Grid Height="6" Margin="0,0,0,4">
          <Rectangle Fill="#2a2a4a" RadiusX="3" RadiusY="3"/>
          <Rectangle x:Name="H5Bar" Fill="#4caf50" RadiusX="3" RadiusY="3"
                     HorizontalAlignment="Left" Width="0"/>
        </Grid>

        <Grid Margin="2,0,0,0">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Foreground="#9090b0" FontSize="9">Used</TextBlock>
            <TextBlock x:Name="H5Used" Foreground="#e0e0e0" FontSize="10"
                       FontFamily="Consolas">—</TextBlock>
          </StackPanel>
          <StackPanel Grid.Column="1" HorizontalAlignment="Right">
            <TextBlock Foreground="#9090b0" FontSize="9" HorizontalAlignment="Right">Remaining</TextBlock>
            <TextBlock x:Name="H5Remain" Foreground="#4caf50" FontSize="10"
                       FontFamily="Consolas" HorizontalAlignment="Right">—</TextBlock>
          </StackPanel>
        </Grid>
        <TextBlock x:Name="H5Pct" Foreground="#666688" FontSize="9"
                   Margin="2,2,0,0">—</TextBlock>

        <Separator Background="#2d2d50" Margin="0,8,0,8"/>

        <!-- ── This Week ── -->
        <TextBlock Text="&#128197;  This Week" Foreground="#9090b0"
                   FontSize="10" FontWeight="SemiBold" Margin="0,0,0,4"/>

        <Grid Height="6" Margin="0,0,0,4">
          <Rectangle Fill="#2a2a4a" RadiusX="3" RadiusY="3"/>
          <Rectangle x:Name="WkBar" Fill="#4caf50" RadiusX="3" RadiusY="3"
                     HorizontalAlignment="Left" Width="0"/>
        </Grid>

        <Grid Margin="2,0,0,0">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Foreground="#9090b0" FontSize="9">Used</TextBlock>
            <TextBlock x:Name="WkUsed" Foreground="#e0e0e0" FontSize="10"
                       FontFamily="Consolas">—</TextBlock>
          </StackPanel>
          <StackPanel Grid.Column="1" HorizontalAlignment="Right">
            <TextBlock Foreground="#9090b0" FontSize="9" HorizontalAlignment="Right">Remaining</TextBlock>
            <TextBlock x:Name="WkRemain" Foreground="#4caf50" FontSize="10"
                       FontFamily="Consolas" HorizontalAlignment="Right">—</TextBlock>
          </StackPanel>
        </Grid>
        <TextBlock x:Name="WkPct" Foreground="#666688" FontSize="9"
                   Margin="2,2,0,0">—</TextBlock>

        <Separator Background="#2d2d50" Margin="0,8,0,8"/>

        <!-- ── Reset countdown + refresh ── -->
        <Grid>
          <StackPanel>
            <TextBlock x:Name="H5ResetLabel" Foreground="#666688" FontSize="9">5h —</TextBlock>
            <TextBlock x:Name="ResetLabel" Foreground="#666688" FontSize="9"
                       Margin="0,1,0,0">Wk —</TextBlock>
            <TextBlock x:Name="UpdatedLabel" Foreground="#444466" FontSize="8"
                       Margin="0,1,0,0">Updated —</TextBlock>
          </StackPanel>
          <Button x:Name="RefreshBtn" Content="&#8635;" HorizontalAlignment="Right"
                  VerticalAlignment="Center" Width="22" Height="22"
                  Foreground="#666688" Background="Transparent" BorderThickness="0"
                  FontSize="14" Cursor="Hand" Padding="0"/>
        </Grid>

      </StackPanel>
    </Grid>
  </Border>
</Window>
"@

# ── Token reader ──────────────────────────────────────────────────────────────
function Get-TokenUsage {
    $candidatePaths = @(
        "\\wsl$\Ubuntu-22.04\home\tako\.claude\projects",
        "\\wsl$\Ubuntu\home\tako\.claude\projects",
        "\\wsl.localhost\Ubuntu-22.04\home\tako\.claude\projects",
        "\\wsl.localhost\Ubuntu\home\tako\.claude\projects"
    )
    $wslPath = $null
    foreach ($p in $candidatePaths) {
        if (Test-Path $p) { $wslPath = $p; break }
    }

    $r = @{ H5=0L; Wk=0L; H5OldestTs=[DateTime]::MaxValue; Error=$null }

    if (-not $wslPath) { $r.Error = "WSL path unavailable"; return $r }

    $nowUtc       = [DateTime]::UtcNow
    $fiveHoursAgo = $nowUtc.AddHours(-5)

    $dow          = [int]$nowUtc.DayOfWeek   # 0=Sun
    $daysFromMon  = if ($dow -eq 0) { 6 } else { $dow - 1 }
    $weekStart    = $nowUtc.Date.AddDays(-$daysFromMon).AddHours(3)  # Mon 03:00 UTC
    if ($nowUtc -lt $weekStart) { $weekStart = $weekStart.AddDays(-7) }

    try {
        $files = Get-ChildItem -Path $wslPath -Recurse -Filter "*.jsonl" -ErrorAction Stop
    } catch { $r.Error = "Cannot read: $_"; return $r }

    foreach ($f in $files) {
        try { $lines = [System.IO.File]::ReadAllLines($f.FullName) } catch { continue }
        foreach ($line in $lines) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $obj = $line | ConvertFrom-Json -ErrorAction Stop
                if ($obj.type -ne "assistant") { continue }
                $tsStr = $obj.timestamp; if (-not $tsStr) { continue }
                $ts = [DateTime]::Parse($tsStr, $null,
                      [System.Globalization.DateTimeStyles]::RoundtripKind)
                if ($ts.Kind -ne [DateTimeKind]::Utc) {
                    $ts = [DateTime]::SpecifyKind($ts, [DateTimeKind]::Utc)
                }
                $u = $obj.message.usage; if (-not $u) { continue }
                # cache_read excluded (too volatile); inp*1 + cc*1.25 + out*1
                $total = [long](
                    [long]($u.input_tokens) * 1.0 +
                    [long]($u.cache_creation_input_tokens) * 1.25 +
                    [long]($u.output_tokens) * 1.0
                )
                if ($ts -ge $fiveHoursAgo) {
                    $r.H5 += $total
                    if ($ts -lt $r.H5OldestTs) { $r.H5OldestTs = $ts }
                }
                if ($ts -ge $weekStart) { $r.Wk += $total }
            } catch { continue }
        }
    }
    return $r
}

# ── UI helpers ────────────────────────────────────────────────────────────────
function Format-Tokens([long]$n) {
    if ($n -ge 1000000) { return "{0:F1}M" -f ($n / 1e6) }
    if ($n -ge 1000)    { return "{0:F0}K" -f ($n / 1e3) }
    return "$n"
}

function Get-Color([double]$pct) {
    if ($pct -lt 0.90) { return "#4caf50" }   # green
    if ($pct -lt 1.0)  { return "#ff9800" }   # orange — 90% warning
    return "#f44336"                            # red — exceeded
}

function Set-Bar($barEl, [double]$pct) {
    $maxW   = 262   # inner width of the bar track
    $barEl.Width = [Math]::Max(0, [Math]::Min($maxW, $maxW * $pct))
    $barEl.Fill  = [System.Windows.Media.BrushConverter]::new().ConvertFromString(
                       (Get-Color $pct))
}

function Set-RemainColor($el, [double]$pct) {
    $el.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString(
                         (Get-Color $pct))
}

# ── Refresh ───────────────────────────────────────────────────────────────────
function Refresh-Display {
    $data = Get-TokenUsage

    if ($data.Error) {
        $window.FindName("H5Used").Text = $data.Error
        return
    }

    # 5h
    $h5Pct = if ($H5_LIMIT -gt 0) { $data.H5 / $H5_LIMIT } else { 0.0 }
    $h5Rem = $H5_LIMIT - $data.H5
    $window.FindName("H5Used").Text    = Format-Tokens $data.H5
    $window.FindName("H5Remain").Text  = Format-Tokens ([Math]::Max(0, $h5Rem))
    $window.FindName("H5Pct").Text     = "{0:P2} used" -f $h5Pct
    Set-Bar  ($window.FindName("H5Bar"))    $h5Pct
    Set-RemainColor ($window.FindName("H5Remain")) $h5Pct

    # Week
    $wkPct = if ($WK_LIMIT -gt 0) { $data.Wk / $WK_LIMIT } else { 0.0 }
    $wkRem = $WK_LIMIT - $data.Wk
    $window.FindName("WkUsed").Text    = Format-Tokens $data.Wk
    $window.FindName("WkRemain").Text  = Format-Tokens ([Math]::Max(0, $wkRem))
    $window.FindName("WkPct").Text     = "{0:P2} used" -f $wkPct
    Set-Bar  ($window.FindName("WkBar"))    $wkPct
    Set-RemainColor ($window.FindName("WkRemain")) $wkPct

    # 5h: countdown until oldest record in window rolls off
    $nowUtc = [DateTime]::UtcNow
    if ($data.H5OldestTs -lt [DateTime]::MaxValue) {
        $h5ResetAt = $data.H5OldestTs.AddHours(5)
        $h5Diff    = $h5ResetAt - $nowUtc
        if ($h5Diff.TotalSeconds -gt 0) {
            $window.FindName("H5ResetLabel").Text = "5h rolls off in {0}h {1}m" -f `
                [int]$h5Diff.TotalHours, $h5Diff.Minutes
        } else {
            $window.FindName("H5ResetLabel").Text = "5h window clearing..."
        }
    } else {
        $window.FindName("H5ResetLabel").Text = "5h — no recent usage"
    }

    # Weekly reset: next Monday 03:00 UTC (= 11:00 Taipei)
    $dow       = [int]$nowUtc.DayOfWeek
    $daysToMon = if ($dow -eq 1) { 7 } else { (8 - $dow) % 7 }
    $nextReset = $nowUtc.Date.AddDays($daysToMon).AddHours(3)
    if ($nextReset -le $nowUtc) { $nextReset = $nextReset.AddDays(7) }
    $diff      = $nextReset - $nowUtc
    $window.FindName("ResetLabel").Text = "Wk resets in {0}d {1}h {2}m" -f `
        [int]$diff.TotalDays, $diff.Hours, $diff.Minutes

    $taipeiNow = $nowUtc.AddHours(8)
    $window.FindName("UpdatedLabel").Text = "Updated " + $taipeiNow.ToString("HH:mm:ss")
}

# ── Bootstrap ─────────────────────────────────────────────────────────────────
$reader = [System.Xml.XmlNodeReader]::new($xaml)
$window = [Windows.Markup.XamlReader]::Load($reader)

$window.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.OriginalSource -is [System.Windows.Controls.Button]) { return }
    $window.DragMove()
})

$window.FindName("CloseBtn").Add_Click({ $window.Close() })
$window.FindName("RefreshBtn").Add_Click({ Refresh-Display })

$timer = [System.Windows.Threading.DispatcherTimer]::new()
$timer.Interval = [TimeSpan]::FromSeconds(60)
$timer.Add_Tick({ Refresh-Display })
$timer.Start()

Refresh-Display
$window.ShowDialog() | Out-Null
