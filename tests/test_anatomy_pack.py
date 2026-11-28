import json,tempfile,unittest,zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"gallery"))
import anatomy_pack as p
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.d=self.r/"data";self.d.mkdir()
        assets={"model.glb":b"glTFsynthetic test only","image.png":b"image test","license.txt":b"test fixture","receipt.json":b"{}"}
        for k,v in assets.items():(self.d/k).write_bytes(v)
        self.c={"schema":"oneirifact.reference-viewer/v1","source_pins":{"fixture":"a"*64},"datasets":[{"id":"fixture","preview":"data/image.png","attribution":"data/license.txt","layers":[{"id":"model","file":"data/model.glb","sha256":p.sha(assets["model.glb"]),"bytes":len(assets["model.glb"])}]}],"evidence":{"receipt":"data/receipt.json"}}
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):(self.d/"catalog.json").write_text(json.dumps(self.c))
    def test_determinism_restore(self):
        a,b=self.r/"a.zip",self.r/"b.zip"
        h=p.pack(self.d,a);self.assertEqual(h,p.pack(self.d,b));self.assertEqual(a.read_bytes(),b.read_bytes())
        dest=self.r/"restored";p.restore(a,h,dest);self.assertEqual(p.inventory(dest),p.inventory(self.d))
        with self.assertRaises(FileExistsError):p.restore(a,h,dest)
    def test_model_hash(self):
        (self.d/"model.glb").write_bytes(b"wrong")
        with self.assertRaises(ValueError):p.pack(self.d,self.r/"a.zip")
    def test_unsafe_path(self):
        self.c["datasets"][0]["preview"]="data/../image.png";self.save()
        with self.assertRaises(ValueError):p.pack(self.d,self.r/"a.zip")
    def test_unreferenced(self):
        (self.d/"unreferenced.txt").write_text("unexpected")
        with self.assertRaises(ValueError):p.pack(self.d,self.r/"a.zip")
    def test_wrong_digest(self):
        a=self.r/"a.zip";p.pack(self.d,a)
        with self.assertRaises(ValueError):p.verify(a,"0"*64)
    def test_zip_traversal(self):
        a=self.r/"a.zip";p.pack(self.d,a)
        with zipfile.ZipFile(a,"a") as z:z.writestr("../outside.txt","no")
        with self.assertRaises(ValueError):p.verify(a,p.digest(a))
    def test_symlink(self):
        (self.d/"extra.txt").symlink_to(self.d/"license.txt")
        with self.assertRaises(ValueError):p.pack(self.d,self.r/"a.zip")
    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):p.parse(b'{"x":1,"x":2}')
if __name__=="__main__":unittest.main()
