#!/usr/bin/env python3
import requests
import hashlib
import hmac
import base64
import urllib.parse
import urllib3
from typing import Dict, Any

# Suppress InsecureRequestWarning for environments that might have SSL verification issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AisweiSolarAPI:
    """Client for the AISWEI/Solplanet Solar API (Pro User)."""
    
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        token: str,
        base_url: str = "https://ap-southeast-1-api-genergal.aisweicloud.com"
    ):
        """
        Initialize the AISWEI Solar API client.
        
        Args:
            app_key: The App Key from your account settings
            app_secret: The App Secret used to sign requests
            token: The Pro user access token
            base_url: Base URL of the API gateway (default is Singapore endpoint)
        """
        self.app_key = app_key.strip() if app_key else ""
        self.app_secret = app_secret.strip() if app_secret else ""
        self.token = token.strip() if token else ""
        self.base_url = base_url.strip() if base_url else "https://ap-southeast-1-api-genergal.aisweicloud.com"

    def _make_request(self, path: str, query_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make an API request with proper HMAC-SHA256 signature.
        
        Args:
            path: API path (e.g., '/pro/getPlanListPro')
            query_params: Dictionary of query parameters
            
        Returns:
            API response as a dictionary
        """
        method = "GET"
        content_type = "application/json; charset=UTF-8"
        accept = "application/json"
        
        # Initialize query params and insert token if not already present
        params = query_params.copy() if query_params else {}
        if "token" not in params:
            params["token"] = self.token
            
        # Filter out None values and convert all values to string
        filtered_params = {k: str(v) for k, v in params.items() if v is not None}
        
        # Sort parameters alphabetically as required by Alibaba API Gateway
        sorted_keys = sorted(filtered_params.keys())
        query_string_parts = []
        for key in sorted_keys:
            # We construct query string. Values should be URL-encoded for the final HTTP request,
            # but we must be careful with how the signature is computed.
            # In the signature string, we use the sorted parameter key-value pairs.
            query_string_parts.append(f"{key}={filtered_params[key]}")
            
        # Re-construct the endpoint path with sorted parameters
        query_string = "&".join(query_string_parts)
        endpoint = path
        if query_string:
            endpoint += f"?{query_string}"
            
        # Prepare headers
        headers = {
            "User-Agent": "app 1.0",
            "Content-Type": content_type,
            "Accept": accept,
            "X-Ca-Signature-Headers": "X-Ca-Key",
            "X-Ca-Key": self.app_key
        }
        
        # Generate signature string
        # StringToSign = HTTPMethod + "\n" + Accept + "\n" + Content-MD5 + "\n" + Content-Type + "\n" + Date + "\n" + Headers + Url
        # Content-MD5 is empty -> \n
        # Date is empty -> \n
        # Headers is: X-Ca-Key:{app_key}
        string_to_sign = f"{method}\n{accept}\n\n{content_type}\n\nX-Ca-Key:{self.app_key}\n{endpoint}"
        
        signature = base64.b64encode(
            hmac.new(
                self.app_secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        headers["X-Ca-Signature"] = signature
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            # We use verify=False in case there are regional SSL certificate hostname mismatches
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    return {"success": False, "error": "Invalid JSON response", "raw": response.text}
            else:
                # Retrieve error message from headers if available
                err_msg = response.headers.get("X-Ca-Error-Message", "HTTP error")
                err_code = response.headers.get("X-Ca-Error-Code", "Unknown")
                return {
                    "success": False, 
                    "error": f"{err_msg} (Code: {err_code})",
                    "status_code": response.status_code,
                    "response": response.text
                }
                
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Connection failed: {str(e)}"}

    def getPlanListPro(self) -> Dict[str, Any]:
        """
        API 3.1: Get the list of all registered power stations (plants).
        
        Returns:
            Dictionary containing plant lists, apikeys, names, statuses, etc.
        """
        return self._make_request("/pro/getPlanListPro")
    
    def getPlantOverviewPro(self, apikey: str) -> Dict[str, Any]:
        """
        API 3.2: Get real-time generation and efficiency overview of a specific plant.
        
        Args:
            apikey: The API Key (NMI) of the plant
        """
        return self._make_request("/pro/getPlantOverviewPro", {"apikey": apikey})
    
    def getPlantOutputPro(self, apikey: str, period: str = "bydays", date_str: str = None) -> Dict[str, Any]:
        """
        API 3.3: Get the historical power output curve of a plant.
        
        Args:
            apikey: The API Key (NMI) of the plant
            period: 'bydays', 'bymonth', 'byyear', or 'bytotal'
            date_str: Format matches the period:
                      - bydays: 'yyyy-MM-dd' (defaults to today)
                      - bymonth: 'yyyy-MM'
                      - byyear: 'yyyy'
        """
        params = {"apikey": apikey, "period": period}
        if date_str:
            params["date"] = date_str
        return self._make_request("/pro/getPlantOutputPro", params)
    
    def getDeviceListPro(self, apikey: str) -> Dict[str, Any]:
        """
        API 3.5: Get the list of devices (inverters, data loggers) in the plant.
        
        Args:
            apikey: The API Key (NMI) of the plant
        """
        return self._make_request("/pro/getDeviceListPro", {"apikey": apikey})
    
    def getLastTsDataPro(self, isnos: str) -> Dict[str, Any]:
        """
        API 3.7: Get real-time detailed telemetry for a set of inverters.
        
        Args:
            isnos: Comma-separated inverter serial numbers (e.g. "SN123,SN456")
        """
        return self._make_request("/pro/getLastTsDataPro", {"isnos": isnos})
