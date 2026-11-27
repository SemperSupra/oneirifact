"""Check pinned scanner behavior with generated, deliberately nonfunctional fixtures."""
import base64
import json
import stat
from pathlib import Path
import subprocess
import sys
import tempfile

def inventory(directory):
    # This preflight is for the small text-only release fixture, not a proof of
    # scanner coverage. Production also needs an exact independently reviewed manifest.
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("scan target missing or not a regular directory")
    paths=[]
    for p in directory.rglob("*"):
        mode=p.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("symlink refused")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode) or p.stat().st_size > 1_000_000:
            raise ValueError("nonregular or oversized scan input")
        paths.append(p.relative_to(directory).as_posix())
    if not paths or len(paths)>100:
        raise ValueError("empty or excessive input inventory")
    return sorted(paths)

def main():
    binary=Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        config=root/"config.toml"
        config.write_text("[extend]\nuseDefault = true\n")
        ignore=root/".gitleaksignore"
        ignore.write_text("")
        # Construct the fake value only in the test process, not in source history.
        fake="AK"+"IA"+"Q7T3R2W5Y6U4H3P7"
        def run(name,body,expected,rule=None,extra_files=None):
            directory=root/name
            directory.mkdir()
            (directory/"example.txt").write_text(body)
            for key,value in (extra_files or {}).items():
                (directory/key).write_text(value)
            actual=inventory(directory)
            assert actual==sorted(['example.txt',*(extra_files or {}).keys()]),(name,'input inventory mismatch')
            report=root/(name+".json")
            args=[str(binary),"dir",str(directory),"--config",str(config),"--gitleaks-ignore-path",str(ignore),"--ignore-gitleaks-allow","--redact=100","--no-banner","--report-format","json","--report-path",str(report),"--exit-code","23","--max-target-megabytes","1","--max-decode-depth","2","--timeout","20"]
            result=subprocess.run(args,capture_output=True,text=True,timeout=30)
            assert result.returncode==expected,(name,result.returncode)
            findings=json.loads(report.read_text()) if report.exists() else []
            if rule: assert any(f.get("RuleID")==rule for f in findings), (name,"rule absent")
            else: assert not findings,(name,"unexpected findings")
            assert fake not in result.stdout+result.stderr+(report.read_text() if report.exists() else ""),(name,"redaction failed")
            print(name,"PASS")
        run("clean","public example: color blue\n",0)
        run("direct","aws_access_key_id = "+fake+"\n",23,"aws-access-token")
        run("allow-comment","aws_access_key_id = "+fake+" # gitleaks:allow\n",23,"aws-access-token")
        run("candidate-config","aws_access_key_id = "+fake+"\n",23,"aws-access-token",{
            ".gitleaks.toml":"[allowlist]\npaths=['.*']\n"})
        run("encoded","encoded = "+base64.b64encode(("aws_access_key_id = "+fake).encode()).decode()+"\n",23,"aws-access-token")
        # Record native behavior: a prior run showed an ambiguous exit code.
        # Never treat native exit code as a completeness witness.
        bad=subprocess.run([str(binary),"dir",str(root/"absent"),"--config",str(config),"--exit-code","23"],capture_output=True,text=True,timeout=10)
        print("native missing-input exit code:",bad.returncode)
        empty=root/"empty"; empty.mkdir()
        oversize=root/"oversize"; oversize.mkdir()
        (oversize/"big.txt").write_bytes(b"x"*1_000_001)
        symlink=root/"symlink"; symlink.mkdir()
        (symlink/"alias").symlink_to(root/"absent")
        for name in ("absent","empty","oversize","symlink"):
            try:
                inventory(root/name)
            except ValueError:
                print(name,"preflight FAIL-CLOSED PASS")
            else:
                raise AssertionError(name+" accepted")
        # A missing scanner executable or timeout must propagate as a failure.
        try:
            subprocess.run([str(root/"missing-scanner")],check=True,timeout=1)
        except OSError:
            print("missing executable FAIL-CLOSED PASS")
        else:
            raise AssertionError("missing scanner accepted")
        print("SYNTHETIC SCANNER QUALIFICATION PASS: 10 checks")
if __name__=="__main__":
    main()
