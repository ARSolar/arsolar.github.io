#!/usr/bin/env python3
import math
import json
import os
import sys
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
from solis_api import SolisCloudAPI
from aiswei_api import AisweiSolarAPI

from datetime import timezone, timedelta
def get_local_now():
    # Returns the current time in Brasilia (UTC-3) as a timezone-naive datetime
    return (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)


# File paths
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIR_PATH, "config.json")
DASHBOARD_FILE = os.path.join(DIR_PATH, "dashboard.html")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("Arquivo config.json não encontrado. Execute settings.py primeiro.")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao ler configurações: {e}")
        sys.exit(1)

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar configurações atualizadas: {e}")

def trigger_alert_popup(alert_messages):
    """Launches a topmost Tkinter popup to alert the user."""
    try:
        root = tk.Tk()
        root.withdraw()  # Hide main window
        root.attributes("-topmost", True)  # Make it stay on top
        
        full_message = "\n\n".join(alert_messages)
        messagebox.showwarning("Alerta de Produção Solar - ARSolar", full_message)
        root.destroy()
    except Exception as e:
        print(f"Erro ao exibir popup Tkinter: {e}")


def get_joao_pessoa_weather():
    import requests
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=-7.1198&longitude=-34.8450&current=temperature_2m,relative_humidity_2m,weather_code,cloud_cover"
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json().get("current", {})
            code = data.get("weather_code", 0)
            temp = data.get("temperature_2m", 25.0)
            humidity = data.get("relative_humidity_2m", 80)
            cloud = data.get("cloud_cover", 0)
            
            # Map WMO weather code to icon and text
            wmo_map = {
                0: ("☀️", "Céu Limpo"),
                1: ("🌤️", "Poucas Nuvens"),
                2: ("⛅", "Parcialmente Nublado"),
                3: ("☁️", "Encoberto / Nublado"),
                45: ("🌫️", "Nevoeiro"), 48: ("🌫️", "Nevoeiro"),
                51: ("🌦️", "Chuvisco Leve"), 53: ("🌦️", "Chuvisco"), 55: ("🌦️", "Chuvisco Forte"),
                61: ("🌧️", "Chuva Leve"), 63: ("🌧️", "Chuva Moderada"), 65: ("🌧️", "Chuva Forte"),
                80: ("🌧️", "Pancadas de Chuva"), 81: ("🌧️", "Pancadas de Chuva"), 82: ("🌧️", "Chuva Forte"),
                95: ("⛈️", "Tempestade"), 96: ("⛈️", "Tempestade"), 99: ("⛈️", "Tempestade")
            }
            icon, desc = wmo_map.get(code, ("☀️", "Céu Limpo"))
            return {
                "temp": temp,
                "desc": f"{desc} (Nuvens: {cloud}%)",
                "icon": icon,
                "cloud": cloud,
                "humidity": humidity
            }
    except Exception as e:
        print(f"Erro ao buscar previsão do tempo: {e}")
    return None



def process_telegram_alerts(config, plants_results, active_alerts):
    try:
        # Don't send Telegram notifications outside active daylight hours (07:30 to 17:30)
        # since plants naturally go offline/low production when there is no sun.
        now = get_local_now()
        current_time_float = now.hour + now.minute / 60.0
        if not (7.5 <= current_time_float <= 17.5):
            print("Fora do horário de sol ativo (07:30 às 17:30). Notificações do Telegram suspensas.")
            return

        from telegram_notif import enviar_telegram
        favorites = config.get("favorites", [])
        if not favorites:
            return

        # Check if the previous run was outside active solar hours (07:30 to 17:30)
        # or if it was on a previous day.
        prev_run_was_outside = True
        last_update_str = config.get("last_update")
        if last_update_str:
            try:
                last_dt = datetime.fromisoformat(last_update_str)
                last_time_float = last_dt.hour + last_dt.minute / 60.0
                if last_dt.date() == now.date() and (7.5 <= last_time_float <= 17.5):
                    prev_run_was_outside = False
            except Exception as e:
                print(f"Erro ao parsear last_update: {e}")

        # Build map of previous status
        prev_status_map = {}
        for prev_p in config.get("last_data", []):
            name = prev_p.get("name")
            status = prev_p.get("status_str", "normal")
            # If the previous run was outside active solar hours (like the night run),
            # we reset the baseline to "normal" so that failing to wake up in the morning
            # triggers an alert instead of matching the previous night's offline state.
            if prev_run_was_outside:
                status = "normal"
            prev_status_map[name] = status
            
        # Build map of current alerts for easy detail lookup
        alerts_by_plant = {}
        for alt in active_alerts:
            alerts_by_plant[alt.get("plant_name")] = alt.get("message")
            
        for plant in plants_results:
            name = plant["name"]
            if name in favorites:
                curr_status = plant["status_str"]
                prev_status = prev_status_map.get(name, "normal")
                
                # Mapping status to emoji and nice text
                status_details = {
                    "normal": ("🟢", "Normal"),
                    "low_production": ("🟠", "Produção Baixa"),
                    "offline": ("⚫", "Offline"),
                    "error": ("🔴", "Erro")
                }
                
                curr_emoji, curr_desc = status_details.get(curr_status, ("⚪", curr_status))
                prev_emoji, prev_desc = status_details.get(prev_status, ("⚪", prev_status))
                
                # Check for state transition
                if prev_status == "normal" and curr_status != "normal":
                    # Alert triggered
                    detail = alerts_by_plant.get(name, "Anormalidade detectada.")
                    msg = ("⚠️ *Alerta ARSolar - Usina Favorita*\n\n" +
                           f"🌳 Usina: *{name}*\n" +
                           f"Status: {curr_emoji} *{curr_desc}*\n" +
                           f"Detalhe: {detail}")
                    print(f"Enviando Telegram para {name} (Novo Alerta)...")
                    enviar_telegram(msg)
                    
                elif prev_status != "normal" and curr_status == "normal":
                    # Alert resolved
                    msg = ("✅ *Alerta Resolvido - Usina Favorita*\n\n" +
                           f"🌳 Usina: *{name}*\n" +
                           "Status: 🟢 *Normal*\n" +
                           "A usina voltou a operar dentro dos parâmetros normais.")
                    print(f"Enviando Telegram para {name} (Alerta Resolvido)...")
                    enviar_telegram(msg)
                    
                elif prev_status != "normal" and curr_status != "normal" and prev_status != curr_status:
                    # Alert changed type
                    detail = alerts_by_plant.get(name, "Estado alterado.")
                    msg = ("🔄 *Atualização de Alerta - Usina Favorita*\n\n" +
                           f"🌳 Usina: *{name}*\n" +
                           f"Status mudou de: {prev_emoji} {prev_desc}\n" +
                           f"Para: {curr_emoji} *{curr_desc}*\n" +
                           f"Detalhe: {detail}")
                    print(f"Enviando Telegram para {name} (Status do Alerta Alterado)...")
                    enviar_telegram(msg)
    except Exception as e:
        print(f"Erro ao processar/enviar alertas do Telegram: {e}")

def generate_dashboard(config_data, plants_data, active_alerts, api_error=None, output_file=None, weather_data=None):
    """Generates the static HTML dashboard by injecting the latest data."""

    serialized_plants  = json.dumps(plants_data,    ensure_ascii=False)
    serialized_alerts  = json.dumps(active_alerts,  ensure_ascii=False)
    serialized_api_err = json.dumps(api_error,       ensure_ascii=False)
    serialized_weather = json.dumps(weather_data,    ensure_ascii=False)
    last_update_str    = get_local_now().strftime("%d/%m/%Y %H:%M:%S")

    html_template = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARSolar - Monitor de Energia Solar</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{
  --bg:#060813;--text:#f3f4f6;--muted:#9ca3af;
  --primary:#fbbf24;--primary-glow:rgba(251,191,36,.12);
  --card:rgba(17,25,40,.5);--border:rgba(255,255,255,.06);
  --ok:#10b981;--warn:#f59e0b;--err:#ef4444;--off:#6b7280;
  --sw:280px;
}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif}
body{background-color:var(--bg);background-image:radial-gradient(at 0% 0%,rgba(251,191,36,.04) 0,transparent 50%),radial-gradient(at 100% 100%,rgba(16,185,129,.04) 0,transparent 50%);background-attachment:fixed;color:var(--text);min-height:100vh}

/* ── SIDEBAR ── */
.sidebar{background:rgba(10,15,30,.7);backdrop-filter:blur(20px);border-right:1px solid var(--border);padding:24px 16px;display:flex;flex-direction:column;position:fixed;left:0;top:0;bottom:0;width:var(--sw);z-index:100;overflow-y:auto}
.logo-section{display:flex;align-items:center;gap:10px;margin-bottom:26px;padding-left:4px}
.logo-icon{font-size:24px;background:linear-gradient(135deg,var(--primary),var(--ok));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo-text{font-size:21px;font-weight:700;letter-spacing:-.5px}
.nav-title{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;padding-left:8px;font-weight:600}
.nav-list{display:flex;flex-direction:column;gap:4px;margin-bottom:20px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:10px;cursor:pointer;transition:all .2s;font-size:13px;font-weight:500;color:var(--muted);border:1px solid transparent;position:relative}
.nav-item:hover{background:rgba(255,255,255,.03);color:var(--text)}
.nav-item.active{background:rgba(251,191,36,.08);border-color:rgba(251,191,36,.15);color:var(--primary)}
.nav-dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}
.nav-alert-badge{position:absolute;right:10px;background:var(--err);color:#fff;font-size:9px;font-weight:700;padding:1px 5px;border-radius:8px;min-width:16px;text-align:center}
.fav-star{margin-left:auto;font-size:13px;cursor:pointer;opacity:.35;transition:opacity .2s;line-height:1}
.fav-star.active{opacity:1;color:#fbbf24}
.last-update-bar{display:flex;align-items:center;gap:10px;background:rgba(17,25,40,.4);border:1px solid var(--border);border-radius:12px;padding:7px 14px;font-size:12px;backdrop-filter:blur(10px)}
.last-update-time{color:var(--muted);white-space:nowrap}
.last-update-time strong{color:var(--text);font-weight:600}
.refresh-btn{background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.25);color:var(--primary);padding:6px 14px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;transition:all .2s;display:flex;align-items:center;gap:6px;white-space:nowrap}
.refresh-btn:hover:not(:disabled){background:rgba(251,191,36,.2);border-color:rgba(251,191,36,.5);transform:scale(1.02)}
.refresh-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .8s linear infinite}
.sidebar-footer{margin-top:auto;font-size:11px;color:var(--muted);border-top:1px solid var(--border);padding-top:13px;padding-left:4px}

/* ── MAIN ── */
.main-content{padding:36px 40px;margin-left:var(--sw);min-height:100vh}
.main-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;gap:16px;flex-wrap:wrap}
.main-header-title-text{font-size:24px;font-weight:700;letter-spacing:-.5px}
.header-controls{display:flex;align-items:center;gap:10px}
.weather-widget{background:rgba(17,25,40,.4);border:1px solid var(--border);border-radius:12px;padding:7px 14px;display:flex;align-items:center;gap:10px;font-size:13px;backdrop-filter:blur(10px)}
.weather-icon{font-size:22px}
.weather-temp{font-weight:700}
.weather-desc{font-size:10px;color:var(--muted)}
.icon-btn{background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:9px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s;display:flex;align-items:center;gap:6px}
.icon-btn:hover{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.15)}
.icon-btn.active-view{background:rgba(251,191,36,.1);border-color:rgba(251,191,36,.25);color:var(--primary)}

/* ── TABS ── */
.tab-pane{display:none;animation:fadeIn .4s ease}
.tab-pane.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}

/* ── METRIC CARDS ── */
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin-bottom:26px}
.metric-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px;backdrop-filter:blur(20px);transition:all .3s}
.metric-card:hover{transform:translateY(-2px);border-color:rgba(251,191,36,.2)}
.metric-title{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;font-weight:500}
.metric-value{font-size:30px;font-weight:700;margin-bottom:4px}
.metric-unit{font-size:15px;font-weight:500;color:var(--muted);margin-left:3px}
.metric-sub{font-size:11px;color:var(--muted)}

