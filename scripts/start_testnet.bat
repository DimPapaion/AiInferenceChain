@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: start_testnet.bat — Start a 3-node InferenceChain testnet on localhost
::
:: Opens three separate Command Prompt windows, one per node.
:: All nodes share the same genesis (config/testnet.yaml).
::
:: Usage:
::   scripts\start_testnet.bat
::
:: After startup:
::   Dashboard:  http://localhost:8000/ui/
::   API docs:   http://localhost:8000/docs
::   Node 1:     http://localhost:8001/docs
::   Node 2:     http://localhost:8002/docs
::
:: To import a dev wallet:
::   python wallet.py import 947f6967eba35761053563545933a3899ed077c4cdb900b90d70f1adf62ccabf --out node0.json
::   python wallet.py info --wallet node0.json --node http://localhost:8000
:: ─────────────────────────────────────────────────────────────────────────────

set PYTHON=C:\Python310\python.exe
set CONFIG=config\testnet.yaml

echo Starting InferenceChain testnet (3 nodes)...
echo.

:: Node 0 — genesis bootstrap node
start "IC Node-0 :8000" cmd /k "%PYTHON% node_runner.py --config %CONFIG% --port 8000 --db-path data\node0.db --f 0"

:: Wait a moment so node-0 is up before the others try to connect
timeout /t 3 /nobreak >nul

:: Node 1
start "IC Node-1 :8001" cmd /k "%PYTHON% node_runner.py --config %CONFIG% --port 8001 --db-path data\node1.db --f 0"

:: Node 2
start "IC Node-2 :8002" cmd /k "%PYTHON% node_runner.py --config %CONFIG% --port 8002 --db-path data\node2.db --f 0"

echo.
echo Nodes starting in separate windows.
echo.
echo  Dashboard : http://localhost:8000/ui/
echo  API docs  : http://localhost:8000/docs
echo.
echo NOTE: Using --f 0 for single-node instant commits.
echo       Change to --f 1 once all 3 nodes are connected.
