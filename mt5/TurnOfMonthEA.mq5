//+------------------------------------------------------------------+
//| TurnOfMonthEA.mq5                                                |
//| S&P 500 turn-of-month: long at the close of the last trading day |
//| of the month, exit at the close of the 3rd trading day of the    |
//| new month. Research: docs/FTMO_TURN_OF_MONTH_2026-11-23.md       |
//|                                                                  |
//| FTMO guards (all fail-closed):                                   |
//|  - daily stop before FTMO Max Daily Loss (equity vs balance at   |
//|    server midnight)                                              |
//|  - total stop before FTMO Max Loss (equity vs initial capital)   |
//|  - catastrophic price stop on every position                     |
//|  - one position, a handful of server requests per month          |
//| RUN ON THE FTMO FREE TRIAL FIRST. Not financial advice.          |
//+------------------------------------------------------------------+
#property version   "1.00"
#include <Trade/Trade.mqh>

input string InpSymbol            = "US500.cash"; // check exact name in Market Watch
input double InpInitialCapital    = 0;            // FTMO initial capital (ISC); 0 = balance at first start
input double InpNotionalMultiple  = 1.0;          // position notional = ISC x this
input int    InpEntryHour         = 22;           // server time (FTMO server = New York + 7h)
input int    InpEntryMinute       = 50;           // 22:50 server = 15:50 New York
input int    InpExitTradingDay    = 3;            // exit on this trading day of the new month
input double InpDailyStopPct      = 3.5;          // % of ISC below midnight balance (FTMO: 5 / 3)
input double InpTotalStopPct      = 8.0;          // % of ISC below ISC (FTMO: 10)
input double InpPriceStopPct      = 5.0;          // catastrophic stop, % below entry
input int    InpMaxHoldDays       = 9;            // safety exit, calendar days
input string InpHolidays          = "2026.01.01,2026.01.19,2026.02.16,2026.04.03,2026.05.25,2026.06.19,2026.07.03,2026.09.07,2026.11.26,2026.12.25,2027.01.01,2027.01.18,2027.02.15,2027.03.26,2027.05.31,2027.06.18,2027.07.05,2027.09.06,2027.11.25,2027.12.24";
input long   InpMagic             = 20261123;

CTrade   trade;
datetime g_holidays[];
datetime g_dayStart      = 0;
double   g_dayStartBal   = 0;
double   g_isc           = 0;      // initial capital actually used
bool     g_blockedToday  = false;
bool     g_disabled      = false;
int      g_enteredMonth  = -1;   // yyyymm of the month whose turn we already traded

//--- helpers ---------------------------------------------------------
datetime DayOf(datetime t) { return t - (t % 86400); }

bool IsHoliday(datetime day)
{
   for(int i = 0; i < ArraySize(g_holidays); i++)
      if(g_holidays[i] == day) return true;
   return false;
}

bool IsTradingDay(datetime day)
{
   MqlDateTime s; TimeToStruct(day, s);
   if(s.day_of_week == 0 || s.day_of_week == 6) return false;
   return !IsHoliday(day);
}

datetime NextTradingDay(datetime day)
{
   datetime d = day + 86400;
   for(int i = 0; i < 10 && !IsTradingDay(d); i++) d += 86400;
   return d;
}

int MonthKey(datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.year * 100 + s.mon; }

bool IsLastTradingDayOfMonth(datetime day)
{
   return IsTradingDay(day) && MonthKey(NextTradingDay(day)) != MonthKey(day);
}

int TradingDayOfMonth(datetime day)   // 1-based index, 0 if not a trading day
{
   if(!IsTradingDay(day)) return 0;
   MqlDateTime s; TimeToStruct(day, s);
   datetime d = day - (s.day - 1) * 86400;
   int k = 0;
   for(; d <= day; d += 86400) if(IsTradingDay(d)) k++;
   return k;
}

bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic) return true;
   }
   return false;
}

datetime PositionOpenTime()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return (datetime)PositionGetInteger(POSITION_TIME);
   }
   return 0;
}

void CloseAll(string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
      {
         if(!trade.PositionClose(tk)) PrintFormat("Close failed (%s): %d", why, trade.ResultRetcode());
         else PrintFormat("Closed position: %s", why);
      }
   }
}

double LotsForNotional()
{
   double price = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   double csize = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double step  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double vmin  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   if(price <= 0 || csize <= 0 || step <= 0) return 0;
   // Assumes account currency USD and a USD-quoted index (US500). Verify on the Free Trial.
   double lots = g_isc * InpNotionalMultiple / (price * csize);
   lots = MathFloor(lots / step) * step;
   if(lots < vmin) { PrintFormat("Notional too small for min lot (%.2f < %.2f)", lots, vmin); return 0; }
   return MathMin(lots, vmax);
}

