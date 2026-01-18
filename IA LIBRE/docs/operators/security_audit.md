```markdown
# Auditoría de Seguridad del Sandbox Docker — IA LIBRE 2026

Objetivo
- Proporcionar una guía operativa para auditar y verificar que el entorno sandbox utilizado para ejecutar código generado por la IA es seguro, aislado y cumple las políticas de `GOVERNANCE.md` y `RUP.md`.

Resumen de requisitos (obligatorios)
1. Docker obligatorio: el runner debe disponer de Docker CLI y daemon. Si Docker no está presente, las pruebas de ejecución deben abortar.
2. Imagen sandbox controlada:
   - Nombre por defecto: `ia-libre/sandbox:latest`
   - Construir desde `docker/sandbox.Dockerfile` o proveer binario firmado.
   - Imagen firmada (opcional): mantener firmas y fingerprints GPG para la imagen si se publica.
3. Runtime de contenedores con restricciones:
   - `--network none`
   - `--cap-drop ALL`
   - `--security-opt no-new-privileges`
   - `--read-only` filesystem (montar sólo un volumen temporal como `/work`)
   - `--tmpfs /tmp:rw,size=64m`
   - `--pids-limit 64`
   - `--user 9999:9999` (usuario sin privilegios)
   - `--memory` y `--cpus` limits
   - `--rm` para eliminar contenedor al finalizar
4. Montaje controlado:
   - El directorio montado debería ser un tmpdir efímero creado por el runner.
   - Evitar montar directorios sensibles desde el host.
5. No persistencia por defecto:
   - Resultados y logs deben devolver al controlador y luego eliminarse del host si contienen metadatos sensibles.
6. Registro y trazabilidad:
   - Cada ejecución debe crear un `reports/` con hash del prompt, duración, y resumen del resultado (no almacenar prompt en texto si contiene PII).
   - Mantener un registro de imágenes y fingerprints en `docs/decisions/`.

Checklist de auditoría (pasos)
- Verificar la existencia de la imagen:
  docker image inspect ia-libre/sandbox:latest
- Inspeccionar Dockerfile y reproducir la imagen localmente:
  docker build -f docker/sandbox.Dockerfile -t ia-libre/sandbox:latest docker/
- Verificar que la imagen crea usuario sin privilegios (uid 9999):
  docker run --rm ia-libre/sandbox:latest id
- Revisar comandos de ejecución del runner:
  - Confirmar flags de seguridad enumerados arriba en scripts/sandbox_runner.py
- Revisar logs de ejecución y `reports/` para detectar anomalías
- Validar que el runner no tiene acceso a la red (ejecutar contenedor con network none y comprobar que `curl` falla dentro)

Buenas prácticas adicionales
- Ejecutar sandbox en nodos dedicados (no mezclar con runners de CI que gestionen secretos).
- Limitar acceso al Docker daemon (no dar sudo a usuarios no fiables).
- Actualizar y parchear la imagen base regularmente.
- Considerar uso de mecanismos de aislamiento más fuertes (gVisor, Kata Containers, Firecracker) si la amenaza lo justifica (ver `docs/operators/advanced_isolation.md` para recomendaciones).

Nota final
- Ninguna solución es 100% infalible. La combinación de: imagen auditable + flags de Docker restrictivos + políticas de acceso al daemon + revisión humana de reports conforma un enfoque robusto y auditable por la comunidad IA LIBRE 2026.
```