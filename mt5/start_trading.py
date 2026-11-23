"""Start the FTMO MT5 terminal logged in with TRADING rights and TurnOfMonthEA attached.

Run on the Windows server as the desktop user (scheduled task FTMOStartTrading).
The trading password is read from SSM Parameter Store /ftmo/demo/master (SecureString,
created by the account owner). It is written to a temporary start-up ini only for the
launch and the ini is deleted afterwards. Nothing secret is printed.
"""
import os
import pathlib
import subprocess
import time

import boto3
from botocore.config import Config

LOGIN, SERVER = 1515378701, "FTMO-Demo"
TERMINAL = r"C:\Users\FTMODemo\FTMO\terminal64.exe"

pw = boto3.client("ssm", region_name="il-central-1",
                  config=Config(connect_timeout=6, read_timeout=10, retries={"max_attempts": 2})
                  ).get_parameter(Name="/ftmo/demo/master", WithDecryption=True)["Parameter"]["Value"]
print("trading credential retrieved", flush=True)
ini = pathlib.Path(os.environ["LOCALAPPDATA"]) / "ftmo-trading.ini"
ini.write_text(
    "[Common]\n"
    f"Login={LOGIN}\nPassword={pw}\nServer={SERVER}\n"
    "[Experts]\nAllowLiveTrading=1\nEnabled=1\nAccount=0\nProfile=0\n"
    "[StartUp]\nExpert=TurnOfMonthEA\nSymbol=US500.cash\nPeriod=H1\nExpertParameters=TurnOfMonthEA.set\n",
    encoding="utf-16")
del pw
try:
    subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
    time.sleep(3)
    p = subprocess.Popen([TERMINAL, "/portable", "/config:" + str(ini)])
    print("terminal started", p.pid, flush=True)
    time.sleep(60)
finally:
    ini.unlink(missing_ok=True)
    print("start-up ini deleted", flush=True)
