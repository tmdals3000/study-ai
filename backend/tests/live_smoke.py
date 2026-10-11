"""Opt-in real-provider smoke test using a synthetic PDF; never sends user documents."""
import json
import os
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["STUDY_DATA_DIR"] = str(ROOT / ".qa" / "live-data")
os.environ["APP_PASSWORD"] = ""
os.environ["EMBEDDING_MODEL"] = ""
import fitz
from fastapi.testclient import TestClient
from app.main import app

def wait(client, doc, kind):
    deadline = time.monotonic() + 900
    previous = None
    while time.monotonic() < deadline:
        value = client.get(f"/api/documents/{doc}/generations/{kind}").json()
        if value["progress"] != previous:
            print(kind, value["status"], flush=True); previous = value["progress"]
        if value["status"] == "done":
            return value
        if value["status"] in ("error", "cancelled"):
            raise RuntimeError(kind + ": " + str(value["error"]))
        time.sleep(1)
    raise TimeoutError(kind)

if __name__ == "__main__":
    pdf = fitz.open()
    pdf.new_page().insert_text((45, 60), "\n".join([
        "Introduction to the water cycle",
        "Evaporation changes liquid water into water vapor.",
        "Solar energy supplies the heat for evaporation.",
        "Condensation changes water vapor into liquid droplets.",
        "Clouds consist of tiny water droplets or ice crystals.",
        "Precipitation is water falling from clouds as rain, snow, sleet, or hail.",
        "Infiltration is the movement of water from the ground surface into soil.",
        "Runoff is water flowing over the land surface into streams and rivers.",
        "Transpiration is water vapor released by plants through their leaves.",
        "The water cycle moves water between the atmosphere, land, and oceans."
    ]), fontsize=11)
    report = {"provider": "configured real provider", "mocked": False}
    with TestClient(app) as client:
        result = client.post("/api/documents", files={"file": ("water-cycle.pdf", pdf.tobytes(), "application/pdf")})
        result.raise_for_status(); doc = result.json()["id"]; report["document_id"] = doc
        for kind in ("summary", "quiz", "cards"):
            response = client.post(f"/api/documents/{doc}/generate/{kind}", json={"count": 3, "force": True})
            response.raise_for_status()
            job = wait(client, doc, kind)
            report[kind] = job["data"]["stats"] if kind == "summary" else job["data"]
            print(kind, "DONE", json.dumps(report[kind], ensure_ascii=True), flush=True)
        questions = client.get(f"/api/documents/{doc}/questions").json()
        report["question_count"] = len(questions)
        if not questions:
            raise RuntimeError("No questions passed verification")
        response = client.post(f"/api/documents/{doc}/chat", json={"question": "What is evaporation?", "mode": "explain"})
        if "event: message" not in response.text:
            raise RuntimeError(response.text)
        messages = client.get(f"/api/documents/{doc}/messages").json()
        report["tutor_citations"] = len(messages[-1]["citations"])
        if not report["tutor_citations"]:
            raise RuntimeError("No tutor evidence")
        (ROOT / ".qa" / "live-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE SMOKE PASSED", flush=True)
