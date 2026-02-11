
import akshare as ak

print("Searching for 'cons' functions in akshare...")
for attr in dir(ak):
    if 'cons' in attr.lower() and ('ths' in attr.lower() or 'industry' in attr.lower()):
        print(attr)
