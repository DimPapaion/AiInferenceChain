@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: start_testnet.bat — Start a 4-node InferenceChain DNN testnet on localhost
::
:: Opens four separate Command Prompt windows, one per DNN validator node.
:: Each node loads a different trained CIFAR-10 model.
:: All nodes share config/testnet.yaml (same genesis block).
::
:: Requirements:
::   - Trained weights in models/weights/  (run scratch/train_cifar10_models.py)
::   - Python venv at .venv\
::
:: Usage:
::   scripts\start_testnet.bat
::
:: After startup:
::   Dashboard : http://localhost:8010/ui/
::   API docs  : http://localhost:8010/docs
::   Node 1    : http://localhost:8011/docs
::   Node 2    : http://localhost:8012/docs
::   Node 3    : http://localhost:8013/docs
::
:: To submit an inference request (after all nodes are connected):
::   curl -X POST http://localhost:8010/inference/image -F "file=@my_image.jpg"
::   curl -X POST http://localhost:8010/inference/request -H "Content-Type: application/json" \
::        -d "{\"image_hash\":\"<hash>\",\"sender\":\"<addr>\",\"nonce\":1,\"fee\":1.0}"
:: ─────────────────────────────────────────────────────────────────────────────

set PYTHON=C:\Users\dpapa\InferenceChain\.venv\Scripts\python.exe
set CONFIG=config\testnet.yaml
set WEIGHTS=models\weights

echo Starting InferenceChain DNN testnet (4 nodes)...
echo.

:: Node 0 — resnet20 — genesis bootstrap node
start "IC DNN-0 resnet20  :8010" cmd /k "%PYTHON% node_runner.py ^
  --config %CONFIG% ^
  --port 8010 ^
  --db-path data\dnn0.db ^
  --node-type dnn ^
  --model resnet20 ^
  --weights-dir %WEIGHTS% ^
  --private-key 5f0182a74c11939cc66bc5f35744ad0f15910a8b6e97fdcc52aafd3633d52228 ^
  --f 1"

:: Wait for node-0 to be up before others try to connect
timeout /t 5 /nobreak >nul

:: Node 1 — resnet56
start "IC DNN-1 resnet56  :8011" cmd /k "%PYTHON% node_runner.py ^
  --config %CONFIG% ^
  --port 8011 ^
  --db-path data\dnn1.db ^
  --node-type dnn ^
  --model resnet56 ^
  --weights-dir %WEIGHTS% ^
  --private-key 84bc2518750071408661eb846b303e02554e4cbea4f07c67ed1e9a5d5bc4ca04 ^
  --f 1"

timeout /t 2 /nobreak >nul

:: Node 2 — vgg11_bn
start "IC DNN-2 vgg11_bn  :8012" cmd /k "%PYTHON% node_runner.py ^
  --config %CONFIG% ^
  --port 8012 ^
  --db-path data\dnn2.db ^
  --node-type dnn ^
  --model vgg11_bn ^
  --weights-dir %WEIGHTS% ^
  --private-key 2ee709c86b49396d86a04566871752846a38f67f65b358b7a054bfb78b232c16 ^
  --f 1"

timeout /t 2 /nobreak >nul

:: Node 3 — densenet40_12
start "IC DNN-3 densenet   :8013" cmd /k "%PYTHON% node_runner.py ^
  --config %CONFIG% ^
  --port 8013 ^
  --db-path data\dnn3.db ^
  --node-type dnn ^
  --model densenet40_12 ^
  --weights-dir %WEIGHTS% ^
  --private-key e8a2b44a69dbe729b7c89f47d6f687ab377bcf1415842c38cd87a7970b08d389 ^
  --f 1"

echo.
echo Nodes starting in separate windows.
echo.
echo  Dashboard : http://localhost:8010/ui/
echo  API docs  : http://localhost:8010/docs
echo.
echo  Wait ~10s for all nodes to peer and then submit an inference request:
echo    POST http://localhost:8010/inference/image   (upload image)
echo    POST http://localhost:8010/inference/request (submit request)
echo    GET  http://localhost:8010/inference/{id}    (poll result)
echo.
