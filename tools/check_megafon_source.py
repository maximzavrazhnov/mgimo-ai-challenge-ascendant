"""Fetch one approved public source and verify the cited paragraph on page 2."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import HTTPRedirectHandler, Request, build_opener

URL = ("https://ceph.megafon.ru/htdocs-pk-ceph/ai/tariff_attrs/"
       "ac3834e1-31c5-4ccf-8258-bcfb3eb64577/"
       "846c61a0-0542-458e-b7c0-8def8dcfb08d/pdf/tariff_5229_orl_79ae0.pdf")
MAX_BYTES = 2_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch():
    request = Request(URL, headers={"Accept": "application/pdf"})
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/pdf":
            raise ValueError("Expected HTTP 200 with the PDF content type")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Unexpected PDF content")
        return data


def page_text(data):
    try:
        from pypdf import PdfReader
    except ImportError:
        binary = shutil.which("pdftotext")
        if not binary:
            raise ValueError("Install pypdf or use an existing pdftotext to parse the live PDF")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.pdf"
            path.write_bytes(data)
            result = subprocess.run([binary, "-f", "2", "-l", "2", str(path), "-"],
                                    capture_output=True, timeout=15, check=True)
            return result.stdout.decode("utf-8")
    pages = PdfReader(io.BytesIO(data)).pages
    if len(pages) < 2:
        raise ValueError("Source no longer has page 2")
    return pages[1].extract_text() or ""


def verify_page(page):
    # Anchor to the family paragraph, not the unrelated daily data add-on.
    normalized = " ".join(page.casefold().split())
    match = re.search(r"вступлении\s+в\s+группу\s+[«\s]*моя\s+семья[»\s]*абоненту\b", normalized)
    if not match:
        raise ValueError("Expected family-plan paragraph was not found on page 2")
    paragraph = normalized[match.start():match.start() + 560]
    required = [r"ежемесячно.{0,110}?1\s*гб", r"исчерпани.{0,110}?64\s*кб",
                r"на\s+планшетах,\s*модемах\s+и\s+роутерах"]
    if not all(re.search(check, paragraph) for check in required):
        raise ValueError("Terms changed or the cited passage did not parse; review manually")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional new receipt file")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    receipt = {"url": URL, "checked_at_utc": stamp}
    try:
        data = fetch()
        verify_page(page_text(data))
        receipt.update(status="verified", http_status=200, sha256=sha256(data).hexdigest(),
                       source_page=2, locator="Примечание 5, абзац об условиях семейного пакета",
                       finding="В опубликованной редакции после исчерпания пакета скорость снижается; для отдельных типов устройств услуга недоступна.")
    except Exception as error:
        # No fallback to any cached copy. Report failures as failures.
        receipt.update(status="unverified", error_type=type(error).__name__, error=str(error))
    payload = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as file:
            file.write(payload)
    sys.stdout.buffer.write(payload.encode("utf-8"))
    return 0 if receipt["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
