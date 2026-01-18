#!/usr/bin/env bash
set -e
ENTRY=${1:-server.py}
NAME=${2:-ia-libre-server}
echo "Building $ENTRY -> $NAME"
pyinstaller --onefile --name "$NAME" --add-data "web:web" --add-data "data:data" "$ENTRY"
echo "Done: dist/$NAME"