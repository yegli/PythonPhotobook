# Mac: make test | build | install        Windows: make test-win | build-win | install-win
# Build on the system you build for: PyInstaller can't build a Windows .exe on a Mac or the other way round.

PY     := .venv/bin/python
APPS   := /Applications
BIN    := $(HOME)/.local/bin
BUNDLE := --name Photobook --windowed --collect-all pillow_heif --noconfirm --clean photobook.py

.PHONY: test build install test-win build-win install-win

$(PY):
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements.txt

test: $(PY)
	$(PY) test_photobook.py

# dist/Photobook.app. With arguments the same binary works as the command line tool.
build: $(PY)
	$(PY) -m pip install -q pyinstaller
	$(PY) -m PyInstaller $(BUNDLE)

install: build
	rm -rf "$(APPS)/Photobook.app" && cp -R dist/Photobook.app "$(APPS)/"
	mkdir -p "$(BIN)" && ln -sf "$(APPS)/Photobook.app/Contents/MacOS/Photobook" "$(BIN)/photobook"
	@echo "Installed: $(APPS)/Photobook.app and $(BIN)/photobook"

# ---- Windows (GNU make, run from cmd or PowerShell) ------------------------------------------------------

ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
endif
WPY := .venv\Scripts\python.exe
# Already on PATH for every Windows user: no PATH editing needed.
WBIN := $(LOCALAPPDATA)\Microsoft\WindowsApps

$(WPY):
	py -3 -m venv .venv && $(WPY) -m pip install -q -r requirements.txt

test-win: $(WPY)
	$(WPY) test_photobook.py

# dist\Photobook.exe: one file, opens the window. ponytail: windowed exe prints nothing; CLI on Windows = photobook.py.
build-win: $(WPY)
	$(WPY) -m pip install -q pyinstaller
	$(WPY) -m PyInstaller --onefile $(BUNDLE)

install-win: build-win
	copy /Y dist\Photobook.exe "$(WBIN)\Photobook.exe"
	@echo Installed: $(WBIN)\Photobook.exe - start it with Win+R, Photobook
