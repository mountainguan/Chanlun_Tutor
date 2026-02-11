
import akshare as ak

print("Checking specific THS cons functions...")
candidates = [
    'stock_board_cons_ths',
    'stock_board_concept_cons_ths',
    'stock_board_industry_cons_ths'
]

for c in candidates:
    if hasattr(ak, c):
        print(f"[FOUND] {c}")
    else:
        print(f"[MISSING] {c}")
