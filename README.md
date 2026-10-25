# Entrevista Vertical

Convierte una entrevista o un pódcast grabado en **horizontal con cámara fija** en vídeos **verticales (1080×1920)** que encuadran a la persona que habla en cada momento. Listos para Instagram, TikTok o YouTube Shorts.

Todo funciona **en tu ordenador**: gratis, sin cuentas y sin subir tus vídeos a ningún sitio.

## Qué hace

1. **Transcribe** el audio palabra a palabra con [Whisper](https://github.com/openai/whisper).
2. **Reconoce las voces** con [SpeechBrain](https://speechbrain.github.io) (ECAPA) y decide quién habla cada segundo.
3. **Asocia cada voz a una cara**: marcas a las personas con un clic y la app comprueba qué cara se mueve cuando suena cada voz. Puedes escuchar una muestra de cada voz y corregirlo.
4. **Encuadra** a quien habla, con plano general cuando hablan a la vez o hay música, y sin cambios de plano bruscos (cada plano dura al menos 3 s).
5. **Divide** el vídeo en las partes que quieras, cortando en una pausa al final de una frase.
6. **Subtítulos** opcionales dibujados en el vídeo y siempre un `.srt` por parte.
7. **Música** opcional al inicio o al final, y **máster de audio** a −14 LUFS (el volumen que usan las redes).

## Instalación (Mac)

Necesitas [Homebrew](https://brew.sh). En la Terminal:

```bash
brew install ffmpeg python@3.11
git clone https://github.com/TU-USUARIO/entrevista-vertical.git
cd entrevista-vertical
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

En Windows o Linux: instala ffmpeg y Python 3.10 o posterior, y usa los mismos comandos (en Windows, `.venv\Scripts\pip`).

## Uso

```bash
.venv/bin/python app.py
```

Se abre `http://127.0.0.1:8765` en el navegador. Después:

1. Arrastra el vídeo.
2. Haz clic en la cara de cada persona y elige en cuántas partes quieres dividirlo.
3. **Analizar.** Tarda más o menos lo que dura el vídeo. La primera vez descarga los modelos: Whisper ~1,5 GB y ECAPA ~80 MB.
4. Revisa las voces y los cortes.
5. **Renderizar.** Los vídeos quedan en `proyectos/<id>/salida/`.

## Límites

- La **cámara debe estar fija** y las personas no deben cambiar de sitio.
- La fuente se recorta y se amplía unas 2 veces: con una grabación en 4K horizontal, los primeros planos quedan más nítidos.
- Hasta 6 personas.
- En un Mac sin ventilador (MacBook Air), un vídeo de 30 min calienta el equipo: es normal. La app limita los hilos para que no se caliente tanto.

## Licencias

El código tiene licencia MIT (ver `LICENSE`). Usa Whisper (MIT), SpeechBrain (Apache 2.0), ffmpeg (LGPL/GPL, se instala aparte) y las fuentes Anton y Rajdhani (SIL Open Font License), que se descargan de Google Fonts la primera vez que se dibujan subtítulos.
