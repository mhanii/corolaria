
import requests
import sys
import json
import time

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "antonio"
PASSWORD = "passowrd"  # As requested by user

def login():
    print(f"Logging in as {USERNAME}...")
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=5
        )
        if response.status_code == 200:
            print("Login successful!")
            return response.json()
        elif response.status_code == 401:
            print("Login failed: Invalid credentials. Trying 'password'...")
            # Fallback
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"username": USERNAME, "password": "password"},
                timeout=5
            )
            if response.status_code == 200:
                print("Login successful with fallback password!")
                return response.json()
    except Exception as e:
        print(f"Login connection failed: {e}")
        return None
    
    print(f"Login failed: {response.status_code} - {response.text}")
    return None

def chat(token):
    print("\nTesting Agent Chat...")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Query that usually requires search/agent logic
    query = "Explica el contenido del artículo 12 de la Constitución y menciona si hay leyes relacionadas."
    
    params = {"collector_type": "agent"}
    data = {
        "message": query,
        "stream": False,
        "history": []
    }
    
    try:
        print(f"Sending query: '{query}' (collector_type=agent)")
        response = requests.post(
            f"{BASE_URL}/chat",
            headers=headers,
            params=params,
            json=data,
            timeout=120 # Agent might take longer
        )
        
        if response.status_code == 200:
            print("\nResponse Received:")
            print("-" * 50)
            res_json = response.json()
            print(json.dumps(res_json, indent=2, ensure_ascii=False))
            print("-" * 50)
            print("Agent test PASS")
        else:
            print(f"Chat failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Chat connection failed: {e}")

if __name__ == "__main__":
    auth_data = login()
    if auth_data:
        token = auth_data["access_token"]
        chat(token)
    else:
        sys.exit(1)
