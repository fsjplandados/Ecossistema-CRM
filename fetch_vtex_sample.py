import requests
import json
import os

account_name = "sjdigital"
environment = "vtexcommercestable"
app_key = "vtexappkey-sjdigital-NBIBYX"
app_token = "ZWWMCOPAPYMWRDDFJXJASHHUYAHMNWFDLQKYEFYTGNOHDWBDBJGDWDRAQKGALTKTJZUTNMSEOSARVFCIQDNTEVGACYJBFYYKDFRYJTFSQJTOANANWPYYWISDULGXVMON"

url = f"https://{account_name}.{environment}.com.br/api/oms/pvt/orders"
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-VTEX-API-AppKey": app_key,
    "X-VTEX-API-AppToken": app_token
}

# Fetch the list of recent orders (just 1 to get an ID)
response = requests.get(url, headers=headers, params={"per_page": 1})

if response.status_code == 200:
    data = response.json()
    if data.get("list"):
        order_id = data["list"][0]["orderId"]
        
        # Fetch full order details
        order_url = f"https://{account_name}.{environment}.com.br/api/oms/pvt/orders/{order_id}"
        order_response = requests.get(order_url, headers=headers)
        
        if order_response.status_code == 200:
            order_data = order_response.json()
            with open("vtex_sample.json", "w", encoding="utf-8") as f:
                json.dump(order_data, f, indent=4, ensure_ascii=False)
            print(f"Sample order {order_id} fetched successfully and saved to vtex_sample.json.")
        else:
            print(f"Failed to fetch order details: {order_response.status_code} - {order_response.text}")
    else:
        print("No orders found.")
else:
    print(f"Failed to list orders: {response.status_code} - {response.text}")
