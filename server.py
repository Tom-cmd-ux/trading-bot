import os
from flask import Flask, jsonify, request
import requests
import json
import re

app = Flask(__name__)

LATEST_TRADE = {"action": "NONE"}

SYSTEM_PROMPT = """Tu es un assistant de trading algorithmique expert sur l'or (XAUUSD). Réponds UNIQUEMENT au format JSON strict, sans markdown ni texte additionnel :
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

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json() or {}
        ticker = data.get("ticker", "XAUUSD")
        price = data.get("price", 0.0)
        message = data.get("message", "Alerte")

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

        url = "https://api.anthropic.com/v1/messages"
        resp = requests.post(url, headers=headers, json=payload)
        
        if resp.status_code != 200:
            return jsonify({"status": "ERROR", "anthropic_error": resp.text}), 400

        resp_data = resp.json()

        # Extraction du bloc de texte brut de Claude
        raw_text = ""
        for block in resp_data.get("content", []):
            if block.get("type") == "text":
                raw_text = block.get("text", "")
                break

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
                trade_plan = json.loads(json_str)
            except Exception:
                try:
                    unescaped = json_str.replace('\\"', '"').replace('\\n', ' ')
                    trade_plan = json.loads(unescaped)
                except Exception as e:
                    trade_plan = {"status": "PARSE_ERROR", "raw_response": raw_text, "error": str(e)}
        else:
            trade_plan = {"status": "RAW_OUTPUT", "raw_response": raw_text}

        global LATEST_TRADE
        LATEST_TRADE = trade_plan

        return jsonify({"status": "SUCCESS", "trade_plan": trade_plan}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 400

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global LATEST_TRADE
    return jsonify(LATEST_TRADE), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
