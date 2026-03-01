import numpy as np
import pandas as pd


def _trade_flag(df):
    flag = pd.Series(False, index=df.index)
    if "amount" in df:
        flag = flag | (df["amount"].fillna(0) > 0)
    if "volume" in df:
        flag = flag | (df["volume"].fillna(0) > 0)
    if "pct" in df:
        flag = flag | (df["pct"].notna() & (df["pct"] != 0))
    if "turnover" in df:
        flag = flag | (df["turnover"].fillna(0) > 0)
    return flag


def rolling_returns(df):
    out = df.copy()
    out["pct"] = pd.to_numeric(out["pct"], errors="coerce").fillna(0)

    def apply_roll(group, sector):
        group = group.copy().sort_values("date")
        pct = group["pct"] / 100.0
        r5 = (1 + pct).rolling(5).apply(np.prod, raw=True) - 1
        r10 = (1 + pct).rolling(10).apply(np.prod, raw=True) - 1
        r20 = (1 + pct).rolling(20).apply(np.prod, raw=True) - 1
        close_idx = (1 + pct).cumprod()
        ma5 = close_idx.rolling(5).mean()
        bias_5 = close_idx / ma5 - 1
        group["ret_5"] = (r5 * 100).round(2)
        group["ret_10"] = (r10 * 100).round(2)
        group["ret_20"] = (r20 * 100).round(2)
        group["bias_5"] = (bias_5 * 100).round(2)
        group["sector"] = sector
        return group

    frames = []
    for sector, group in out.groupby("sector", group_keys=False):
        frames.append(apply_roll(group, sector))
    return pd.concat(frames, ignore_index=True)


def price_metrics(df):
    out = df.copy()
    if "close" in out.columns:
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
    else:
        out["close"] = np.nan
    if "open" in out.columns:
        out["open"] = pd.to_numeric(out["open"], errors="coerce")
    if "high" in out.columns:
        out["high"] = pd.to_numeric(out["high"], errors="coerce")
    if "low" in out.columns:
        out["low"] = pd.to_numeric(out["low"], errors="coerce")

    def apply_calc(group, sector):
        group = group.sort_values("date").copy()
        group["sector"] = sector
        pct = pd.to_numeric(group["pct"], errors="coerce").fillna(0) / 100.0
        close = group["close"]
        if close.isna().all():
            close = (1 + pct).cumprod() * 1000
        else:
            close = close.ffill().bfill()
            if close.isna().all():
                close = (1 + pct).cumprod() * 1000
        group["close"] = close
        trade = _trade_flag(group)
        trade_close = close.where(trade)
        ma20_trade = trade_close[trade].rolling(20).mean()
        ma60_trade = trade_close[trade].rolling(60).mean()
        ma20_slope_trade = (ma20_trade - ma20_trade.shift(5)) / ma20_trade.shift(5) * 100
        ma60_slope_trade = (ma60_trade - ma60_trade.shift(5)) / ma60_trade.shift(5) * 100
        ma20 = ma20_trade.reindex(group.index)
        ma60 = ma60_trade.reindex(group.index)
        ma20_slope = ma20_slope_trade.reindex(group.index)
        ma60_slope = ma60_slope_trade.reindex(group.index)
        group["ma20"] = ma20
        group["ma60"] = ma60
        group["ma20_slope"] = ma20_slope
        group["ma60_slope"] = ma60_slope
        group["bias_20"] = (close / ma20 - 1) * 100
        if "open" in group.columns and "high" in group.columns and "low" in group.columns:
            op = group["open"]
            hi = group["high"]
            lo = group["low"]
            denom = hi - lo
            score = (close - op) / denom.replace(0, np.nan)
            group["intra_score"] = score.replace([np.inf, -np.inf], np.nan)
        else:
            group["intra_score"] = np.nan
        return group

    frames = []
    for sector, group in out.groupby("sector", group_keys=False):
        frames.append(apply_calc(group, sector))
    return pd.concat(frames, ignore_index=True)


def amount_share(df):
    out = df.copy()
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
    if "type" in out.columns and (out["type"] == "market").any():
        market_total = out[out["type"] == "market"].groupby("date")["amount"].sum()
    elif "type" in out.columns:
        market_total = out[out["type"] == "sector"].groupby("date")["amount"].sum()
    else:
        exclude = {"上证", "深证", "创业板", "科创板", "科创50", "10年国债", "30年国债", "沪深成交额"}
        market_total = out[~out["sector"].isin(exclude)].groupby("date")["amount"].sum()
    total = out["date"].map(market_total)
    share = out["amount"] / total.replace(0, np.nan)
    if "type" in out.columns:
        sector_mask = out["type"] == "sector"
    else:
        sector_mask = ~out["sector"].isin({"上证", "深证", "创业板", "科创板", "科创50", "10年国债", "30年国债", "沪深成交额"})
    out["amount_share"] = np.where(sector_mask, (share * 100).round(2), np.nan)
    out["amount_share_pct"] = (
        out.groupby("sector", group_keys=False)
        .apply(lambda g: rolling_percentile(g, "amount_share", 180))
    )
    out["amount_abs_pct"] = (
        out.groupby("sector", group_keys=False)
        .apply(lambda g: rolling_percentile(g, "amount", 180))
    )
    return out


