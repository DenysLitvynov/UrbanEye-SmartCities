import os, requests
from transformers import pipeline

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
_classifier = pipeline("zero-shot-classification",
                       model="valhalla/distilbart-mnli-12-1", device=-1)
_LABELS = ["vandalismo", "grafiti", "acto sospechoso", "otro"]

def classify_and_alert(inc):
    text = inc.get("Descripcion","") or inc.get("Texto Extraido","")
    if not text:
        inc.update({"security_label":"otro",
                    "security_score":0.0,
                    "security_level":"bajo"})
        return inc

    out = _classifier(text, candidate_labels=_LABELS)
    label, score = out["labels"][0], out["scores"][0]
    level = "alto" if score>=0.9 else "medio" if score>=0.7 else "bajo"

    inc.update({
      "security_label": label,
      "security_score": float(score),
      "security_level": level
    })

    if level in ("medio","alto") and SLACK_WEBHOOK:
        msg = (f"*🚨 Alerta {level.upper()}* (ID {inc.get('ID')})\n"
               f"Tipo: {label}\nDescripción: {text}\n"
               f"Ubicación: {inc.get('Ubicación')}")
        try:
            requests.post(SLACK_WEBHOOK, json={"text": msg})
        except: pass

    return inc