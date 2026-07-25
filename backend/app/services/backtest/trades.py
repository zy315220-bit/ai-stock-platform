from __future__ import annotations

from typing import Any

import pandas as pd


# ==================================================
# 台灣 ETF 交易成本
# ==================================================

COMMISSION_RATE = 0.001425
ETF_TRANSACTION_TAX_RATE = 0.001


def _calculate_buy_cost(
    price: float,
    shares: int,
    commission_rate: float,
) -> dict[str, float]:
    """
    計算買進成本。
    """

    gross_amount = (
        price * shares
    )

    commission = (
        gross_amount
        * commission_rate
    )

    total_cost = (
        gross_amount
        + commission
    )

    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "total_cost": total_cost,
    }

def _calculate_sell_value(
    price: float,
    shares: int,
    commission_rate: float,
    transaction_tax_rate: float,
) -> dict[str, float]:
    """
    計算賣出後實際取得的金額。
    """

    gross_amount = (
        price * shares
    )

    commission = (
        gross_amount
        * commission_rate
    )

    transaction_tax = (
        gross_amount
        * transaction_tax_rate
    )

    net_amount = (
        gross_amount
        - commission
        - transaction_tax
    )

    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "transaction_tax": (
            transaction_tax
        ),
        "net_amount": net_amount,
    }

def _calculate_purchasable_shares(
    cash: float,
    price: float,
    commission_rate: float,
) -> int:
    """
    計算包含買進手續費後，
    實際最多可以購買的股數。
    """

    if cash <= 0 or price <= 0:
        return 0

    estimated_cost_per_share = (
        price
        * (
            1
            + commission_rate
        )
    )

    shares = int(
        cash
        // estimated_cost_per_share
    )

    while shares > 0:
        buy_cost = _calculate_buy_cost(
            price=price,
            shares=shares,
            commission_rate=(
                commission_rate
            ),
        )

        if (
            buy_cost["total_cost"]
            <= cash
        ):
            return shares

        shares -= 1

    return 0

def _enrich_trades_with_excursions(
    df: pd.DataFrame,
    trades: list[dict[str, Any]],
) -> None:
    """
    依照每筆交易的進出場日期，補上交易期間分析：

    - holding_days：日曆持有天數
    - holding_bars：持有期間交易日數
    - highest_price / highest_date：持有期間最高價與日期
    - lowest_price / lowest_date：持有期間最低價與日期
    - mfe_percent：最大有利變動（Maximum Favorable Excursion）
    - mae_percent：最大不利變動（Maximum Adverse Excursion）

    此函式直接修改 trades 內的每筆交易資料。
    """

    if df is None or df.empty or not trades:
        return

    working_df = df.copy()

    if "Date" not in working_df.columns:
        return

    working_df["Date"] = pd.to_datetime(
        working_df["Date"],
        errors="coerce",
    )

    working_df = working_df.dropna(
        subset=["Date", "High", "Low"]
    ).copy()

    if working_df.empty:
        return

    for trade in trades:
        entry_date = trade.get("entry_date")
        exit_date = trade.get("exit_date")
        entry_price = float(
            trade.get("entry_price", 0.0) or 0.0
        )

        if not entry_date or not exit_date:
            trade["holding_days"] = None
            trade["holding_bars"] = 0
            trade["highest_price"] = None
            trade["highest_date"] = None
            trade["lowest_price"] = None
            trade["lowest_date"] = None
            trade["mfe_percent"] = None
            trade["mae_percent"] = None
            continue

        entry_timestamp = pd.Timestamp(entry_date)
        exit_timestamp = pd.Timestamp(exit_date)

        period_df = working_df.loc[
            (working_df["Date"] >= entry_timestamp)
            & (working_df["Date"] <= exit_timestamp)
        ].copy()

        holding_days = max(
            (exit_timestamp - entry_timestamp).days,
            0,
        )

        trade["holding_days"] = holding_days
        trade["holding_bars"] = int(len(period_df))

        if period_df.empty or entry_price <= 0:
            trade["highest_price"] = None
            trade["highest_date"] = None
            trade["lowest_price"] = None
            trade["lowest_date"] = None
            trade["mfe_percent"] = None
            trade["mae_percent"] = None
            continue

        highest_index = period_df["High"].astype(float).idxmax()
        lowest_index = period_df["Low"].astype(float).idxmin()

        highest_price = float(
            period_df.loc[highest_index, "High"]
        )
        lowest_price = float(
            period_df.loc[lowest_index, "Low"]
        )

        highest_date = pd.Timestamp(
            period_df.loc[highest_index, "Date"]
        ).strftime("%Y-%m-%d")

        lowest_date = pd.Timestamp(
            period_df.loc[lowest_index, "Date"]
        ).strftime("%Y-%m-%d")

        mfe_percent = (
            (highest_price - entry_price)
            / entry_price
            * 100
        )

        mae_percent = (
            (lowest_price - entry_price)
            / entry_price
            * 100
        )

        trade["highest_price"] = round(
            highest_price,
            2,
        )
        trade["highest_date"] = highest_date
        trade["lowest_price"] = round(
            lowest_price,
            2,
        )
        trade["lowest_date"] = lowest_date
        trade["mfe_percent"] = round(
            mfe_percent,
            2,
        )
        trade["mae_percent"] = round(
            mae_percent,
            2,
        )