def rolling_percentile(group, value_col, window):
    group = group.sort_values("date")
    values = group[value_col].to_list()
    vals = []
    for i, v in enumerate(values):
        if pd.isna(v):
            vals.append(np.nan)
            continue
        start = max(0, i - window + 1)
        buf = [x for x in values[start:i + 1] if not pd.isna(x)]
        if not buf:
            vals.append(np.nan)
            continue
        arr = np.array(buf)
        vals.append(float((arr <= v).mean() * 100))
    return pd.Series(vals, index=group.index)


def turnover_metrics(df):
    out = df.copy()
    out["turnover"] = pd.to_numeric(out["turnover"], errors="coerce").fillna(0)
    out["turnover_ma20"] = (
        out.groupby("sector")["turnover"]
        .transform(lambda s: s.rolling(20).mean())
    )
    out["turnover_dev"] = out["turnover"] / out["turnover_ma20"]
    out["turnover_dev"] = out["turnover_dev"].replace([np.inf, -np.inf], np.nan) - 1
    out["turnover_pct"] = (
        out.groupby("sector", group_keys=False)
        .apply(lambda g: rolling_percentile(g, "turnover", 180))
    )
    return out


def dynamic_benchmark_metrics(df, benchmark_names):
    out = df.copy()
    base = (
        out[out["sector"].isin(benchmark_names)]
        .groupby(["date", "sector"], as_index=False)["pct"]
        .last()
        .pivot(index="date", columns="sector", values="pct")
    )
    if base.empty:
        out["bench_pct"] = np.nan
        out["bench_ret_5"] = np.nan
        out["bench_ret_10"] = np.nan
        out["bench_ret_20"] = np.nan
        if "alpha_5" not in out.columns:
            out["alpha_5"] = np.nan
        out["alpha_10"] = np.nan
        out["alpha_20"] = np.nan
        if "relative_bias" in out.columns:
            out["bias"] = out["relative_bias"]
        else:
            out["bias"] = np.nan
        return out

    def roll_ret(s, window):
        pct = s / 100.0
        r = (1 + pct).rolling(window).apply(np.prod, raw=True) - 1
        return r * 100

    bench_ret_5 = base.apply(lambda s: roll_ret(s, 5))
    bench_ret_10 = base.apply(lambda s: roll_ret(s, 10))
    bench_ret_20 = base.apply(lambda s: roll_ret(s, 20))
    bench_pct_long = base.stack().rename("bench_pct")
    bench_ret_5_long = bench_ret_5.stack().rename("bench_ret_5")
    bench_ret_10_long = bench_ret_10.stack().rename("bench_ret_10")
    bench_ret_20_long = bench_ret_20.stack().rename("bench_ret_20")
    bench_df = (
        pd.concat([bench_pct_long, bench_ret_5_long, bench_ret_10_long, bench_ret_20_long], axis=1)
        .reset_index()
        .rename(columns={"sector": "bench_name"})
    )
    out = out.merge(bench_df, how="left", on=["date", "bench_name"])
    if "alpha_5" in out.columns:
        out["alpha_5"] = out["alpha_5"].fillna(out["ret_5"] - out["bench_ret_5"])
    else:
        out["alpha_5"] = out["ret_5"] - out["bench_ret_5"]
    out["alpha_10"] = out["ret_10"] - out["bench_ret_10"]
    out["alpha_20"] = out["ret_20"] - out["bench_ret_20"]
    if "relative_bias" in out.columns:
        out["bias"] = out["relative_bias"]
    else:
        out["bias"] = out["alpha_5"]
    return out


