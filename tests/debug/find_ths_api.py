
import akshare as ak

print("Searching for THS related functions in akshare...")
for attr in dir(ak):
    if 'ths' in attr.lower() and 'industry' in attr.lower():
        print(attr)
    elif 'ths' in attr.lower() and 'cons' in attr.lower():
        print(attr)
