# scribdl-web

Save Scribd documents as PDF files, from the command line or from a small web page that runs on your own computer.

It opens the document's embed viewer in headless Chromium (Playwright), captures each page as an image, and joins the pages into one PDF with img2pdf.

## Features

- Local web UI (Flask): paste one or many URLs and get a progress bar and a download button for each
- Command-line mode with single URLs, batch `.txt` files and parallel downloads
- Page selection: `all`, `3`, `1-10`, `1-3,7`
- Adjustable quality (1x, 2x, 3x) and scroll delay
- Works with the bundled Playwright Chromium, or Chrome, Edge, Brave or Chromium already on your system
- Keeps a download history in `history.json`

## Setup

Needs Python 3.9+.

```bash
pip install -r requirements.txt
playwright install chromium
```

## Web UI

```bash
python app.py
```

Then open http://127.0.0.1:5000.

| Variable | Default | Meaning |
|---|---|---|
| `SCRIBDL_HOST` | `127.0.0.1` | Address to listen on (local only by default) |
| `SCRIBDL_PORT` | `5000` | Port |
| `SCRIBDL_MAX_JOBS` | `2` | Documents processed at the same time |

## Command line

```bash
python scribdl.py https://www.scribd.com/document/123456789/Example
python scribdl.py 123456789 --pages 1-10 --scale 2
python scribdl.py --file urls.txt --threads 3
```

Options: `--output/-o`, `--pages/-p`, `--delay/-d`, `--scale/-s`, `--browser-path/-b`, `--threads/-t`, `--quiet/-q`.

PDFs are saved to `output/`.

## Config file (optional)

Create `config.ini` next to the scripts:

```ini
[SETTINGS]
delay = 0.5
scale = 2
output =
browser_path =
```

## Disclaimer

This tool is for personal use with documents you have the right to download, such as your own uploads or openly licensed material. Respect Scribd's Terms of Service and the rights of document authors. The authors of this project are not responsible for how it is used.