def rs_and_rank(df, corr_col="bench_corr_20", corr_threshold=0.3):
    out = df.copy()
    out["alpha_20"] = pd.to_numeric(out.get("alpha_20"), errors="coerce")
    out["ret_20"] = pd.to_numeric(out.get("ret_20"), errors="coerce")
    if corr_col not in out.columns:
        out[corr_col] = np.nan
    corr_vals = pd.to_numeric(out[corr_col], errors="coerce")
    base = np.where(corr_vals >= corr_threshold, out["alpha_20"], out["ret_20"])
    base = np.where(pd.isna(base), out["ret_20"], base)
    out["rs_base_20"] = base

    def apply_rs(group, sector):
        group = group.sort_values("date").copy()
        group["sector"] = sector
        group["rs_change20"] = group["rs_base_20"] - group["rs_base_20"].shift(20)
        return group

    frames = []
    for sector, group in out.groupby("sector", group_keys=False):
        frames.append(apply_rs(group, sector))
    out = pd.concat(frames, ignore_index=True)

    def rank_percent(group, col):
        s = group[col]
        n = s.notna().sum()
        if n == 0:
            return pd.Series([np.nan] * len(s), index=s.index)
        if n == 1:
            return pd.Series([100.0 if pd.notna(v) else np.nan for v in s], index=s.index)
        ranks = s.rank(ascending=False, method="min")
        pct = (1 - (ranks - 1) / (n - 1)) * 100
        return pct.where(s.notna())

    sector_mask = out["type"].eq("sector") if "type" in out.columns else pd.Series(True, index=out.index)
    for col, out_col in [("ret_20", "rank_ret_20"), ("rs_change20", "rank_rs_change20"), ("intra_score", "rank_intra_score")]:
        ranks = (
            out[sector_mask]
            .groupby("date", group_keys=False)
            .apply(lambda g: rank_percent(g, col))
        )
        out[out_col] = np.nan
        out.loc[sector_mask, out_col] = ranks

    def score_row(row):
        items = [("rank_ret_20", 0.4), ("rank_rs_change20", 0.4), ("rank_intra_score", 0.2)]
        total = 0.0
        weight = 0.0
        for col, w in items:
            v = row.get(col)
            if pd.notna(v):
                total += v * w
                weight += w
        if weight == 0:
            return np.nan
        return total / weight

    out["signal_score"] = out.apply(score_row, axis=1)
    return out


def lifecycle_stage(df):
    out = df.copy()
    def apply_stage(group, sector):
        group = group.sort_values("date").copy()
        group["sector"] = sector
        close = pd.to_numeric(group["close"], errors="coerce")
        ma20 = pd.to_numeric(group["ma20"], errors="coerce")
        ma60 = pd.to_numeric(group["ma60"], errors="coerce")
        ma20_slope = pd.to_numeric(group["ma20_slope"], errors="coerce")
        ma60_slope = pd.to_numeric(group["ma60_slope"], errors="coerce")
        bias_20 = pd.to_numeric(group["bias_20"], errors="coerce")
        rs_change20 = pd.to_numeric(group["rs_change20"], errors="coerce")
        amount_share_pct = pd.to_numeric(group.get("amount_share_pct"), errors="coerce")
        pct = pd.to_numeric(group.get("pct"), errors="coerce")
        close_max20 = close.rolling(20).max()
        rs_max20 = rs_change20.rolling(20).max()
        share_max20 = amount_share_pct.rolling(20).max()
        share_drop = share_max20 - amount_share_pct
        stage = []
        for i in range(len(group)):
            c = close.iloc[i]
            m20 = ma20.iloc[i]
            m60 = ma60.iloc[i]
            m20s = ma20_slope.iloc[i]
            m60s = ma60_slope.iloc[i]
            b20 = bias_20.iloc[i]
            rs = rs_change20.iloc[i]
            sh = amount_share_pct.iloc[i]
            shd = share_drop.iloc[i]
            cm = close_max20.iloc[i]
            rsm = rs_max20.iloc[i]
            p = pct.iloc[i]
            label = None
            if pd.notna(c) and pd.notna(m20) and pd.notna(m60) and c < m20 and m20 < m60:
                label = "衰退期"
            elif pd.notna(c) and pd.notna(cm) and c >= cm * 0.995 and pd.notna(rsm) and pd.notna(rs) and rs < rsm * 0.7:
                label = "背离期"
            elif pd.notna(shd) and shd >= 20:
                label = "背离期"
            elif pd.notna(b20) and b20 >= 8 and pd.notna(m20s) and m20s > 0:
                label = "加速期"
            elif pd.notna(b20) and b20 >= 2 and b20 <= 5 and pd.notna(m20s) and abs(m20s) <= 0.2:
                label = "震荡期"
            elif pd.notna(c) and pd.notna(m60) and c > m60 and pd.notna(m60s) and m60s > 0 and pd.notna(p) and p >= 2 and pd.notna(sh) and sh >= 60:
                label = "启动期"
            elif pd.notna(c) and pd.notna(m60) and c < m60 and pd.notna(rs) and rs >= -0.2 and pd.notna(sh) and sh <= 30:
                label = "潜伏期"
            else:
                if pd.notna(c) and pd.notna(m60) and c >= m60:
                    label = "震荡期"
                else:
                    label = "潜伏期"
            stage.append(label)
        group["lifecycle"] = stage
        return group

    frames = []
    for sector, group in out.groupby("sector", group_keys=False):
        frames.append(apply_stage(group, sector))
    return pd.concat(frames, ignore_index=True)


def style_hint(df):
    out = df.copy()
    if "bench_label" not in out.columns:
        out["style_hint"] = np.nan
        return out
    labels = out["bench_label"].fillna("")
    hint = []
    for v in labels:
        if v in ["科创板", "科创50", "创业板"]:
            hint.append("进攻")
        elif v in ["上证", "深证", "上证50", "沪深300"]:
            hint.append("防御")
        elif v in ["中证2000"]:
            hint.append("微盘")
        else:
            hint.append("-")
    out["style_hint"] = hint
    return out
