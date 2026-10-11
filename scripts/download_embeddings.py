"""Explicit opt-in download. Does not access or send study documents."""
import argparse
from pathlib import Path
from sentence_transformers import SentenceTransformer
parser = argparse.ArgumentParser()
parser.add_argument("--model", default="BAAI/bge-m3")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
destination = root / "data" / "models" / args.model.replace("/", "--")
if destination.exists():
    print("Model directory already exists:", destination)
else:
    model = SentenceTransformer(args.model, device="cpu", trust_remote_code=False)
    model.save(str(destination))
print("Set this in .env and restart; then reprocess existing documents:")
print("EMBEDDING_MODEL=" + destination.as_posix())
