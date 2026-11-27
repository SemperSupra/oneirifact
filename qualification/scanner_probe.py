"""Check pinned scanner behavior with generated, deliberately nonfunctional fixtures."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile

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
        bad=subprocess.run([str(binary),"dir",str(root/"absent"),"--config",str(config),"--exit-code","23"],capture_output=True,text=True,timeout=10)
        assert bad.returncode not in (0,23),"scanner failure must not masquerade as clean or a finding"
        print("missing-input FAIL-CLOSED PASS")
        print("SYNTHETIC SCANNER QUALIFICATION PASS: 6 checks")
if __name__=="__main__":
    main()
