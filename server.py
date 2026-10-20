import os
import threading
from flask import Flask, jsonify, request
import requests
import json
import re

app = Flask(__name__)

LATEST_TRADE = {"status": "INVALID", "action": "NONE"}

# --- SYSTEM PROMPT ULTRA-SÉLECTIF ET CONTEXTUEL ---
SYSTEM_PROMPT = """Tu es un gestionnaire de risque et analyste senior intransigeant sur XAUUSD.
Ta mission est de filtrer drastiquement les alertes TradingView. Ton rôle par défaut est de REJETER le trade sauf si les conditions techniques et le ratio de risque sont exceptionnels.

Analyse l'alerte et renvoie UNIQUEMENT un JSON strict avec la structure suivante (sans markdown ni texte additionnel) :
{
    "status": "INVALID",                 // "VALID" uniquement si le setup est parfait, sinon "INVALID" par défaut
    "direction": "BUY",                  // "BUY" ou "SELL"
    "type_ordre": "MARKET",              // "MARKET" ou "LIMIT"
    "zone_attente": "Niveau precis",     // Le niveau de prix vise ou "Au marche"
    "declencheur": "Explication rapide",
    "entree": 0.00,                      // Prix exact d'entree
    "stop_loss": 0.00,
    "cible_1": 0.00,
    "cible_2": 0.00,
    "risque_rendement": 0.0,
    "validation_macro": "REJECT"         // "OK" ou "REJECT"
}

REGLES D'ANALYSE STRICTES :
1. Si le signal est ambigu, contre-tendance, ou que le ratio risque/rendement est inférieur à 1.5 : mets IMPÉRATIVEMENT status = "INVALID".
2. Ne valide un trade qu'en cas d'alignement clair des indicateurs fournis dans le payload.
3. En cas de doute, la sécurité prime : refuse le trade."""

def process_claude_async(ticker, price, message, raw_payload):
    global LATEST_TRADE
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # --- ENRICHISSEMENT DES DONNÉES ENVOYÉES À CLAUDE ---
        # On transmet l'intégralité du payload TradingView (indicateurs, prix, message, etc.)
        payload_str = json.dumps(raw_payload, ensure_ascii=False)
        user_prompt = f"Ticker: {ticker}, Prix actuel: {price}\nPayload technique complet de TradingView: {payload_str}"

        payload = {
            "model": "claude-opus-5-5",
            "max_tokens": 600,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}]
        }

        url = "https://api.anthropic.com" + "/v1/messages"
        resp = requests.post(url, headers=headers, json=payload)

        trade_plan = None

        if resp.status_code == 200:
            resp_data = resp.json()

            raw_text = ""
            for block in resp_data.get("content", []):
                if block.get("type") == "text":
                    raw_text = block.get("text", "")
                    break

            print("\n=================== [CLAUDE AI RESPONSE RAW] ===================")
            print(raw_text)
            print("=================================================================\n")

            if raw_text.strip():
                cleaned_text = raw_text.strip()
                cleaned_text = re.sub(r'^```json\s*', '', cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r'^```\s*', '', cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
                cleaned_text = cleaned_text.strip()

                start_idx = cleaned_text.find('{')
                end_idx = cleaned_text.rfind('}')

                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = cleaned_text[start_idx:end_idx+1]
                    try:
                        fixed_str = json_str.replace('\\\\u', '\\u')
                        trade_plan = json.loads(fixed_str)
                    except Exception:
                        try:
                            sanitized = re.sub(r'(?<!\\)\n', ' ', json_str)
                            sanitized = re.sub(r'(?<!\\)\r', ' ', sanitized)
                            sanitized = re.sub(r'\s+', ' ', sanitized)
                            trade_plan = json.loads(sanitized)
                        except Exception:
                            pass

        # --- SÉCURITÉ INVERSÉE DU REPLI ---
        # Si Claude échoue à répondre ou que le JSON est corrompu, on REJETTE par défaut (INVALID)
        if not trade_plan:
            print("[-] Avertissement : Échec de lecture du plan de Claude -> REJET PAR SÉCURITÉ.")
            trade_plan = {
                "status": "INVALID",
                "direction": raw_payload.get("action", "BUY"),
                "type_ordre": "MARKET",
                "zone_attente": "Rejeté",
                "declencheur": "Erreur de traitement ou format invalide",
                "entree": float(price),
                "stop_loss": 0.0,
                "cible_1": 0.0,
                "risque_rendement": 0.0,
                "validation_macro": "REJECT"
            }

        LATEST_TRADE = trade_plan

        print("\n================ [CLAUDE AI DECISION PARSED] ================")
        print(json.dumps(LATEST_TRADE, indent=2, ensure_ascii=False))
        print("=============================================================\n")

    except Exception as e:
        print(f"Erreur critique arrière-plan Claude : {e}")
        # En cas d'exception globale, on bloque tout
        LATEST_TRADE = {
            "status": "INVALID",
            "direction": "HOLD",
            "declencheur": f"Exception critique: {str(e)}"
        }

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json() or {}
        ticker = data.get("symbol") or data.get("ticker", "XAUUSD")
        price = data.get("price", 0.0)
        message = data.get("message", "Alerte")

        # Lancement de l'analyse Claude en arrière-plan
        threading.Thread(target=process_claude_async, args=(ticker, price, message, data)).start()

        return jsonify({"status": "SUCCESS", "message": "Alerte reçue et en cours de filtration"}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 400

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global LATEST_TRADE
    return jsonify(LATEST_TRADE), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
