import json
import os
import sys


def main() -> int:
    start = sys.argv[1] if len(sys.argv) >= 2 else "2025-05-19"
    end = sys.argv[2] if len(sys.argv) >= 3 else None
    scale_arg = sys.argv[3] if len(sys.argv) >= 4 else None

    try:
        import akshare as ak
        import pandas as pd
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import failed: {e}"}), file=sys.stdout)
        return 0

    try:
        sh = ak.stock_zh_index_daily_tx(symbol="sh000001")
        sz = ak.stock_zh_index_daily_tx(symbol="sz399001")
        if sh is None or sh.empty or sz is None or sz.empty:
            print(json.dumps({"ok": False, "error": "empty index data"}), file=sys.stdout)
            return 0

        sh = sh.rename(columns={"date": "day", "amount": "sh_amount"})
        sz = sz.rename(columns={"date": "day", "amount": "sz_amount"})
        sh["day"] = pd.to_datetime(sh["day"]).dt.strftime("%Y-%m-%d")
        sz["day"] = pd.to_datetime(sz["day"]).dt.strftime("%Y-%m-%d")
        sh = sh[["day", "sh_amount"]]
        sz = sz[["day", "sz_amount"]]
        df = pd.merge(sh, sz, on="day", how="outer")
        df["sh_amount"] = pd.to_numeric(df["sh_amount"], errors="coerce").fillna(0)
        df["sz_amount"] = pd.to_numeric(df["sz_amount"], errors="coerce").fillna(0)
        df["total_amount"] = df["sh_amount"] + df["sz_amount"]
        df = df.sort_values("day")
        df = df[df["day"] >= start]
        if end:
            df = df[df["day"] <= end]
        df = df[df["total_amount"] > 0]

        scale = None
        if scale_arg:
            try:
                scale = float(scale_arg)
            except Exception:
                scale = None
        if scale is None:
            try:
                import requests
                snap = requests.get("http://localhost:8787/api/snapshot/latest?ai=0", timeout=5).json()
                vol_wan = float(((snap.get("sentiment") or {}).get("volume")) or 0.0)
                target_yuan = vol_wan * 10000.0
                last_total = float(df["total_amount"].iloc[-1])
                if last_total > 0 and target_yuan > 0:
                    scale = target_yuan / last_total
            except Exception:
                scale = None
        if scale is not None and scale > 0:
            df["sh_amount"] = df["sh_amount"] * scale
            df["sz_amount"] = df["sz_amount"] * scale
            df["total_amount"] = df["total_amount"] * scale

        out_path = os.path.join(os.path.dirname(__file__), "..", "data", "market-amount-daily.jsonl")
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for _, r in df.iterrows():
                row = [r["day"], float(r["total_amount"]), float(r["sh_amount"]), float(r["sz_amount"])]
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(json.dumps({"ok": True, "start": start, "end": end, "rows": int(df.shape[0]), "path": out_path, "scale": scale}, ensure_ascii=False), file=sys.stdout)
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