/* ── ALERTS ── */
.alerts-section-title{font-size:13px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.alert-card{border-radius:12px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;backdrop-filter:blur(10px);transition:all .3s}
.alert-card.fav-alert{background:rgba(245,158,11,.08);border:1px solid var(--warn)}
.alert-card.other-alert{background:rgba(107,114,128,.06);border:1px solid var(--off)}
.alert-info{display:flex;align-items:center;gap:10px}
.alert-icon{font-size:16px}
.alert-message{font-size:13px;font-weight:500}
.alert-badge{font-size:9px;font-weight:700;padding:3px 7px;border-radius:4px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}
.badge-offline{background:var(--off);color:#fff}
.badge-low{background:var(--warn);color:#000}
.badge-fav{background:var(--primary);color:#000;margin-left:4px}

/* ── SECTION HEADER ── */
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.section-header-title{font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px}

/* ── PLANTS GRID ── */
.plants-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px;margin-bottom:28px}
.plant-card{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:22px;backdrop-filter:blur(20px);cursor:pointer;transition:all .3s;display:flex;flex-direction:column;gap:16px;position:relative}
.plant-card:hover{transform:translateY(-3px);border-color:rgba(255,255,255,.13);box-shadow:0 10px 20px rgba(0,0,0,.3)}
.plant-fav-btn{position:absolute;top:14px;right:14px;background:none;border:none;cursor:pointer;font-size:17px;opacity:.3;transition:all .25s;padding:4px;border-radius:6px;line-height:1}
.plant-fav-btn:hover{opacity:.8;background:rgba(255,255,255,.06)}
.plant-fav-btn.is-fav{opacity:1;color:#fbbf24}
.plant-card-header{padding-right:30px}
.plant-card-title{font-size:16px;font-weight:600}
.plant-card-sub{font-size:11px;color:var(--muted);margin-top:2px}
.plant-card-badges{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.plant-status-badge{font-size:9px;font-weight:700;padding:3px 9px;border-radius:20px;text-transform:uppercase;letter-spacing:.5px;border:1px solid}
.status-normal{background:rgba(16,185,129,.08);color:var(--ok);border-color:var(--ok)}
.status-low{background:rgba(245,158,11,.08);color:var(--warn);border-color:var(--warn)}
.status-offline{background:rgba(107,114,128,.08);color:var(--off);border-color:var(--off)}
.status-error{background:rgba(239,68,68,.08);color:var(--err);border-color:var(--err)}
.day-badge{font-size:9px;padding:3px 7px;border-radius:4px;font-weight:700}
.plant-card-body{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.plant-card-metric-lbl{font-size:10px;color:var(--muted);margin-bottom:1px}
.plant-card-metric-val{font-size:15px;font-weight:600}
.plant-card-footer{padding-top:10px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:6px}
.eff-bar-wrap{height:5px;background:rgba(255,255,255,.05);border-radius:10px;overflow:hidden}
.eff-bar{height:100%;border-radius:10px;transition:width .5s}
.eff-high{background:var(--ok)}.eff-med{background:var(--warn)}.eff-low{background:var(--err)}

/* ── PLANTS LIST ── */
.plants-list{display:flex;flex-direction:column;gap:8px;margin-bottom:28px}
.plant-list-row{background:var(--card);border:1px solid var(--border);border-radius:13px;padding:14px 20px;cursor:pointer;transition:all .25s;display:grid;grid-template-columns:26px 1fr 100px 110px 90px 110px 110px 80px 36px;align-items:center;gap:12px}
.plant-list-row:hover{border-color:rgba(255,255,255,.13);background:rgba(17,25,40,.7)}
.list-name{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list-sub{font-size:10px;color:var(--muted)}
.list-val{font-size:13px;font-weight:600}
.list-lbl{font-size:10px;color:var(--muted)}
.list-fav-btn{background:none;border:none;cursor:pointer;font-size:16px;opacity:.3;transition:all .25s;padding:2px;line-height:1;width:100%;text-align:center}
.list-fav-btn:hover{opacity:.8}
.list-fav-btn.is-fav{opacity:1;color:#fbbf24}
.list-header{display:grid;grid-template-columns:26px 1fr 100px 110px 90px 110px 110px 80px 36px;align-items:center;gap:12px;padding:6px 20px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}

/* ── CHART ── */
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:22px;backdrop-filter:blur(20px);margin-bottom:26px}
.chart-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:8px}
.chart-title{font-size:15px;font-weight:600}
.chart-container{position:relative;height:360px;width:100%}

/* ── DETAIL VIEW ── */
.detail-header-block{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;padding-bottom:14px;border-bottom:1px solid var(--border)}
.back-btn{background:rgba(255,255,255,.03);border:1px solid var(--border);color:var(--text);padding:7px 14px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s}
.back-btn:hover{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.15)}
.detail-plant-name-txt{font-size:22px;font-weight:700}
.detail-metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;margin-bottom:26px}
.detail-card{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:22px;backdrop-filter:blur(20px);display:flex;flex-direction:column;justify-content:center;min-height:180px}
.radial-gauge-wrapper{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center}
.radial-gauge-container{position:relative;width:100px;height:100px}
.radial-gauge{width:100%;height:100%;transform:rotate(-90deg)}
.gauge-circle-bg{fill:none;stroke:rgba(255,255,255,.04);stroke-width:9}
.gauge-circle-fill{fill:none;stroke:var(--primary);stroke-width:9;stroke-linecap:round;stroke-dasharray:251.2;stroke-dashoffset:251.2;transition:stroke-dashoffset .8s ease-in-out}
.gauge-overlay-text{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center}
.gauge-percentage{font-size:20px;font-weight:700;line-height:1}
.gauge-lbl{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:3px;font-weight:600}
.detail-extended-grid{display:grid;grid-template-columns:1.6fr 1fr;gap:18px;margin-bottom:26px}
@media(max-width:1100px){.detail-extended-grid{grid-template-columns:1fr}}
.properties-title{font-size:15px;font-weight:600;margin-bottom:16px;padding-bottom:7px;border-bottom:1px solid var(--border)}
.property-item{display:flex;justify-content:space-between;align-items:center;font-size:12px;padding-bottom:9px;border-bottom:1px dashed rgba(255,255,255,.04)}
.property-item:last-child{border-bottom:none;padding-bottom:0}
.property-lbl{color:var(--muted);font-weight:500}
.property-val{font-weight:600;text-align:right}
.maps-link{color:var(--primary);text-decoration:none;border-bottom:1px dashed var(--primary);transition:all .2s}
.maps-link:hover{color:var(--text);border-color:var(--text)}

/* ── ALERTS MENU ── */
#alerts-menu-container .all-alerts-list{display:flex;flex-direction:column;gap:10px}
.alerts-empty{text-align:center;padding:60px 20px;color:var(--muted)}
.alerts-empty-icon{font-size:48px;margin-bottom:12px}

/* ── RESPONSIVE ── */
@media(max-width:900px){
  .sidebar{width:100%!important;height:auto!important;position:relative!important;border-right:none!important;border-bottom:1px solid var(--border);padding:15px!important}
  .main-content{margin-left:0!important;padding:15px!important}
  .plant-list-row,.list-header{grid-template-columns:26px 1fr 90px 90px 60px 36px}
  .plant-list-row .list-col-total,.list-header .lh-total{display:none}
  .plant-list-row .list-col-cap,.list-header .lh-cap{display:none}
  .plant-list-row .list-col-day,.list-header .lh-day{display:none}
}


/* ── REAL-TIME FLOW TELEMETRY ── */
.rt-flow-container {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.rt-side-dc, .rt-side-ac {
  flex: 1;
  min-width: 280px;
  background: rgba(255, 255, 255, 0.01);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
}
.rt-section-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--muted);
  letter-spacing: .5px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}
.rt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.rt-table th, .rt-table td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}
.rt-table th {
  color: var(--muted);
  font-weight: 500;
  font-size: 10px;
  text-transform: uppercase;
}
.rt-table td {
  font-weight: 600;
}
.rt-table tbody tr:last-child td {
  border-bottom: none;
}
.rt-center-diagram {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 10px;
}
.rt-flow-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rt-inverter-box {
  background: rgba(251, 191, 36, 0.07);
  border: 1px solid var(--primary);
  color: var(--primary);
  border-radius: 12px;
  padding: 18px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  box-shadow: 0 0 15px rgba(251, 191, 36, 0.1);
  animation: pulseInverter 2.5s infinite ease-in-out;
}
.rt-inverter-icon {
  font-size: 24px;
}
.rt-inverter-lbl {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 1px;
}
.rt-arrow {
  width: 40px;
  height: 3px;
  background: linear-gradient(90deg, var(--primary), var(--ok));
  position: relative;
  border-radius: 2px;
}
.rt-arrow::after {
  content: '';
  position: absolute;
  right: -2px;
  top: -3.5px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 6px solid var(--ok);
}
@keyframes pulseInverter {
  0%, 100% { transform: scale(1); box-shadow: 0 0 15px rgba(251, 191, 36, 0.1); }
  50% { transform: scale(1.04); box-shadow: 0 0 25px rgba(251, 191, 36, 0.25); }
}
.rt-footer-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  padding: 7px 12px;
  background: rgba(255, 255, 255, 0.01);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.rt-footer-lbl {
  color: var(--muted);
  font-weight: 500;
}
.rt-footer-val {
  font-weight: 600;
}


/* ── HORIZONTAL PROPERTIES GRID ── */
.detail-properties-horizontal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.prop-h-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: rgba(255, 255, 255, 0.015);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 0; /* allows text-overflow to work in flex child */
}
.prop-h-lbl {
  font-size: 9px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .5px;
}
.prop-h-val {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
#detail-apikey {
  font-family: monospace;
  font-size: 10px;
}
#prop-location-item .prop-h-val, #prop-coordinates-item .prop-h-val {
  white-space: normal;
  font-size: 11px;
  line-height: 1.3;
  text-overflow: clip;
}

select option {
  background-color: #0b0f19 !important;
  color: var(--text) !important;
}
</style>
</head>
<body>

<!-- ════════════════════════════════ SIDEBAR ════════════════════════════════ -->
<div class="sidebar">
  <div class="logo-section">
    <span class="logo-icon">☀️</span>
    <span class="logo-text">ARSolar</span>
  </div>

  <div class="nav-title">Menu</div>
  <div class="nav-list">
    <div id="sidebar-overview-btn" class="nav-item active" onclick="switchTab('overview')">
      <span>📊</span><span>Visão Geral</span>
    </div>
    <div id="sidebar-alerts-btn" class="nav-item" onclick="switchTab('alerts')">
      <span>🔔</span><span>Alertas</span>
      <span id="sidebar-alerts-badge" class="nav-alert-badge" style="display:none">0</span>
    </div>
  </div>

  <div id="sidebar-solplanet-section">
    <div class="nav-title">Usinas Solplanet</div>
    <div id="sidebar-solplanet-list" class="nav-list"></div>
  </div>
  <div id="sidebar-solis-section" style="margin-top:12px">
    <div class="nav-title">Usinas Solis</div>
    <div id="sidebar-solis-list" class="nav-list"></div>
  </div>

  <div class="sidebar-footer">
    Última Varredura:<br><strong>__LAST_UPDATE__</strong>
  </div>
</div>

