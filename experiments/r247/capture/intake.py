#!/usr/bin/env python3
"""Bounded primary-linked capture intake; no crawling, mirrors, or execution."""
import hashlib
import html.parser
import io
import json
import os
import re
import sys
import traceback
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

PUBLISHER = "https://sites.google.com/a/cgspeed.com/cgspeed/motion-capture/the-motionbuilder-friendly-bvh-conversion-release-of-cmus-motion-capture-database"
README_URL = PUBLISHER+"/readme-motionbuilder-2010-release"
DONOR_COMMIT = "8501d53f66fffa8d2574a01532c30e195c8d2998"
SOURCES = [
    {"id": "CMU_07_01", "member": "07_01.bvh", "action": "walking", "official_listing": "https://mocap.cs.cmu.edu/search.php?subjectnumber=7", "publisher_archive_id": "o6ncxuu1oq5r6z9", "archive": "cmuconvert-mb2-01-09.zip"},
    {"id": "CMU_13_01", "member": "13_01.bvh", "action": "sit on high stool, stand up", "official_listing": "https://mocap.cs.cmu.edu/search.php?subjectnumber=13", "publisher_archive_id": "z6pr5bk3h1o5045", "archive": "cmuconvert-mb2-10-14.zip"},
]


def sha(b): return hashlib.sha256(b).hexdigest()


def fetch(url, maximum, timeout=40):
    request = urllib.request.Request(url, headers={"User-Agent": "Oneirifact-R247-bounded-source-intake/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(maximum+1)
        if len(data) > maximum: raise ValueError("source exceeds bounded byte limit")
        return data, response.url, dict(response.headers)


class DownloadLink(html.parser.HTMLParser):
    def __init__(self): super().__init__(); self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("id") == "downloadButton" and attrs.get("href"):
            self.urls.append(attrs["href"])


def bvh_inventory(data):
    text = data.decode("utf-8-sig")
    hierarchy, motion = text.split("MOTION", 1)
    frames = re.search(r"Frames:\s*(\d+)", motion)
    time = re.search(r"Frame Time:\s*([\d.Ee+-]+)", motion)
    if not frames or not time: raise ValueError("missing BVH frame metadata")
    declared, dt = int(frames[1]), float(time[1])
    rows = [line.split() for line in motion[time.end():].splitlines() if line.strip()]
    channels = sum(int(n) for n in re.findall(r"CHANNELS\s+(\d+)", hierarchy))
    if len(rows) != declared or not rows or any(len(row) != channels for row in rows): raise ValueError("BVH frame/channel census mismatch")
    if abs(dt-1/120) > 1e-6: raise ValueError("selected conversion does not declare expected120Hz")
    names = re.findall(r"(?:ROOT|JOINT)\s+(\S+)", hierarchy)
    if not {"Hips", "LeftUpLeg", "RightUpLeg", "LeftFoot", "RightFoot"} <= set(names): raise ValueError("unexpected source rig naming")
    return {"frames": declared, "frame_time_s": dt, "channels": channels, "joints": names,
            "first_added_reference_frame": 0, "captured_motion_frame_range_in_file": [1, declared-1],
            "capture_duration_s_excluding_reference": max(0, declared-2)*dt,
            "scope": "Publisher adds the first reference pose; its pose is an empirical conversion reference, not an original measured T-pose."}


def main(destination):
    destination.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": "oneirifact.r247-capture-source-intake/v1", "status": "IN_PROGRESS", "source_head": os.environ.get("SOURCE_HEAD_SHA"),
               "run_id": os.environ.get("GITHUB_RUN_ID"), "publisher": PUBLISHER, "publisher_readme": README_URL,
               "source_authority": "https://mocap.cs.cmu.edu/", "selected_capture_count": 2, "no_crawl": True,
               "rights": {"permitted": "research and inclusion in commercial products", "restriction": "no direct resale of raw or converted motion data", "conversion": "publisher states no additional restrictions; current CMU terms govern", "finger_thumb": "not captured; do not infer finger or grip realism"},
               "donor": {"repository": "https://github.com/Diffeomorphic/retarget_bvh", "commit": DONOR_COMMIT, "tag": "version_5_2_0", "license": "GPL-2.0-or-later", "adoption": "NOT_RUN"},
               "sources": [], "failures": [], "files": {}}
    for source in SOURCES:
        row = dict(source, status="IN_PROGRESS")
        receipt["sources"].append(row)
        try:
            page_url = "https://www.mediafire.com/file/"+source["publisher_archive_id"]+"/"+source["archive"]+"/file"
            page, final, headers = fetch(page_url, 3_000_000)
            row.update(download_page=page_url, page_final_url=final, download_page_sha256=sha(page))
            parser = DownloadLink(); parser.feed(page.decode("utf-8", errors="strict"))
            if len(parser.urls) != 1: raise ValueError("expected one primary-linked ordinary download button")
            url = parser.urls[0]
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname.endswith(".mediafire.com"):
                raise ValueError("download button destination outside primary-linked HTTPS host")
            archive, final, headers = fetch(url, 100_000_000, timeout=75)
            row.update(archive_sha256=sha(archive), archive_bytes=len(archive), downloaded_host=urllib.parse.urlparse(final).hostname)
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                candidates = [p for p in z.namelist() if Path(p).name.lower() == source["member"].lower()]
                notices = [p for p in z.namelist() if Path(p).name.upper() == "READMEFIRST.TXT"]
                if len(candidates) != 1 or len(notices) != 1: raise ValueError("selected capture/README not uniquely identified")
                # Only the two explicitly selected motions and their bundled notice
                # are decompressed. Other motions are neither read nor retained.
                data = z.read(candidates[0]); notice = z.read(notices[0])
                if len(data) > 15_000_000 or len(notice) > 200_000: raise ValueError("selected member exceeds intake bound")
                inventory = bvh_inventory(data)
                output = source["member"]; notice_name = source["id"]+"-READMEFIRST.txt"
                destination.joinpath(output).write_bytes(data); destination.joinpath(notice_name).write_bytes(notice)
                row.update(status="SELECTED_SOURCE_BYTES_VERIFIED", selected_archive_member=candidates[0],
                           bvh_sha256=sha(data), bvh_bytes=len(data), notice_sha256=sha(notice), inventory=inventory)
            print(json.dumps({"id": source["id"], "status": row["status"], "bytes": row["bvh_bytes"], "sha256": row["bvh_sha256"]}), flush=True)
        except Exception as error:
            row.update(status="SOURCE_DOWNLOAD_OR_INVENTORY_FAILED", error=type(error).__name__+": "+str(error))
            receipt["failures"].append({"id": source["id"], "reason": row["error"]})
            print(json.dumps({"id": source["id"], "status": row["status"], "error": row["error"]}), flush=True)
    receipt["status"] = "PASS_SELECTED_SOURCE_INTAKE" if not receipt["failures"] else "HOLD_SOURCE_INTAKE"
    receipt["retarget_acceptance"] = "NOT_RUN"
    for path in destination.iterdir():
        if path.is_file() and path.name != "source-intake.json": receipt["files"][path.name] = {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
    destination.joinpath("source-intake.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps({"status": receipt["status"], "failed_sources": len(receipt["failures"])}), flush=True)
    return 0 if not receipt["failures"] else 2


if __name__ == "__main__": sys.exit(main(Path(sys.argv[1])))