//--- lifecycle -------------------------------------------------------
int OnInit()
{
   if(InpInitialCapital < 0 || InpNotionalMultiple <= 0 || InpNotionalMultiple > 2.0 ||
      InpDailyStopPct <= 0 || InpDailyStopPct >= 5 || InpTotalStopPct <= 0 || InpTotalStopPct >= 10 ||
      InpExitTradingDay < 1 || InpExitTradingDay > 5)
   { Print("Invalid inputs (fail-closed)"); return INIT_PARAMETERS_INCORRECT; }
   if(!SymbolSelect(InpSymbol, true)) { PrintFormat("Symbol %s not found", InpSymbol); return INIT_FAILED; }

   string parts[]; int n = StringSplit(InpHolidays, ',', parts);
   ArrayResize(g_holidays, 0);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]);
      if(StringLen(parts[i]) == 0) continue;
      datetime d = StringToTime(parts[i]);
      if(d <= 0) { PrintFormat("Bad holiday date '%s'", parts[i]); return INIT_PARAMETERS_INCORRECT; }
      int k = ArraySize(g_holidays); ArrayResize(g_holidays, k + 1); g_holidays[k] = DayOf(d);
   }
   // initial capital: explicit input, else remembered first-start balance for this login
   string gv = StringFormat("TOM_ISC_%I64d", AccountInfoInteger(ACCOUNT_LOGIN));
   if(InpInitialCapital > 0) g_isc = InpInitialCapital;
   else if(GlobalVariableCheck(gv)) g_isc = GlobalVariableGet(gv);
   else { g_isc = AccountInfoDouble(ACCOUNT_BALANCE); GlobalVariableSet(gv, g_isc); }
   if(g_isc <= 0) { Print("Initial capital unknown (fail-closed)"); return INIT_FAILED; }
   if(!(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) Print("WARNING: account trading not allowed (investor mode?)");
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   EventSetTimer(20);
   PrintFormat("TurnOfMonthEA ready: %s, notional %.2fx of %.0f, %d holidays", InpSymbol, InpNotionalMultiple, g_isc, ArraySize(g_holidays));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   datetime now   = TimeCurrent();          // server time
   datetime today = DayOf(now);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);

   // new server day: FTMO daily limit is anchored on the balance at midnight
   if(today != g_dayStart) { g_dayStart = today; g_dayStartBal = balance; g_blockedToday = false; }

   // --- guards first ---
   if(equity <= g_isc * (1.0 - InpTotalStopPct / 100.0))
   {
      if(!g_disabled) { CloseAll("total stop"); g_disabled = true; Print("EA disabled: total stop hit"); }
      return;
   }
   if(equity <= g_dayStartBal - g_isc * InpDailyStopPct / 100.0)
   {
      if(!g_blockedToday) { CloseAll("daily stop"); g_blockedToday = true; }
      return;
   }
   if(g_disabled || g_blockedToday) return;

   MqlDateTime s; TimeToStruct(now, s);
   int minutes = s.hour * 60 + s.min;
   int entryAt = InpEntryHour * 60 + InpEntryMinute;
   bool inWindow = minutes >= entryAt && minutes < entryAt + 8;   // a few retries, then give up

   // --- exit ---
   if(HasPosition())
   {
      datetime opened = PositionOpenTime();
      int tdom = TradingDayOfMonth(today);
      bool newMonth = MonthKey(today) != MonthKey(opened);
      if((newMonth && tdom >= InpExitTradingDay && minutes >= entryAt) ||
         (now - opened) > InpMaxHoldDays * 86400)
         CloseAll(StringFormat("exit day %d of month", tdom));
      return;
   }

   // --- entry ---
   if(inWindow && IsLastTradingDayOfMonth(today) && g_enteredMonth != MonthKey(today))
   {
      double lots = LotsForNotional();
      if(lots <= 0) { g_enteredMonth = MonthKey(today); return; }
      double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
      int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
      double sl = NormalizeDouble(ask * (1.0 - InpPriceStopPct / 100.0), digits);
      if(trade.Buy(lots, InpSymbol, 0.0, sl, 0.0, "TOM"))
      {
         g_enteredMonth = MonthKey(today);
         PrintFormat("Entered TOM long %.2f lots at ~%.2f, SL %.2f", lots, ask, sl);
      }
      else PrintFormat("Entry failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}
//+------------------------------------------------------------------+
