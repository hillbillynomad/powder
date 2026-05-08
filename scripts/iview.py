#!/usr/bin/env python3

import os
import time
import requests


def get_coordinates(query):
    """Get latitude and longitude for a location query using Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    
    params = {
        'q': query,
        'format': 'json',
        'limit': 1  # Only return the best match
    }
    
    # Nominatim requires a valid User-Agent with contact info
    headers = {
        'User-Agent': 'PowderSnowTracker/1.0 (https://github.com/powder-project)'
    }
    
    # Nominatim requires max 1 request per second
    time.sleep(1)

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            print(f"Found coordinates for '{query}': lat={lat}, lon={lon}")
            return lat, lon
        else:
            print(f"No results found for '{query}'")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error getting coordinates: {e}")
        return None


def get_snowfall(location):
    """Get snowfall data for a location."""
    # First get coordinates
    result = get_coordinates(location)
    if result is None:
        return None
    
    latitude, longitude = result  # get_coordinates returns (lat, lon)
    
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'start_date': "2025-01-01",
        'end_date': "2025-01-10",
        'daily': "snowfall_sum",
        'timezone': "UTC"
    }
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    
    try:
        print(f"Fetching snowfall data from: {url}")
        print(f"Parameters: {params}")
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        print(f"Response: {data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error getting snowfall: {e}")
        return None


if __name__ == '__main__':
    # For debugging, use a hardcoded location or prompt
    location = input("Enter location (e.g., 'Mammoth Mountain, CA'): ") if not os.environ.get('OUTPUT_PATH') else input()
    
    if os.environ.get('OUTPUT_PATH'):
        # HackerRank mode
        fptr = open(os.environ['OUTPUT_PATH'], 'w')
        result = get_snowfall(location)
        if result:
            fptr.write(str(result))
        fptr.write('\n')
        fptr.close()
    else:
        # Debug mode
        result = get_snowfall(location)
        if result:
            print("\n=== Snowfall Results ===")
            if 'daily' in result:
                dates = result['daily'].get('time', [])
                snowfall = result['daily'].get('snowfall_sum', [])
                for date, snow in zip(dates, snowfall):
                    print(f"  {date}: {snow} cm")
