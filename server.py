import os
import threading
from flask import Flask, jsonify, request
import requests
import json
import re

app = Flask(__name__)

LATEST_TRADE = {"status": "INVALID", "action": "NONE"}

# --- SYSTEM PROMPT MIS À JOUR (Moins strict, tolérant sur le momentum) ---
SYSTEM_PROMPT = """Tu es un analyste de trading senior sur XAUUSD pragmatique et orienté tendance.
Ta mission est d'analyser les alertes TradingView en cherchant à **valider** les opportunités lorsque le marché montre une vraie force directionnelle (momentum).

Analyse l'alerte et renvoie UNIQUEMENT un JSON strict avec la structure suivante (sans markdown ni texte additionnel) :
{
    "status": "VALID",                     // Mets "VALID" dès que la direction est soutenue par la tendance, ou "INVALID" si le signal est totalement incohérent
    "direction": "BUY",                    // "BUY" ou "SELL"
    "type_ordre": "MARKET",                // "MARKET" de préférence pour surfer les mouvements
    "zone_attente": "Au marche",           // Niveau visé ou "Au marche"
    "declencheur": "Explication rapide",
    "entree": 0.00,                        // Prix exact d'entree
    "stop_loss": 0.00,
    "cible_1": 0.00,
    "cible_2": 0.00,
    "risque_rendement": 0.0,
    "validation_macro": "OK"               // "OK" par défaut si le mouvement est impulsif
}

REGLES D'ANALYSE SOUPLES ET MOMENTUM :
1. **Ne rejette PAS** un trade sous prétexte que le RSI est en zone de surachat (>70) ou de survente (<30) : une forte extension est souvent la signature d'un puissant momentum (cassure ou explosion des prix).
2. Accepte les entrées au marché (MARKET) pour ne pas rater le début ou le milieu des grandes vagues directionnelles.
3. Sois beaucoup moins frileux : tant que la tendance globale et le signal de l'alerte vont dans le même sens, autorise le trade (status = "VALID")."""

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
        payload_str = json.dumps(raw_payload, ensure_ascii=False)
        user_prompt = f"Ticker: {ticker}, Prix actuel: {price}\nPayload technique complet de TradingView: {payload_str}"

        payload = {
            "model": "claude-opus-5-5",
            "max_tokens": 1000,
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

        # --- SÉCURITÉ DE SECOURS ---
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
