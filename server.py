import os
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-usr-13bdsWK-Q6pTHW9hEkxJbXcSSRJYFNt02NT4rIKuaeN5XYGIR1kSJYhe3fpAIHLOTUe4pokLW04FOVnh1xps4UWelChlQAA")
client = Anthropic(api_key=ANTHROPIC_API_KEY)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True) or request.form.to_dict()
    
    if not data:
        return jsonify({"status": "error", "message": "Aucune donnée reçue"}), 400

    print(f"[+] Alerte reçue : {data}")

    prompt = f"Analyse cette alerte de trading et donne un avis rapide en 2 phrases : {data}"

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        analysis = response.content[0].text
        print(f"[+] Analyse Claude : {analysis}")
        
        return jsonify({
            "status": "success",
            "received_data": data,
            "analysis": analysis
        }), 200

    except Exception as e:
        print(f"[-] Erreur Claude API : {e}")
        return jsonify({
            "status": "warning",
            "received_data": data,
            "error": str(e)
        }), 200

@app.route('/', methods=['GET'])
def home():
    return "Bot Trading Opérationnel !"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
