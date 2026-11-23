//+------------------------------------------------------------------+
//| US100TripleEA.mq5                                                |
//| Three US100 modules, one account, separate magics:               |
//|  TOM - long at the close of the last trading day of the month,   |
//|        exit at the close of the 3rd trading day of the new month |
//|  DIP - RSI(2) of daily closes < 10 -> buy at the close,          |
//|        exit at the close when RSI(2) > 50                        |
//|  BTM - intraday "noise area" momentum (Zarattini/Aziz/Barbon):   |
//|        every 30 min, long above upper band and VWAP, short below |
//|        lower band and VWAP, flat otherwise, all closed by 22:58  |
//| Research: docs/FTMO_US100_TRIPLE_2026-11-23.md                   |
//|                                                                  |
//| FTMO guards (fail-closed): daily stop vs balance at server       |
//| midnight, total stop vs initial capital, server-side price stop  |
//| on every position. RUN ON THE FREE TRIAL FIRST. Not advice.      |
//+------------------------------------------------------------------+
#property version   "1.01"
#include <Trade/Trade.mqh>

input string InpSymbol         = "US100.cash";
input double InpInitialCapital = 0;      // 0 = remembered first-start balance
input double InpMult           = 2.0;    // notional per module = ISC x this (max 3)
input bool   InpUseTOM         = true;
input bool   InpUseDIP         = true;
input bool   InpUseBTM         = true;
input int    InpCloseHour      = 22;     // daily-close decision, server time (NY+7)
input int    InpCloseMinute    = 50;
input int    InpExitTradingDay = 3;
input double InpDipEntryRSI    = 10;
input double InpDipExitRSI     = 50;
input int    InpBtmLookback    = 14;     // sessions for the noise band
input double InpDailyStopPct   = 4.0;    // % of ISC below midnight balance (FTMO 5)
input double InpTotalStopPct   = 8.0;    // % of ISC below ISC (FTMO 10)
input double InpTomStopPct     = 5.0;    // server-side price stops
input double InpDipStopPct     = 8.0;
input double InpBtmStopPct     = 3.0;
input string InpHolidays       = "2026.01.01,2026.01.19,2026.02.16,2026.04.03,2026.05.25,2026.06.19,2026.07.03,2026.09.07,2026.11.26,2026.12.25,2027.01.01,2027.01.18,2027.02.15,2027.03.26,2027.05.31,2027.06.18,2027.07.05,2027.09.06,2027.11.25,2027.12.24";
input string InpHalfDays       = "2026.11.27,2026.12.24,2027.11.26"; // early close: no BTM, no DIP decision
input long   InpMagicBase      = 20261124;

CTrade   trade;
datetime g_hol[], g_half[];
double   g_isc = 0, g_dayStartBal = 0;
datetime g_dayStart = 0;
bool     g_blockedToday = false, g_disabled = false;
datetime g_closeDone = 0;          // day whose daily-close decisions are done
int      g_tomMonth = -1;
int      g_btmSlotDone = -1;       // minute-of-day of last processed BTM slot
datetime g_btmSlotDay = 0;
bool     g_btmFlatDone = false;
string   g_btmInfo = "";        // last BTM evaluation, for the heartbeat log

long MagicTOM() { return InpMagicBase + 1; }
long MagicDIP() { return InpMagicBase + 2; }
long MagicBTM() { return InpMagicBase + 3; }

//--- calendar ---------------------------------------------------------
datetime DayOf(datetime t) { return t - (t % 86400); }
bool InList(datetime &arr[], datetime d) { for(int i = 0; i < ArraySize(arr); i++) if(arr[i] == d) return true; return false; }
bool IsTradingDay(datetime d) { MqlDateTime s; TimeToStruct(d, s); return s.day_of_week >= 1 && s.day_of_week <= 5 && !InList(g_hol, d); }
datetime NextTradingDay(datetime d) { datetime x = d + 86400; for(int i = 0; i < 10 && !IsTradingDay(x); i++) x += 86400; return x; }
int MonthKey(datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.year * 100 + s.mon; }
bool IsLastTradingDayOfMonth(datetime d) { return IsTradingDay(d) && MonthKey(NextTradingDay(d)) != MonthKey(d); }
int TradingDayOfMonth(datetime d)
{
   if(!IsTradingDay(d)) return 0;
   MqlDateTime s; TimeToStruct(d, s);
   int k = 0;
   for(datetime x = d - (s.day - 1) * 86400; x <= d; x += 86400) if(IsTradingDay(x)) k++;
   return k;
}
bool ParseDates(string csv, datetime &arr[])
{
   string p[]; int n = StringSplit(csv, ',', p); ArrayResize(arr, 0);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(p[i]); StringTrimRight(p[i]);
      if(StringLen(p[i]) == 0) continue;
      datetime d = StringToTime(p[i]);
      if(d <= 0) { PrintFormat("Bad date '%s'", p[i]); return false; }
      int k = ArraySize(arr); ArrayResize(arr, k + 1); arr[k] = DayOf(d);
   }
   return true;
}

