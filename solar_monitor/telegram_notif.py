import urllib.request
import urllib.parse
import json
import os

DIR_PATH = os.path.dirname(os.path.abspath(__file__))
TELEGRAM_CONFIG_FILE = os.path.join(DIR_PATH, "telegram_config.json")

def carregar_config_telegram():
    try:
        with open(TELEGRAM_CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return None

def enviar_telegram(mensagem, token=None, chat_id=None):
    """
    Envia mensagem via Telegram.
    Se token/chat_id não forem passados, tenta carregar do arquivo.
    """
    if not token or not chat_id:
        config = carregar_config_telegram()
        if config:
            token = config["token"]
            chat_id = config["chat_id"]
        else:
            return False, "Configuração não encontrada"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            return True, "Mensagem enviada"
    except Exception as e:
        return False, f"Erro: {e}"
