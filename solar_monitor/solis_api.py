#!/usr/bin/env python3
import requests
import hashlib
import hmac
import base64
import json
import datetime
from typing import Dict, Any

class SolisCloudAPI:
    """Client for the Ginlong (Solis) Cloud Platform API (V2.0.3)."""
    
    def __init__(
        self,
        key_id: str,
        key_secret: str,
        base_url: str = "https://www.soliscloud.com:13333"
    ):
        """
        Initialize the Solis Cloud API client.
        
        Args:
            key_id: KeyID (API ID) from Solis API Management
            key_secret: KeySecret from Solis API Management
            base_url: The API base URL
        """
        self.key_id = key_id.strip() if key_id else ""
        self.key_secret = key_secret.strip() if key_secret else ""
        self.base_url = base_url.strip() if base_url else "https://www.soliscloud.com:13333"
        # Ensure base_url does not end with a slash
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]

    def _make_request(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a POST request to Solis Cloud API with proper signature and headers.
        """
        url = f"{self.base_url}{path}"
        
        # 1. Format body as compact JSON string
        body_str = json.dumps(body, separators=(',', ':'))
        
        # 2. Compute Content-MD5
        md5_hash = hashlib.md5(body_str.encode('utf-8')).digest()
        content_md5 = base64.b64encode(md5_hash).decode('utf-8')
        
        # 3. Compute GMT date (EEE, d MMM yyyy HH:mm:ss GMT - Locale US independent)
        now = datetime.datetime.now(datetime.timezone.utc)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        date_str = f"{days[now.weekday()]}, {now.day} {months[now.month - 1]} {now.year} {now.hour:02d}:{now.minute:02d}:{now.second:02d} GMT"
        
        # 4. Generate Signature
        content_type = "application/json"
        string_to_sign = f"POST\n{content_md5}\n{content_type}\n{date_str}\n{path}"
        
        sign_bytes = hmac.new(
            self.key_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        ).digest()
        sign = base64.b64encode(sign_bytes).decode('utf-8')
        
        # 5. Build Headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Content-MD5": content_md5,
            "Content-Type": content_type,
            "Date": date_str,
            "Authorization": f"API {self.key_id}:{sign}"
        }
        
        try:
            response = requests.post(url, data=body_str, headers=headers, timeout=15)
            # Standard Solis API responses return HTTP 200 even for logical errors,
            # with code/success in JSON body.
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "code": str(response.status_code),
                    "msg": f"Erro do servidor HTTP: {response.status_code}",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "code": "API_ERROR",
                "msg": f"Erro de conexão: {str(e)}",
                "data": None
            }

    def getStationList(self, page_no: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        Retrieve list of power stations.
        """
        path = "/v1/api/userStationList"
        body = {
            "pageNo": page_no,
            "pageSize": page_size
        }
        return self._make_request(path, body)

    def getStationDay(self, station_id: int, date_str: str, timezone_offset: int = -3) -> Dict[str, Any]:
        """
        Retrieve real-time power generation data points for a single station on a given day.
        
        Args:
            station_id: The ID of the power station
            date_str: Date in 'yyyy-MM-dd' format
            timezone_offset: Hour offset from UTC (default -3 for Brazil)
        """
        path = "/v1/api/stationDay"
        body = {
            "id": int(station_id),
            "money": "BRL",
            "time": date_str,
            "timeZone": str(timezone_offset)
        }
        return self._make_request(path, body)

    def getInverterList(self, station_id: int, page_no: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        Retrieve list of inverters under a station.
        """
        path = "/v1/api/inverterList"
        body = {
            "pageNo": page_no,
            "pageSize": page_size,
            "stationId": str(station_id)
        }
        return self._make_request(path, body)
