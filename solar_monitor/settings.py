#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import subprocess
import sys
from aiswei_api import AisweiSolarAPI

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

class SettingsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Solar Monitor - Configurações")
        self.root.geometry("620x650")
        self.root.minsize(580, 550)
        
        # Load existing configuration
        self.config_data = self.load_config()
        
        # Setup styling
        self.style = ttk.Style()
        self.style.theme_use("vista" if "vista" in self.style.theme_names() else "default")
        
        self.create_widgets()
        self.load_fields_from_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate keys
                    if "plants" not in data:
                        data["plants"] = []
                    if "base_url" not in data:
                        data["base_url"] = "https://eu-api-genergal.aisweicloud.com"
                    return data
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao ler arquivo config.json:\n{e}")
        
        # Default empty config
        return {
            "app_key": "",
            "app_secret": "",
            "token": "",
            "base_url": "https://eu-api-genergal.aisweicloud.com",
            "plants": []
        }

    def save_config_to_file(self):
        # Update text credentials from entries
        self.config_data["app_key"] = self.entry_app_key.get().strip()
        self.config_data["app_secret"] = self.entry_app_secret.get().strip()
        self.config_data["token"] = self.entry_token.get().strip()
        self.config_data["base_url"] = self.entry_base_url.get().strip()
        self.config_data["mock_mode"] = self.var_mock_mode.get()
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações:\n{e}")
            return False

    def create_widgets(self):
        # Main Frame
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title Label
        title_label = ttk.Label(main_frame, text="Configurações do Monitor Solar", font=("Helvetica", 14, "bold"))
        title_label.pack(anchor=tk.W, pady=(0, 15))

        # Credentials Group (LabelFrame)
        creds_frame = ttk.LabelFrame(main_frame, text=" Credenciais Solplanet API ", padding="10")
        creds_frame.pack(fill=tk.X, pady=(0, 15))

        # App Key
        ttk.Label(creds_frame, text="App Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_app_key = ttk.Entry(creds_frame, width=40)
        self.entry_app_key.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)

        # App Secret
        ttk.Label(creds_frame, text="App Secret:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entry_app_secret = ttk.Entry(creds_frame, width=40, show="*")
        self.entry_app_secret.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Toggle show/hide secret
        self.btn_show_secret = ttk.Checkbutton(creds_frame, text="Mostrar Secret", command=self.toggle_secret)
        self.btn_show_secret.grid(row=1, column=2, sticky=tk.W, padx=5)

        # User Token
        ttk.Label(creds_frame, text="User Token:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.entry_token = ttk.Entry(creds_frame, width=40)
        self.entry_token.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)

        # Base URL
        ttk.Label(creds_frame, text="Base URL:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.entry_base_url = ttk.Entry(creds_frame, width=40)
        self.entry_base_url.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)

        # Grid config
        creds_frame.columnconfigure(1, weight=1)

        # Plants Group (LabelFrame)
        plants_frame = ttk.LabelFrame(main_frame, text=" Plantas Solares Cadastradas ", padding="10")
        plants_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Plants List Box
        self.plants_listbox = tk.Listbox(plants_frame, font=("Helvetica", 10))
        self.plants_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=5)

        # Scrollbar for listbox
        scrollbar = ttk.Scrollbar(plants_frame, orient=tk.VERTICAL, command=self.plants_listbox.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y, pady=5)
        self.plants_listbox.config(yscrollcommand=scrollbar.set)

        # Action Buttons frame for plants
        btn_plants_frame = ttk.Frame(plants_frame)
        btn_plants_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        ttk.Button(btn_plants_frame, text="Adicionar Planta", command=self.add_plant).pack(fill=tk.X, pady=3)
        ttk.Button(btn_plants_frame, text="Editar Planta", command=self.edit_plant).pack(fill=tk.X, pady=3)
        ttk.Button(btn_plants_frame, text="Remover Planta", command=self.remove_plant).pack(fill=tk.X, pady=3)

        # Bottom Action Buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)

        # Test Connection Button
        ttk.Button(bottom_frame, text="Testar Conexão API", command=self.test_connection).pack(side=tk.LEFT, padx=5)
        
        # Run Monitor Now
        ttk.Button(bottom_frame, text="Executar Monitor Agora", command=self.run_monitor).pack(side=tk.LEFT, padx=5)

        # Demo mode checkbox
        self.var_mock_mode = tk.BooleanVar(value=self.config_data.get("mock_mode", False))
        self.chk_mock_mode = ttk.Checkbutton(bottom_frame, text="Simular Dados (Modo Demo)", variable=self.var_mock_mode)
        self.chk_mock_mode.pack(side=tk.LEFT, padx=10)

        # Save Button
        ttk.Button(bottom_frame, text="Salvar Configurações", command=self.save_settings).pack(side=tk.RIGHT, padx=5)

    def toggle_secret(self):
        if self.entry_app_secret.cget("show") == "*":
            self.entry_app_secret.config(show="")
        else:
            self.entry_app_secret.config(show="*")

    def load_fields_from_config(self):
        # Prefill credentials
        self.entry_app_key.insert(0, self.config_data.get("app_key", ""))
        self.entry_app_secret.insert(0, self.config_data.get("app_secret", ""))
        self.entry_token.insert(0, self.config_data.get("token", ""))
        self.entry_base_url.insert(0, self.config_data.get("base_url", "https://eu-api-genergal.aisweicloud.com"))
        
        self.refresh_plants_list()

    def refresh_plants_list(self):
        self.plants_listbox.delete(0, tk.END)
        for idx, plant in enumerate(self.config_data["plants"]):
            name = plant.get("name", "Sem Nome")
            capacity = plant.get("capacity_kw", 0.0)
            threshold = plant.get("threshold_pct", 15.0)
            key = plant.get("apikey", "Sem Chave")[:10] + "..." if plant.get("apikey") else "Sem Chave"
            self.plants_listbox.insert(tk.END, f"{idx+1}. {name} ({capacity} kW) - Limiar: {threshold}% - Chave: {key}")

    def add_plant(self):
        plant_dialog = PlantDialog(self.root, "Adicionar Planta Solar")
        if plant_dialog.result:
            self.config_data["plants"].append(plant_dialog.result)
            self.refresh_plants_list()

    def edit_plant(self):
        selected_index = self.plants_listbox.curselection()
        if not selected_index:
            messagebox.showwarning("Aviso", "Selecione uma planta solar para editar.")
            return
            
        idx = selected_index[0]
        current_plant = self.config_data["plants"][idx]
        
        plant_dialog = PlantDialog(self.root, "Editar Planta Solar", current_plant)
        if plant_dialog.result:
            self.config_data["plants"][idx] = plant_dialog.result
            self.refresh_plants_list()

    def remove_plant(self):
        selected_index = self.plants_listbox.curselection()
        if not selected_index:
            messagebox.showwarning("Aviso", "Selecione uma planta solar para remover.")
            return
            
        idx = selected_index[0]
        plant_name = self.config_data["plants"][idx].get("name", "Sem Nome")
        
        if messagebox.askyesno("Confirmar Remoção", f"Tem certeza que deseja remover a planta solar '{plant_name}'?"):
            self.config_data["plants"].pop(idx)
            self.refresh_plants_list()

    def save_settings(self):
        if self.save_config_to_file():
            messagebox.showinfo("Sucesso", "Configurações salvas com sucesso em config.json!")

    def test_connection(self):
        app_key = self.entry_app_key.get().strip()
        app_secret = self.entry_app_secret.get().strip()
        token = self.entry_token.get().strip()
        base_url = self.entry_base_url.get().strip()
        
        if not app_key or not app_secret:
            messagebox.showwarning("Aviso", "Por favor, preencha App Key e App Secret para testar a conexão.")
            return
            
        # Temporarily test connection using entered credentials
        api = AisweiSolarAPI(app_key=app_key, app_secret=app_secret, token=token, base_url=base_url)
        
        self.root.config(cursor="wait")
        self.root.update()
        
        result = api.getPlanListPro()
        
        self.root.config(cursor="")
        
        # Check result
        if result.get("status") == 200:
            plants_found = len(result.get("data", {}).get("result", []))
            messagebox.showinfo("Sucesso", f"Conexão API OK!\nConexão estabelecida com sucesso.\nPlantas encontradas na nuvem: {plants_found}")
        else:
            err_msg = result.get("error", "Erro desconhecido")
            if "Invalid AppKey" in err_msg:
                messagebox.showerror("Erro de Conexão", f"Falha na API Gateway:\n{err_msg}\n\nNota: Verifique se sua conta foi ativada para acesso de API pela Solplanet ou se o servidor regional está correto.")
            else:
                messagebox.showerror("Erro de Conexão", f"Falha na conexão com a API Solplanet:\n{err_msg}\nResultado completo:\n{result}")

    def run_monitor(self):
        # Save first
        if not self.save_config_to_file():
            return
            
        monitor_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.py")
        if not os.path.exists(monitor_script):
            messagebox.showerror("Erro", "Script monitor.py não encontrado na mesma pasta.")
            return
            
        self.root.config(cursor="wait")
        self.root.update()
        
        try:
            # Execute monitor.py and capture result
            res = subprocess.run([sys.executable, monitor_script, "--force"], capture_output=True, text=True, timeout=30)
            self.root.config(cursor="")
            
            if res.returncode == 0:
                messagebox.showinfo("Sucesso", "Monitor executado com sucesso!\nO arquivo dashboard.html foi atualizado.")
            else:
                messagebox.showerror("Erro na Execução", f"O script monitor retornou erro (código {res.returncode}):\n{res.stderr}\n\nOutput:\n{res.stdout}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Erro", f"Falha ao executar o script:\n{e}")

