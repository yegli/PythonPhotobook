PY  := .venv/bin/python
BIN := $(HOME)/.local/bin

.PHONY: test build install

$(PY):
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements.txt

test: $(PY)
	$(PY) test_photobook.py

# Standalone binary for this OS in dist/ (no Python needed to run it). No arguments opens the window.
build: $(PY)
	$(PY) -m pip install -q pyinstaller
	$(PY) -m PyInstaller --onefile --name photobook --collect-all pillow_heif --noconfirm --clean photobook.py

install: build
	mkdir -p $(BIN) && cp dist/photobook $(BIN)/photobook
	@echo "Installed: $(BIN)/photobook"
