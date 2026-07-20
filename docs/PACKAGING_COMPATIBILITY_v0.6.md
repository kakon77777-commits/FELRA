# FELRA v0.6 Packaging Compatibility Revision

## Status

This is a packaging-only compatibility revision of FELRA v0.6.0.  
The Python package version remains `0.6.0`; no analytical behavior or public API is changed.

## Problem

Windows PowerShell `Expand-Archive` may decode non-ASCII ZIP member names inconsistently.
The affected historical path was:

```text
docs/GCPR-RWL-FELRA_技術白皮書_v1.0.md
```

## Resolution

The physical archive path is now:

```text
docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md
```

The document itself remains Traditional Chinese. The path migration is declared in:

```text
ARCHIVE_FILENAME_MAP.json
```

All distributed ZIP member paths are now restricted to ASCII-safe characters.

## Agent requirement

Use the corrected ASCII-safe source archive rather than the earlier v0.6 source archive.
During synchronization, read `ARCHIVE_FILENAME_MAP.json` and remove the legacy tracked path only when it exists.