class PlantDialog(simpledialog.Dialog):
    def __init__(self, parent, title, plant_data=None):
        self.plant_data = plant_data
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nome da Planta:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_name = ttk.Entry(master, width=30)
        self.entry_name.grid(row=0, column=1, pady=5, padx=5)

        ttk.Label(master, text="Planta API Key (NMI):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entry_key = ttk.Entry(master, width=30)
        self.entry_key.grid(row=1, column=1, pady=5, padx=5)

        ttk.Label(master, text="Capacidade Nominal (kW):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.entry_capacity = ttk.Entry(master, width=30)
        self.entry_capacity.grid(row=2, column=1, pady=5, padx=5)

        ttk.Label(master, text="Limiar Alerta Prod. Baixa (%):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.entry_threshold = ttk.Entry(master, width=30)
        self.entry_threshold.grid(row=3, column=1, pady=5, padx=5)

        # Prefill values if editing
        if self.plant_data:
            self.entry_name.insert(0, self.plant_data.get("name", ""))
            self.entry_key.insert(0, self.plant_data.get("apikey", ""))
            self.entry_capacity.insert(0, str(self.plant_data.get("capacity_kw", 10.0)))
            self.entry_threshold.insert(0, str(self.plant_data.get("threshold_pct", 15.0)))
        else:
            self.entry_capacity.insert(0, "10.0")
            self.entry_threshold.insert(0, "15.0")

        return self.entry_name # focus

    def validate(self):
        name = self.entry_name.get().strip()
        key = self.entry_key.get().strip()
        capacity_str = self.entry_capacity.get().strip()
        threshold_str = self.entry_threshold.get().strip()

        if not name or not key:
            messagebox.showwarning("Aviso", "Nome e API Key são obrigatórios.")
            return False

        try:
            capacity = float(capacity_str)
            if capacity <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "Capacidade nominal deve ser um número maior que zero.")
            return False

        try:
            threshold = float(threshold_str)
            if not (0 <= threshold <= 100):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Aviso", "O limiar de alerta deve ser uma porcentagem entre 0% e 100%.")
            return False

        self.result = {
            "name": name,
            "apikey": key,
            "capacity_kw": capacity,
            "threshold_pct": threshold
        }
        return True

def main():
    root = tk.Tk()
    app = SettingsApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
