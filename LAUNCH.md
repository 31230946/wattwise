# How to run WattWise

WattWise has two parts that run side by side, each in its own terminal:

```
Browser  ──►  wattwise_app  (Node + Express, port 5050)  ──►  wattwise_ml  (Python FastAPI, port 8000)
```

You open **http://localhost:5050**. Port 8000 is the ML service working in the background.

**Before you start:** put the project in a folder **without spaces** in its path, for example `C:\Projects\WattWise` or `~/Projects/WattWise`.

Jump to: [Windows](#windows) · [Mac](#mac) · [Problems](#problems)

---

## Windows

Commands below are for **Git Bash**. If you use **PowerShell** or **Command Prompt**, only the activate line changes (shown in the comments).

### 1. Install once
- **Python 3.11** (exactly 3.11, TensorFlow needs it): https://www.python.org/downloads/release/python-3119/ → "Windows installer (64-bit)". On the first screen tick **"Add python.exe to PATH"**.
- **Node.js** LTS (18 or newer): https://nodejs.org/
- **Git**: https://git-scm.com/download/win (includes Git Bash)

Close and reopen Git Bash, then check:
```bash
py -3.11 --version      # should print Python 3.11.x
node -v                 # should print v18 or higher
```

### 2. Set up the ML service (once, 5-10 min)
```bash
cd /c/Projects/WattWise/wattwise_ml
py -3.11 -m venv venv                 # create a private Python for this project
source venv/Scripts/activate          # PowerShell: venv\Scripts\Activate.ps1   CMD: venv\Scripts\activate.bat
python --version                      # must say 3.11.x
python -m pip install --upgrade pip
pip install -r requirements.txt       # ~1 GB download
python -m pytest -q tests             # should end with "34 passed"
```
PowerShell says "running scripts is disabled"? Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

### 3. Set up the website (once)
```bash
cd /c/Projects/WattWise/wattwise_app
npm install
npm run build
```

### 4. Start WattWise (every time, two terminals)
**Terminal 1: ML service** (leave it open)
```bash
cd /c/Projects/WattWise/wattwise_ml
source venv/Scripts/activate          # PowerShell: venv\Scripts\Activate.ps1
python -m uvicorn api:app --port 8000
```
**Terminal 2: website**
```bash
cd /c/Projects/WattWise/wattwise_app
npm start
```
Open **http://localhost:5050**. The badge at the top right should say **"Model online"** (green).

To stop: press `Ctrl + C` in both terminals.

---

## Mac

Works on Apple Silicon (M1/M2/M3) and Intel. Commands are for **Terminal**.

### 1. Install once
```bash
# Homebrew (skip if you have it): https://brew.sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.11 libomp node   # libomp is needed by XGBoost on Mac
python3.11 --version                   # should print Python 3.11.x
node -v                                # should print v18 or higher
```

### 2. Set up the ML service (once, 5-10 min)
```bash
cd ~/Projects/WattWise/wattwise_ml
python3.11 -m venv venv
source venv/bin/activate
python --version                      # must say 3.11.x
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q tests             # should end with "34 passed"
```

### 3. Set up the website (once)
```bash
cd ~/Projects/WattWise/wattwise_app
npm install
npm run build
```

### 4. Start WattWise (every time, two Terminal windows)
**Terminal 1: ML service** (leave it open)
```bash
cd ~/Projects/WattWise/wattwise_ml
source venv/bin/activate
python -m uvicorn api:app --port 8000
```
**Terminal 2: website**
```bash
cd ~/Projects/WattWise/wattwise_app
npm start
```
Open **http://localhost:5050**. The badge at the top right should say **"Model online"**.

To stop: press `Ctrl + C` in both windows.

---

## Handy commands (both systems)

Run these inside `wattwise_ml` with the venv active (`source venv/Scripts/activate` on Windows Git Bash, `source venv/bin/activate` on Mac).

| What | Command |
|---|---|
| Run the tests | `python -m pytest -q tests` |
| Run the tests with names | `python -m pytest -v tests` |
| Try the API in the browser | start the ML service, then open http://localhost:8000/docs |
| Check the ML service is alive | open http://localhost:8000/health |
| Use it with no server at all | `python cli.py demo` |
| Bill for some units | `python cli.py bill --units 280 295 306` |
| Forecast from 7 days | `python cli.py daily --kwh 9.1 8.7 10.2 9.8 11.0 10.5 9.9` |
| Homes like yours | `python cli.py like --units 140 150 210 --last-month 4 --ac yes` |
| Retrain the models | `python train.py --real` (needs the LCL data file in `data/`, see `wattwise_ml/DATASETS.md`) |
| Leave the venv | `deactivate` |

Inside `wattwise_app`:

| What | Command |
|---|---|
| Rebuild after changing anything in `src/` | `npm run build` |
| Live-editing the website | `npm start` in one terminal, `npm run dev` in another, then open http://localhost:5173 |

**Show it on a phone (same Wi-Fi):** with everything running, find your laptop's IP (`ipconfig` on Windows, `ipconfig getifaddr en0` on Mac), e.g. `192.168.1.23`, and open `http://192.168.1.23:5050` on the phone. Windows may ask to let Node.js through the firewall: allow it on private networks.

---

## Problems

| Problem | Fix |
|---|---|
| Badge says **"Model offline"** | Terminal 1 (ML service) isn't running or crashed. Read its error, start it again; the page reconnects by itself |
| `py -3.11` not found (Windows) | Python 3.11 isn't installed, or Git Bash was open during install. Install it, then reopen Git Bash |
| `No module named uvicorn` / `pytest not found` | The venv isn't active. Run the `source venv/...` line again (prompt should start with `(venv)`) |
| `No matching distribution found for tensorflow` | The venv was made with the wrong Python. Delete the `venv` folder and redo step 2 with 3.11 |
| `venv/bin/activate: No such file` on Windows | Windows uses `venv/Scripts/activate`, not `venv/bin/activate` |
| XGBoost error mentioning `libomp` (Mac) | `brew install libomp` |
| `npm` not recognised | Install Node.js, then open a **new** terminal |
| "The website is not built yet" | In `wattwise_app`: `npm run build` |
| Port 5050 or 8000 already in use | ML service: add `--port 8001`. Website (Git Bash / Mac): `ML_URL=http://localhost:8001 npm start`. Website (CMD): `set ML_URL=http://localhost:8001 && npm start`. To move the website itself: `PORT=5060 npm start` |
| ML terminal shows `oneDNN` / `cuda` lines | Harmless TensorFlow info |
| First forecast is slow (5-10 s) | The model loads on first use. Later ones are fast |
| Fonts look plain | No internet for Google Fonts. Everything else still works |
