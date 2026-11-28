"""Explicit gross-anatomy worklist, matched to exact acquired donor identities.
Conservative name screen only, never proof of anatomical equivalence or placement.
"""
import json,zipfile,hashlib,re,sys,csv
from pathlib import Path
from collections import Counter
PINS={"male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"}
# Original authored worklist. Cross-system, adult gross/mesoscale scope. Not an
# exhaustive FMA/UBERON ontology, no count of cells, capillaries or individual hairs.
GROUPS={
"integumentary":["skin","epidermis","dermis","subcutaneous fat","hair follicle","sweat gland","sebaceous gland","nail plate","nail bed","external ear","eyelid","eyebrow","eyelash","lip","nose","nipple","areola"],
"endocrine":["pituitary gland","pineal gland","thyroid gland","parathyroid gland","adrenal gland","thymus","pancreas"],
"respiratory":["nasal cavity","nasal septum","superior nasal concha","middle nasal concha","inferior nasal concha","frontal sinus","maxillary sinus","sphenoidal sinus","ethmoidal sinus","nasopharynx","oropharynx","laryngopharynx","larynx","epiglottis","vocal fold","thyroid cartilage","cricoid cartilage","arytenoid cartilage","trachea","main bronchus","lobar bronchus","segmental bronchus","lung","pleura","diaphragm"],
"digestive":["oral cavity","tongue","hard palate","soft palate","uvula","gingiva","tooth","parotid gland","submandibular gland","sublingual gland","parotid duct","submandibular duct","pharynx","esophagus","stomach","cardia","pylorus","duodenum","jejunum","ileum","cecum","vermiform appendix","ascending colon","transverse colon","descending colon","sigmoid colon","rectum","anal canal","liver","gallbladder","common bile duct","cystic duct","hepatic duct","pancreatic duct","pancreas","greater omentum","lesser omentum","mesentery","peritoneum"],
"urinary":["kidney","renal cortex","renal medulla","renal pelvis","ureter","urinary bladder","urethra"],
"cardiovascular":["heart","right atrium","left atrium","right ventricle","left ventricle","tricuspid valve","mitral valve","aortic valve","pulmonary valve","interventricular septum","pericardium","aorta","pulmonary trunk","pulmonary artery","pulmonary vein","superior vena cava","inferior vena cava","coronary artery","coronary sinus","common carotid artery","internal carotid artery","external carotid artery","internal jugular vein","subclavian artery","axillary artery","brachial artery","radial artery","ulnar artery","renal artery","renal vein","hepatic portal vein","common iliac artery","external iliac artery","internal iliac artery","femoral artery","popliteal artery","anterior tibial artery","posterior tibial artery","great saphenous vein","small saphenous vein","capillary network"],
"lymphatic":["spleen","thymus","palatine tonsil","pharyngeal tonsil","lingual tonsil","lymph node","cervical lymph node","axillary lymph node","inguinal lymph node","mesenteric lymph node","thoracic duct","right lymphatic duct","cisterna chyli","lymphatic vessel","bone marrow"],
"nervous":["brain","cerebrum","cerebellum","brainstem","midbrain","pons","medulla oblongata","thalamus","hypothalamus","corpus callosum","hippocampus","amygdala","third ventricle","lateral ventricle","fourth ventricle","dura mater","arachnoid mater","pia mater","spinal cord","spinal nerve","dorsal root ganglion","olfactory nerve","optic nerve","oculomotor nerve","trochlear nerve","trigeminal nerve","abducens nerve","facial nerve","vestibulocochlear nerve","glossopharyngeal nerve","vagus nerve","accessory nerve","hypoglossal nerve","brachial plexus","lumbar plexus","sacral plexus","sciatic nerve","femoral nerve","median nerve","ulnar nerve","radial nerve","sympathetic trunk"],
"sensory":["eyeball","cornea","sclera","iris","lens","retina","choroid","optic nerve","ciliary body","vitreous body","lacrimal gland","lacrimal duct","external acoustic meatus","tympanic membrane","malleus","incus","stapes","cochlea","vestibule","semicircular canal","auditory tube"],
"skeletal":["skull","frontal bone","parietal bone","temporal bone","occipital bone","sphenoid bone","ethmoid bone","maxilla","mandible","zygomatic bone","nasal bone","lacrimal bone","palatine bone","vomer","inferior nasal concha","hyoid bone","sternum","manubrium","xiphoid process","sacrum","coccyx","clavicle","scapula","humerus","radius","ulna","scaphoid","lunate","triquetrum","pisiform","trapezium","trapezoid","capitate","hamate","ilium","ischium","pubis","femur","patella","tibia","fibula","talus","calcaneus","navicular","cuboid","medial cuneiform","intermediate cuneiform","lateral cuneiform","metacarpal","metatarsal","phalanges","rib","cervical vertebra","thoracic vertebra","lumbar vertebra"],
"connective":["articular cartilage","meniscus","intervertebral disc","annulus fibrosus","nucleus pulposus","joint capsule","synovial membrane","anterior cruciate ligament","posterior cruciate ligament","medial collateral ligament","lateral collateral ligament","patellar ligament","Achilles tendon","rotator cuff tendon","plantar fascia","thoracolumbar fascia","deep fascia","superficial fascia","tendon sheath","bursa","periosteum"],
"muscular":["masseter","temporalis","orbicularis oculi","orbicularis oris","buccinator","sternocleidomastoid","trapezius","deltoid","supraspinatus","infraspinatus","teres minor","subscapularis","pectoralis major","pectoralis minor","serratus anterior","latissimus dorsi","biceps brachii","triceps brachii","brachialis","brachioradialis","pronator teres","supinator","flexor carpi radialis","flexor carpi ulnaris","extensor digitorum","rectus abdominis","external oblique","internal oblique","transversus abdominis","quadratus lumborum","erector spinae","psoas major","iliacus","gluteus maximus","gluteus medius","gluteus minimus","piriformis","obturator internus","obturator externus","adductor longus","adductor brevis","adductor magnus","gracilis","sartorius","rectus femoris","vastus lateralis","vastus medialis","vastus intermedius","biceps femoris","semitendinosus","semimembranosus","gastrocnemius","soleus","tibialis anterior","tibialis posterior","fibularis longus","fibularis brevis","flexor hallucis longus","flexor digitorum longus","levator ani","coccygeus","external anal sphincter","external urethral sphincter"],
"male_reproductive":["testis","epididymis","ductus deferens","seminal vesicle","ejaculatory duct","prostate","bulbourethral gland","duct of bulbourethral gland","penis","glans penis","corpus cavernosum","corpus spongiosum","tunica albuginea","prepuce","scrotum","spermatic cord","pampiniform plexus"],
"female_reproductive":["ovary","uterine tube","fimbriae","uterus","cervix","endometrium","myometrium","vagina","vulva","mons pubis","labium majus","labium minus","clitoris","clitoral glans","clitoral body","clitoral crus","vestibular bulb","greater vestibular gland","duct of greater vestibular gland","paraurethral gland","mammary gland","lactiferous duct","broad ligament of uterus","round ligament of uterus","ovarian ligament","suspensory ligament of ovary"]
}
PAIRED=set("adrenal gland,superior nasal concha,middle nasal concha,inferior nasal concha,frontal sinus,maxillary sinus,sphenoidal sinus,ethmoidal sinus,lung,main bronchus,parotid gland,submandibular gland,sublingual gland,kidney,ureter,eyeball,cornea,sclera,iris,lens,retina,choroid,ciliary body,lacrimal gland,malleus,incus,stapes,cochlea,semicircular canal,clavicle,scapula,humerus,radius,ulna,scaphoid,lunate,triquetrum,pisiform,trapezium,trapezoid,capitate,hamate,ilium,ischium,pubis,femur,patella,tibia,fibula,talus,calcaneus,navicular,cuboid,medial cuneiform,intermediate cuneiform,lateral cuneiform,anterior cruciate ligament,posterior cruciate ligament,medial collateral ligament,lateral collateral ligament,Achilles tendon,patellar ligament,testis,epididymis,ductus deferens,seminal vesicle,ejaculatory duct,bulbourethral gland,duct of bulbourethral gland,corpus cavernosum,spermatic cord,ovary,uterine tube,labium majus,labium minus,clitoral crus,vestibular bulb,greater vestibular gland,duct of greater vestibular gland,mammary gland,round ligament of uterus,ovarian ligament,suspensory ligament of ovary".split(","))
ALIASES={"uterine tube":["fallopian tube","oviduct"],"ductus deferens":["vas deferens"],"greater vestibular gland":["bartholin gland","bartholins gland","major vestibular gland"],"duct of greater vestibular gland":["bartholin duct","duct of bartholin gland"],"bulbourethral gland":["cowper gland","cowpers gland","bulbo urethral gland"],"duct of bulbourethral gland":["cowper duct","duct of cowper gland"],"testis":["testicle"],"labium majus":["labia majora","greater labium"],"labium minus":["labia minora","lesser labium"],"fibularis longus":["peroneus longus"],"fibularis brevis":["peroneus brevis"],"thyroid gland":["thyroid"],"parathyroid gland":["parathyroid"],"pineal gland":["pineal body","pineal"],"pituitary gland":["hypophysis","pituitary"],"adrenal gland":["suprarenal gland","adrenal"],"vermiform appendix":["appendix"],"eyeball":["eye"],"external ear":["auricle","pinna"],"intervertebral disc":["intervertebral disk"],"Achilles tendon":["calcaneal tendon"],"cervix":["cervix uteri","uterine cervix"],"glans penis":["glans of penis","glans"],"clitoral glans":["glans of clitoris"],"clitoral body":["body of clitoris"],"clitoral crus":["crus of clitoris"],"vestibular bulb":["bulb of vestibule"],"paraurethral gland":["skene gland"],"mammary gland":["breast gland"]}
def norm(s):
    s=re.sub(r"^(VH_[MF]_?|Allen_?|HRA:)", "",s,flags=re.I)
    s=re.sub(r"([a-z])([A-Z])",r"\1 \2",s)
    s=re.sub(r"[^A-Za-z0-9]+"," ",s).strip().lower()
    s=re.sub(r"\b(l|left)\b","left",s);s=re.sub(r"\b(r|right)\b","right",s)
    return " ".join(s.split())
