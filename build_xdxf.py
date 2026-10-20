#!/usr/bin/env python3
"""Convierte el DictFile de reader.dict (Wikcionario en español) a XDXF maquetado para PocketBook.

Maquetación de cada entrada:
    palabra  [pronunciación]
    sustantivo                       (categoría en cursiva)
    1. Mamíferos. Definición…        (marca de uso en cursiva)
       a) Sinónimos: …
    2. …
    Etimología: Del latín …          (en gris)

Uso: python3 build_xdxf.py src/dict-es-es.df salida.xdxf [--limit N] [--sample palabra,palabra]
"""
import html
import re
import sys
from html.parser import HTMLParser

LABEL = re.compile(r"^([A-ZÁÉÍÓÚÑ][^:.]{1,40}):\s+")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Body(HTMLParser):
    """Recorre el HTML de una entrada y produce líneas ya maquetadas en XDXF."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf = [], []
        self.depth = 0          # nivel de <ol>
        self.n = [0, 0]         # contador de acepciones y subacepciones
        self.in_p = self.p_bold = False
        self.p_has_text = False

    # texto con formato en línea
    def handle_starttag(self, tag, attrs):
        if tag == "ol":
            self.flush()
            self.depth += 1
            if self.depth == 1:
                self.n[0] = 0
            else:
                self.n[1] = 0
        elif tag == "li":
            self.flush()
            if self.depth <= 1:
                self.n[0] += 1
                self.buf.append(f"<b>{self.n[0]}.</b> ")
            else:
                self.n[1] += 1
                self.buf.append(f"\x00{'abcdefghijklmnopqrstuvwxyz'[(self.n[1] - 1) % 26]}) ")
        elif tag == "p":
            self.flush()
            self.in_p, self.p_bold, self.p_has_text = True, False, False
        elif tag == "b":
            if self.in_p and not self.p_has_text:
                self.p_bold = True
            self.buf.append("<b>")
        elif tag == "i":
            self.buf.append("<i>")
        elif tag == "br":
            self.flush()

    def handle_endtag(self, tag):
        if tag == "ol":
            self.flush()
            self.depth -= 1
        elif tag == "li":
            self.flush()
        elif tag == "p":
            self.flush(kind="pos" if self.p_bold else "etym")
            self.in_p = False
        elif tag in ("b", "i"):
            self.buf.append(f"</{tag}>")

    def handle_data(self, data):
        if data.strip():
            self.p_has_text = True
        self.buf.append(esc(data))

    def flush(self, kind=None):
        text = re.sub(r"[ \t\r\n]+", " ", "".join(self.buf)).strip(" ")
        self.buf = []
        if not text or text in ("<b></b>", "<i></i>"):
            return
        if kind == "pos":
            # "Sustantivo masculino" -> "sustantivo masculino" en cursiva, como en los diccionarios impresos
            plain = re.sub(r"</?b>", "", text)
            self.lines.append(f"<i>{plain[:1].lower() + plain[1:]}</i>")
        elif kind == "etym":
            self.lines.append(f'<c c="gray"><i>Etimología:</i> {text}</c>')
        else:
            # marca de uso al principio de la acepción: "Mamíferos: …" -> "Mamíferos. …" en cursiva
            m = re.match(r"^(<b>\d+\.</b> )(.*)$", text)
            if m:
                head, rest = m.groups()
                lm = LABEL.match(rest)
                if lm and "<" not in lm.group(1):
                    rest = f"<i>{lm.group(1)}.</i> " + rest[lm.end():]
                text = head + rest
            if text.startswith("\x00"):  # subacepción: sangrada y en gris
                text = f'<c c="gray">\u2003\u2003{text[1:]}</c>'
            self.lines.append(text)


def entries(path):
    word, pron, forms, body = None, None, [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("@ "):
                if word and body:
                    yield word, pron, forms, body
                word, pron, forms, body = line[2:].strip(), None, [], None
            elif line.startswith(": ") and word:
                pron = line[2:].strip()
            elif line.startswith("& ") and word:
                forms.append(line[2:].strip())
            elif line.startswith("<html>") and word:
                body = line[6:]
    if word and body:
        yield word, pron, forms, body


def article(word, pron, forms, body, headwords=frozenset()):
    p = Body()
    p.feed(html.unescape(body).replace("&nbsp;", " ").replace(" ", " "))
    p.flush()
    # el lector ya pone la palabra como título: aquí solo la pronunciación
    head = [f'<c c="gray">{esc(pron)}</c>'] if pron else []
    return f"<ar><k>{esc(word)}</k><def>" + "".join(to_html(l) for l in head + p.lines) + "</def></ar>\n", p.lines


# gris oscuro: en las pantallas a color (Kaleido) un gris medio se ve muy claro
GRAY = "#3c3c3c"


def to_html(line):
    """Una línea de la maquetación → bloque HTML (los PocketBook pintan HTML con el motor de Qt).

    pbdt descarta el texto que es solo espacios entre dos etiquetas ("</i> <b>ir"), así que el espacio
    se mete dentro de la etiqueta siguiente ("</i><b> ir") para que no se peguen las palabras."""
    return re.sub(r">[ \t]+<([a-z]+)([^>]*)>", r"><\1\2> ", _to_html(line))


def _to_html(line):
    sub = '<c c="gray">\u2003\u2003' in line
    line = line.replace('<c c="gray">\u2003\u2003', "").replace('<c c="gray">', f'<span style="color:{GRAY}">').replace("</c>", "</span>")
    if sub:
        return f'<div style="margin-left:1.4em;color:{GRAY}">{line.replace("</span>", "", 1) if line.endswith("</span>") else line}</div>'
    if line.startswith("<i>") and "</i>" in line and not line.startswith("<i>Etim"):
        return f'<div style="margin-top:6px;color:{GRAY}">{line}</div>'
    if line.startswith(f'<span style="color:{GRAY}"><i>Etimología'):
        return f'<div style="margin-top:6px">{line}</div>'
    return f"<div>{line}</div>"


def summary(lines):
    """Categoría y primera acepción, para las entradas de remisión."""
    pos = next((l for l in lines if l.startswith("<i>") and not l.startswith("<b>")), "")
    first = next((l for l in lines if l.startswith("<b>1.</b>")), "")
    first = re.sub(r"^<b>1\.</b> ", "", first)
    plain = re.sub(r"<[^>]+>", "", first)
    if len(plain) > 110:
        first = esc(plain[:107].rsplit(" ", 1)[0]) + "…"
    return pos, first


def pointer(form, targets):
    """Entrada corta para formas sin entrada propia: fuimos -> ser, perros -> perro."""
    body = []
    for word, (pos, first) in targets:
        body.append(f"<i>forma de</i> <b>{esc(word)}</b>" + (f"  {pos}" if pos else ""))
        if first:
            body.append(first)
    return f"<ar><k>{esc(form)}</k><def>" + "".join(to_html(l) for l in body) + "</def></ar>\n"


def main():
    src, out = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    sample = set(sys.argv[sys.argv.index("--sample") + 1].split(",")) if "--sample" in sys.argv else None
    headwords = frozenset(w for w, *_ in entries(src))
    forms_of = {}   # forma -> [palabras de las que es forma]
    n = 0
    with open(out, "w", encoding="utf-8") as o:
        o.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xdxf SYSTEM "xdxf_lousy.dtd">\n')
        o.write('<xdxf lang_from="es" lang_to="es" format="visual">\n')
        o.write("<full_name>Diccionario de español</full_name>\n")
        o.write("<description>Definiciones del Wikcionario en español (CC BY-SA 4.0), procesadas por reader.dict "
                "y maquetadas para PocketBook.</description>\n")
        for word, pron, forms, body in entries(src):
            if sample and word not in sample:
                continue
            text, lines = article(word, pron, forms, body)
            o.write(text)
            info = summary(lines)
            for f in forms:
                if f != word and f not in headwords:
                    forms_of.setdefault(f, []).append((word, info))
            n += 1
            if limit and n >= limit:
                break
        for f, targets in forms_of.items():
            o.write(pointer(f, targets[:3]))
        o.write("</xdxf>\n")
    print(f"{n} entradas + {len(forms_of)} formas -> {out}")


if __name__ == "__main__":
    main()
