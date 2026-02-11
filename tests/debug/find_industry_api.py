
import akshare as ak

print("Searching for 'industry' functions in akshare...")
for attr in dir(ak):
    if 'industry' in attr.lower():
        print(attr)
