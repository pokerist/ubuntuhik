import hmac, hashlib, base64
from urllib.parse import urlparse

method = 'POST'
accept = 'application/json'
content_type = 'application/json;charset=UTF-8'
app_key = '22452825'
app_secret = 'Q9bWogAziordVdIngfoa'
nonce = '0049395a-85a5-4991-8240-148dcf3e3612'
timestamp = '1592894521052'
# base URL used in real requests (we'll show both path-only and include-port variants)
base_url = 'https://10.19.133.55:443/artemis'
endpoint = '/artemis/api/common/v1/version'
# No body in example
body = ''

def build_string_to_sign(uri_for_sign: str):
	parts = [method, accept]
	# content-md5 omitted because body empty
	parts.append(content_type)
	parts.append(f"x-ca-key:{app_key}")
	parts.append(f"x-ca-nonce:{nonce}")
	parts.append(f"x-ca-timestamp:{timestamp}")
	parts.append(uri_for_sign)
	return '\n'.join(parts)

parsed = urlparse(base_url)
base_path = parsed.path.rstrip('/') if parsed.path else ''
port = parsed.port

# Variant A: path-only
uri_a = f"{base_path}{endpoint}"
string_a = build_string_to_sign(uri_a)
sig_a = base64.b64encode(hmac.new(app_secret.encode('utf-8'), string_a.encode('utf-8'), hashlib.sha256).digest()).decode()

# Variant B: include port (if available)
if port:
	uri_b = f"{base_path}:{port}{endpoint}"
	string_b = build_string_to_sign(uri_b)
	sig_b = base64.b64encode(hmac.new(app_secret.encode('utf-8'), string_b.encode('utf-8'), hashlib.sha256).digest()).decode()
else:
	uri_b = None
	string_b = None
	sig_b = None

print('--- Variant A: PATH-ONLY ---')
print('URI used for sign:', uri_a)
print('STRING_TO_SIGN:\n' + string_a)
print('\nSIGNATURE:')
print(sig_a)

if uri_b:
	print('\n--- Variant B: INCLUDE-PORT ---')
	print('URI used for sign:', uri_b)
	print('STRING_TO_SIGN:\n' + string_b)
	print('\nSIGNATURE:')
	print(sig_b)
