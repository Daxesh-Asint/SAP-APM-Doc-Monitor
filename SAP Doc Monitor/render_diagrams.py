"""Render Mermaid .mmd files to PNG images using kroki.io API."""
import json
import urllib.request
import os
import sys

DIAGRAMS = {
    "pipeline": "docs/mermaid/pipeline.mmd",
    "architecture": "docs/mermaid/architecture.mmd",
    "snapshot_lifecycle": "docs/mermaid/snapshot_lifecycle.mmd",
    "comparison_engine": "docs/mermaid/comparison_engine.mmd",
}

OUTPUT_DIR = "docs/images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

for name, filepath in DIAGRAMS.items():
    print(f"Reading {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        mmd_content = f.read()

    output_path = os.path.join(OUTPUT_DIR, f"{name}.png")
    url = "https://kroki.io/mermaid/png"

    payload = json.dumps({"diagram_source": mmd_content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/png",
        },
        method="POST",
    )

    print(f"Rendering {name} via kroki.io...")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(output_path, "wb") as out:
                out.write(resp.read())
        size = os.path.getsize(output_path)
        print(f"  OK: {output_path} ({size:,} bytes)")
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr)

print("\nDone!")
