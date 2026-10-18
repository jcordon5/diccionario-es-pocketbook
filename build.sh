#!/bin/sh
# Genera dist/diccionario-es.dic desde cero. Solo necesita Python 3 y Docker (o Go 1.25 si se prefiere).
set -eu
cd "$(dirname "$0")"
mkdir -p src dist tools

# 1. Wikcionario en español ya limpio por reader.dict (formato DictFile)
curl -fsSL -o src/dict-es-es.df.bz2 https://www.reader-dict.com/file/es/dict-es-es.df.bz2
bunzip2 -kf src/dict-es-es.df.bz2

# 2. Maquetación propia → XDXF con HTML
python3 build_xdxf.py src/dict-es-es.df dist/diccionario-es.xdxf

# 3. Reglas de ordenación y de formas del español para PocketBook (Markismus/LanguageFilesPocketbookConverter)
#    + nuestros metadatos (nombre e idiomas es → es, para que el lector lo clasifique como español)
[ -d tools/langfiles ] || git clone -q --depth 1 https://github.com/Markismus/LanguageFilesPocketbookConverter.git tools/langfiles
rm -rf build/meta-es && mkdir -p build/meta-es && cp tools/langfiles/spa/*.txt meta/metadata.json build/meta-es/

# 4. pbdt (código abierto) empaqueta el .dic con los metadatos de idioma (es → es)
[ -d tools/pbdt ] || git clone -q --depth 1 https://codeberg.org/datyoma/pbdt.git tools/pbdt
if command -v go >/dev/null 2>&1; then
  (cd tools/pbdt && go build -o pbdt ./main.go)
  ./tools/pbdt/pbdt convert dist/diccionario-es.xdxf dist/diccionario-es.dic --meta-dir build/meta-es
else
  docker run --rm -v "$PWD":/w -w /w/tools/pbdt golang:1.25 sh -c 'CGO_ENABLED=0 go build -o pbdt-linux ./main.go'
  docker run --rm -v "$PWD":/w -w /w debian:bookworm-slim \
    ./tools/pbdt/pbdt-linux convert dist/diccionario-es.xdxf dist/diccionario-es.dic --meta-dir build/meta-es
fi
ls -lh dist/diccionario-es.dic
