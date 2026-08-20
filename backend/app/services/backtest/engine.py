from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services.history_policy import (
    BACKTEST_WARMUP_MONTHS,
    RESEARCH_HISTORY_MONTHS,
    default_research_start_date,
)
from app.services.research_history import frame_coverage

# 這三個模組位於 backend 根目錄
from indicators import add_indicators
from score_engine.calculate import calculate_score
from stock import download_stock
from corporate_actions import dividends_by_ex_date

from .benchmark import _calculate_buy_and_hold
from .drawdown import (
    _calculate_drawdown_statistics,
    _calculate_max_drawdown,
)
from .metrics import _calculate_performance_metrics
from .report import (
    _extract_score,
    _get_row_date,
    _prepare_stock_data,
)
from .trades import (
    COMMISSION_RATE,
    ETF_TRANSACTION_TAX_RATE,
    _calculate_advanced_trade_statistics,
    _calculate_buy_cost,
    _calculate_exposure_percent,
    _calculate_purchasable_shares,
    _calculate_sell_value,
    _enrich_trades_with_excursions,
)


MAX_INITIAL_CAPITAL = 2_000_000

# 回測只應因「實際交易與核心評分所需」欄位缺值而刪除日期。
# add_indicators 也會產生輔助診斷欄位；其中任一欄位偶發 NaN 時，
# 若使用無條件 dropna()，會把原本有效的多年行情誤裁成較短期間。
BACKTEST_REQUIRED_COLUMNS = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "EMA20",
    "EMA60",
    "ATR",
]