def _calculate_exposure_percent(
    equity_curve: list[dict[str, Any]],
) -> float:
    """
    計算策略持倉曝險比例。

    曝險比例 =
    有持倉的交易日數 / 全部回測交易日數 × 100%
    """

    if not equity_curve:
        return 0.0

    invested_points = sum(
        1
        for point in equity_curve
        if int(point.get("shares", 0) or 0) > 0
    )

    return (
        invested_points
        / len(equity_curve)
        * 100
    )

def _calculate_advanced_trade_statistics(
    trades: list[dict[str, Any]],
    initial_capital: float,
    final_capital: float,
    max_drawdown_percent: float,
    exposure_percent: float,
) -> dict[str, Any]:
    """
    計算進階交易統計：

    - 平均獲利、平均虧損
    - Payoff Ratio
    - Expectancy
    - Recovery Factor
    - 最大連勝、最大連敗
    - 最長、最短持有天數
    - 平均 MFE、平均 MAE
    - Exposure
    """

    if not trades:
        return {
            "average_win": 0.0,
            "average_loss": 0.0,
            "payoff_ratio": None,
            "expectancy": 0.0,
            "recovery_factor": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "longest_holding_days": 0,
            "shortest_holding_days": 0,
            "average_mfe_percent": 0.0,
            "average_mae_percent": 0.0,
            "exposure_percent": round(
                exposure_percent,
                2,
            ),
        }

    profits = [
        float(trade.get("profit", 0.0) or 0.0)
        for trade in trades
    ]

    winning_profits = [
        profit
        for profit in profits
        if profit > 0
    ]

    losing_profits = [
        profit
        for profit in profits
        if profit < 0
    ]

    average_win = (
        sum(winning_profits)
        / len(winning_profits)
        if winning_profits
        else 0.0
    )

    average_loss = (
        abs(sum(losing_profits))
        / len(losing_profits)
        if losing_profits
        else 0.0
    )

    payoff_ratio: float | None

    if average_loss > 0:
        payoff_ratio = (
            average_win
            / average_loss
        )
    elif average_win > 0:
        payoff_ratio = None
    else:
        payoff_ratio = 0.0

    win_probability = (
        len(winning_profits)
        / len(trades)
    )

    loss_probability = (
        len(losing_profits)
        / len(trades)
    )

    expectancy = (
        win_probability * average_win
        - loss_probability * average_loss
    )

    total_profit = (
        final_capital
        - initial_capital
    )

    max_drawdown_amount = (
        initial_capital
        * max_drawdown_percent
        / 100
    )

    recovery_factor = (
        total_profit / max_drawdown_amount
        if max_drawdown_amount > 0
        else 0.0
    )

    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0

    for profit in profits:
        if profit > 0:
            current_wins += 1
            current_losses = 0
        elif profit < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0

        max_consecutive_wins = max(
            max_consecutive_wins,
            current_wins,
        )

        max_consecutive_losses = max(
            max_consecutive_losses,
            current_losses,
        )

    holding_days = [
        int(trade["holding_days"])
        for trade in trades
        if trade.get("holding_days") is not None
    ]

    mfe_values = [
        float(trade["mfe_percent"])
        for trade in trades
        if trade.get("mfe_percent") is not None
    ]

    mae_values = [
        float(trade["mae_percent"])
        for trade in trades
        if trade.get("mae_percent") is not None
    ]

    return {
        "average_win": round(
            average_win,
            2,
        ),
        "average_loss": round(
            average_loss,
            2,
        ),
        "payoff_ratio": (
            round(payoff_ratio, 3)
            if payoff_ratio is not None
            else None
        ),
        "expectancy": round(
            expectancy,
            2,
        ),
        "recovery_factor": round(
            recovery_factor,
            3,
        ),
        "max_consecutive_wins": int(
            max_consecutive_wins
        ),
        "max_consecutive_losses": int(
            max_consecutive_losses
        ),
        "longest_holding_days": (
            max(holding_days)
            if holding_days
            else 0
        ),
        "shortest_holding_days": (
            min(holding_days)
            if holding_days
            else 0
        ),
        "average_mfe_percent": round(
            sum(mfe_values) / len(mfe_values),
            2,
        )
        if mfe_values
        else 0.0,
        "average_mae_percent": round(
            sum(mae_values) / len(mae_values),
            2,
        )
        if mae_values
        else 0.0,
        "exposure_percent": round(
            exposure_percent,
            2,
        ),
    }