def variants(name,side):
    names=[norm(name)]+[norm(x) for x in ALIASES.get(name,[])]
    if side=="unspecified":return set(names)
    return {v for n in names for v in (side+" "+n,n+" "+side,n+" of "+side,n+" of "+side+" side")}
def load(p,sex):
    assert hashlib.sha256(p.read_bytes()).hexdigest()==PINS[sex]
    with zipfile.ZipFile(p) as z:return json.loads(z.read("inventory.json"))
def main(m,f,out):
    out.mkdir(parents=True,exist_ok=False)
    inventories={"male":load(m,"male"),"female":load(f,"female")}
    direct={};compound={}
    for sex,rows in inventories.items():
        d={};c={}
        for r in rows:
            if sex=="male":
                names=[x[1] for x in r["concepts"]];ances=[]
            else:
                names=[r["source_node"]];ances=r["hierarchy"][1:]
            for label in names:d.setdefault(norm(label),set()).add(r["id"])
            for label in ances:c.setdefault(norm(label),set()).add(r["id"])
        direct[sex]=d;compound[sex]=c
    results=[]
    for group,names in GROUPS.items():
        sexes=["male"] if group.startswith("male_") else ["female"] if group.startswith("female_") else ["male","female"]
        for name in names:
            sides=["left","right"] if name in PAIRED else ["unspecified"]
            # Four normal parathyroids are separate requirements.
            if name=="parathyroid gland":sides=["left superior","left inferior","right superior","right inferior"]
            for sex in sexes:
                for side in sides:
                    aliases=variants(name,side);match=sorted(set().union(*(direct[sex].get(x,set()) for x in aliases)))
                    anc=sorted(set().union(*(compound[sex].get(x,set()) for x in aliases)))
                    other="female" if sex=="male" else "male"
                    other_matches=sorted(set().union(*(direct[other].get(x,set()) for x in aliases)))
                    status="DIRECT_NAME_MATCH_REVIEW" if match else "COMPOUND_ANCESTOR_REVIEW" if anc else "NO_EXACT_NAME_MATCH"
                    results.append({"system":group,"structure":name,"sex":sex,"laterality":side,"status":status,"source_mesh_ids":match,"compound_descendants":anc,"other_sex_exact_candidates":other_matches,"geometry_admission":"NOT_QUALIFIED","next_action":"review exact source geometry and identity" if match or anc else "synonym/ontology search then acquire or research-model"})
    counts=Counter(r["status"] for r in results)
    summary={"requirements":len(results),"counts":dict(counts),"by_sex":{s:dict(Counter(r["status"] for r in results if r["sex"]==s)) for s in inventories},"scope":"First explicit gross/mesoscale anatomy worklist; not all FMA/UBERON concepts. Name matching deliberately conservative; no exact name match is not proof anatomy absent. Existing sources include aliases and compound meshes; human review required. No automatic opposite-sex grafting.","source_pins":PINS,"reference":"OpenStax Anatomy and Physiology 2e, 1.2 and organ-system chapters, original authored checklist; https://openstax.org/books/anatomy-and-physiology-2e/pages/1-2-structural-organization-of-the-human-body"}
    (out/"worklist.json").write_text(json.dumps({"summary":summary,"requirements":results},indent=2))
    with (out/"worklist.csv").open("w",newline="") as q:
        w=csv.DictWriter(q,fieldnames=list(results[0]));w.writeheader()
        for r in results:w.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in r.items()})
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("R224_WORKLIST",json.dumps(summary))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