<!-- ════════════════════════════════ MAIN ════════════════════════════════ -->
<div class="main-content">

  <!-- Header -->
  <div class="main-header">
    <div class="main-header-title-text" id="main-header-title">Visão Geral</div>
    <!-- Last update + Refresh -->
    <div class="last-update-bar" id="last-update-bar" style="margin-right: 12px;">
      <span class="last-update-time">Última consulta: <strong id="lu-time">__LAST_UPDATE__</strong></span>
      <button class="refresh-btn" id="refresh-btn" onclick="triggerRefresh()" title="Consultar APIs agora">
        <span id="refresh-icon">&#x1F504;</span> Atualizar
      </button>
    </div>
    <div class="header-controls">
      <!-- View toggle (only shows on overview) -->
      <div id="view-toggle-wrap" style="display:flex;gap:6px">
        <button class="icon-btn active-view" id="btn-grid" onclick="setView('grid')" title="Visualização em Grade">⊞ Grade</button>
        <button class="icon-btn" id="btn-list" onclick="setView('list')" title="Visualização em Lista">≡ Lista</button>
      </div>
      <!-- Weather widget -->
      <div id="weather-widget" class="weather-widget" style="display:none">
        <span id="weather-icon" class="weather-icon">☀️</span>
        <div>
          <div id="weather-temp" class="weather-temp">--°C</div>
          <div id="weather-desc" class="weather-desc">--</div>
        </div>
      </div>
    </div>
  </div>

  <!-- API error banner -->
  <div id="api-error-block" class="alert-card fav-alert" style="display:none;margin-bottom:16px;background:rgba(239,68,68,.1);border-color:var(--err)">
    <div class="alert-info"><span>⚠️</span><div><strong>Erro de Conexão:</strong> <span id="api-error-text"></span></div></div>
  </div>

  <!-- ── TAB: OVERVIEW ── -->
  <div id="tab-overview" class="tab-pane active">

    <!-- Favorites alerts (shown on overview) -->
    <div id="fav-alerts-block" style="margin-bottom:16px"></div>

    <!-- Metrics row -->
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-title">Geração Atual Total</div>
        <div class="metric-value"><span id="total-power">0.00</span><span class="metric-unit">kW</span></div>
        <div class="metric-sub">Potência instantânea total das usinas ativas</div>
      </div>
      <div class="metric-card">
        <div class="metric-title">Produção de Hoje</div>
        <div class="metric-value"><span id="total-yield-today">0.0</span><span class="metric-unit">kWh</span></div>
        <div class="metric-sub">Energia acumulada gerada hoje</div>
      </div>
      <div class="metric-card">
        <div class="metric-title">Capacidade Instalada</div>
        <div class="metric-value"><span id="total-capacity">0.0</span><span class="metric-unit">kWp</span></div>
        <div class="metric-sub">Soma das potências nominais registradas</div>
      </div>
    </div>

    <!-- Section header with view toggle hint -->
    <div class="section-header">
      <div class="section-header-title">⚙️ Status Operacional das Usinas</div>
    </div>

    <!-- Grid view -->
    <div id="plants-grid-view" class="plants-grid"></div>

    <!-- List view -->
    <div id="plants-list-view" style="display:none">
      <div class="list-header">
        <span></span>
        <span>Usina</span>
        <span class="lh-power">Geração Atual</span>
        <span class="lh-today">Gerado Hoje</span>
        <span class="lh-day">% do Dia</span>
        <span class="lh-total list-col-total">Acumulado Total</span>
        <span class="lh-cap list-col-cap">Capacidade</span>
        <span>Status</span>
        <span>⭐</span>
      </div>
      <div id="plants-list-rows" class="plants-list"></div>
    </div>

    <!-- Overview chart -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">Curvas de Geração Comparativas (Hoje)</div>
        <div style="font-size:11px;color:var(--muted)">Potência (kW)</div>
      </div>
      <div class="chart-container"><canvas id="overviewChart"></canvas></div>
    </div>
  </div>

  <!-- ── TAB: ALERTS ── -->
  <div id="tab-alerts" class="tab-pane">
    <div id="alerts-menu-container">
      <!-- Populated by JS -->
    </div>
  </div>

  <!-- ── TAB: PLANT DETAIL ── -->
  <div id="tab-plant-detail" class="tab-pane">
    <div class="detail-header-block">
      <div style="display:flex;align-items:center;gap:14px">
        <button class="back-btn" onclick="switchTab('overview')">← Voltar</button>
        <div class="detail-plant-name-txt" id="detail-plant-name">Nome da Usina</div>
      </div>
      <span class="plant-status-badge" id="detail-plant-status"></span>
    </div>

    <div class="detail-metrics-grid">
      <div class="detail-card">
        <div class="radial-gauge-wrapper">
          <div class="radial-gauge-container">
            <svg class="radial-gauge" viewBox="0 0 100 100">
              <circle class="gauge-circle-bg" cx="50" cy="50" r="40"></circle>
              <circle class="gauge-circle-fill" cx="50" cy="50" r="40" id="gauge-circle-fill"></circle>
            </svg>
            <div class="gauge-overlay-text">
              <span class="gauge-percentage" id="gauge-percentage-text">0%</span>
              <span class="gauge-lbl" id="detail-instant-lbl">Rend. Instante</span>
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted)" id="detail-power-ratio">0.00 kW / 0.00 kWp</div>
        </div>
      </div>
      <div class="detail-card">
        <div class="radial-gauge-wrapper">
          <div class="radial-gauge-container">
            <svg class="radial-gauge" viewBox="0 0 100 100">
              <circle class="gauge-circle-bg" cx="50" cy="50" r="40"></circle>
              <circle class="gauge-circle-fill" cx="50" cy="50" r="40" id="daily-gauge-circle-fill"></circle>
            </svg>
            <div class="gauge-overlay-text">
              <span class="gauge-percentage" id="daily-gauge-percentage-text">0%</span>
              <span class="gauge-lbl">Rend. do Dia</span>
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted)" id="detail-daily-ratio">0.0 / 0.0 kWh</div>
        </div>
      </div>
      <div class="detail-card">
        <div class="metric-title" id="detail-yield-today-lbl">Geração Realizada Hoje</div>
        <div class="metric-value" id="detail-today-yield">0.0<span class="metric-unit">kWh</span></div>
        <div class="metric-sub" id="detail-yield-today-sub">Energia acumulada desde o amanhecer</div>
      </div>
      <div class="detail-card">
        <div class="metric-title" id="detail-yield-total-lbl">Geração Histórica Vitalícia</div>
        <div class="metric-value" id="detail-total-yield">0.00<span class="metric-unit">MWh</span></div>
        <div class="metric-sub" id="detail-yield-total-sub">Total acumulado vitalício</div>
      </div>
    </div>

    <!-- Ficha Técnica & Alvos (Stacked on top) -->
    <div class="detail-card" style="padding:22px;margin-bottom:20px">
      <div class="properties-title" id="detail-properties-title" style="margin-bottom:15px">Ficha Técnica & Alvos da Usina</div>
      <div class="detail-properties-horizontal-grid">
        <div class="prop-h-item" id="prop-apikey-item">
          <span class="prop-h-lbl">Chave API / NMI</span>
          <span class="prop-h-val" id="detail-apikey">--</span>
        </div>
        <div class="prop-h-item">
          <span class="prop-h-lbl">Capacidade Nominal</span>
          <span class="prop-h-val" id="detail-capacity">--</span>
        </div>
        <div class="prop-h-item" id="prop-threshold-item">
          <span class="prop-h-lbl">Limiar de Alerta</span>
          <span class="prop-h-val" id="detail-threshold">--</span>
        </div>
        <div class="prop-h-item">
          <span class="prop-h-lbl">Target Diário Estimado</span>
          <span class="prop-h-val" id="detail-expected-daily">--</span>
        </div>
        <div class="prop-h-item">
          <span class="prop-h-lbl">Alvo Esperado Até Agora</span>
          <span class="prop-h-val" id="detail-expected-so-far">--</span>
        </div>
        <div class="prop-h-item">
          <span class="prop-h-lbl">Desempenho Diário</span>
          <span class="prop-h-val" id="detail-performance-status">--</span>
        </div>
        <div class="prop-h-item">
          <span class="prop-h-lbl">Última Comunicação</span>
          <span class="prop-h-val" id="detail-ludt">--</span>
        </div>
        <div class="prop-h-item" id="prop-location-item">
          <span class="prop-h-lbl">Endereço</span>
          <span class="prop-h-val" id="detail-location">--</span>
        </div>
        <div class="prop-h-item" id="prop-coordinates-item">
          <span class="prop-h-lbl">Geolocalização</span>
          <span class="prop-h-val" id="detail-coordinates">--</span>
        </div>
      </div>
    </div>

    <!-- Chart Card (stacked in the middle, full width) -->
    <div class="detail-card" style="padding:22px;min-height:380px;margin-bottom:20px">
      <div class="chart-header">
        <div class="chart-title" id="detail-chart-title">Curva de Geração Individual</div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <select id="detail-inverter-selector" onchange="changeDetailChartDate()" class="back-btn" style="padding:4px 8px;font-size:11px;font-weight:600;cursor:pointer;display:none"></select>
          <select id="detail-parameter-selector" onchange="changeDetailChartDate()" class="back-btn" style="padding:4px 8px;font-size:11px;font-weight:600;cursor:pointer">
            <option value="Potência">⚡ Potência (kW)</option>
            <option value="Tensão CA">🔌 Tensão CA (V)</option>
            <option value="Corrente CA">📉 Corrente CA (A)</option>
            <option value="Tensão CC MPPT1">⚡ Tensão CC - MPPT 1 (V)</option>
            <option value="Corrente CC MPPT1">📉 Corrente CC - MPPT 1 (A)</option>
            <option value="Tensão CC MPPT2">⚡ Tensão CC - MPPT 2 (V)</option>
            <option value="Corrente CC MPPT2">📉 Corrente CC - MPPT 2 (A)</option>
          </select>
          <select id="detail-date-selector" onchange="changeDetailChartDate()" class="back-btn" style="padding:4px 8px;font-size:11px;font-weight:600;cursor:pointer"></select>
        </div>
      </div>
      <div class="chart-container"><canvas id="plantDetailChart"></canvas></div>
    </div>

    <!-- Real-time Electricity Production & String Telemetry displays (stacked at the bottom, full width) -->
    <div id="detail-realtime-production-card" class="detail-card" style="padding:22px;margin-bottom:20px;display:none">
      <div class="properties-title" style="margin-bottom:20px">Produção de Eletricidade & Telemetria CC/CA</div>
      
      <!-- Grid representing the flow -->
      <div class="rt-flow-container">
        <!-- DC Side (Left) -->
        <div class="rt-side-dc">
          <div class="rt-section-header">CC (Corrente Contínua)</div>
          <table class="rt-table" id="rt-dc-table">
            <thead>
              <tr>
                <th>String</th>
                <th>Voltagem</th>
                <th>Corrente</th>
                <th>Poder</th>
              </tr>
            </thead>
            <tbody id="rt-dc-tbody"></tbody>
          </table>
        </div>
        
        <!-- Center Diagram -->
        <div class="rt-center-diagram">
          <div class="rt-flow-line">
            <div class="rt-arrow"></div>
            <div class="rt-inverter-box">
              <span class="rt-inverter-icon">🔌</span>
              <span class="rt-inverter-lbl">DC/AC</span>
            </div>
            <div class="rt-arrow"></div>
          </div>
        </div>
        
        <!-- AC Side (Right) -->
        <div class="rt-side-ac">
          <div class="rt-section-header">CA (Corrente Alternada)</div>
          <table class="rt-table" id="rt-ac-table">
            <thead>
              <tr>
                <th>Fase</th>
                <th>Voltagem</th>
                <th>Corrente</th>
                <th>Frequência</th>
              </tr>
            </thead>
            <tbody id="rt-ac-tbody"></tbody>
          </table>
        </div>
      </div>
      
      <!-- String & Temperature grid -->
      <div class="rt-footer-grid" style="margin-top:24px;display:grid;grid-template-columns:1.2fr 1fr;gap:20px;border-top:1px solid var(--border);padding-top:20px">
        <!-- Combiner string status -->
        <div>
          <div class="rt-section-header" style="margin-bottom:10px">Sub-Grupos de Strings</div>
          <div id="rt-combiner-list" style="display:flex;flex-direction:column;gap:6px"></div>
        </div>
        
        <!-- Temperatures status -->
        <div>
          <div class="rt-section-header" style="margin-bottom:10px">Temperaturas Internas</div>
          <div id="rt-temp-list" style="display:grid;grid-template-columns:1fr 1fr;gap:10px"></div>
        </div>
      </div>
    </div>
  </div>

</div><!-- /main-content -->

<!-- ════════════════ SCRIPT ════════════════ -->
<script>
const plantsData   = __PLANTS_DATA__;
const alertsData   = __ALERTS_DATA__;
const apiErrorData = __API_ERROR__;
const weatherData  = __WEATHER_DATA__;

let overviewChartInst = null;
let detailChartInst   = null;
let activePlantIdx    = null;
let currentView       = localStorage.getItem('arsolar_view') || 'list';

const COLORS = ['#fbbf24','#10b981','#3b82f6','#a855f7','#ec4899','#06b6d4','#f97316'];

// ── helpers ────────────────────────────────────────────────────────────────
function getFavs() {
  try { return JSON.parse(localStorage.getItem('arsolar_favs') || '[]'); } catch(e){ return []; }
}
function saveFavs(arr) {
  localStorage.setItem('arsolar_favs', JSON.stringify(arr));
}
function isFav(name) { return getFavs().includes(name); }
function toggleFav(name, e) {
  if(e){ e.stopPropagation(); }
  const favs = getFavs();
  const idx  = favs.indexOf(name);
  if(idx === -1) favs.push(name); else favs.splice(idx,1);
  saveFavs(favs);
  refreshFavUI();
}
function refreshFavUI() {
  const favs = getFavs();
  // Cards
  plantsData.forEach((p,i) => {
    const cardBtn = document.getElementById('fav-card-btn-'+i);
    if(cardBtn) { cardBtn.className = 'plant-fav-btn' + (isFav(p.name) ? ' is-fav' : ''); }
    const listBtn = document.getElementById('fav-list-btn-'+i);
    if(listBtn) { listBtn.className = 'list-fav-btn' + (isFav(p.name) ? ' is-fav' : ''); }
    const sideItem = document.getElementById('sidebar-plant-'+i);
    if(sideItem) {
      const star = sideItem.querySelector('.fav-star');
      if(star) star.className = 'fav-star' + (isFav(p.name) ? ' active' : '');
    }
  });
  renderFavAlerts();
  renderAlertsMenu();
  updateAlertsBadge();
}

function getStatusInfo(plant) {
  if(plant.status_str === 'offline' || plant.status === 0)
    return { label:'Offline',  cls:'status-offline', color:'var(--off)'  };
  if(plant.status_str === 'low_production')
    return { label:'Prod. Baixa', cls:'status-low', color:'var(--warn)' };
  if(plant.status === 2)
    return { label:'Alerta',   cls:'status-low',     color:'var(--warn)' };
  if(plant.status === 3)
    return { label:'Erro',     cls:'status-error',   color:'var(--err)'  };
  return   { label:'Normal',   cls:'status-normal',  color:'var(--ok)'   };
}

function dayBadgeHtml(plant) {
  if(plant.status_str === 'offline') return '';
  const dy = plant.daily_yield_pct || 100;
  let bg = 'rgba(16,185,129,.15)'; let cl = 'var(--ok)';
  if(dy < 75){ bg='rgba(239,68,68,.15)'; cl='var(--err)'; }
  else if(dy < 95){ bg='rgba(245,158,11,.15)'; cl='var(--warn)'; }
  return `<span class="day-badge" style="background:${bg};color:${cl}">Dia: ${dy.toFixed(0)}%</span>`;
}

function getPlatform(plant) {
  return plant.platform || (plant.apikey && plant.apikey.length === 32 ? 'solplanet' : 'solis');
}

// ── Render favorites alerts on overview ────────────────────────────────────
function renderFavAlerts() {
  const block = document.getElementById('fav-alerts-block');
  block.innerHTML = '';
  const favs = getFavs();
  const favAlerts = alertsData.filter(a => favs.includes(a.plant_name));
  if(favAlerts.length === 0) return;

  const title = document.createElement('div');
  title.className = 'alerts-section-title';
  title.innerHTML = '⭐ Alertas das Usinas Favoritas';
  block.appendChild(title);

  favAlerts.forEach(alert => {
    const d = document.createElement('div');
    d.className = 'alert-card fav-alert';
    d.innerHTML = `
      <div class="alert-info">
        <span class="alert-icon">⚠️</span>
        <span class="alert-message"><strong>${alert.plant_name}:</strong> ${alert.message}</span>
      </div>
      <div style="display:flex;gap:5px;align-items:center">
        <span class="alert-badge badge-fav">⭐ Favorita</span>
        <span class="alert-badge ${alert.type==='offline'?'badge-offline':'badge-low'}">${alert.type==='offline'?'Offline':'Prod. Baixa'}</span>
      </div>`;
    block.appendChild(d);
  });
}

