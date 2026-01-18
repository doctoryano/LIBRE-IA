# IA LIBRE 2026 — Proyecto completo (v0.1)

Objetivo
- Plataforma abierta para entrenar, auditar y ejecutar una IA de asistencia de código bajo el "Protocolo IA LIBRE 2026".
- Prioriza: Transparencia, Soberanía, Privacidad Radical, No-armamento, Sostenibilidad.

Resumen de la entrega
- Pipeline de ingestión y limpieza (Gutenberg + CodeSearchNet ejemplo).
- Filtros de PII y detección de contenido bélico (lista editable en `data/filters/banned_keywords.txt`).
- Servidor web con UI (FastAPI + frontend estático), autenticación JWT y almacenamiento de conversaciones en SQLite.
- Adaptadores para inferencia: Echo (simulado), HF (Hugging Face), vLLM (GPU) y ggml/llama.cpp (CPU). Auto-selección según entorno.
- Scripts de gestión de claves GPG y verificación.
- Scripts para construcción del ejecutable Windows (PowerShell + .bat) y build Unix (bash).
- Tests y workflows CI.

Estructura principal
- server.py — backend FastAPI (endpoints: /api/register, /api/login, /api/chat (stream SSE), /api/conversations ...)
- app/ — auth, db y adaptadores
- web/ — frontend (login + chat)
- scripts/ — ingest, clean, gpg, build helpers
- data/ — filters, keys, logs
- tests/ — pytest tests
- .github/workflows/ci.yml — workflow de CI (smoke)

Rápido inicio (Linux / macOS / WSL)
1. Clona y entra:
   git clone <tu-repo>
   cd ia-libre-2026

2. Entorno Python:
   python -m venv .venv
   source .venv/bin/activate

3. Instala dependencias:
   pip install -r requirements.txt
   pip install -r web_requirements.txt

4. Inicializa la base de datos (se crea automáticamente al registrar el primer usuario).

5. Ejecuta servidor (modo desarrollo):
   uvicorn server:app --host 0.0.0.0 --port 8080 --reload

6. Abre UI:
   http://localhost:8080/

Autenticación
- Registro: POST /api/register { "username", "password" }
- Login: POST /api/login { "username", "password" } -> devuelve JWT
- Para /api/chat envía header: Authorization: Bearer <token>

Build ejecutable Windows (guía)
- En una máquina Windows 11:
  1. Instala Python 3.10+, Git y Visual Studio Build Tools (para compilación nativa si hace falta).
  2. Crea y activa entorno virtual:
     python -m venv .venv
     .venv\Scripts\activate
  3. Instala dependencias:
     pip install -r requirements.txt
     pip install -r web_requirements.txt
     pip install pyinstaller
  4. Ejecuta:
     .\scripts\build_windows.ps1
  5. Resultado: `dist\ia-libre-server.exe`. Lanza con `start_server.bat`.

Seguridad y gobernanza
- Utiliza `data/filters/banned_keywords.txt` para ampliar la política de no-armamento.
- Añade firmas GPG de fuentes a `data/gpg-keys/` y registra fingerprints en `data/gpg-keys/authorized_keys.json`.
- Todos los releases y reportes deben acompañarse de `dataset_manifest.csv`, `*.clean_report.json` y estimación CO2.

Notas operativas
- vLLM y ggml requieren dependencias y modelos externos; los adaptadores son esqueleto y deben apuntar a binarios/instalaciones existentes en cada host.
- Logging: por defecto se guarda sólo hash de prompts si ENABLE_LOGGING=1; nunca almacenamos texto plano con PII por defecto.
- Recomendación: correr `scripts/shadow_ingest.py` en tu runner autohosted para validar pipeline sin descargar datos externos.

Soporte
- Si quieres que genere un ZIP con todos estos archivos listos para descargar, dímelo.
- Para integración/commits, prefieres revisar localmente: "ya tengo los archivos" o pides que los formatee para un solo patch.

Licencia
- Código: Apache-2.0 (incluido en LICENSE)

Fecha: 2026-01-17