def backtest_stock(
    stock_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    entry_score: float = 75,
    exit_score: float = 55,
    initial_capital: float = 100_000,
    commission_rate: float = (
        COMMISSION_RATE
    ),
    transaction_tax_rate: float = (
        ETF_TRANSACTION_TAX_RATE
    ),
) -> dict[str, Any]:
    """
    台灣股票型 ETF 日線回測：

    - 評分 >= entry_score：
      下一交易日開盤買進
    - 評分 <= exit_score：
      下一交易日開盤賣出
    - 每次使用全部可用資金
    - 買進與賣出皆計算手續費
    - 賣出時計算 ETF 證券交易稅
    """

    normalized_code = (
        stock_code
        .strip()
        .upper()
    )

    if not normalized_code:
        raise ValueError(
            "股票代號不能空白。"
        )

    normalized_capital = float(initial_capital)

    if not math.isfinite(normalized_capital) or normalized_capital <= 0:
        raise ValueError(
            "初始資金必須大於 0。"
        )

    if normalized_capital > MAX_INITIAL_CAPITAL:
        raise ValueError(
            "初始資金不能超過 2,000,000 元。"
        )

    if entry_score <= exit_score:
        raise ValueError(
            "進場分數必須高於出場分數。"
        )

    if not (
        0
        <= commission_rate
        < 1
    ):
        raise ValueError(
            "手續費率必須介於 0 到 1 之間。"
        )

    if not (
        0
        <= transaction_tax_rate
        < 1
    ):
        raise ValueError(
            "交易稅率必須介於 0 到 1 之間。"
        )

    effective_start_date = start_date or default_research_start_date().isoformat()
    warmup_start_date = (
        pd.Timestamp(effective_start_date)
        - pd.DateOffset(months=BACKTEST_WARMUP_MONTHS)
    ).strftime("%Y-%m-%d")

    df = download_stock(
        normalized_code,
        prefer_official=True,
        update_with_intraday=False,
        official_months=RESEARCH_HISTORY_MONTHS + BACKTEST_WARMUP_MONTHS,
        include_corporate_actions=True,
    )

    if df is None or df.empty:
        raise ValueError(
            f"找不到 "
            f"{normalized_code} "
            "的歷史資料。"
        )

    data_source = str(df.attrs.get("source", "未知"))
    corporate_action_attrs = {
        "dividends": list(df.attrs.get("dividends", [])),
        "split_adjustments": list(df.attrs.get("split_adjustments", [])),
        "dividend_source": df.attrs.get("dividend_source"),
        "price_basis": df.attrs.get("price_basis"),
    }

    df = _prepare_stock_data(
        df=df,
        start_date=warmup_start_date,
        end_date=end_date,
    )

    df = add_indicators(
        df.copy()
    )

    if df is None or df.empty:
        raise ValueError(
            "技術指標計算後沒有可用資料。"
        )

    df = (
        df
        .dropna(subset=BACKTEST_REQUIRED_COLUMNS)
        .reset_index(
            drop=True
        )
    )
    df.attrs.update(corporate_action_attrs)

    requested_start_timestamp = pd.Timestamp(effective_start_date).normalize()
    df = df.loc[df["Date"] >= requested_start_timestamp].reset_index(drop=True)
    df.attrs.update(corporate_action_attrs)

    if len(df) < 61:
        raise ValueError(
            "計算技術指標後的歷史資料不足，"
            "至少需要約 61 個有效交易日。"
        )

    cash = normalized_capital

    shares = 0

    entry_price: (
        float | None
    ) = None

    entry_date: (
        str | None
    ) = None

    entry_signal_score: (
        float | None
    ) = None

    entry_gross_amount = 0.0
    entry_commission = 0.0
    entry_total_cost = 0.0

    trades: list[
        dict[str, Any]
    ] = []

    equity_curve: list[
        dict[str, Any]
    ] = []

    total_commission = 0.0
    total_transaction_tax = 0.0
    total_dividends = 0.0
    position_dividends = 0.0
    dividend_schedule = dividends_by_ex_date(df)

    for index in range(
        60,
        len(df) - 1,
    ):
        historical_df = df.iloc[
            : index + 1
        ].copy()

        current_row = df.iloc[
            index
        ]

        next_row = df.iloc[
            index + 1
        ]

        score_result = calculate_score(
            historical_df
        )

        score = _extract_score(
            score_result
        )

        next_date = _get_row_date(
            next_row
        )

        next_open = float(
            next_row["Open"]
        )

        next_close = float(
            next_row["Close"]
        )

        if next_open <= 0:
            continue

        # 除息日開盤前已持有者享有配息；先入帳再處理當日開盤賣出，
        # 當日才買進者不會錯領該次配息。
        dividend_per_share = dividend_schedule.get(next_date, 0.0)
        if shares > 0 and dividend_per_share > 0:
            received_dividend = shares * dividend_per_share
            cash += received_dividend
            total_dividends += received_dividend
            position_dividends += received_dividend

        # ==========================================
        # 進場
        # ==========================================

        if (
            shares == 0
            and score >= entry_score
        ):
            purchasable_shares = (
                _calculate_purchasable_shares(
                    cash=cash,
                    price=next_open,
                    commission_rate=(
                        commission_rate
                    ),
                )
            )

            if purchasable_shares > 0:
                buy_cost = (
                    _calculate_buy_cost(
                        price=next_open,
                        shares=(
                            purchasable_shares
                        ),
                        commission_rate=(
                            commission_rate
                        ),
                    )
                )

                shares = (
                    purchasable_shares
                )

                cash -= buy_cost[
                    "total_cost"
                ]

                entry_price = (
                    next_open
                )

                entry_date = (
                    next_date
                )

                entry_signal_score = (
                    score
                )

                entry_gross_amount = (
                    buy_cost[
                        "gross_amount"
                    ]
                )

                entry_commission = (
                    buy_cost[
                        "commission"
                    ]
                )

                entry_total_cost = (
                    buy_cost[
                        "total_cost"
                    ]
                )

                total_commission += (
                    entry_commission
                )

        # ==========================================
        # 出場
        # ==========================================

        elif (
            shares > 0
            and score <= exit_score
        ):
            sell_result = (
                _calculate_sell_value(
                    price=next_open,
                    shares=shares,
                    commission_rate=(
                        commission_rate
                    ),
                    transaction_tax_rate=(
                        transaction_tax_rate
                    ),
                )
            )

            cash += sell_result[
                "net_amount"
            ]

            exit_commission = (
                sell_result[
                    "commission"
                ]
            )

            transaction_tax = (
                sell_result[
                    "transaction_tax"
                ]
            )

            total_commission += (
                exit_commission
            )

            total_transaction_tax += (
                transaction_tax
            )

            net_profit = (
                sell_result[
                    "net_amount"
                ]
                + position_dividends
                - entry_total_cost
            )

            return_percent = (
                net_profit
                / entry_total_cost
                * 100
                if entry_total_cost > 0
                else 0.0
            )

            trades.append(
                {
                    "entry_date": (
                        entry_date
                    ),
                    "exit_date": (
                        next_date
                    ),
                    "entry_price": round(
                        entry_price or 0,
                        2,
                    ),
                    "exit_price": round(
                        next_open,
                        2,
                    ),
                    "shares": shares,
                    "entry_gross_amount": (
                        round(
                            entry_gross_amount,
                            2,
                        )
                    ),
                    "entry_commission": (
                        round(
                            entry_commission,
                            2,
                        )
                    ),
                    "entry_total_cost": (
                        round(
                            entry_total_cost,
                            2,
                        )
                    ),
                    "exit_gross_amount": (
                        round(
                            sell_result[
                                "gross_amount"
                            ],
                            2,
                        )
                    ),
                    "exit_commission": (
                        round(
                            exit_commission,
                            2,
                        )
                    ),
                    "transaction_tax": (
                        round(
                            transaction_tax,
                            2,
                        )
                    ),
                    "exit_net_amount": (
                        round(
                            sell_result[
                                "net_amount"
                            ],
                            2,
                        )
                    ),
                    "profit": round(
                        net_profit,
                        2,
                    ),
                    "return_percent": (
                        round(
                            return_percent,
                            2,
                        )
                    ),
                    "entry_score": (
                        round(
                            entry_signal_score,
                            2,
                        )
                        if (
                            entry_signal_score
                            is not None
                        )
                        else None
                    ),
                    "exit_score": round(
                        score,
                        2,
                    ),
                    "exit_reason": (
                        "score_below_exit_threshold"
                    ),
                    "dividends": round(position_dividends, 2),
                }
            )

            shares = 0
            entry_price = None
            entry_date = None
            entry_signal_score = None

            entry_gross_amount = 0.0
            entry_commission = 0.0
            entry_total_cost = 0.0
            position_dividends = 0.0

        equity = (
            cash
            + shares
            * next_close
        )

        equity_curve.append(
            {
                "date": (
                    next_date
                ),
                "equity": round(
                    equity,
                    2,
                ),
                "cash": round(
                    cash,
                    2,
                ),
                "shares": shares,
                "close": round(
                    next_close,
                    2,
                ),
                "score": round(
                    score,
                    2,
                ),
            }
        )

    # ==============================================
    # 回測結束，強制平倉
    # ==============================================

    if shares > 0:
        final_row = df.iloc[-1]

        final_close = float(
            final_row["Close"]
        )

        final_date = _get_row_date(
            final_row
        )

        sell_result = (
            _calculate_sell_value(
                price=final_close,
                shares=shares,
                commission_rate=(
                    commission_rate
                ),
                transaction_tax_rate=(
                    transaction_tax_rate
                ),
            )
        )

        cash += sell_result[
            "net_amount"
        ]

        exit_commission = (
            sell_result[
                "commission"
            ]
        )

        transaction_tax = (
            sell_result[
                "transaction_tax"
            ]
        )

        total_commission += (
            exit_commission
        )

        total_transaction_tax += (
            transaction_tax
        )

        net_profit = (
            sell_result[
                "net_amount"
            ]
            + position_dividends
            - entry_total_cost
        )

        return_percent = (
            net_profit
            / entry_total_cost
            * 100
            if entry_total_cost > 0
            else 0.0
        )

        trades.append(
            {
                "entry_date": (
                    entry_date
                ),
                "exit_date": (
                    final_date
                ),
                "entry_price": round(
                    entry_price or 0,
                    2,
                ),
                "exit_price": round(
                    final_close,
                    2,
                ),
                "shares": shares,
                "entry_gross_amount": (
                    round(
                        entry_gross_amount,
                        2,
                    )
                ),
                "entry_commission": (
                    round(
                        entry_commission,
                        2,
                    )
                ),
                "entry_total_cost": (
                    round(
                        entry_total_cost,
                        2,
                    )
                ),
                "exit_gross_amount": (
                    round(
                        sell_result[
                            "gross_amount"
                        ],
                        2,
                    )
                ),
                "exit_commission": (
                    round(
                        exit_commission,
                        2,
                    )
                ),
                "transaction_tax": (
                    round(
                        transaction_tax,
                        2,
                    )
                ),
                "exit_net_amount": (
                    round(
                        sell_result[
                            "net_amount"
                        ],
                        2,
                    )
                ),
                "profit": round(
                    net_profit,
                    2,
                ),
                "return_percent": (
                    round(
                        return_percent,
                        2,
                    )
                ),
                "entry_score": (
                    round(
                        entry_signal_score,
                        2,
                    )
                    if (
                        entry_signal_score
                        is not None
                    )
                    else None
                ),
                "exit_score": None,
                "exit_reason": (
                    "end_of_backtest"
                ),
                "dividends": round(position_dividends, 2),
            }
        )

        shares = 0

        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)
            equity_curve[-1]["cash"] = round(cash, 2)
            equity_curve[-1]["shares"] = 0

    final_capital = float(
        cash
    )

    total_profit = (
        final_capital
        - initial_capital
    )

    total_return = (
        total_profit
        / initial_capital
        * 100
    )

    winning_trades = [
        trade
        for trade in trades
        if float(
            trade["profit"]
        ) > 0
    ]

    win_rate = (
        len(winning_trades)
        / len(trades)
        * 100
        if trades
        else 0.0
    )

    max_drawdown = (
        _calculate_max_drawdown(
            equity_curve
        )
    )

    actual_start_date = (
        _get_row_date(
            df.iloc[0]
        )
    )

    actual_end_date = (
        _get_row_date(
            df.iloc[-1]
        )
    )

    history_coverage = frame_coverage(df.set_index("Date"))

    buy_and_hold = _calculate_buy_and_hold(
        df=df,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        transaction_tax_rate=transaction_tax_rate,
    )

    buy_and_hold_return = float(
        buy_and_hold.get(
            "return_percent",
            0.0,
        )
    )

    alpha_percent = (
        total_return
        - buy_and_hold_return
    )

    _enrich_trades_with_excursions(
        df=df,
        trades=trades,
    )

    exposure_percent = (
        _calculate_exposure_percent(
            equity_curve
        )
    )

    drawdown_statistics = (
        _calculate_drawdown_statistics(
            equity_curve
        )
    )

    advanced_trade_statistics = (
        _calculate_advanced_trade_statistics(
            trades=trades,
            initial_capital=initial_capital,
            final_capital=final_capital,
            max_drawdown_percent=max_drawdown,
            exposure_percent=exposure_percent,
        )
    )

    performance_metrics = (
        _calculate_performance_metrics(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
            final_capital=final_capital,
            actual_start_date=actual_start_date,
            actual_end_date=actual_end_date,
            max_drawdown_percent=max_drawdown,
        )
    )

    return {
        "stock_code": (
            normalized_code
        ),
        "data_source": data_source,
        "requested_start_date": (
            effective_start_date
        ),
        "requested_end_date": (
            end_date
        ),
        "actual_start_date": (
            actual_start_date
        ),
        "actual_end_date": (
            actual_end_date
        ),
        "history_coverage": history_coverage,
        "requested_history_months": RESEARCH_HISTORY_MONTHS,
        "entry_score": (
            entry_score
        ),
        "exit_score": (
            exit_score
        ),
        "commission_rate": (
            commission_rate
        ),
        "transaction_tax_rate": (
            transaction_tax_rate
        ),
        "initial_capital": round(
            initial_capital,
            2,
        ),
        "final_capital": round(
            final_capital,
            2,
        ),
        "total_profit": round(
            total_profit,
            2,
        ),
        "total_return_percent": round(
            total_return,
            2,
        ),
        "total_commission": round(
            total_commission,
            2,
        ),
        "total_transaction_tax": (
            round(
                total_transaction_tax,
                2,
            )
        ),
        "total_dividends": round(total_dividends, 2),
        "corporate_actions": {
            "price_basis": corporate_action_attrs.get("price_basis"),
            "split_adjustments": corporate_action_attrs.get("split_adjustments", []),
            "dividend_source": corporate_action_attrs.get("dividend_source"),
            "dividend_event_count": len(corporate_action_attrs.get("dividends", [])),
        },
        "total_transaction_cost": (
            round(
                total_commission
                + total_transaction_tax,
                2,
            )
        ),
        "trade_count": len(
            trades
        ),
        "winning_trade_count": len(
            winning_trades
        ),
        "win_rate_percent": round(
            win_rate,
            2,
        ),
        "max_drawdown_percent": round(
            max_drawdown,
            2,
        ),
        "buy_and_hold": buy_and_hold,
        "alpha_percent": round(
            alpha_percent,
            2,
        ),
        "performance_metrics": (
            performance_metrics
        ),
        "advanced_trade_statistics": (
            advanced_trade_statistics
        ),
        "drawdown_statistics": (
            drawdown_statistics
        ),
        "exposure_percent": round(
            exposure_percent,
            2,
        ),
        "trades": trades,
        "equity_curve": (
            equity_curve
        ),
    }
