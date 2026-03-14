"""
download.py
-----------
Responsible for downloading the AQA A-level Economics specification PDF
and saving it to the local 'data/' directory.

This module is intentionally kept separate from parsing, so that:
  - You can re-run the parser without re-downloading the PDF each time.
  - The download logic is easy to find and update if the URL ever changes.
"""

import requests       # third-party library for making HTTP requests (downloading files from the web)
import os             # standard library for interacting with the file system (paths, directories)


# The direct URL to the AQA A-level Economics specification PDF.
# If AQA ever updates the spec and the URL changes, this is the only line you need to edit.
SPEC_URL = "https://filestore.aqa.org.uk/resources/economics/specifications/AQA-7135-7136-SP-2015.PDF"

# Where to save the downloaded file.
# os.path.dirname(__file__) gives us the directory that *this* file (download.py) lives in.
# os.path.join then builds a path relative to that — going up one level (..) and into 'data/'.
# ⚠️  SLIGHTLY ADVANCED: __file__ is a special Python variable that holds the path to the
#     current script. os.path.dirname gets the folder it lives in.
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PDF_PATH = os.path.join(DATA_DIR, "aqa_economics_spec.pdf")


def download_spec(url: str = SPEC_URL, save_path: str = PDF_PATH) -> str:
    """
    Downloads the AQA spec PDF from the given URL and saves it to save_path.

    Parameters:
        url       — the web address to download from (defaults to the AQA spec URL above)
        save_path — where to save the file on your computer (defaults to data/ folder)

    Returns:
        The path where the file was saved.
    """

    # os.makedirs creates the target directory if it doesn't exist yet.
    # exist_ok=True means it won't raise an error if the directory already exists.
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Check if we've already downloaded the file — no need to download it again.
    if os.path.exists(save_path):
        print(f"PDF already exists at: {save_path}")
        print("Delete it and re-run if you want to download a fresh copy.")
        return save_path

    print(f"Downloading AQA Economics spec from:\n  {url}")

    # requests.get() sends an HTTP GET request to the URL — the same as visiting it in a browser.
    # stream=True means we download the file in chunks rather than all at once,
    # which is more memory-efficient for large files.
    # ⚠️  SLIGHTLY ADVANCED: 'stream=True' and writing in chunks is standard practice
    #     for downloading files, but you can think of it as "download a little at a time".
    response = requests.get(url, stream=True)

    # raise_for_status() checks if the download succeeded.
    # If the server returned an error (e.g. 404 Not Found), it raises an exception here
    # rather than saving a broken file silently.
    response.raise_for_status()

    # Open the destination file in binary-write mode ("wb") and write the content in chunks.
    # "binary" mode is required because PDFs are not plain text.
    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):  # 8192 bytes = 8 KB per chunk
            f.write(chunk)

    print(f"Saved to: {save_path}")
    return save_path


# This block only runs if you execute this file directly (e.g. `python download.py`).
# It does NOT run when this file is imported by another script.
# It's a useful way to test a module on its own.
if __name__ == "__main__":
    download_spec()