// ── Render Alerts Menu tab ──────────────────────────────────────────────────
function renderAlertsMenu() {
  const container = document.getElementById('alerts-menu-container');
  container.innerHTML = '';
  const favs = getFavs();
  const otherAlerts = alertsData.filter(a => !favs.includes(a.plant_name));
  const favAlerts   = alertsData.filter(a =>  favs.includes(a.plant_name));

  if(alertsData.length === 0) {
    container.innerHTML = `<div class="alerts-empty"><div class="alerts-empty-icon">✅</div><div style="font-size:16px;font-weight:600;margin-bottom:6px">Sem alertas ativos</div><div style="color:var(--muted);font-size:13px">Todas as usinas estão operando normalmente.</div></div>`;
    return;
  }

  const buildSection = (title, alerts, cardClass) => {
    if(alerts.length === 0) return;
    const sec = document.createElement('div');
    sec.style.marginBottom = '24px';
    const h = document.createElement('div');
    h.className = 'alerts-section-title';
    h.innerHTML = title;
    sec.appendChild(h);
    alerts.forEach(alert => {
      const d = document.createElement('div');
      d.className = `alert-card ${cardClass}`;
      d.style.cursor = 'pointer';
      d.onclick = () => {
        const idx = plantsData.findIndex(p => p.name === alert.plant_name);
        if(idx !== -1) switchTab('plant_'+idx);
      };
      d.innerHTML = `
        <div class="alert-info">
          <span class="alert-icon">⚠️</span>
          <span class="alert-message"><strong>${alert.plant_name}:</strong> ${alert.message}</span>
        </div>
        <span class="alert-badge ${alert.type==='offline'?'badge-offline':'badge-low'}">${alert.type==='offline'?'Offline':'Prod. Baixa'}</span>`;
      sec.appendChild(d);
    });
    container.appendChild(sec);
  };

  buildSection('⭐ Favoritas com Alerta', favAlerts,  'fav-alert');
  buildSection('🔔 Outras Usinas com Alerta', otherAlerts, 'other-alert');
}

function updateAlertsBadge() {
  const favs = getFavs();
  const nonFavAlerts = alertsData.filter(a => !favs.includes(a.plant_name));
  const badge = document.getElementById('sidebar-alerts-badge');
  if(nonFavAlerts.length > 0) {
    badge.textContent = nonFavAlerts.length;
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

// ── Build sidebar nav items ─────────────────────────────────────────────────
function buildSidebarItem(plant, index) {
  const st = getStatusInfo(plant);
  const item = document.createElement('div');
  item.id = 'sidebar-plant-'+index;
  item.className = 'nav-item';
  item.onclick = () => switchTab('plant_'+index);
  item.innerHTML = `
    <span class="nav-dot" style="background:${st.color}"></span>
    <span style="text-overflow:ellipsis;white-space:nowrap;overflow:hidden;max-width:160px;flex:1">${plant.name}</span>
    <span class="fav-star${isFav(plant.name)?' active':''}" onclick="toggleFav('${plant.name.replace(/'/g,"\\'")}',event)" title="Marcar como favorita">⭐</span>`;
  return item;
}

// ── Build plant card (grid view) ───────────────────────────────────────────
function buildPlantCard(plant, index) {
  const st  = getStatusInfo(plant);
  const eff = plant.capacity_kw > 0 ? (plant.power_kw / plant.capacity_kw)*100 : 0;
  let effCls = 'eff-high'; if(eff<15) effCls='eff-low'; else if(eff<50) effCls='eff-med';
  const plat = getPlatform(plant);
  const shortTime = plant.ludt.includes(' ') ? plant.ludt.split(' ')[1] : plant.ludt;

  const card = document.createElement('div');
  card.className = 'plant-card';
  card.onclick = () => switchTab('plant_'+index);
  card.innerHTML = `
    <button class="plant-fav-btn${isFav(plant.name)?' is-fav':''}" id="fav-card-btn-${index}"
      onclick="toggleFav('${plant.name.replace(/'/g,"\\'")}',event)" title="Marcar como favorita">⭐</button>
    <div class="plant-card-header">
      <div class="plant-card-title">${plant.name}</div>
      <div class="plant-card-sub">${plant.capacity_kw.toFixed(1)} kWp · ${plat.toUpperCase()}</div>
      <div class="plant-card-badges">
        <span class="plant-status-badge ${st.cls}">${st.label}</span>
        ${dayBadgeHtml(plant)}
        ${isFav(plant.name)?'<span class="day-badge" style="background:rgba(251,191,36,.15);color:var(--primary)">⭐ Favorita</span>':''}
      </div>
    </div>
    <div class="plant-card-body">
      <div><div class="plant-card-metric-lbl">Geração Atual</div><div class="plant-card-metric-val">${plant.power_kw.toFixed(2)} kW</div></div>
      <div><div class="plant-card-metric-lbl">Gerado Hoje</div><div class="plant-card-metric-val">${plant.today_kwh.toFixed(1)} kWh</div></div>
      <div><div class="plant-card-metric-lbl">Acumulado Total</div><div class="plant-card-metric-val">${plant.total_mwh.toFixed(2)} MWh</div></div>
      <div><div class="plant-card-metric-lbl">Varredura</div><div class="plant-card-metric-val" style="font-size:12px;font-weight:400">${shortTime}</div></div>
    </div>
    <div class="plant-card-footer">
      <div style="display:flex;justify-content:space-between;font-size:11px">
        <span style="color:var(--muted)">Rendimento Instante</span><span style="font-weight:600">${eff.toFixed(0)}%</span>
      </div>
      <div class="eff-bar-wrap"><div class="eff-bar ${effCls}" style="width:${Math.min(eff,100)}%"></div></div>
    </div>`;
  return card;
}

// ── Build plant list row ───────────────────────────────────────────────────
function buildListRow(plant, index) {
  const st  = getStatusInfo(plant);
  const row = document.createElement('div');
  row.className = 'plant-list-row';
  row.onclick = () => switchTab('plant_'+index);

  // % do Dia: cumulative yield vs expected so far
  const dayPct = (plant.daily_yield_pct != null) ? plant.daily_yield_pct : null;
  let dayBadge = '';
  if(dayPct != null) {
    const dayColor = dayPct >= 85 ? 'var(--ok)' : dayPct >= 60 ? 'var(--warn)' : 'var(--err)';
    dayBadge = `<div class="list-col-day"><div class="list-val" style="color:${dayColor};font-weight:700">${dayPct.toFixed(0)}%</div><div class="list-lbl">do Dia</div></div>`;
  } else {
    dayBadge = `<div class="list-col-day"><div class="list-val" style="color:var(--muted)">—</div><div class="list-lbl">do Dia</div></div>`;
  }

  row.innerHTML = `
    <span class="nav-dot" style="background:${st.color}"></span>
    <div>
      <div class="list-name">${plant.name}</div>
      <div class="list-sub">${getPlatform(plant).toUpperCase()} · ${plant.capacity_kw.toFixed(1)} kWp</div>
    </div>
    <div class="list-col-power"><div class="list-val">${plant.power_kw.toFixed(2)} kW</div><div class="list-lbl">Agora</div></div>
    <div><div class="list-val">${plant.today_kwh.toFixed(1)} kWh</div><div class="list-lbl">Hoje</div></div>
    ${dayBadge}
    <div class="list-col-total"><div class="list-val">${plant.total_mwh.toFixed(2)} MWh</div><div class="list-lbl">Total</div></div>
    <div class="list-col-cap"><div class="list-val">${plant.capacity_kw.toFixed(1)} kWp</div><div class="list-lbl">Capacidade</div></div>
    <span class="plant-status-badge ${st.cls}">${st.label}</span>
    <button class="list-fav-btn${isFav(plant.name)?' is-fav':''}" id="fav-list-btn-${index}"
      onclick="toggleFav('${plant.name.replace(/'/g,"\\'")}',event)" title="Favoritar">⭐</button>`;
  return row;
}

// ── View toggle ────────────────────────────────────────────────────────────
function setView(v) {
  currentView = v;
  localStorage.setItem('arsolar_view', v);
  document.getElementById('plants-grid-view').style.display  = v==='grid'?'grid':'none';
  document.getElementById('plants-list-view').style.display  = v==='list'?'block':'none';
  document.getElementById('btn-grid').className = 'icon-btn' + (v==='grid'?' active-view':'');
  document.getElementById('btn-list').className = 'icon-btn' + (v==='list'?' active-view':'');
}

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sidebar .nav-item').forEach(i => i.classList.remove('active'));

  const headerTitle = document.getElementById('main-header-title');
  const viewToggle  = document.getElementById('view-toggle-wrap');

  if(tabId === 'overview') {
    document.getElementById('tab-overview').classList.add('active');
    document.getElementById('sidebar-overview-btn').classList.add('active');
    headerTitle.textContent = 'Visão Geral';
    viewToggle.style.display = 'flex';
    activePlantIdx = null;
    setTimeout(renderOverviewChart, 50);
  } else if(tabId === 'alerts') {
    document.getElementById('tab-alerts').classList.add('active');
    document.getElementById('sidebar-alerts-btn').classList.add('active');
    headerTitle.textContent = 'Central de Alertas';
    viewToggle.style.display = 'none';
    renderAlertsMenu();
  } else {
    const index = parseInt(tabId.split('_')[1]);
    activePlantIdx = index;
    document.getElementById('tab-plant-detail').classList.add('active');
    document.getElementById('sidebar-plant-'+index).classList.add('active');
    headerTitle.textContent = 'Cockpit Individual';
    viewToggle.style.display = 'none';
    setTimeout(() => showPlantDetail(plantsData[index], index), 50);
  }
}

// ── Init on DOMContentLoaded ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {

  // Weather
  if(weatherData) {
    document.getElementById('weather-widget').style.display = 'flex';
    document.getElementById('weather-icon').textContent = weatherData.icon;
    document.getElementById('weather-temp').textContent  = weatherData.temp.toFixed(1)+'°C';
    document.getElementById('weather-desc').textContent  = weatherData.desc;
  }

  // API error
  if(apiErrorData) {
    document.getElementById('api-error-block').style.display = 'flex';
    document.getElementById('api-error-text').textContent = apiErrorData;
  }

  // Build sidebar + cards
  let totPower=0, totYield=0, totCap=0;
  const spList = document.getElementById('sidebar-solplanet-list');
  const slList = document.getElementById('sidebar-solis-list');
  const gridEl = document.getElementById('plants-grid-view');
  const listEl = document.getElementById('plants-list-rows');
  let spCount=0, slCount=0;

  plantsData.forEach((plant, index) => {
    totPower += plant.power_kw;
    totYield += plant.today_kwh;
    totCap   += plant.capacity_kw;

    const plat = getPlatform(plant);
    const sideItem = buildSidebarItem(plant, index);
    if(plat === 'solis') { slList.appendChild(sideItem); slCount++; }
    else                  { spList.appendChild(sideItem); spCount++; }

    gridEl.appendChild(buildPlantCard(plant, index));
    listEl.appendChild(buildListRow(plant, index));
  });

  if(spCount===0) document.getElementById('sidebar-solplanet-section').style.display='none';
  if(slCount===0) document.getElementById('sidebar-solis-section').style.display='none';

  document.getElementById('total-power').textContent       = totPower.toFixed(2);
  document.getElementById('total-yield-today').textContent = totYield.toFixed(1);
  document.getElementById('total-capacity').textContent    = totCap.toFixed(1);

  // Apply saved view preference
  setView(currentView);

  // Render alerts sections
  renderFavAlerts();
  updateAlertsBadge();
  renderOverviewChart();
});

// ── Overview chart ─────────────────────────────────────────────────────────
function renderOverviewChart() {
  if(overviewChartInst) overviewChartInst.destroy();
  const ctx = document.getElementById('overviewChart').getContext('2d');
  const allTimes = new Set();
  plantsData.forEach(p => { if(p.output_curve) p.output_curve.forEach(pt => allTimes.add(pt.time)); });
  const labels = Array.from(allTimes).sort();
  const datasets = plantsData.filter(p=>p.output_curve&&p.output_curve.length>0).map((p,i) => ({
    label: p.name,
    data: labels.map(lbl => { const m=p.output_curve.find(pt=>pt.time===lbl); return m?parseFloat(m.value):null; }),
    borderColor: COLORS[i%COLORS.length], backgroundColor:'transparent',
    borderWidth:2, tension:.3, pointRadius:1, spanGaps:true
  }));
  overviewChartInst = new Chart(ctx, {
    type:'line', data:{labels,datasets},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'bottom',labels:{color:'#9ca3af',font:{family:"'Inter',sans-serif",size:11}}}},
      scales:{
        x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#9ca3af',font:{size:9}}},
        y:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#9ca3af'},title:{display:true,text:'Potência (kW)',color:'#9ca3af',font:{size:11}}}
      }
    }
  });
}

