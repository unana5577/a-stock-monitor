import json
import sys
from datetime import datetime


def main() -> int:
    day_override = sys.argv[1] if len(sys.argv) >= 2 else None
    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import akshare failed: {e}"}), file=sys.stdout)
        return 0

    try:
        df = ak.fund_etf_category_sina(symbol="ETF基金")
        if df is None or df.empty:
            print(json.dumps({"ok": False, "error": "empty result"}), file=sys.stdout)
            return 0

        amount_col = "成交额"
        if amount_col not in df.columns:
            print(json.dumps({"ok": False, "error": f"missing column: {amount_col}"}), file=sys.stdout)
            return 0

        total = float(df[amount_col].fillna(0).astype(float).sum())
        out = {
            "ok": True,
            "date": str(day_override or datetime.now().strftime("%Y-%m-%d")),
            "total_amount": total,
            "count": int(df.shape[0]),
        }
        print(json.dumps(out, ensure_ascii=False), file=sys.stdout)
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
