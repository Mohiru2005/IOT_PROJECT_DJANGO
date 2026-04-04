import json
import urllib.request
from urllib.error import URLError
import os
import time

_weather_cache = {"data": None, "last_updated": 0}

def get_vaddeswaram_weather():
    now = time.time()
    # Cache for 10 minutes (600 seconds)
    if _weather_cache["data"] and (now - _weather_cache["last_updated"] < 600):
        return _weather_cache["data"]

    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    # Using coordinates for Vaddeswaram since the city name isn't found in OpenWeather
    url = f"http://api.openweathermap.org/data/2.5/weather?lat=16.4442&lon=80.6224&appid={api_key}&units=metric"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            temp = data['main']['temp']
            desc = data['weather'][0]['description'].title()
            icon = data['weather'][0]['icon']
            result = {"temp": f"{temp}°C", "desc": desc, "icon_url": f"http://openweathermap.org/img/wn/{icon}.png"}
            _weather_cache["data"] = result
            _weather_cache["last_updated"] = now
            return result
    except Exception as e:
        if _weather_cache["data"]:
            return _weather_cache["data"]
        return {"temp": "--°C", "desc": "Unavailable", "icon_url": ""}