//--- positions --------------------------------------------------------
int PosDir(long magic)   // +1 long, -1 short, 0 none
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol && PositionGetInteger(POSITION_MAGIC) == magic)
         return PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
   }
   return 0;
}
datetime PosTime(long magic)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol && PositionGetInteger(POSITION_MAGIC) == magic)
         return (datetime)PositionGetInteger(POSITION_TIME);
   }
   return 0;
}
void CloseMagic(long magic, string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetString(POSITION_SYMBOL) == InpSymbol && PositionGetInteger(POSITION_MAGIC) == magic)
      {
         trade.SetExpertMagicNumber(magic);
         if(trade.PositionClose(tk)) PrintFormat("[%I64d] closed: %s", magic, why);
         else PrintFormat("[%I64d] close failed (%s): %d", magic, why, trade.ResultRetcode());
      }
   }
}
void CloseAll(string why) { CloseMagic(MagicTOM(), why); CloseMagic(MagicDIP(), why); CloseMagic(MagicBTM(), why); }

double Lots()
{
   double price = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   double csize = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double step  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double vmin  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   if(price <= 0 || csize <= 0 || step <= 0) return 0;
   double lots = MathFloor(g_isc * InpMult / (price * csize) / step) * step;   // USD account, USD index
   if(lots < vmin) { PrintFormat("Notional below min lot (%.2f < %.2f)", lots, vmin); return 0; }
   return MathMin(lots, vmax);
}
bool Open(long magic, int dir, double stopPct, string tag)
{
   double lots = Lots(); if(lots <= 0) return false;
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   trade.SetExpertMagicNumber(magic);
   bool ok;
   if(dir > 0)
   {
      double px = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
      ok = trade.Buy(lots, InpSymbol, 0.0, NormalizeDouble(px * (1 - stopPct / 100), digits), 0.0, tag);
   }
   else
   {
      double px = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
      ok = trade.Sell(lots, InpSymbol, 0.0, NormalizeDouble(px * (1 + stopPct / 100), digits), 0.0, tag);
   }
   if(ok) PrintFormat("[%s] %s %.2f lots", tag, dir > 0 ? "BUY" : "SELL", lots);
   else   PrintFormat("[%s] open failed: %d %s", tag, trade.ResultRetcode(), trade.ResultRetcodeDescription());
   return ok;
}

//--- signals ----------------------------------------------------------
// RSI(2), Wilder, on the closes of the 22:45 M5 bar (closes 22:50 server) of each session.
double DipRSI()
{
   MqlRates r[];
   int n = CopyRates(InpSymbol, PERIOD_M5, TimeCurrent() - 70 * 86400, TimeCurrent(), r);
   if(n <= 0) return -1;
   double c[]; ArrayResize(c, 0);
   for(int i = 0; i < n; i++)
   {
      MqlDateTime s; TimeToStruct(r[i].time, s);
      if(s.hour == InpCloseHour && s.min == InpCloseMinute - 5)
      { int k = ArraySize(c); ArrayResize(c, k + 1); c[k] = r[i].close; }
   }
   int m = ArraySize(c);
   if(m < 20) return -1;
   MqlDateTime last; TimeToStruct(r[n - 1].time, last);
   double ag = 0, al = 0;
   for(int i = 1; i < m; i++)
   {
      double ch = c[i] - c[i - 1], g = MathMax(ch, 0), l = MathMax(-ch, 0);
      if(i <= 2) { ag += g / 2; al += l / 2; }
      else { ag = (ag + g) / 2; al = (al + l) / 2; }
   }
   return al == 0 ? 100 : 100 - 100 / (1 + ag / al);
}

