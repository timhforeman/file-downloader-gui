#!/usr/bin/env python3
"""
Simple GUI web crawler to download files of a specific type (default: PDF)
from a given URL by following links on the same domain.
"""

import os
import re
import time
import threading
import hashlib
import json
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag
from tkinter import Tk, Label, Entry, Button, Text, Scrollbar, Frame, StringVar, filedialog, messagebox
from tkinter import ttk
import requests
from bs4 import BeautifulSoup

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".file_downloader_history.json")
SEED_URL = "https://ftp.idu.ac.id/wp-content/uploads/ebook/"

class FileDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("URL File Downloader")
        self.root.geometry("700x520")

        # Variables
        self.url_var = StringVar()
        self.ext_var = StringVar(value="pdf")
        self.folder_var = StringVar(value=os.getcwd())
        self.running = False
        self.stop_flag = False
        self.history = self.load_history()

        # GUI Layout
        Frame(root).pack(fill="x", padx=10, pady=5)
        Label(root, text="Start URL:").pack(anchor="w", padx=10)
        self.url_combo = ttk.Combobox(root, textvariable=self.url_var, width=78)
        self.url_combo.pack(fill="x", padx=10, pady=2)
        self.update_history_combo()

        Label(root, text="File extension (default: pdf):").pack(anchor="w", padx=10)
        Entry(root, textvariable=self.ext_var, width=20).pack(anchor="w", padx=10, pady=2)

        Label(root, text="Download folder:").pack(anchor="w", padx=10)
        folder_frame = Frame(root)
        folder_frame.pack(fill="x", padx=10, pady=2)
        Entry(folder_frame, textvariable=self.folder_var, width=60).pack(side="left", fill="x", expand=True)
        Button(folder_frame, text="Browse", command=self.browse_folder).pack(side="left", padx=5)

        btn_frame = Frame(root)
        btn_frame.pack(pady=10)
        self.start_btn = Button(btn_frame, text="Start Download", command=self.start_download, bg="#4CAF50", fg="white")
        self.start_btn.pack(side="left", padx=5)
        self.stop_btn = Button(btn_frame, text="Stop", command=self.stop_download, bg="#f44336", fg="white", state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        Label(root, text="Log:").pack(anchor="w", padx=10)
        log_frame = Frame(root)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = Text(log_frame, wrap="word", height=15)
        scrollbar = Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_var.set(url)

        ext = self.ext_var.get().strip().lower().lstrip(".")
        if not ext:
            ext = "pdf"
        self.ext_var.set(ext)

        folder = self.folder_var.get()
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create folder: {e}")
                return

        self.running = True
        self.stop_flag = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log(f"Starting crawl from: {url}")
        self.log(f"Looking for: .{ext} files")
        self.log(f"Saving to: {folder}")

        # Add to history
        self.add_to_history(url)

        thread = threading.Thread(target=self.crawl_and_download, args=(url, ext, folder), daemon=True)
        thread.start()

    def stop_download(self):
        self.stop_flag = True
        self.log("Stopping...")

    def crawl_and_download(self, start_url, extension, download_folder):
        visited = set()
        queue = deque([start_url])
        domain = urlparse(start_url).netloc
        downloaded = set()
        max_pages = 300
        delay = 0.5

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        while queue and not self.stop_flag and len(visited) < max_pages:
            current_url = queue.popleft()
            current_url = urldefrag(current_url)[0]  # remove fragment
            if current_url in visited:
                continue
            visited.add(current_url)

            self.log(f"Checking: {current_url}")

            try:
                resp = session.get(current_url, timeout=15, allow_redirects=True)
                resp.raise_for_status()
            except Exception as e:
                self.log(f"  Failed: {e}")
                continue

            content_type = resp.headers.get("content-type", "").lower()
            final_url = resp.url

            # Check if this response is a matching file
            if self.is_target_file(final_url, content_type, extension):
                if final_url not in downloaded:
                    self.download_file(resp, final_url, download_folder, extension)
                    downloaded.add(final_url)
                continue  # don't parse file content as HTML

            # Only parse HTML-like content for links
            if "html" not in content_type and "text" not in content_type:
                continue

            try:
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception:
                continue

            for link in soup.find_all("a", href=True):
                href = link["href"]
                absolute = urljoin(final_url, href)
                absolute = urldefrag(absolute)[0]
                parsed = urlparse(absolute)

                if parsed.scheme not in ("http", "https"):
                    continue
                if parsed.netloc != domain:
                    continue
                if absolute in visited:
                    continue

                # Always queue potential pages / directories
                queue.append(absolute)

            time.sleep(delay)

        self.log(f"\nDone. Visited {len(visited)} pages. Downloaded {len(downloaded)} files.")
        self.running = False
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))

    def is_target_file(self, url, content_type, extension):
        url_lower = url.lower()
        if url_lower.endswith(f".{extension}"):
            return True
        if extension in content_type and ("application/" in content_type or "octet-stream" in content_type):
            return True
        return False

    def download_file(self, response, url, folder, extension):
        filename = os.path.basename(urlparse(url).path)
        if not filename or "." not in filename:
            filename = f"file_{int(time.time())}.{extension}"
        # Sanitize filename
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        filepath = os.path.join(folder, filename)

        # Check for existing file and skip if duplicate
        if os.path.exists(filepath):
            existing_size = os.path.getsize(filepath)
            new_size = len(response.content)
            if existing_size == new_size:
                # Compare hashes for certainty
                existing_hash = self.file_hash(filepath)
                new_hash = hashlib.md5(response.content).hexdigest()
                if existing_hash == new_hash:
                    self.log(f"  Skipped duplicate: {filename}")
                    return
            # Different file with same name: use numbered name
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base}_{counter}{ext}"
                counter += 1
            filename = os.path.basename(filepath)

        try:
            with open(filepath, "wb") as f:
                f.write(response.content)
            self.log(f"  Downloaded: {filename}")
        except Exception as e:
            self.log(f"  Save failed: {e}")

    def file_hash(self, filepath, chunk_size=8192):
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()

    def load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return [SEED_URL]

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def update_history_combo(self):
        self.url_combo["values"] = self.history
        if self.history and not self.url_var.get():
            self.url_var.set(self.history[0])

    def add_to_history(self, url):
        if url in self.history:
            self.history.remove(url)
        self.history.insert(0, url)
        self.history = self.history[:50]  # keep last 50
        self.save_history()
        self.update_history_combo()

if __name__ == "__main__":
    root = Tk()
    app = FileDownloaderApp(root)
    root.mainloop()
