# Suggested Obsidian Layout

Audience: human readers setting up their vault structure. This file is a usage/reference note, not an agent execution contract.

Daily briefs are grouped by month under `01_Daily/`. Weekly and monthly reports are auto-triggered by the daily pipeline.

```text
Research_Intel/
├── 00_Config/
├── 01_Daily/
│   ├── 2026-03/
│   │   ├── 2026_03_01_Daily.md
│   │   └── 2026_03_23_Daily.md
│   └── 2026-04/
│       └── 2026_04_01_Daily.md
├── 02_Deep_Dives/
├── 03_Weekly/
│   └── 2026-03-W13-academic-weekly.md
├── 04_Monthly/
│   └── 2026-03-academic-monthly.md
├── 05_Index/
└── 99_System/
```

Output paths:

- Daily: `01_Daily/<YYYY-MM>/YYYY_MM_DD_Daily.md`
- Weekly: `03_Weekly/YYYY-MM-WNN-academic-weekly.md` (auto-generated on Sundays)
- Monthly: `04_Monthly/YYYY-MM-academic-monthly.md` (auto-generated on last day of month)
- Optional future path: `02_Deep_Dives/YYYY/paper-<id>-summary.md`
- Optional future path: `02_Deep_Dives/YYYY/paper-<id>-repro.md`
