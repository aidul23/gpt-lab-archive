#!/usr/bin/env bash
# Backup SQLite DB and member photo uploads into backups/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$ROOT/backups/backup-$STAMP"

mkdir -p "$DEST/static/uploads"
cp "$ROOT/database/lab_publications.db" "$DEST/lab_publications.db"
if [[ -d "$ROOT/static/uploads/members" ]]; then
  cp -R "$ROOT/static/uploads/members" "$DEST/static/uploads/"
fi

echo "Backup written to $DEST"
du -sh "$DEST"
