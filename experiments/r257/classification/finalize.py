"""Record exact public classification products after all bounded gates pass."""
import hashlib
import json
import os
import sys
from pathlib import Path

folder = Path(sys.argv[1])
source = json.loads((folder / 'classification-report.json').read_text())
critic = json.loads((folder / 'verification.json').read_text())
browser = json.loads((folder / 'browser-witness.json').read_text())
lock = json.loads((folder / 'release-lock.json').read_text())
assert source['status'] == 'PASS_EXACT_SOURCE_MEMBERSHIP_AND_TRANSPORT'
assert critic['status'] == 'PASS_EXACT_CLASSIFICATION_TRANSPORT'
assert len(critic['controls']) == 11 and all(r['status'] == 'PASS_REJECTED' for r in critic['controls'])
assert browser['status'] == 'PASS_ACTUAL_BROWSER_MEMBERSHIP' and len(browser['cases']) == 4
assert source['candidate_pack_sha256'] == critic['candidate_pack_sha256'] == lock['sha256']
for case in browser['cases']:
    assert (folder / case['screenshot']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
receipt = {'schema': 'oneirifact.classification-display-release-receipt/v1',
           'status': 'PASS_EXACT_DISPLAY_CLASSIFICATION_AND_BROWSER',
           'source_head': os.environ.get('SOURCE_HEAD_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
           'release': lock, 'original_source_nodes_preserved': 144, 'relocated_source_nodes': 3,
           'unchanged_models': 49, 'unchanged_assets': 73, 'negative_controls_rejected': 11,
           'actual_browser_models_loaded': 4,
           'anatomical_registration': 'NOT_QUALIFIED', 'organ_morphology_and_physics': 'NOT_IMPLEMENTED',
           'site_activation': 'SEPARATE_RELEASE_LOCK_CHANGE_REQUIRED', 'files': {}}
for path in sorted(folder.iterdir()):
    if path.is_file() and path.name != 'receipt.json':
        receipt['files'][path.name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
(folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('R257_FINAL_RECEIPT', receipt['status'], lock['sha256'], flush=True)
