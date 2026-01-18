# Visión Blindada — Face Redaction (Operadores)

Objetivo
- Redactar rostros antes del captioning para proteger la privacidad y reducir sesgos.

Descargas recomendadas (face detector DNN)
- Modelo (Caffe): res10_300x300_ssd_iter_140000_fp16.caffemodel
- Prototxt: deploy.prototxt
Fuentes:
- https://github.com/opencv/opencv/tree/master/samples/dnn/face_detector (prototxt)
- https://github.com/opencv/opencv_3rdparty/tree/dnn_samples_face_detector_20170830 (caffemodel links)
Coloca ambos archivos en: data/models/face_detector/

Instalación rápida:
- pip install opencv-python-headless numpy

Configuración (.env):
- FACE_REDACT_ENABLE=yes
- FACE_REDACT_METHOD=blur
- FACE_REDACT_CONF=0.5

Recomendaciones:
- Método 'blur' es equilibrado; 'pixelate' más anónimo visualmente; 'blackbox' máximo anonimato pero detectabilidad de manipulación.
- Umbral 0.5–0.6 suele equilibrar detecciones y evitar falsos positivos.
- No almacenar imágenes: sistema procesa en memoria y descarta.

Pruebas:
- Ejecutar: python -c "from scripts.face_redact import redact_faces; open('in.jpg','rb') as f: out=redact_faces(f.read()); open('out.jpg','wb').write(out)"
- Verifica que las caras están redacted en out.jpg.

Auditoría:
- Mantén hashes SHA256 de modelos de detección en docs/decisions/ (no publicar modelos).
- Actualiza la lista de keywords y política de red-team para capturar fallos.