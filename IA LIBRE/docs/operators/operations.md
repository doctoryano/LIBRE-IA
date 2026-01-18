# Operaciones — instrucciones rápidas

- Preparar:
  - Edita dataset_manifest.csv y data/filters/banned_keywords.txt
  - Añade claves GPG en data/gpg-keys/ y authorized_keys.json (ver scripts/manage_gpg_keys.py)

- Probar shadow ingest:
  python scripts/shadow_ingest.py --manifest dataset_manifest.csv

- Fetch + ingest:
  python scripts/fetch_sources.py --manifest dataset_manifest.csv
  python pipeline_ingest.py --manifest dataset_manifest.csv --ids project_gutenberg code_search_net

- Ejecutar servidor:
  uvicorn server:app --host 0.0.0.0 --port 8080

- Construir exe (Windows):
  .venv\Scripts\activate
  pip install pyinstaller
  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1