// BTM target for the slot whose decision bar opened at slotOpen (server, same day)
int BtmTarget(datetime slotOpen)
{
   MqlRates r[];
   int n = CopyRates(InpSymbol, PERIOD_M5, TimeCurrent() - (InpBtmLookback + 12) * 86400, TimeCurrent(), r);
   g_btmInfo = "no data";
   if(n <= 0) return 0;
   datetime today = DayOf(slotOpen);
   int slotMin = (int)((slotOpen - today) / 60);
   // per-day: open at 16:30, close of 22:55, move at slot
   datetime days[]; double opens[], moves[], closes[];
   double O = 0, vw = 0, vv = 0, cNow = 0, prevClose = 0;
   datetime curDay = 0; double dOpen = 0, dMove = -1, dClose = 0;
   for(int i = 0; i <= n; i++)
   {
      datetime d = i < n ? DayOf(r[i].time) : 0;
      if(d != curDay)
      {
         if(curDay != 0 && curDay < today && dOpen > 0 && dMove >= 0 && dClose > 0)
         { int k = ArraySize(days); ArrayResize(days, k + 1); ArrayResize(moves, k + 1); ArrayResize(closes, k + 1);
           days[k] = curDay; moves[k] = dMove; closes[k] = dClose; }
         curDay = d; dOpen = 0; dMove = -1; dClose = 0;
      }
      if(i == n) break;
      int mm = (int)((r[i].time - d) / 60);
      if(mm == 16 * 60 + 30) dOpen = r[i].open;
      if(mm == slotMin && dOpen > 0) dMove = MathAbs(r[i].close / dOpen - 1);
      if(mm == 22 * 60 + 55) dClose = r[i].close;
      if(d == today && mm >= 16 * 60 + 30 && mm <= slotMin)
      {
         if(mm == 16 * 60 + 30) O = r[i].open;
         double tv = MathMax((double)r[i].tick_volume, 1.0);
         vw += (r[i].high + r[i].low + r[i].close) / 3 * tv; vv += tv;
         if(mm == slotMin) cNow = r[i].close;
      }
   }
   int k = ArraySize(days);
   if(O <= 0 || cNow <= 0 || vv <= 0 || k < InpBtmLookback) { g_btmInfo = StringFormat("not enough history (sessions %d)", k); return 0; }
   prevClose = closes[k - 1];
   double sig = 0; for(int j = k - InpBtmLookback; j < k; j++) sig += moves[j]; sig /= InpBtmLookback;
   double ub = MathMax(O, prevClose) * (1 + sig), lb = MathMin(O, prevClose) * (1 - sig), vwap = vw / vv;
   g_btmInfo = StringFormat("c=%.2f ub=%.2f lb=%.2f vwap=%.2f", cNow, ub, lb, vwap);
   if(cNow > ub && cNow > vwap) return 1;
   if(cNow < lb && cNow < vwap) return -1;
   return 0;
}

//--- lifecycle --------------------------------------------------------
int OnInit()
{
   if(InpInitialCapital < 0 || InpMult <= 0 || InpMult > 3.0 || InpDailyStopPct <= 0 || InpDailyStopPct >= 5 ||
      InpTotalStopPct <= 0 || InpTotalStopPct >= 10 || InpBtmLookback < 5 || InpExitTradingDay < 1 || InpExitTradingDay > 5)
   { Print("Invalid inputs (fail-closed)"); return INIT_PARAMETERS_INCORRECT; }
   if(!SymbolSelect(InpSymbol, true)) { PrintFormat("Symbol %s not found", InpSymbol); return INIT_FAILED; }
   if(!ParseDates(InpHolidays, g_hol) || !ParseDates(InpHalfDays, g_half)) return INIT_PARAMETERS_INCORRECT;
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string gv = StringFormat("TRI_ISC_%I64d", login), gvOld = StringFormat("TOM_ISC_%I64d", login);
   if(InpInitialCapital > 0) g_isc = InpInitialCapital;
   else if(GlobalVariableCheck(gv)) g_isc = GlobalVariableGet(gv);
   else if(GlobalVariableCheck(gvOld)) { g_isc = GlobalVariableGet(gvOld); GlobalVariableSet(gv, g_isc); }
   else { g_isc = AccountInfoDouble(ACCOUNT_BALANCE); GlobalVariableSet(gv, g_isc); }
   if(g_isc <= 0) { Print("Initial capital unknown (fail-closed)"); return INIT_FAILED; }
   trade.SetDeviationInPoints(100);
   trade.SetTypeFillingBySymbol(InpSymbol);
   EventSetTimer(10);
   PrintFormat("US100TripleEA ready: %s %.1fx per module of %.0f, TOM=%d DIP=%d BTM=%d", InpSymbol, InpMult, g_isc, InpUseTOM, InpUseDIP, InpUseBTM);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); }
