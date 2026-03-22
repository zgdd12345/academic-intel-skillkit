# macOS Scheduled Deployment (launchd)

Set up the daily pipeline to run automatically at 09:00 every day on macOS.

## Option 1: launchd (recommended for macOS)

### 1. Create the plist

```bash
cat > ~/Library/LaunchAgents/com.academic-intel.daily-brief.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.academic-intel.daily-brief</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/miniconda3/condabin/conda</string>
        <string>run</string>
        <string>-n</string>
        <string>crawer</string>
        <string>--no-capture-output</string>
        <string>python</string>
        <string>scripts/run_daily_pipeline.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/fsm/project/MyProject/academic-intel-skillkit</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/academic-intel-daily.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/academic-intel-daily.err</string>
</dict>
</plist>
PLIST
```

### 2. Load the job

```bash
launchctl load ~/Library/LaunchAgents/com.academic-intel.daily-brief.plist
```

### 3. Verify

```bash
launchctl list | grep academic-intel
```

### 4. Test run (without waiting for 9am)

```bash
launchctl start com.academic-intel.daily-brief
# Check output:
tail -f /tmp/academic-intel-daily.log
```

### Unload

```bash
launchctl unload ~/Library/LaunchAgents/com.academic-intel.daily-brief.plist
```

## Option 2: crontab

```bash
crontab -e
```

Add this line:

```cron
0 9 * * * cd /Users/fsm/project/MyProject/academic-intel-skillkit && /opt/miniconda3/condabin/conda run -n crawer --no-capture-output python scripts/run_daily_pipeline.py >> /tmp/academic-intel-daily.log 2>&1
```

## Notes

- Both methods require the machine to be awake at 09:00. launchd will run the job at next wake if the Mac was asleep at the scheduled time.
- Logs go to `/tmp/academic-intel-daily.log`. Rotate or redirect as needed.
- Ensure `config/research-topics.local.yaml` exists before the first run.
- For LLM enrichment, set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in your shell profile or add `EnvironmentVariables` to the plist.
