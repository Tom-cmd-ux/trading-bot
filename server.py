import os
import threading
from flask import Flask, jsonify, request
import requests
import json
import re

app = Flask(__name__)

LATEST_TRADE = {"action": "NONE"}

SYSTEM_PROMPT = """Tu es un assistant de trading algorithmique expert sur l'or (XAUUSD). Réponds UNIQUEMENT au format JSON strict, sans markdown ni texte additionnel. Utilise des caractères standards :
{
    "status": "VALID",
    "direction": "BUY",
    "zone_attente": "Niveau",
    "declencheur": "Signal",
    "entree": 0.00,
    "stop_loss": 0.00,
    "cible_1": 0.00,
    "cible_2": 0.00,
    "risque_rendement": 0.0,
    "validation_macro": "OK"
}"""

def process_claude_async(ticker, price, message):
    global LATEST_TRADE
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": "claude-opus-5-5",
            "max_tokens": 600,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"Ticker: {ticker}, Prix: {price}, Msg: {message}"}]
        }

        # URL protégée par concaténation contre les crochets parasites
        url = "https://api.anthropic.com" + "/v1/messages"
        resp = requests.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            resp_data = resp.json()

            # Extraction propre du texte brut renvoyé par Claude
            raw_text = ""
            for block in resp_data.get("content", []):
                if block.get("type") == "text":
                    raw_text = block.get("text", "")
                    break

            # --- PRINT POUR AFFICHER LA RÉPONSE BRUTE DE CLAUDE DANS LES LOGS RENDER ---
            print("\n=================== [CLAUDE AI RESPONSE RAW] ===================")
            print(raw_text)
            print("=================================================================\n")

            # Nettoyage des balises Markdown
            cleaned_text = raw_text.strip()
            cleaned_text = re.sub(r'^```json\s*', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'^```\s*', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
            cleaned_text = cleaned_text.strip()

            trade_plan = None
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = cleaned_text[start_idx:end_idx+1]
                try:
                    # Correction pour les caractères unicode échappés
                    fixed_str = json_str.replace('\\\\u', '\\u')
                    trade_plan = json.loads(fixed_str)
                except Exception:
                    try:
                        # Nettoyage des sauts de ligne non échappés à l'intérieur du JSON
                        sanitized = re.sub(r'(?<!\\)\n', ' ', json_str)
                        sanitized = re.sub(r'(?<!\\)\r', ' ', sanitized)
                        sanitized = re.sub(r'\s+', ' ', sanitized)
                        trade_plan = json.loads(sanitized)
                    except Exception:
                        pass

            # Si le parsing échoue, on renvoie une ERREUR propre (plus de faux fallback à 2640)
            if not trade_plan:
                trade_plan = {
                    "status": "ERROR",
                    "message": "Impossible de parser la réponse de Claude",
                    "raw_message": raw_text
                }

            LATEST_TRADE = trade_plan

            # --- PRINT POUR AFFICHER LA DÉCISION FINALE PARSÉE DANS LES LOGS RENDER ---
            print("\n================ [CLAUDE AI DECISION PARSED] ================")
            print(json.dumps(LATEST_TRADE, indent=2, ensure_ascii=False))
            print("=============================================================\n")

        else:
            print(f"Erreur API Anthropic (Status {resp.status_code}) : {resp.text}")

    except Exception as e:
        print(f"Erreur arrière-plan Claude : {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json() or {}
        ticker = data.get("symbol") or data.get("ticker", "XAUUSD")
        price = data.get("price", 0.0)
        message = data.get("message", "Alerte")

        # Lancement de l'analyse Claude en arrière-plan
        threading.Thread(target=process_claude_async, args=(ticker, price, message)).start()

        # Réponse immédiate à TradingView (< 50ms) pour éviter le timeout
        return jsonify({"status": "SUCCESS", "message": "Alerte reçue et en cours de traitement"}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 400

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global LATEST_TRADE
    return jsonify(LATEST_TRADE), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