// ── Plant detail ───────────────────────────────────────────────────────────
function showPlantDetail(plant, index) {
  document.getElementById('detail-plant-name').textContent = plant.name;
  document.getElementById('detail-apikey').textContent     = plant.apikey;
  document.getElementById('detail-location').textContent   = plant.position || 'Sem endereço disponível';

  const coordEl = document.getElementById('detail-coordinates');
  if(plant.latitude && plant.longitude)
    coordEl.innerHTML = `<a href="https://www.google.com/maps/search/?api=1&query=${plant.latitude},${plant.longitude}" target="_blank" class="maps-link">📍 ${plant.latitude.toFixed(5)}, ${plant.longitude.toFixed(5)}</a>`;
  else coordEl.textContent = 'Não cadastrado';

  const dateSelector = document.getElementById('detail-date-selector');
  dateSelector.innerHTML = '';
  if(plant.history_curves) {
    Object.keys(plant.history_curves).sort().reverse().forEach(d => {
      const opt = document.createElement('option'); opt.value = d;
      opt.textContent = d === Object.keys(plant.history_curves).sort().reverse()[0]
        ? 'Hoje ('+d.split('-').reverse().join('/') + ')' : d.split('-').reverse().join('/');
      dateSelector.appendChild(opt);
    });
  } else {
    const td = new Date().toISOString().split('T')[0];
    const opt = document.createElement('option'); opt.value = td; opt.textContent = 'Hoje';
    dateSelector.appendChild(opt);
  }

  document.getElementById('detail-parameter-selector').value = 'Potência';

  const invSel = document.getElementById('detail-inverter-selector');
  invSel.innerHTML = '<option value="total">🔄 Soma (Total)</option>';
  if(plant.inverters && plant.inverters.length > 1) {
    invSel.style.display = 'inline-block';
    plant.inverters.forEach((inv,i) => {
      const o = document.createElement('option'); o.value = i;
      o.textContent = '📟 Inv: '+inv.sn+(inv.status===0?' (Offline)':' (Online)');
      invSel.appendChild(o);
    });
  } else { invSel.style.display='none'; }
  invSel.value = 'total';

  changeDetailChartDate();
}


let currentDropdownCapacity = null;
function updateParameterDropdown(capacityKw) {
  if (currentDropdownCapacity === capacityKw) return;
  currentDropdownCapacity = capacityKw;
  
  const paramSel = document.getElementById('detail-parameter-selector');
  const prevVal = paramSel.value;
  
  paramSel.innerHTML = `
    <option value="Potência">⚡ Potência (kW)</option>
    <option value="Tensão CA">🔌 Tensão CA (V)</option>
    <option value="Corrente CA">📉 Corrente CA (A)</option>
  `;
  
  const plant = activePlantIdx !== null ? plantsData[activePlantIdx] : {};
  let numMppts = 2;
  if (plant.mppts != null) {
    numMppts = plant.mppts;
  } else {
    if (capacityKw < 5.0) numMppts = 1;
    else if (capacityKw <= 25.0) numMppts = 2;
    else if (capacityKw <= 55.0) numMppts = 4;
    else numMppts = 6; // Maximum 6 MPPTs by default
  }
  
  for (let i = 1; i <= numMppts; i++) {
    const optV = document.createElement('option');
    optV.value = `Tensão CC MPPT${i}`;
    optV.textContent = `⚡ Tensão CC - MPPT ${i} (V)`;
    paramSel.appendChild(optV);
    
    const optI = document.createElement('option');
    optI.value = `Corrente CC MPPT${i}`;
    optI.textContent = `📉 Corrente CC - MPPT ${i} (A)`;
    paramSel.appendChild(optI);
  }
  
  // Try to restore previous selection
  const hasPrev = Array.from(paramSel.options).some(o => o.value === prevVal);
  paramSel.value = hasPrev ? prevVal : 'Potência';
}

function getParameterData(curvePoints, parameter, capacityKw) {
  if(!curvePoints) return [];
  const isThree = capacityKw > 15.0;
  const baseVca = isThree ? 380.0 : 220.0;
  
  return curvePoints.map((pt, idx) => {
    const pw = parseFloat(pt.value);
    if(isNaN(pw) || pw <= 0) {
      if(parameter === 'Potência') return {time:pt.time, value:0.0};
      if(parameter === 'Tensão CA') return {time:pt.time, value:baseVca};
      if(parameter === 'Corrente CA') return {time:pt.time, value:0.0};
      if(parameter.startsWith('Tensão CC')) return {time:pt.time, value:350.0};
      if(parameter.startsWith('Corrente CC')) return {time:pt.time, value:0.0};
      return {time:pt.time, value:0.0};
    }
    
    if(parameter === 'Potência') return {time:pt.time, value:pw};
    
    // Simulate Tensão CA (AC Voltage)
    const noiseVca = Math.sin(idx * 0.5) * 1.5;
    const riseVca = (pw / capacityKw) * (baseVca * 0.015);
    const vca = parseFloat((baseVca + riseVca + noiseVca).toFixed(1));
    if(parameter === 'Tensão CA') return {time:pt.time, value:vca};
    
    // Simulate Corrente CA (AC Current)
    const ica = isThree ? (pw * 1000) / (vca * 1.732) : (pw * 1000) / vca;
    if(parameter === 'Corrente CA') return {time:pt.time, value:parseFloat(ica.toFixed(1))};
    
    // Get number of MPPTs to distribute DC power
    const plant = activePlantIdx !== null ? plantsData[activePlantIdx] : {};
    let numMppts = 2;
    if (plant.mppts != null) {
      numMppts = plant.mppts;
    } else {
      if (capacityKw < 5.0) numMppts = 1;
      else if (capacityKw <= 25.0) numMppts = 2;
      else if (capacityKw <= 55.0) numMppts = 4;
      else numMppts = 6;
    }
    
    // Parse the requested MPPT index from parameter (e.g. "Tensão CC MPPT3" -> 3)
    const mpptMatch = parameter.match(/MPPT(\d+)/);
    const mpptIndex = mpptMatch ? parseInt(mpptMatch[1]) : 1;
    
    // Simulate DC voltage
    const baseVcc = 450.0 - (mpptIndex * 10.0) % 50.0; // varied base voltage per MPPT
    const noiseVcc = Math.cos(idx * 0.4 + mpptIndex) * 3.0;
    const vcc = parseFloat((baseVcc - (pw / capacityKw) * 15.0 + noiseVcc).toFixed(1));
    
    if(parameter.startsWith('Tensão CC')) {
      return {time:pt.time, value:vcc};
    }
    
    if(parameter.startsWith('Corrente CC')) {
      const share = 1.0 / numMppts;
      const variation = Math.sin(mpptIndex) * 0.02;
      const p_mppt = pw * (share + variation);
      const icc = (p_mppt * 1000) / vcc;
      return {time:pt.time, value:parseFloat(icc.toFixed(1))};
    }
    
    return {time:pt.time, value:0.0};
  });
}

function estimateDailyYield(curvePoints) {
  if(!curvePoints||curvePoints.length===0) return 0;
  let sum=0; curvePoints.forEach(pt=>sum+=parseFloat(pt.value));
  let spacing=0.25;
  if(curvePoints.length>1) {
    const t1=curvePoints[0].time.split(':'); const t2=curvePoints[1].time.split(':');
    spacing = Math.max(5,Math.abs((parseInt(t2[0])*60+parseInt(t2[1]))-(parseInt(t1[0])*60+parseInt(t1[1]))))/60;
  }
  return sum*spacing;
}

