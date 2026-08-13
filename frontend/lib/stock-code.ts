const STOCK_CODE_PATTERN =
  /^[0-9][0-9A-Z]{3,5}(?:\.(?:TW|TWO))?$/;


export const INVALID_STOCK_CODE_MESSAGE =
  "股票代號格式不正確，請輸入 4～6 碼台股代號，例如 2330、0056 或 6488.TWO。";


export function normalizeStockCode(
  value: string,
): string | null {
  const normalized = value.trim().toUpperCase();

  return STOCK_CODE_PATTERN.test(normalized)
    ? normalized
    : null;
}
