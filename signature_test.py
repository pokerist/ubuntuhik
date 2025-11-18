import hmac, hashlib, base64
method='POST'
accept='application/json'
content_type='application/json;charset=UTF-8'
app_key='22452825'
app_secret='Q9bWogAziordVdIngfoa'
nonce='0049395a-85a5-4991-8240-148dcf3e3612'
timestamp='1592894521052'
uri='/artemis/api/common/v1/version'
# No body in example
body=''
parts=[method, accept]
# content-md5 omitted because body empty
parts.append(content_type)
parts.append(f"x-ca-key:{app_key}")
parts.append(f"x-ca-nonce:{nonce}")
parts.append(f"x-ca-timestamp:{timestamp}")
parts.append(uri)
string_to_sign='\n'.join(parts)
print('STRING_TO_SIGN:\n'+string_to_sign)
signature = base64.b64encode(hmac.new(app_secret.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
print('\nSIGNATURE:')
print(signature)
