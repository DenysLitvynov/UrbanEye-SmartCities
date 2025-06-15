import os, requests
from transformers import pipeline

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
_classifier = pipeline("zero-shot-classification",
                       model="valhalla/distilbart-mnli-12-1", device="cpu")
_LABELS = ["vandalismo", "grafiti", "acto sospechoso", "daño intencional", "robo", "otro"]

def classify_and_alert(inc):
    # Obtener texto de diferentes campos posibles
    text = inc.get("Descripción adicional (ES)", "") or inc.get("Descripción adicional (EN)", "") or inc.get("Texto Extraído", "")
    if not text:
        inc.update({
            "security_label": "otro",
            "security_score": 0.0,
            "security_level": "bajo"
        })
        return inc

    # Palabras clave para diferentes niveles de seguridad
    high_security_keywords = [
        # Vandalismo
        "vandalismo", "vandalizado", "vandalizada", "destrozado", "destrozada", "roto", "rota", 
        "destruido", "destruida", "quemado", "quemada", "incendiado", "incendiada",
        # Robo
        "robo", "robado", "robada", "hurtado", "hurtada", "sustraído", "sustraída",
        # Daño intencional
        "intencional", "intencionado", "intencionada", "malicioso", "maliciosa",
        # Inglés
        "vandalism", "broken", "damaged", "destroyed", "stolen", "theft", "intentional",
        "malicious", "sabotage", "sabotaged", "burned", "burnt"
    ]

    medium_security_keywords = [
        # Daños
        "daño", "dañado", "dañada", "mal estado", "desperfecto", "desperfectos",
        "golpeado", "golpeada", "rayado", "rayada", "abollado", "abollada",
        # Problemas
        "problema", "fallo", "avería", "defecto", "defectos", "mal funcionamiento",
        # Inglés
        "damage", "poor condition", "defect", "defects", "malfunction",
        "scratched", "dented", "hit", "impact"
    ]

    # Contar coincidencias de palabras clave
    text_lower = text.lower()
    high_count = sum(1 for word in high_security_keywords if word in text_lower)
    medium_count = sum(1 for word in medium_security_keywords if word in text_lower)

    # Clasificación con el modelo
    try:
        context = f"This is a security incident description: {text}"
        out = _classifier(context, candidate_labels=_LABELS)
        label, score = out["labels"][0], out["scores"][0]
        
        # Ajustar el score basado en palabras clave
        if high_count > 0:
            score = min(1.0, score + 0.3)  # Aumentado de 0.2 a 0.3
        elif medium_count > 0:
            score = min(1.0, score + 0.2)  # Aumentado de 0.1 a 0.2
            
        # Determinar nivel de seguridad con umbrales más sensibles
        if score >= 0.7 or high_count >= 2:  # Bajado de 0.8 a 0.7
            level = "alto"
        elif score >= 0.5 or medium_count >= 2 or high_count == 1:  # Bajado de 0.6 a 0.5
            level = "medio"
        else:
            level = "bajo"

        inc.update({
            "security_label": label,
            "security_score": float(score),
            "security_level": level
        })

        # Enviar alerta si es necesario
        if level in ("medio", "alto") and SLACK_WEBHOOK:
            msg = (f"*🚨 Alerta {level.upper()}* (ID {inc.get('ID')})\n"
                   f"Tipo: {label}\n"
                   f"Descripción: {text}\n"
                   f"Ubicación: {inc.get('Ubicación')}\n"
                   f"Score: {score:.2f}\n"
                   f"Palabras clave detectadas: {high_count} alta, {medium_count} media")
            try:
                requests.post(SLACK_WEBHOOK, json={"text": msg})
            except: pass

    except Exception as e:
        # Fallback basado en palabras clave si el modelo falla
        if high_count >= 2:
            level = "alto"
            label = "vandalismo"
        elif high_count == 1 or medium_count >= 2:
            level = "medio"
            label = "daño intencional"
        else:
            level = "bajo"
            label = "otro"
            
        inc.update({
            "security_label": label,
            "security_score": 0.5 if level != "bajo" else 0.0,
            "security_level": level
        })

    return inc