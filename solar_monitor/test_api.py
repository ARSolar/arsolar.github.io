#!/usr/bin/env python3
import unittest
import os
import json
from aiswei_api import AisweiSolarAPI
import monitor

class TestSolarMonitor(unittest.TestCase):
    def setUp(self):
        self.app_key = "205024068"
        self.app_secret = "aRTTFBY9lfByMJtG0awanbNX4sQj8wG9"
        self.token = "test_token"
        
    def test_api_client_initialization(self):
        """Test API client initialization values."""
        api = AisweiSolarAPI(self.app_key, self.app_secret, self.token)
        self.assertEqual(api.app_key, self.app_key)
        self.assertEqual(api.app_secret, self.app_secret)
        self.assertEqual(api.token, self.token)
        self.assertEqual(api.base_url, "https://ap-southeast-1-api-genergal.aisweicloud.com")

    def test_dashboard_generation(self):
        """Test generating the dashboard file with mock data."""
        mock_config = {
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "token": self.token,
            "base_url": "https://ap-southeast-1-api-genergal.aisweicloud.com",
            "plants": [
                {
                    "apikey": "test_plant_1_key",
                    "name": "Planta Teste 1 (Geração Normal)",
                    "capacity_kw": 12.5,
                    "threshold_pct": 15.0
                },
                {
                    "apikey": "test_plant_2_key",
                    "name": "Planta Teste 2 (Produção Baixa)",
                    "capacity_kw": 8.0,
                    "threshold_pct": 20.0
                }
            ]
        }
        
        mock_plants_data = [
            {
                "name": "Planta Teste 1 (Geração Normal)",
                "apikey": "test_plant_1_key",
                "capacity_kw": 12.5,
                "threshold_pct": 15.0,
                "power_kw": 8.75, # 70% efficiency
                "today_kwh": 42.6,
                "total_mwh": 14.82,
                "status": 1,
                "status_str": "normal",
                "ludt": "08/07/2026 15:00:00",
                "output_curve": [
                    {"time": "08:00", "no": "0", "value": "1.2"},
                    {"time": "10:00", "no": "1", "value": "5.4"},
                    {"time": "12:00", "no": "2", "value": "8.75"},
                    {"time": "14:00", "no": "3", "value": "7.9"}
                ]
            },
            {
                "name": "Planta Teste 2 (Produção Baixa)",
                "apikey": "test_plant_2_key",
                "capacity_kw": 8.0,
                "threshold_pct": 20.0,
                "power_kw": 0.8, # 10% efficiency -> below threshold of 20%!
                "today_kwh": 12.4,
                "total_mwh": 5.12,
                "status": 1,
                "status_str": "low_production",
                "ludt": "08/07/2026 15:00:00",
                "output_curve": [
                    {"time": "08:00", "no": "0", "value": "0.5"},
                    {"time": "10:00", "no": "1", "value": "1.8"},
                    {"time": "12:00", "no": "2", "value": "0.8"},
                    {"time": "14:00", "no": "3", "value": "0.7"}
                ]
            }
        ]
        
        mock_alerts = [
            {
                "plant_name": "Planta Teste 2 (Produção Baixa)",
                "type": "low_production",
                "message": "Produção baixa: gerando 0.80 kW (capacidade de 8.0 kW, limiar de 20.0%)"
            }
        ]
        
        # Call generate_dashboard inside monitor to a test file
        test_dashboard_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_test.html")
        monitor.generate_dashboard(mock_config, mock_plants_data, mock_alerts, output_file=test_dashboard_file)
        
        # Verify dashboard_test.html exists
        self.assertTrue(os.path.exists(test_dashboard_file))
        
        # Check content size
        size = os.path.getsize(test_dashboard_file)
        self.assertGreater(size, 5000) # HTML should be larger than 5KB
        print(f"Dashboard dry-run generated successfully! File size: {size} bytes")
        
        # Clean up
        if os.path.exists(test_dashboard_file):
            os.remove(test_dashboard_file)

if __name__ == "__main__":
    unittest.main()
