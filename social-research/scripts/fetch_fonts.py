#!/usr/bin/env python3
"""Fetch latin-subset woff2 from Google Fonts CSS2 (no fonttools/brotli needed).

Google already serves per-unicode-range subsets; we keep only the `latin` range
block and download its woff2. This reproduces every face the three skins bundle in
reference/styles/fonts/ (that directory is the source of truth; re-run to refresh).

Static families (IBM Plex Mono) yield one file per weight, named
  <Family>-<style>-w<weight>.woff2
Variable families (Fraunces, Newsreader, IBM Plex Sans, Fredoka, Outfit) return
ONE file covering their whole weight range; it is written as
  <Family>-<style>.woff2            (the dedicated variable instances), or, for the
  two editorial faces whose committed names pin a representative weight,
  <Family>-<style>-w<weight>.woff2  (declare a weight RANGE in the @font-face).
See fonts/README.md for the @font-face form. Confirm OFL before bundling.
"""
import re, sys, subprocess
from pathlib import Path
from urllib.parse import quote

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT.mkdir(parents=True, exist_ok=True)

# family -> (css2 axis spec, output-name template).
#   "{slug}-{style}-w{weight}.woff2"  keeps the weight in the name
#   "{slug}-{style}.woff2"            drops it (variable single-file instances)
SPECS = {
    # editorial (variable faces, committed names pin a representative weight)
    "Fraunces":      ("ital,wght@0,400;1,300",             "{slug}-{style}-w{weight}.woff2"),
    "Newsreader":    ("ital,wght@0,400;1,400",             "{slug}-{style}-w{weight}.woff2"),
    # editorial + dossier (static weights -> one file each)
    "IBM Plex Mono": ("wght@400;500;600",                  "{slug}-{style}-w{weight}.woff2"),
    # dossier (variable -> single file, weight dropped from name)
    "IBM Plex Sans": ("ital,wght@0,400;0,500;0,600;0,700", "{slug}-{style}.woff2"),
    # playful (variable -> single file, weight dropped from name)
    "Fredoka":       ("wght@400;500;600;700",              "{slug}-{style}.woff2"),
    "Outfit":        ("wght@400;500;600;700",              "{slug}-{style}.woff2"),
    "Space Mono":    ("ital,wght@0,400;0,700;1,400",       "{slug}-{style}-w{weight}.woff2"),
}

def curl(url):
    return subprocess.run(["curl", "-sS", "-A", UA, url], capture_output=True, text=True, check=True).stdout

def curl_bin(url, dest):
    subprocess.run(["curl", "-sS", "-A", UA, "-o", str(dest), url], check=True)

BLOCK = re.compile(r"/\*\s*latin\s*\*/\s*(@font-face\s*\{.*?\})", re.S)
FIELD = lambda name, css: re.search(rf"{name}:\s*([^;]+);", css).group(1).strip().strip("'\"")
URLRE = re.compile(r"url\((https://[^)]+\.woff2)\)")

manifest, seen = [], set()
for family, (axis, name_tpl) in SPECS.items():
    url = f"https://fonts.googleapis.com/css2?family={quote(family)}:{axis}&display=swap"
    css = curl(url)
    for block in BLOCK.findall(css):
        fam = FIELD("font-family", block)
        style = FIELD("font-style", block)
        weight = FIELD("font-weight", block).split()[0]
        woff = URLRE.search(block).group(1)
        fname = name_tpl.format(slug=fam.replace(" ", ""), style=style, weight=weight)
        if fname in seen:        # variable families repeat the same file per weight
            continue
        seen.add(fname)
        dest = OUT / fname
        curl_bin(woff, dest)
        manifest.append(fname)
        print(f"{fname:34s} {dest.stat().st_size:>7d}  ({style} {weight})")

print(f"\n{len(manifest)} file(s) written to {OUT}")
