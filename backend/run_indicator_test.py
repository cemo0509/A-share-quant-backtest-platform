from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

resp = client.get('/api/stocks/indicators', params={'symbol': 'sh600276'})
print('status_code=', resp.status_code)
try:
    data = resp.json()
    print('json_keys=', list(data.keys())[:10])
    # Check for NaN presence
    import json
    s = json.dumps(data)
    print('json_valid_length=', len(s))
    # Quick scan for NaN or Infinity
    if 'NaN' in s or 'Infinity' in s or 'inf' in s:
        print('Found non-finite values in JSON string')
    else:
        print('No non-finite literals found in JSON string')
except Exception as e:
    print('resp.json() failed:', e)
    print(resp.text)
