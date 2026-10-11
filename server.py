import os
from flask import Flask, jsonify, request
import requests
import json

app = Flask(__name__)

LATEST_TRADE = {"action": "NONE"}

SYSTEM_PROMPT = """Tu es un assistant de trading algorithmique expert sur l'or (XAUUSD). Réponds UNIQUEMENT au format JSON strict :
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
            "model": "claude-3-haiku-20240307",
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"Ticker: {ticker}, Prix: {price}, Msg: {message}"}]
        }

        resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        
        if resp.status_code != 200:
            return jsonify({"status": "ERROR", "anthropic_error": resp.text}), 400

        resp_data = resp.json()
        content = resp_data["content"][0]["text"].strip()
        
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()

        trade_plan = json.loads(content)
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
