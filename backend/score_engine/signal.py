def score_to_signal(result):
    """
    將評分結果轉換成文字訊號。

    result可以是：
    1. float或int分數
    2. ScoreResult完整物件
    """

    if hasattr(result, "total_score"):
        score = float(result.total_score)

        trade_eligible = bool(
            getattr(result, "trade_eligible", False)
        )

        stage = getattr(
            result,
            "stage",
            "UNKNOWN",
        )

        if stage == "PAUSED":
            return "🔴 風控暫停"

        if stage == "FILTERED":
            return "🔴 日線趨勢不符合"

        if stage == "WAITING_PULLBACK":
            return "🟡 等待回檔"

        if stage == "PREPARING_TRIGGER":
            return "🟡 準備觸發"

        if stage == "WAITING_BREAKOUT":
            return "🟡 等待突破"

        if trade_eligible and score >= 85:
            return "🟢 強勢買進訊號"

        if trade_eligible and score >= 75:
            return "🟢 買進訊號"

        if score >= 70:
            return "🟡 高分觀察"

        if score >= 60:
            return "🟠 中性等待"

        return "🔴 不建議進場"

    score = float(result)

    if score >= 85:
        return "🟢 強勢觀察"

    if score >= 75:
        return "🟢 偏多觀察"

    if score >= 65:
        return "🟡 中性觀察"

    if score >= 50:
        return "🟠 偏弱"

    return "🔴 不建議"