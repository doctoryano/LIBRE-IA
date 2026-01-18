# Checklist del Operador — IA LIBRE 2026 (Despliegue & CI Soberano)

Propósito
- Convertir la configuración del `.env` y las operaciones técnicas en decisiones operativas reproducibles y auditables.
- Proveer valores recomendados según hardware (3090/4090, A100, H100) y por tipo de energía regional.

1) Preparación del Runner Self-Hosted
- Requisitos mínimos:
  - Docker Engine instalado y accesible por el usuario del runner.
  - NVIDIA drivers y NVIDIA Container Toolkit (nvidia-docker2) instalados para permitir `--gpus`.
  - Espacio en disco para modelos (depende del checkpoint; 7B ~ 10–20GB; Llama-70B >> 350GB).
  - Labels/Tags en el runner: agregar `self-hosted`, `gpu` y si es A100/H100 opcional `a100` o `h100`.
- Seguridad:
  - Limitar acceso al Docker daemon únicamente a usuarios de confianza.
  - No ejecutar runner en máquinas compartidas sin aislamiento (preferentemente VMs privadas).
  - Mantener el sistema operativo y drivers actualizados.

2) Variables .env (qué significan y valores recomendados)
- IJL_SECRET_KEY
  - Obligatorio: cadena larga, aleatoria. Ej.: generar con `openssl rand -hex 32`.
- REQUIRE_DOCKER
  - "yes" — el runner abortará si Docker no está presente.
- ADAPTER_RUNTIME
  - "vllm" en entornos con GPU y vllm instalado.
  - "ggml" para nodos CPU-only.
  - "auto" para autodetección.
- VLLM_MODEL_PATH
  - Ruta absoluta en el runner donde se alojan los modelos (ej. `/mnt/models/my-model`).
- SANDBOX_IMAGE
  - Nombre de la imagen sandbox; preferible usar `ia-libre/sandbox:latest` (construir localmente desde Dockerfile).
- ENERGY_MIX_KG_CO2_KWH
  - Grid intensity (kgCO2e/kWh). Valores recomendados:
    - Europa (media renovable): 0.20
    - Francia (alta nuclear): 0.06
    - Noruega/Iceland (renovable): 0.02
    - EEUU (media): 0.45
    - China (media): 0.70
    - Global average fallback: 0.40
  - Operador: establece el valor más fiel a la localización del datacenter o nodo doméstico.
- GPU_SAMPLE_INTERVAL
  - 0.25–1.0 seg. Más pequeño → mayor resolución y más overhead.
- SANDBOX_MEM_MB / SANDBOX_CPUS
  - Memoria mínima 128–256 MB por ejecución de task; CPUs 0.5–1.0.
  - Para nodos A100/H100 puedes aumentar para benchmarks más exigentes.

3) Recomendaciones por hardware
- RTX 3090 / 4090 (workstation):
  - ADAPTER_RUNTIME: vllm (si drivers y CUDA OK)
  - Use bf16 not always supported; prefer fp16 with vllm config if card lacks bf16
  - ENERGY_MIX: set to local value (home, coworking)
- A100 (DGX / cloud):
  - ADAPTER_RUNTIME: vllm
  - Prefer bf16, enable tensor parallelism (vllm flags)
  - Sanitize node isolation and quotas; use reserved GPUs for CI
- H100:
  - ADAPTER_RUNTIME: vllm
  - Use bf16 and optimized vLLM config for H100; consider multi-GPU tensor parallel
  - Ensure power capping policies if needed (datacenter)

4) Checklist pre-despliegue (antes de ejecutar CI)
- [ ] `.env` copiado de `.env.example` y editado con valores correctos.
- [ ] `docker/sandbox.Dockerfile` y `docker/vllm_pro.Dockerfile` revisados y aprobados por auditoría.
- [ ] Imagen sandbox construida y fingerprint registrada en `data/gpg-keys/authorized_keys.json` (opcional).
- [ ] Modelos descargados, hashes SHA256 calculados y registrados en `dataset_manifest.csv` o `models/manifest.json`.
- [ ] Runner etiquetado (`self-hosted`, `gpu`) y con acceso controlado.
- [ ] Prueba manual: ejecutar `scripts/ci_run_benchmark.sh` en modo local (no CI) y validar reportes.
- [ ] Validación legal de licencias de modelos y datasets.

5) Operación diaria / post-benchmark
- Recolectar reportes (artifact) y verificar:
  - `total_kwh`, `total_kg_co2`, `ttft_s`, `gen_time_s`, `tokens`
  - Ver logs de sandbox y vLLM (no contengan PII sin autorización)
- Si `kg_co2` por workload es alto, considerar:
  - quantización (AWQ/GPTQ)
  - uso de hardware más eficiente
  - re-agendar entrenamientos a ventanas con baja huella energética
- En caso de incidente (fuga PII, ejecución maliciosa):
  - Seguir `docs/data-removal-process.md` y `GOVERNANCE.md`
  - Notificar al Security Response Team y registrar en `docs/decisions/`

6) Auditoría periódica
- Cada mes: reconstruir sandbox image desde Dockerfile y verificar fingerprints.
- Cada sprint: ejecutar benchmark SOBERANA en runner controlado y publicar report resumido en `docs/decisions/` (sin PII).
- Mantener `data/filters/banned_keywords.txt` y `authorized_keys.json` en revisión por PR (Steering Committee).

7) Contactos y Escalada
- Security & PII: security@tu-dominio.example
- Mantenedores: maintainers@tu-dominio.example
