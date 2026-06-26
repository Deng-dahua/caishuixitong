# Automation: 重启财税系统

## 2026-06-27 01:10
- Killed all Python processes + freed ports 8000/8001
- Copied report-modules.js → rm.js, tax-doc-analysis.js → tda.js
- Fixed index.html cache refs (tda.js2026062701 → tda.js?v=2026062701, added rm.js?v=2026062701)
- Git commit 58fafd5 "auto restart", pushed to main
- Server started on port 8001 (PID 34296), listening
- HTTP check returned UnicodeDecodeError (app-level, server is up)
