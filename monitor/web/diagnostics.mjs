export function diagnostic(text) {
  const colon = text.indexOf(":");
  const title = colon < 0 ? "פירוט הסורק" : text.slice(0, colon);
  const body = colon < 0 ? text : text.slice(colon + 1);
  const values = Object.fromEntries([...text.matchAll(/\b([A-Za-z][A-Za-z0-9]*)=(-?\d+(?:\.\d+)?|true|false)\b/g)].map(m => [m[1], m[2]]));
  const conditions = [];
  const booleanLabels = {trend:"מגמה",reclaim:"חזרה לרמה",aligned:"התאמת כיוון",previousBelow:"מתחת לרצועה בנר קודם",previousAbove:"מעל לרצועה בנר קודם",reclaimed:"חזרה לרצועה",crossed:"חצייה"};
  for (const [key, label] of Object.entries(booleanLabels)) {
    if (values[key] === "true" || values[key] === "false") conditions.push({label, pass:values[key] === "true",value:values[key] === "true" ? "✓" : "×"});
  }
  for (const [key, label, lower, upper] of [["volume","נפח יחסי","minVolume","maxVolume"],["adx","ADX","minAdx","maxAdx"],["rsi","RSI","minRsi","maxRsi"]]) {
    if (values[key] == null) continue;
    for (const [bound, isMin] of [[lower,true],[upper,false]]) {
      if (values[bound] == null) continue;
      const actual=Number(values[key]), threshold=Number(values[bound]);
      conditions.push({label,pass:isMin?actual>=threshold:actual<=threshold,value:actual+" / "+(isMin?"≥ ":"≤ ")+threshold});
    }
  }
  // Preserve the scanner's verdict. Diagnostic fragments are not a complete signal gate.
  const rejected = /לא עמד|אין התאמה|נפסל/.test(body);
  return {title,explanation:body.split(";")[0].trim(),conditions,rejected,raw:text};
}
