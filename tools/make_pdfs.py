"""
Write the printable PDFs from print.html using headless Chromium.

    pip install playwright && playwright install chromium   (already installed in this session)
    python tools/make_pdfs.py

Serves the repo folder on a local port, opens print.html for each workout, and saves
pdf/<workout id>.pdf plus pdf/yae-all-workouts.pdf. Letter, landscape.
"""
import http.server, json, os, socketserver, sys, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "pdf")
PORT = 8799


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    os.chdir(ROOT)
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(PDF, exist_ok=True)
    data = json.load(open(os.path.join(ROOT, "data", "yae.json")))
    ids = [w["id"] for g in data["groups"] for w in g["workouts"]]
    srv = serve()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1100, "height": 850})
        for wid in ids + [""]:
            page.goto(f"http://127.0.0.1:{PORT}/print.html#{wid}")
            page.wait_for_selector(".page img")
            page.wait_for_timeout(800)
            page.evaluate("() => Promise.all([...document.images].map(i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r })))")
            out = os.path.join(PDF, (wid or "yae-all-workouts") + ".pdf")
            page.pdf(path=out, format="Letter", landscape=True, print_background=True, prefer_css_page_size=True)
            print("wrote", os.path.relpath(out, ROOT))
        b.close()
    srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
