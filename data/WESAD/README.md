# Dataset WESAD (Wearable Stress and Affect Detection)

## Descarga

Este sistema utiliza el dataset WESAD para simular señales fisiológicas. El dataset no se incluye en la entrega por su tamaño (~15 GB).

### Instrucciones de descarga

1. Acceder a la página oficial del dataset:
   https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detection

2. Descargar el archivo completo del dataset.

3. Descomprimir y colocar las carpetas de sujetos dentro de esta carpeta (data/WESAD/), de modo que la estructura quede:

```
data/WESAD/
├── S2/
│   ├── S2.pkl        ← archivo principal que usa el producer
│   ├── S2_quest.csv
│   └── ...
├── S3/
│   ├── S3.pkl
│   └── ...
└── ...
```

### Sujeto por defecto

El sistema usa por defecto el sujeto **S2** (configurable via variable de entorno SUBJECT_ID).
Solo es necesario descargar al menos la carpeta S2/ para que el sistema funcione.

## Referencia

Schmidt, P., Reiss, A., Duerichen, R., Marquardt, C., & Van Laerhoven, K. (2018).
*Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection.*
Proceedings of the 2018 ACM International Conference on Multimodal Interaction (ICMI '18).