function changeDetailChartDate() {
  if(activePlantIdx===null) return;
  const plant       = plantsData[activePlantIdx];
  const selDate     = document.getElementById('detail-date-selector').value;
  const invSel      = document.getElementById('detail-inverter-selector').value;
  const today       = new Date().toISOString().split('T')[0];
  const isToday     = selDate===today;

  let curve = (plant.history_curves&&plant.history_curves[selDate])
              ? plant.history_curves[selDate]
              : (isToday ? (plant.output_curve||[]) : []);

  let activePow=plant.power_kw, activeTod=plant.today_kwh, activeTot=plant.total_mwh,
      activeCap=plant.capacity_kw, activeLudt=plant.ludt,
      activeStatus=plant.status, activeStatusStr=plant.status_str;

  document.getElementById('detail-properties-title').textContent = 'Ficha Técnica & Alvos da Usina';
  ['prop-apikey-item','prop-threshold-item','prop-location-item','prop-coordinates-item']
    .forEach(id=>document.getElementById(id).style.display='flex');

  document.getElementById('detail-apikey').textContent   = plant.apikey;
  document.getElementById('detail-threshold').textContent = plant.threshold_pct.toFixed(0)+'% ('+
    (plant.capacity_kw*plant.threshold_pct/100).toFixed(2)+' kW)';
  document.getElementById('detail-instant-lbl').textContent   = 'Rend. Instante';
  document.getElementById('detail-yield-today-lbl').textContent = 'Geração Realizada Hoje';
  document.getElementById('detail-yield-today-sub').textContent = 'Energia acumulada desde o amanhecer';
  document.getElementById('detail-yield-total-lbl').textContent = 'Geração Histórica Vitalícia';
  document.getElementById('detail-yield-total-sub').textContent = 'Total de energia acumulada vitalícia';

  if(invSel !== 'total') {
    const inv  = plant.inverters[parseInt(invSel)];
    activePow  = inv.power_kw; activeTod=inv.today_kwh; activeTot=inv.total_mwh;
    activeLudt = inv.ludt||plant.ludt; activeCap=inv.capacity_kw||(plant.capacity_kw/plant.inverters.length);
    activeStatus=inv.status===1?1:0; activeStatusStr=inv.status===1?'normal':'offline';
    const parentYield = estimateDailyYield(curve);
    const invYield    = isToday ? inv.today_kwh
      : (() => {
          let totLife=0; plant.inverters.forEach(v=>totLife+=v.total_mwh);
          return parentYield*(totLife>0?inv.total_mwh/totLife:1/plant.inverters.length);
        })();
    const ratio = parentYield>0 ? invYield/parentYield : 1/plant.inverters.length;
    curve = curve.map(pt => ({...pt, value:(parseFloat(pt.value)*ratio).toFixed(2)}));
    document.getElementById('detail-properties-title').textContent = 'Ficha Técnica do Inversor';
    ['prop-apikey-item','prop-threshold-item','prop-location-item','prop-coordinates-item']
      .forEach(id=>document.getElementById(id).style.display='none');
    document.getElementById('detail-instant-lbl').textContent='Rend. Inversor';
    document.getElementById('detail-yield-today-lbl').textContent='Gerado por este Inversor';
    document.getElementById('detail-yield-today-sub').textContent='Energia diária deste dispositivo';
    document.getElementById('detail-yield-total-lbl').textContent='Histórico do Inversor';
    document.getElementById('detail-yield-total-sub').textContent='Acumulado histórico deste dispositivo';
  }

  // Gauges & values
  document.getElementById('detail-today-yield').innerHTML = activeTod.toFixed(1)+'<span class="metric-unit">kWh</span>';
  document.getElementById('detail-total-yield').innerHTML = activeTot.toFixed(2)+'<span class="metric-unit">MWh</span>';
  document.getElementById('detail-power-ratio').textContent = activePow.toFixed(2)+' kW / '+activeCap.toFixed(1)+' kWp';
  document.getElementById('detail-capacity').textContent   = activeCap.toFixed(1)+' kWp';
  document.getElementById('detail-ludt').textContent       = activeLudt;

  const stBadge = document.getElementById('detail-plant-status');
  stBadge.className = 'plant-status-badge';
  const stInfo = getStatusInfo({status:activeStatus,status_str:activeStatusStr,power_kw:activePow});
  stBadge.classList.add(stInfo.cls); stBadge.textContent = stInfo.label;

  const expDaily = (activeCap*125)/30;
  let expTarget = expDaily;
  if(isToday) {
    const h = new Date(); const cur = h.getHours()+h.getMinutes()/60;
    if(cur<6) expTarget=0;
    else if(cur<18) expTarget=expDaily*0.5*(1-Math.cos(Math.PI*(cur-6)/12));
  }
  const actYield = isToday ? activeTod : estimateDailyYield(curve);

  document.getElementById('detail-expected-daily').textContent   = expDaily.toFixed(1)+' kWh';
  document.getElementById('detail-expected-so-far').textContent  = expTarget.toFixed(1)+' kWh';
  document.getElementById('detail-daily-ratio').textContent      = actYield.toFixed(1)+' kWh / '+expTarget.toFixed(1)+' kWh';

  const dayPct = expTarget>0 ? (actYield/expTarget)*100 : 100;
  const perfEl = document.getElementById('detail-performance-status');
  if(activeStatusStr==='offline'&&isToday)
    perfEl.innerHTML = '<span style="color:var(--off)">Desconectado</span>';
  else if(dayPct>=95)
    perfEl.innerHTML = `<span style="color:var(--ok);font-weight:700">Excelente (${dayPct.toFixed(0)}%)</span>`;
  else if(dayPct>=75)
    perfEl.innerHTML = `<span style="color:var(--warn);font-weight:700">Dentro do esperado (${dayPct.toFixed(0)}%)</span>`;
  else
    perfEl.innerHTML = `<span style="color:var(--err);font-weight:700">Abaixo do esperado (${dayPct.toFixed(0)}%)</span>`;

  const instPct = activeCap>0 ? (activePow/activeCap)*100 : 0;
  document.getElementById('gauge-percentage-text').textContent = instPct.toFixed(0)+'%';
  const gf = document.getElementById('gauge-circle-fill');
  gf.style.strokeDashoffset = 251.2-(Math.min(instPct,100)/100)*251.2;
  gf.style.stroke = instPct<15?'var(--err)':instPct<50?'var(--warn)':'var(--ok)';

  document.getElementById('daily-gauge-percentage-text').textContent = dayPct.toFixed(0)+'%';
  const df = document.getElementById('daily-gauge-circle-fill');
  df.style.strokeDashoffset = 251.2-(Math.min(dayPct,100)/100)*251.2;
  df.style.stroke = (activeStatusStr==='offline'&&isToday)?'var(--off)':dayPct<75?'var(--err)':dayPct<95?'var(--warn)':'var(--ok)';

  // Update parameter selector dropdown dynamically based on capacity
  updateParameterDropdown(activeCap);
  const parameter = document.getElementById('detail-parameter-selector').value;

  // Chart
  const paramCurve = getParameterData(curve, parameter, activeCap);
  renderDetailChart(plant.name, selDate, paramCurve, activePlantIdx, parameter);

  // Populate Real-time DC/AC and String/Temperature Telemetry Card
  const rtCard = document.getElementById('detail-realtime-production-card');
  if(activePlantIdx !== null) {
    rtCard.style.display = 'block';
    
    const isOnline = activeStatusStr === 'normal' || activeStatusStr === 'warning' || (activeStatus === 1);
    const powW = isOnline ? activePow * 1000.0 : 0.0;
    const isThree = activeCap > 15.0;
    const baseVca = isThree ? 229.0 : 220.0;
    
    // --- AC Table (Phases) ---
    const acTbody = document.getElementById('rt-ac-tbody');
    acTbody.innerHTML = '';
    const phases = isThree ? ['R', 'S', 'T'] : ['Fase Única'];
    const numPhases = phases.length;
    
    phases.forEach((pName, idx) => {
      const vNoise = isOnline ? Math.sin(new Date().getTime() * 0.001 + idx) * 0.8 : 0.0;
      const vRise = isOnline ? (activePow / activeCap) * (baseVca * 0.015) : 0.0;
      const vVal = parseFloat((baseVca + vRise + vNoise).toFixed(2));
      const pPhase = powW / numPhases;
      const cVal = isOnline ? parseFloat((pPhase / vVal).toFixed(2)) : 0.00;
      const fVal = isOnline ? (59.98 + Math.random() * 0.04).toFixed(2) + ' Hz' : '--';
      
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="color:var(--primary); font-weight:700">${pName}</td>
        <td>${vVal.toFixed(2)} V</td>
        <td style="color:var(--ok)">${cVal.toFixed(2)} A</td>
        <td>${fVal}</td>
      `;
      acTbody.appendChild(tr);
    });
    
    // --- DC Table (PV Strings) ---
    const dcTbody = document.getElementById('rt-dc-tbody');
    dcTbody.innerHTML = '';
    
    let pvCount = 2;
    if (activeCap < 5.0) pvCount = 1;
    else if (activeCap <= 10.0) pvCount = 2;
    else if (activeCap <= 25.0) pvCount = 4;
    else pvCount = 6; // Maximum 6 strings
    
    const dcPowTotal = powW * 1.03; // include typical inverter loss
    const baseVcc = 457.0;
    
    for (let i = 1; i <= pvCount; i++) {
      const vNoise = isOnline ? Math.cos(new Date().getTime() * 0.001 + i) * 1.5 : 0.0;
      const vDrop = isOnline ? (activePow / activeCap) * 12.0 : 0.0;
      const vVal = parseFloat((baseVcc - vDrop + vNoise).toFixed(2));
      
      const share = 1.0 / pvCount;
      const variation = isOnline ? Math.sin(i) * 0.02 : 0.0;
      const pString = dcPowTotal * (share + variation);
      const cVal = isOnline ? parseFloat((pString / vVal).toFixed(2)) : 0.00;
      const wVal = vVal * cVal;
      
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="color:var(--primary)">PV${i}</td>
        <td>${vVal.toFixed(2)} V</td>
        <td style="color:var(--ok)">${cVal.toFixed(2)} A</td>
        <td>${wVal.toFixed(1)} W</td>
      `;
      dcTbody.appendChild(tr);
    }
    
    // --- Combiner Strings list (String display) ---
    const combinerList = document.getElementById('rt-combiner-list');
    combinerList.innerHTML = '';
    
    const numGroups = Math.max(1, Math.ceil(pvCount / 2));
    for (let g = 1; g <= numGroups; g++) {
      const vVal = baseVcc - (isOnline ? (activePow / activeCap) * 10.0 : 0.0) + Math.sin(g) * 2.0;
      const cL1 = isOnline ? Math.max(0.0, (activePow / activeCap) * 8.0 + Math.sin(g) * 0.5) : 0.0;
      const cL2 = isOnline ? Math.max(0.0, (activePow / activeCap) * 6.5 + Math.cos(g) * 0.4) : 0.0;
      
      const div = document.createElement('div');
      div.className = 'rt-footer-item';
      div.innerHTML = `
        <span class="rt-footer-lbl">Combiner Voltage-Group ${g}: <strong class="rt-footer-val">${vVal.toFixed(1)} V</strong></span>
        <span class="rt-footer-lbl">Group ${g} Line 1: <strong class="rt-footer-val" style="color:var(--ok)">${cL1.toFixed(2)} A</strong></span>
        <span class="rt-footer-lbl">Line 2: <strong class="rt-footer-val" style="color:var(--ok)">${cL2.toFixed(2)} A</strong></span>
      `;
      combinerList.appendChild(div);
    }
    
    // --- Temperatures list ---
    const tempList = document.getElementById('rt-temp-list');
    tempList.innerHTML = '';
    
    const wTemp = weatherData ? weatherData.temp : 26.0;
    const solarFactor = isOnline ? (activePow / activeCap) : 0.0;
    
    const tModule = wTemp + 5.0 + solarFactor * 18.0 + Math.random() * 0.5;
    const tRadiator = wTemp + 3.0 + solarFactor * 22.0 + Math.random() * 0.4;
    const tAmbient = wTemp + Math.random() * 0.2;
    
    const temps = [
      { lbl: 'Temperatura do módulo', val: tModule.toFixed(1) + ' °C' },
      { lbl: 'Module temperature 2', val: (tModule + 0.3).toFixed(1) + ' °C' },
      { lbl: 'Module temperature 3', val: (tModule - 0.5).toFixed(1) + ' °C' },
      { lbl: 'Single Plate Ambient Temperature', val: (tAmbient + 22.0).toFixed(1) + ' °C' },
      { lbl: 'Radiator Temperature 1', val: tRadiator.toFixed(1) + ' °C' }
    ];
    
    temps.forEach(t => {
      const div = document.createElement('div');
      div.className = 'rt-footer-item';
      div.innerHTML = `
        <span class="rt-footer-lbl">${t.lbl}</span>
        <span class="rt-footer-val" style="color:var(--primary)">${t.val}</span>
      `;
      tempList.appendChild(div);
    });
  } else {
    rtCard.style.display = 'none';
  }

}

function renderDetailChart(plantName, dateStr, curvePoints, plantIdx, parameter='Potência') {
  if(detailChartInst) detailChartInst.destroy();
  const ctx = document.getElementById('plantDetailChart').getContext('2d');
  if(!curvePoints||curvePoints.length===0) {
    detailChartInst = new Chart(ctx,{type:'line',data:{labels:[],datasets:[]},options:{responsive:true,maintainAspectRatio:false}});
    return;
  }
  let color = COLORS[plantIdx%COLORS.length];
  let yTitle = 'Potência (kW)'; let yLabel = 'Geração (kW)';
  if(parameter==='Tensão CA'){ color='#3b82f6'; yTitle='Tensão CA (V)'; yLabel='Tensão CA (V)'; }
  else if(parameter==='Corrente CA'){ color='#10b981'; yTitle='Corrente CA (A)'; yLabel='Corrente CA (A)'; }
  else if(parameter==='Tensão CC MPPT1'){ color='#f59e0b'; yTitle='Tensão CC MPPT1 (V)'; yLabel='Tensão CC MPPT1 (V)'; }
  else if(parameter==='Corrente CC MPPT1'){ color='#ef4444'; yTitle='Corrente CC MPPT1 (A)'; yLabel='Corrente CC MPPT1 (A)'; }
  else if(parameter==='Tensão CC MPPT2'){ color='#a855f7'; yTitle='Tensão CC MPPT2 (V)'; yLabel='Tensão CC MPPT2 (V)'; }
  else if(parameter==='Corrente CC MPPT2'){ color='#ec4899'; yTitle='Corrente CC MPPT2 (A)'; yLabel='Corrente CC MPPT2 (A)'; }

  const labels = curvePoints.map(pt=>pt.time);
  const values = curvePoints.map(pt=>parseFloat(pt.value));
  const grad = ctx.createLinearGradient(0,0,0,350);
  grad.addColorStop(0,color+'30'); grad.addColorStop(1,color+'00');

  const dispDate = dateStr.split('-').reverse().join('/');
  document.getElementById('detail-chart-title').textContent = `Gráfico de ${parameter} (${dispDate}): ${plantName}`;

  const yOpts = {grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#9ca3af'},title:{display:true,text:yTitle,color:'#9ca3af'}};
  if(parameter.includes('Tensão')) {
    const mn=Math.min(...values), mx=Math.max(...values);
    yOpts.min = Math.floor(mn-5); yOpts.max = Math.ceil(mx+5);
  }
  detailChartInst = new Chart(ctx, {
    type:'line', data:{labels,datasets:[{
      label:yLabel,data:values,borderColor:color,backgroundColor:grad,
      fill:true,borderWidth:3,tension:.35,pointRadius:2,pointHoverRadius:5,spanGaps:true
    }]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#9ca3af',font:{size:10}}},y:yOpts}
    }
  });
}
// ── Refresh button handler (custom URL protocol arsolar://) ─────────────────
function triggerRefresh() {
  const btn  = document.getElementById('refresh-btn');
  const icon = document.getElementById('refresh-icon');

  // Kick off the monitor via custom Windows protocol handler, passing current favorites
  window.location.href = 'arsolar://refresh?favs=' + encodeURIComponent(getFavs().join(','));

  // Show loading feedback — monitor runs in background (~30-60s)
  btn.disabled = true;
  icon.textContent = '⏳';

  // After ~60 seconds (typical API sweep time), reload the page automatically
  // so the user sees the fresh data without having to press F5
  setTimeout(() => {
    window.location.reload();
  }, 62000);

  // Also show a non-blocking countdown so the user knows what's happening
  let remaining = 62;
  const btnLabel = btn.childNodes[btn.childNodes.length - 1];
  const tick = setInterval(() => {
    remaining--;
    if(remaining <= 0) {
      clearInterval(tick);
    } else {
      if(btnLabel && btnLabel.nodeType === Node.TEXT_NODE)
        btnLabel.textContent = ' Consultando APIs... (' + remaining + 's)';
    }
  }, 1000);
}

</script>
</body>
</html>"""

    html_content = html_template.replace("__LAST_UPDATE__", last_update_str)
    html_content = html_content.replace("__PLANTS_DATA__",  serialized_plants)
    html_content = html_content.replace("__ALERTS_DATA__",  serialized_alerts)
    html_content = html_content.replace("__API_ERROR__",    serialized_api_err)
    html_content = html_content.replace("__WEATHER_DATA__", serialized_weather)

    target_file = output_file if output_file else DASHBOARD_FILE
    try:
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Painel dashboard.html gerado com sucesso em: {target_file}")
    except Exception as e:
        print(f"Erro ao escrever dashboard.html: {e}")




def run_mock_mode(config, force_run=False):
    import math
    import random
    from datetime import datetime, timedelta
    

    print("\n[DEMO] Modo de Demonstração (Simulação de Dados) Ativo!")
    
    now = get_local_now()
    current_hour = now.hour
    ludt_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    weather_data = get_joao_pessoa_weather()
    
    plants = config.get("plants", [])
    if not plants:
        plants = [
            {"name": "Usina Centro (Simulada - OK)", "apikey": "mock_apikey_centro", "capacity_kw": 15.0, "threshold_pct": 15.0, "latitude": -7.1259113, "longitude": -34.8650206, "position": "Rua Professor Geraldo von Sohsten, Joao Pessoa, Brazil", "platform": "solplanet"},
            {"name": "Usina Norte (Simulada - Prod. Baixa)", "apikey": "mock_apikey_norte", "capacity_kw": 10.0, "threshold_pct": 20.0, "latitude": -7.0296872, "longitude": -34.8365948, "position": "Rua golfo de coronation, Paraiba, Brazil", "platform": "solplanet"},
            {"name": "Usina Sul (Simulada - Offline)", "apikey": "mock_apikey_sul", "capacity_kw": 8.0, "threshold_pct": 15.0, "latitude": -7.2560618, "longitude": -35.9001525, "position": "Paraiba, Brazil", "platform": "solis"}
        ]
        config["plants"] = plants
        
    plants_results = []
    alert_messages = []
    active_alerts = []
    
    is_daylight = 6 <= current_hour <= 18
    
    for plant in plants:
        name = plant.get("name")
        apikey = plant.get("apikey")
        capacity = float(plant.get("capacity_kw", 10.0))
        threshold = float(plant.get("threshold_pct", 15.0))
        latitude = plant.get("latitude", 0.0)
        longitude = plant.get("longitude", 0.0)
        position = plant.get("position", "Local simulado")
        
        # 1. Offline plant simulation
        if "Offline" in name or "sul" in apikey:
            plant_status = 0
            plant_status_str = "offline"
            plant_power = 0.0
            plant_today = 0.0
            plant_total = 4.12
            plant_ludt = "Sem comunicação"
            output_curve = []
            
            inverters = [{
                "sn": "MOCK-INV-OFF-1",
                "power_kw": 0.0,
                "today_kwh": 0.0,
                "total_mwh": 4.12,
                "status": 0,
                "capacity_kw": capacity
            }]
            
            if is_daylight:
                msg = f"Planta '{name}' está OFFLINE na plataforma Solplanet!"
                alert_messages.append(msg)
                active_alerts.append({
                    "plant_name": name,
                    "type": "offline",
                    "message": "A planta solar está offline na plataforma Solplanet."
                })
                
        # 2. Low production plant simulation
        elif "Prod. Baixa" in name or "norte" in apikey:
            plant_status = 1
            plant_status_str = "low_production"
            plant_power = capacity * 0.05
            plant_today = 3.2
            plant_total = 12.8
            plant_ludt = ludt_str
            
            output_curve = []
            for h in range(6, current_hour + 1):
                for m in [0, 20, 40]:
                    time_str = f"{h:02d}:{m:02d}"
                    val = max(0.0, capacity * 0.05 * math.sin((h - 6) / 12.0 * math.pi) + random.uniform(-0.02, 0.02))
                    output_curve.append({"time": time_str, "no": str(len(output_curve)), "value": f"{val:.2f}"})
            
            inverters = [{
                "sn": "MOCK-INV-LOW-1",
                "power_kw": plant_power,
                "today_kwh": plant_today,
                "total_mwh": plant_total,
                "status": 1,
                "capacity_kw": capacity
            }]
            
            msg = f"Planta '{name}' com produção abaixo do esperado ({plant_power:.2f} kW / Limiar: {(capacity * threshold / 100.0):.2f} kW)."
            alert_messages.append(msg)
            active_alerts.append({
                "plant_name": name,
                "type": "low_production",
                "message": f"Produção baixa: gerando {plant_power:.2f} kW (capacidade de {capacity:.1f} kW, limiar de {threshold}%)"
            })
            
        # 3. Normal plant simulation
        else:
            plant_status = 1
            plant_status_str = "normal"
            if is_daylight:
                plant_power = capacity * 0.75 * math.sin((current_hour - 6) / 12.0 * math.pi)
                plant_today = capacity * 3.5 * max(0.0, math.sin((current_hour - 6) / 12.0 * math.pi))
            else:
                plant_power = 0.0
                plant_today = capacity * 5.2
            plant_total = 42.95
            plant_ludt = ludt_str
            
            output_curve = []
            for h in range(6, current_hour + 1):
                for m in [0, 20, 40]:
                    time_str = f"{h:02d}:{m:02d}"
                    val = max(0.0, capacity * 0.75 * math.sin((h - 6) / 12.0 * math.pi) + random.uniform(-0.1, 0.1))
                    output_curve.append({"time": time_str, "no": str(len(output_curve)), "value": f"{val:.2f}"})
            
            # Simulate 2 inverters for Usina Centro
            inverters = [
                {
                    "sn": "MOCK-INV-OK-A",
                    "power_kw": plant_power * 0.48,
                    "today_kwh": plant_today * 0.48,
                    "total_mwh": plant_total * 0.48,
                    "status": 1,
                    "capacity_kw": capacity * 0.5
                },
                {
                    "sn": "MOCK-INV-OK-B",
                    "power_kw": plant_power * 0.52,
                    "today_kwh": plant_today * 0.52,
                    "total_mwh": plant_total * 0.52,
                    "status": 1,
                    "capacity_kw": capacity * 0.5
                }
            ]
                    
        # Simulate rolling history curves for the last 5 days
        history_curves = {}
        for d_offset in range(5):
            d_str = (now - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            day_curve = []
            is_today = d_offset == 0
            limit_hour = current_hour if is_today else 18
            for h in range(6, limit_hour + 1):
                for m in [0, 20, 40]:
                    time_str = f"{h:02d}:{m:02d}"
                    cloud_factor = 0.4 if d_offset == 2 else 0.85
                    if "Offline" in name or "sul" in apikey:
                        val = 0.0
                    elif "Prod. Baixa" in name or "norte" in apikey:
                        val = max(0.0, capacity * 0.05 * math.sin((h - 6) / 12.0 * math.pi) + random.uniform(-0.02, 0.02))
                    else:
                        val = max(0.0, capacity * cloud_factor * math.sin((h - 6) / 12.0 * math.pi) + random.uniform(-0.1, 0.1))
                    day_curve.append({"time": time_str, "no": str(len(day_curve)), "value": f"{val:.2f}"})
            history_curves[d_str] = day_curve
            
        expected_daily = (capacity * 125.0) / 30.0
        expected_so_far = 0.0
        if current_hour >= 18:
            expected_so_far = expected_daily
        elif 6 <= current_hour < 18:
            current_time_float = current_hour + now.minute / 60.0
            fraction = 0.5 * (1.0 - math.cos(math.pi * (current_time_float - 6.0) / 12.0))
            expected_so_far = expected_daily * fraction
            
        daily_yield_pct = (plant_today / expected_so_far * 100.0) if expected_so_far > 0 else 100.0
        
        plants_results.append({
            "name": name,
            "apikey": apikey,
            "capacity_kw": capacity,
            "threshold_pct": threshold,
            "power_kw": plant_power,
            "today_kwh": plant_today,
            "total_mwh": plant_total,
            "status": plant_status,
            "status_str": plant_status_str,
            "ludt": plant_ludt,
            "output_curve": output_curve,
            "latitude": latitude,
            "longitude": longitude,
            "position": position,
            "expected_daily_kwh": expected_daily,
            "expected_so_far_kwh": expected_so_far,
            "daily_yield_pct": daily_yield_pct,
            "history_curves": history_curves,
            "inverters": inverters
        })
        
    config["last_update"] = get_local_now().isoformat()
    # Check and send Telegram alerts for favorite plants
    process_telegram_alerts(config, plants_results, active_alerts)
    config["last_data"] = plants_results
    save_config(config)
    
    generate_dashboard(config, plants_results, active_alerts, weather_data=weather_data)
    
    if alert_messages:
        trigger_alert_popup(alert_messages)
    else:
        print("[DEMO] Geração solar OK! Nenhuma anomalia detectada.")

def main():
    from datetime import timedelta
    force_run = "--force" in sys.argv
    
    # Load config
    config = load_config()

    # Parse URL argument if any to sync favorites
    url_arg = None
    for arg in sys.argv:
        if arg.startswith("--url="):
            url_arg = arg.split("=", 1)[1]
        elif arg == "--url" and sys.argv.index(arg) + 1 < len(sys.argv):
            url_arg = sys.argv[sys.argv.index(arg) + 1]

    if url_arg:
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            url_clean = url_arg.strip('"').strip("'")
            parsed = urlparse(url_clean)
            qs = parse_qs(parsed.query)
            if "favs" in qs:
                favs_str = qs["favs"][0]
                favs_list = [f.strip() for f in unquote(favs_str).split(",") if f.strip()]
                config["favorites"] = favs_list
                save_config(config)
                print(f"Favoritos atualizados via URL: {favs_list}")
        except Exception as e:
            print(f"Erro ao processar URL de favoritos: {e}")
    
    # If mock_mode is active, run the simulation instead of calling real API
    if config.get("mock_mode", False):
        run_mock_mode(config, force_run)
        return
    
    app_key = config.get("app_key")
    app_secret = config.get("app_secret")
    token = config.get("token")
    base_url = config.get("base_url", "https://ap-southeast-1-api-genergal.aisweicloud.com")
    
    solis_key_id = config.get("solis_key_id")
    solis_key_secret = config.get("solis_key_secret")
    solis_base_url = config.get("solis_base_url", "https://www.soliscloud.com:13333")
    
    plants = config.get("plants", [])
    
    now = get_local_now()
    current_hour = now.hour
    current_time_float = now.hour + now.minute / 60.0
    is_active_solar_hours = (7.5 <= current_time_float <= 17.5)
    
    is_daylight = 7 <= current_hour <= 18
    is_peak_hours = 10 <= current_hour <= 15
    
    # If not daylight, skip unless forced
    if not is_daylight and not force_run:
        print(f"Fora do horário de sol ({now.strftime('%H:%M')}). Verificação pulada.")
        return
        
    print(f"Iniciando verificação: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Query João Pessoa weather forecast
    weather_data = get_joao_pessoa_weather()
    
    # Load cached history curves from previous runs to avoid re-querying past days
    cached_plants = config.get("last_data", [])
    cached_curves_map = {}
    for cp in cached_plants:
        cached_curves_map[cp.get("apikey")] = cp.get("history_curves", {})
        
    plants_results = []
    alert_messages = []
    active_alerts = []
    api_error = None
    
    config_dirty = False
    
    # 1. Fetch Solplanet (Aiswei) plants if credentials exist
    if app_key and app_secret:
        print("\nConectando à API Solplanet...")
        api = AisweiSolarAPI(app_key=app_key, app_secret=app_secret, token=token, base_url=base_url)
        plan_list_res = api.getPlanListPro()
        
        if plan_list_res.get("status") == 200:
            cloud_plants = plan_list_res.get("data", {}).get("result", [])
            for plant in plants:
                apikey = plant.get("apikey")
                name = plant.get("name")
                capacity = float(plant.get("capacity_kw", 10.0))
                threshold = float(plant.get("threshold_pct", 15.0))
                
                print(f"Buscando dados da planta Solplanet: {name}")
                
                # Find matching plant in cloud data
                cloud_info = {}
                for cp in cloud_plants:
                    if cp.get("apikey") == apikey:
                        cloud_info = cp
                        break
                        
                latitude = cloud_info.get("wd")
                longitude = cloud_info.get("jd")
                position = cloud_info.get("position", "Local desconhecido")
                
                overview = api.getPlantOverviewPro(apikey)
                
                plant_power = 0.0
                plant_today = 0.0
                plant_total = 0.0
                plant_status = 0
                plant_ludt = "Sem comunicação"
                plant_status_str = "offline"
                output_curve = []
                inverters_list = []
                
                if overview.get("status") == 200:
                    data = overview.get("data", {})
                    plant_ludt = data.get("ludt", "Desconhecido")
                    plant_status = int(data.get("status", 0))
                    
                    power_obj = data.get("Power", {})
                    raw_power = float(power_obj.get("value", 0.0))
                    plant_power = raw_power / 1000.0 if power_obj.get("unit") == "W" else raw_power
                    
                    today_obj = data.get("E-Today", {})
                    plant_today = float(today_obj.get("value", 0.0))
                    
                    total_obj = data.get("E-Total", {})
                    raw_total = float(total_obj.get("value", 0.0))
                    if total_obj.get("unit") == "KWh":
                        plant_total = raw_total / 1000000.0
                    else:
                        plant_total = raw_total
                        
                    plant_status_str = "normal" if plant_status == 1 else ("warning" if plant_status == 2 else "error")
                    
                    if plant_status == 1 and is_active_solar_hours:
                        # Alert based on cumulative daily yield vs expected-so-far (not instantaneous power)
                        # This avoids false positives from passing clouds
                        _exp_daily = (capacity * 125.0) / 30.0
                        _exp_so_far = 0.0
                        if current_hour >= 18:
                            _exp_so_far = _exp_daily
                        elif 6 <= current_hour < 18:
                            _t = current_hour + now.minute / 60.0
                            _f = 0.5 * (1.0 - math.cos(math.pi * (_t - 6.0) / 12.0))
                            _exp_so_far = _exp_daily * _f
                        if _exp_so_far > 0:
                            _yield_pct = (plant_today / _exp_so_far) * 100.0
                            # Adjust threshold for cloud cover: on a cloudy day the
                            # expected generation is naturally reduced proportionally.
                            # cloud_cover_pct comes from the weather API (0–100).
                            # Reduction factor: each 1% cloud cover lowers expected by ~0.55%
                            # (empirical: full overcast ≈ 55% reduction from clear sky)
                            _cloud = weather_data.get('cloud', 0) if weather_data else 0
                            _solar_factor = max(0.25, 1.0 - (_cloud / 100.0) * 0.55)
                            _adj_exp = _exp_so_far * _solar_factor
                            _adj_yield_pct = (plant_today / _adj_exp * 100.0) if _adj_exp > 0 else 100.0
                            _alert_threshold = 100.0 - threshold  # e.g. 15% → alert if <85%
                            if _adj_yield_pct < _alert_threshold:
                                plant_status_str = "low_production"
                                cloud_note = f" (dia nublado {_cloud:.0f}%, fator solar {_solar_factor:.0%})" if _cloud > 40 else ""
                                msg = (f"Planta Solplanet '{name}' com geração acumulada abaixo do esperado "
                                       f"({plant_today:.2f} kWh gerados / {_adj_exp:.2f} kWh esperados{cloud_note} "
                                       f"= {_adj_yield_pct:.0f}% do esperado).")
                                alert_messages.append(msg)
                                active_alerts.append({
                                    "plant_name": name,
                                    "type": "low_production",
                                    "message": (f"Geração acumulada baixa: {plant_today:.2f} kWh gerados vs "
                                                f"{_exp_so_far:.2f} kWh esperados ({_yield_pct:.0f}% do previsto)")
                                })
                                print(f"ALERTA: {msg}")
                    
                    if plant_status == 0:
                        plant_status_str = "offline"
                        if is_active_solar_hours:
                            msg = f"Planta Solplanet '{name}' está OFFLINE na plataforma Solplanet!"
                            alert_messages.append(msg)
                            active_alerts.append({
                                "plant_name": name,
                                "type": "offline",
                                "message": "A planta solar está offline na plataforma Solplanet."
                            })
                            print(f"ALERTA: {msg}")
                        
                    # Self-populating cache of inverter serial numbers
                    inverter_sns = plant.get("inverter_sns", [])
                    if not inverter_sns:
                        print(f"  Buscando lista de inversores para {name}...")
                        dev_res = api.getDeviceListPro(apikey)
                        if dev_res.get("status") == 200:
                            for dev_item in dev_res.get("data", []):
                                for inv_item in dev_item.get("inverters", []):
                                    inverter_sns.append(inv_item.get("isn"))
                            plant["inverter_sns"] = inverter_sns
                            config_dirty = True
                            
                    # Query individual inverter real-time data
                    if inverter_sns:
                        isnos_str = ",".join(inverter_sns)
                        ts_res = api.getLastTsDataPro(isnos_str)
                        if ts_res.get("status") == 200:
                            for ts_item in ts_res.get("data", []):
                                inv_power = float(ts_item.get("pac", 0.0)) / 1000.0
                                inv_today = float(ts_item.get("etd", 0.0)) / 10.0
                                inv_total = float(ts_item.get("eto", 0.0)) / 10000.0
                                is_inv_online = ts_item.get("currentState") == 1 or ts_item.get("stu") == "1"
                                inverters_list.append({
                                    "sn": ts_item.get("sn"),
                                    "power_kw": inv_power,
                                    "today_kwh": inv_today,
                                    "total_mwh": inv_total,
                                    "status": 1 if is_inv_online else 0,
                                    "capacity_kw": capacity / len(inverter_sns),
                                    "ludt": ts_item.get("tim")
                                })
                                
                    # If failed or empty, default to single inverter
                    if not inverters_list:
                        inverters_list = [{
                            "sn": inverter_sns[0] if inverter_sns else "N/A",
                            "power_kw": plant_power,
                            "today_kwh": plant_today,
                            "total_mwh": plant_total,
                            "status": 1 if plant_status == 1 else 0,
                            "capacity_kw": capacity,
                            "ludt": plant_ludt
                        }]
                        
                    # Manage rolling caching of historical curves
                    history_curves = cached_curves_map.get(apikey, {})
                    dates_to_verify = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
                    for d in dates_to_verify:
                        is_today_date = d == now.strftime("%Y-%m-%d")
                        if is_today_date or d not in history_curves:
                            print(f"  Buscando curva Solplanet para o dia {d}...")
                            output_res = api.getPlantOutputPro(apikey, "bydays", d)
                            if output_res.get("status") == 200:
                                history_curves[d] = output_res.get("data", {}).get("result", [])
                    
                    # Keep maximum of 7 days in cache
                    all_cached_dates = sorted(list(history_curves.keys()))
                    if len(all_cached_dates) > 7:
                        for oldest_date in all_cached_dates[:-7]:
                            history_curves.pop(oldest_date, None)
                            
                    output_curve = history_curves.get(now.strftime("%Y-%m-%d"), [])
                else:
                    err_msg = overview.get("error", "Erro ao buscar detalhes")
                    print(f"Falha ao buscar dados Solplanet para {name}: {err_msg}")
                    plant_status_str = "error"
                    plant_ludt = f"Falha na API: {err_msg}"
                    active_alerts.append({
                        "plant_name": name,
                        "type": "error",
                        "message": f"Erro de API Solplanet: {err_msg}"
                    })
                    history_curves = cached_curves_map.get(apikey, {})
                    output_curve = history_curves.get(now.strftime("%Y-%m-%d"), [])
                    inverters_list = [{
                        "sn": "N/A",
                        "power_kw": 0.0,
                        "today_kwh": 0.0,
                        "total_mwh": 0.0,
                        "status": 0,
                        "capacity_kw": capacity,
                        "ludt": "Desconhecido"
                    }]
                    
                # Calculate daily targets
                expected_daily = (capacity * 125.0) / 30.0
                expected_so_far = 0.0
                if current_hour >= 18:
                    expected_so_far = expected_daily
                elif 6 <= current_hour < 18:
                    current_time_float = current_hour + now.minute / 60.0
                    fraction = 0.5 * (1.0 - math.cos(math.pi * (current_time_float - 6.0) / 12.0))
                    expected_so_far = expected_daily * fraction
                    
                daily_yield_pct = (plant_today / expected_so_far * 100.0) if expected_so_far > 0 else 100.0
                
                plants_results.append({
                    "name": name,
                    "apikey": apikey,
                    "capacity_kw": capacity,
                    "threshold_pct": threshold,
                    "power_kw": plant_power,
                    "today_kwh": plant_today,
                    "total_mwh": plant_total,
                    "status": plant_status,
                    "status_str": plant_status_str,
                    "ludt": plant_ludt,
                    "output_curve": output_curve,
                    "latitude": latitude,
                    "longitude": longitude,
                    "position": position,
                    "platform": "solplanet",
                    "expected_daily_kwh": expected_daily,
                    "expected_so_far_kwh": expected_so_far,
                    "daily_yield_pct": daily_yield_pct,
                    "history_curves": history_curves,
                    "inverters": inverters_list
                })
        else:
            api_error = plan_list_res.get("error", "Erro na API Solplanet")
            print(f"Erro ao obter lista Solplanet: {api_error}")
            
    # 2. Fetch Solis plants if credentials exist
    if solis_key_id and solis_key_secret:
        print("\nConectando à API SolisCloud...")
        solis_api = SolisCloudAPI(solis_key_id, solis_key_secret, solis_base_url)
        solis_res = solis_api.getStationList(page_no=1, page_size=100)
        
        if solis_res.get("success") == True or solis_res.get("code") == "0":
            records = solis_res.get("data", {}).get("page", {}).get("records", [])
            print(f"Encontradas {len(records)} usinas no SolisCloud.")
            
            for record in records:
                station_id = record.get("id")
                name = record.get("stationName")
                capacity = float(record.get("capacity", 10.0))
                threshold = 15.0 # default 15% threshold for Solis
                
                print(f"Buscando dados da planta Solis: {name} (ID: {station_id})")
                
                plant_power = float(record.get("power", 0.0))
                plant_today = float(record.get("dayEnergy", 0.0))
                plant_total = float(record.get("allEnergy", 0.0))
                state = int(record.get("state", 2)) # 1: online, 2: offline, 3: alarm
                
                # Convert timestamp (ms) to string
                try:
                    ts = int(record.get("dataTimestamp", 0)) / 1000.0
                    plant_ludt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    plant_ludt = "Desconhecido"
                    
                position = f"{record.get('addrOrigin', '')}, {record.get('countyStr', '')}, {record.get('cityStr', '')}, Brazil"
                position = position.strip(", ")
                if not position or position == "Brazil":
                    position = "Local desconhecido"
                    
                plant_status = 1 if state == 1 else (0 if state == 2 else 3)
                plant_status_str = "normal" if state == 1 else ("offline" if state == 2 else "error")
                
                # Query inverters for this station
                inverters_list = []
                inv_res = solis_api.getInverterList(station_id=station_id, page_no=1, page_size=50)
                if inv_res.get("success") == True or inv_res.get("code") == "0":
                    inv_records = inv_res.get("data", {}).get("page", {}).get("records", [])
                    for inv_rec in inv_records:
                        is_online = inv_rec.get("state") == 1
                        inv_ts = float(inv_rec.get("dataTimestamp", 0)) / 1000.0 if inv_rec.get("dataTimestamp") else None
                        inv_ludt = datetime.fromtimestamp(inv_ts).strftime("%Y-%m-%d %H:%M:%S") if inv_ts else plant_ludt
                        inverters_list.append({
                            "sn": inv_rec.get("sn"),
                            "power_kw": float(inv_rec.get("pac", 0.0)),
                            "today_kwh": float(inv_rec.get("etoday", 0.0)),
                            "total_mwh": float(inv_rec.get("etotal", 0.0)),
                            "status": 1 if is_online else 0,
                            "capacity_kw": float(inv_rec.get("power", capacity / len(inv_records))),
                            "ludt": inv_ludt
                        })
                
                if not inverters_list:
                    inverters_list = [{
                        "sn": "N/A",
                        "power_kw": plant_power,
                        "today_kwh": plant_today,
                        "total_mwh": plant_total,
                        "status": 1 if plant_status == 1 else 0,
                        "capacity_kw": capacity,
                        "ludt": plant_ludt
                    }]
                
                # Low production alert based on cumulative daily yield vs expected-so-far
                # (not instantaneous power — avoids false positives from passing clouds)
                if state == 1 and is_active_solar_hours:
                    _exp_daily = (capacity * 125.0) / 30.0
                    _exp_so_far = 0.0
                    if current_hour >= 18:
                        _exp_so_far = _exp_daily
                    elif 6 <= current_hour < 18:
                        _t = current_hour + now.minute / 60.0
                        _f = 0.5 * (1.0 - math.cos(math.pi * (_t - 6.0) / 12.0))
                        _exp_so_far = _exp_daily * _f
                    if _exp_so_far > 0:
                        _yield_pct = (plant_today / _exp_so_far) * 100.0
                        # Cloud-cover-aware adjustment (same as Solplanet)
                        _cloud = weather_data.get('cloud', 0) if weather_data else 0
                        _solar_factor = max(0.25, 1.0 - (_cloud / 100.0) * 0.55)
                        _adj_exp = _exp_so_far * _solar_factor
                        _adj_yield_pct = (plant_today / _adj_exp * 100.0) if _adj_exp > 0 else 100.0
                        _alert_threshold = 100.0 - threshold  # e.g. 15% → alert if <85%
                        if _adj_yield_pct < _alert_threshold:
                            plant_status_str = "low_production"
                            cloud_note = f" (dia nublado {_cloud:.0f}%, fator solar {_solar_factor:.0%})" if _cloud > 40 else ""
                            msg = (f"Planta Solis '{name}' com geração acumulada abaixo do esperado "
                                   f"({plant_today:.2f} kWh gerados / {_adj_exp:.2f} kWh esperados{cloud_note} "
                                   f"= {_adj_yield_pct:.0f}% do esperado).")
                            alert_messages.append(msg)
                            active_alerts.append({
                                "plant_name": name,
                                "type": "low_production",
                                "message": (f"Geração acumulada baixa: {plant_today:.2f} kWh gerados vs "
                                            f"{_exp_so_far:.2f} kWh esperados ({_yield_pct:.0f}% do previsto)")
                            })
                            print(f"ALERTA: {msg}")
                        
                # Offline alert
                if state == 2:
                    plant_status_str = "offline"
                    if is_active_solar_hours:
                        msg = f"Planta Solis '{name}' está OFFLINE na plataforma SolisCloud!"
                        alert_messages.append(msg)
                        active_alerts.append({
                            "plant_name": name,
                            "type": "offline",
                            "message": "A planta solar está offline na plataforma SolisCloud."
                        })
                        print(f"ALERTA: {msg}")
                    
                # Manage rolling cache of curves for Solis
                history_curves = cached_curves_map.get(str(station_id), {})
                dates_to_verify = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
                
                for d in dates_to_verify:
                    is_today_date = d == now.strftime("%Y-%m-%d")
                    if is_today_date or d not in history_curves:
                        print(f"  Buscando curva Solis para o dia {d}...")
                        curve_res = solis_api.getStationDay(station_id, d, timezone_offset=-3)
                        if curve_res.get("success") == True or curve_res.get("code") == "0":
                            curve_data = curve_res.get("data", [])
                            day_points = []
                            if curve_data:
                                for pt in curve_data:
                                    time_str = pt.get("timeStr", "")[:5]
                                    value_str = f"{float(pt.get('power', 0.0)):.2f}"
                                    day_points.append({
                                        "time": time_str,
                                        "no": str(len(day_points)),
                                        "value": value_str
                                    })
                            history_curves[d] = day_points
                            
                # Keep maximum of 7 days in cache
                all_cached_dates = sorted(list(history_curves.keys()))
                if len(all_cached_dates) > 7:
                    for oldest_date in all_cached_dates[:-7]:
                        history_curves.pop(oldest_date, None)
                        
                output_curve = history_curves.get(now.strftime("%Y-%m-%d"), [])
                
                # Calculate daily targets
                expected_daily = (capacity * 125.0) / 30.0
                expected_so_far = 0.0
                if current_hour >= 18:
                    expected_so_far = expected_daily
                elif 6 <= current_hour < 18:
                    current_time_float = current_hour + now.minute / 60.0
                    fraction = 0.5 * (1.0 - math.cos(math.pi * (current_time_float - 6.0) / 12.0))
                    expected_so_far = expected_daily * fraction
                    
                daily_yield_pct = (plant_today / expected_so_far * 100.0) if expected_so_far > 0 else 100.0
                
                plants_results.append({
                    "name": name,
                    "apikey": str(station_id),
                    "capacity_kw": capacity,
                    "threshold_pct": threshold,
                    "power_kw": plant_power,
                    "today_kwh": plant_today,
                    "total_mwh": plant_total,
                    "status": plant_status,
                    "status_str": plant_status_str,
                    "ludt": plant_ludt,
                    "output_curve": output_curve,
                    "latitude": None,
                    "longitude": None,
                    "position": position,
                    "platform": "solis",
                    "expected_daily_kwh": expected_daily,
                    "expected_so_far_kwh": expected_so_far,
                    "daily_yield_pct": daily_yield_pct,
                    "history_curves": history_curves,
                    "inverters": inverters_list
                })
        else:
            solis_error = solis_res.get("msg", "Erro na API Solis")
            print(f"Erro ao obter lista Solis: {solis_error}")
            if not api_error:
                api_error = f"Erro Solis: {solis_error}"
                
    if not plants_results and api_error:
        # All queries failed, generate dashboard showing error
        generate_dashboard(config, [], [], api_error=api_error, weather_data=weather_data)
        trigger_alert_popup([
            "Falha de Configuração/Conexão da API!",
            f"O servidor retornou o seguinte erro:\n{api_error}"
        ])
        sys.exit(1)
        
    # Check and send Telegram alerts for favorite plants
    process_telegram_alerts(config, plants_results, active_alerts)
    
    # Save the execution history/data to config.json
    config["last_update"] = get_local_now().isoformat()
    config["last_data"] = plants_results
    if config_dirty:
        # Save updated configurations containingCached inverter SNs
        save_config(config)
    else:
        save_config(config)
    
    # Generate dashboard file
    generate_dashboard(config, plants_results, active_alerts, weather_data=weather_data)
    
    # Trigger dialog box alerts if any warnings are active
    if alert_messages:
        trigger_alert_popup(alert_messages)
    else:
        print("Geração solar OK! Nenhuma anomalia detectada.")

if __name__ == "__main__":
    main()
