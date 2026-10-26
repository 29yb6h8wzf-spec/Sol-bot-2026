// SignalPilot Pro: pure research-only position sizing. No order placement.
// Inputs are quoted prices, not guarantees of fill or maximum realized loss.
export function evaluateSetup({direction,entry,stop,target,feeRate=0.0005,slippageRate=0.0005,riskBudget=1.5,minProfit=5,leverage=3,availableMargin=Infinity}) {
  const nums=[entry,stop,target,feeRate,slippageRate,riskBudget,minProfit,leverage,availableMargin];
  if(!nums.every(x=>typeof x==='number'&&!Number.isNaN(x))||!nums.slice(0,3).every(x=>Number.isFinite(x)&&x>0)||!Number.isFinite(riskBudget)||riskBudget<=0||minProfit<0||feeRate<0||slippageRate<0||!Number.isFinite(leverage)||leverage<1||availableMargin<0)throw Error('Invalid sizing input');
  if(!['LONG','SHORT'].includes(direction))throw Error('Invalid direction');
  const side=direction==='LONG'?1:-1;
  const stopDistance=side*(entry-stop);
  const targetDistance=side*(target-entry);
  if(stopDistance<=0||targetDistance<=0)return {eligible:false,reason:'Invalid stop/target direction'};
  // Conservative estimated two-sided fees and slippage on notional.
  const friction=2*(feeRate+slippageRate);
  const riskFraction=stopDistance/entry+friction;
  const rewardFraction=targetDistance/entry-friction;
  if(rewardFraction<=0)return {eligible:false,reason:'Expected costs exceed target move'};
  const notional=riskBudget/riskFraction;
  const margin=notional/leverage;
  const expectedProfit=notional*rewardFraction;
  const expectedLoss=notional*riskFraction;
  const ratio=expectedProfit/expectedLoss;
  const eligible=expectedProfit>=minProfit&&margin<=availableMargin;
  return {eligible,reason:eligible?'Meets configured research thresholds':margin>availableMargin?'Insufficient margin':'Target below minimum net profit',notional,margin,expectedProfit,expectedLoss,rewardRisk:ratio,leverage,riskBudget,feeRate,slippageRate};
}