void OnTick() { }   // tester drives OnTimer too; logic lives there

void OnTimer()
{
   datetime now = TimeCurrent(), today = DayOf(now);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY), balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(today != g_dayStart) { g_dayStart = today; g_dayStartBal = balance; g_blockedToday = false; g_btmFlatDone = false; }

   // --- guards ---
   if(equity <= g_isc * (1 - InpTotalStopPct / 100))
   { if(!g_disabled) { CloseAll("total stop"); g_disabled = true; Print("EA disabled: total stop"); } return; }
   if(equity <= g_dayStartBal - g_isc * InpDailyStopPct / 100)
   { if(!g_blockedToday) { CloseAll("daily stop"); g_blockedToday = true; } return; }
   if(g_disabled || g_blockedToday || !IsTradingDay(today)) return;

   MqlDateTime s; TimeToStruct(now, s);
   int minutes = s.hour * 60 + s.min;
   int closeAt = InpCloseHour * 60 + InpCloseMinute;
   bool half = InList(g_half, today);

   // --- BTM: 30-minute slots 17:00..22:30 (decision bar opened 5 min earlier), flat at 22:58 ---
   if(InpUseBTM && !half)
   {
      if(minutes >= 22 * 60 + 58)
      { if(!g_btmFlatDone) { if(PosDir(MagicBTM()) != 0) CloseMagic(MagicBTM(), "BTM session end"); g_btmFlatDone = true; } }
      else if(minutes >= 17 * 60 && minutes <= 22 * 60 + 33)
      {
         int slot = 17 * 60 + ((minutes - 17 * 60) / 30) * 30;
         if(minutes - slot <= 3 && (g_btmSlotDay != today || g_btmSlotDone != slot))
         {
            g_btmSlotDay = today; g_btmSlotDone = slot;
            int target = BtmTarget(today + (slot - 5) * 60);
            int cur = PosDir(MagicBTM());
            PrintFormat("[CHK BTM] slot=%02d:%02d target=%d cur=%d %s", slot / 60, slot % 60, target, cur, g_btmInfo);
            if(target != cur)
            {
               if(cur != 0) CloseMagic(MagicBTM(), "BTM signal change");
               if(target != 0) Open(MagicBTM(), target, InpBtmStopPct, "BTM");
            }
         }
      }
   }

   // --- daily-close decisions (TOM, DIP) once per day in an 8-minute window ---
   if(minutes >= closeAt && minutes < closeAt + 8 && g_closeDone != today)
   {
      g_closeDone = today;
      if(InpUseTOM)
      {
         PrintFormat("[CHK TOM] tdom=%d lastday=%d pos=%d", TradingDayOfMonth(today), IsLastTradingDayOfMonth(today), PosDir(MagicTOM()));
         if(PosDir(MagicTOM()) != 0)
         {
            datetime opened = PosTime(MagicTOM());
            if((MonthKey(today) != MonthKey(opened) && TradingDayOfMonth(today) >= InpExitTradingDay) || now - opened > 9 * 86400)
               CloseMagic(MagicTOM(), "TOM exit");
         }
         else if(IsLastTradingDayOfMonth(today) && g_tomMonth != MonthKey(today))
         { g_tomMonth = MonthKey(today); Open(MagicTOM(), 1, InpTomStopPct, "TOM"); }
      }
      if(InpUseDIP && !half)
      {
         double rsi = DipRSI();
         if(rsi < 0) Print("DIP: not enough history");
         else
         {
            int cur = PosDir(MagicDIP());
            PrintFormat("[CHK DIP] rsi=%.1f pos=%d", rsi, cur);
            if(cur != 0 && rsi > InpDipExitRSI) CloseMagic(MagicDIP(), StringFormat("DIP exit rsi %.1f", rsi));
            else if(cur == 0 && rsi < InpDipEntryRSI) Open(MagicDIP(), 1, InpDipStopPct, StringFormat("DIP %.1f", rsi));
         }
      }
   }
}
//+------------------------------------------------------------------+
