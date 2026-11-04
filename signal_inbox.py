import json,sqlite3,time
DB='/opt/signalpilot/signal-inbox.sqlite3'
def accept(p,db=DB):
 if not isinstance(p,dict) or set(p)!={'signal_id','symbol','direction','score','timestamp','source'}: raise ValueError('schema')
 sid=p['signal_id']
 if not isinstance(sid,str) or not 1<=len(sid)<=32 or not all(c.isalnum() or c in '-_' for c in sid): raise ValueError('id')
 if p['symbol'] not in ('BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT') or p['direction'] not in ('long','short'): raise ValueError('market')
 if type(p['score']) is not int or not 85<=p['score']<=100 or p['source']!='verified_85_score_engine': raise ValueError('score/source')
 if type(p['timestamp']) is not int or abs(int(time.time())-p['timestamp'])>120: raise ValueError('stale')
 with sqlite3.connect(db,timeout=10) as c:
  c.execute('CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY,received_at INTEGER NOT NULL,payload TEXT NOT NULL)')
  try: c.execute('INSERT INTO signals VALUES(?,?,?)',(sid,int(time.time()),json.dumps(p,sort_keys=True)));return True
  except sqlite3.IntegrityError:return False
