"""Bounded evaluated-geometry kinematic fitting. No force/dynamics inference.

The original authored inputs, every root/ankle displacement and both the initial
and final contact residuals are retained. No source vertex/rest/weight is edited.
"""
import copy,hashlib
from pathlib import Path
import numpy as np
import baseline_choreography

BASELINE_SHA="acbbf10c99c05f5797a918e1f1861b683eed2416d395d48a6079dbb996f38cc4"
assert hashlib.sha256(Path(baseline_choreography.__file__).read_bytes()).hexdigest()==BASELINE_SHA

AFFECTED={"slip_fall","trip_fall","backward_fall","cartwheel","judo_partner_throw","wrestling_partner_takedown","push_up"}
FLOOR=.002
ITERATIONS=12
ROOT_BUDGET=.30
FOOT_BUDGET=.18
PALM_HEIGHT_BUDGET=.06

def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value

def evaluate(actors,frames,record=False):
    for a,f in zip(actors,frames):a.stage(f)
    anchors=[a.anchors() for a in actors]
    rows=[a.arms(anchors[1-i] if len(actors)==2 else None,record=False) for i,a in enumerate(actors)]
    if len(actors)==2:
        # Re-resolve actual partner vertices after both actors' arm poses;
        # shoulder skin vertices can have arm influences.
        anchors=[a.anchors() for a in actors]
        rows=[a.arms(anchors[1-i],record=record) for i,a in enumerate(actors)]
    elif record:rows=[actors[0].arms(record=True)]
    if len(actors)==2:
        final_anchors=[a.anchors() for a in actors]
        for i,row in enumerate(rows):
            for c in row["contacts"]:
                if c["kind"]=="partner_source_surface_intent":
                    key=c["partner_anchor"];c["solved_target_m"]=c["point_m"]
                    c["point_m"]=final_anchors[1-i][key];c["partner_actor"]=actors[1-i].id;c["partner_source_vertex_id"]=actors[1-i].anchor_ids[key]
                    c["distance_m"]=float(np.linalg.norm(np.array(c["actual_point_m"])-c["point_m"]))
    return rows

def fit(actors,frames,activity):
    original=copy.deepcopy(frames);frames=copy.deepcopy(frames)
    baseline=[baseline_choreography.sample(a.meta,activity,f["time_s"],i) for i,(a,f) in enumerate(zip(actors,frames))]
    initial=evaluate(actors,frames);rows=initial;steps=[]
    if activity in AFFECTED:
        for iteration in range(ITERATIONS):
            changes=[]
            for i,(actor,frame,row) in enumerate(zip(actors,frames,rows)):
                root=np.zeros(3);foot={s:0. for s in ("L","R")};hand={s:0. for s in ("L","R")};reasons=[]
                palms=[c for c in row["contacts"] if c["kind"] in ("ground_support_intent","partner_source_surface_intent") and "distance_m" in c]
                if palms:
                    residuals=[np.array(c["point_m"])-c["actual_point_m"] for c in palms]
                    active=[v for v in residuals if np.linalg.norm(v)>.0005]
                    if active:
                        root+=np.mean(active,axis=0)*.85;reasons.append("actual_source_palm_target_residual")
                planted_ankle_residuals=[frame["feet"][s]-row["actual_ankles_m"][s] for s in ("L","R") if frame["stance"][s] and row["target_errors_m"]["ankle."+s]>.001]
                if planted_ankle_residuals:
                    root+=np.mean(planted_ankle_residuals,axis=0)*.85;reasons.append("actual_planted_ankle_target_residual")
                # First repair penetrating stance-foot skin by moving its IK
                # target vertically, retaining world X/Z and source geometry.
                for c in row["contacts"]:
                    if c["actor_part"].startswith("foot.") and c["actual_min_y_m"]<FLOOR:
                        s=c["actor_part"][-1];foot[s]=min(.05,FLOOR-c["actual_min_y_m"]);reasons.append("evaluated_stance_foot_plane_"+s)
                    if c["actor_part"].startswith("palm.") and c["kind"]=="ground_support_intent" and c["actual_hand_skin_min_y_m"]<FLOOR:
                        s=c["actor_part"][-1];frame.setdefault("palm_height_offsets_m",{});previous=frame["palm_height_offsets_m"].get(s,0.)
                        hand[s]=min(.04,FLOOR-c["actual_hand_skin_min_y_m"],max(0.,PALM_HEIGHT_BUDGET-previous))
                        frame["palm_height_offsets_m"][s]=previous+hand[s];reasons.append("evaluated_whole_hand_patch_plane_"+s)
                # When the lowest geometry is not an adjusted stance foot,
                # project the authored actor root upward. Airborne limbs move
                # with that root; planted source foot targets stay fixed.
                # Micrometre-sized patch updates must not suppress a larger
                # head/torso floor correction or trigger premature convergence.
                if row["whole_skin_min_y_m"]<FLOOR and max([*foot.values(),*hand.values()])<.0001:
                    root[1]=max(root[1],min(.08,FLOOR-row["whole_skin_min_y_m"]));reasons.append("evaluated_whole_skin_floor")
                length=np.linalg.norm(root)
                if length>.06:root*=.06/length
                total=frame["hip"]+root-original[i]["hip"]
                if np.linalg.norm(total)>ROOT_BUDGET:
                    total*=ROOT_BUDGET/np.linalg.norm(total);root=original[i]["hip"]+total-frame["hip"]
                frame["hip"]+=root
                for s in ("L","R"):
                    if not frame["stance"][s]:frame["feet"][s]+=root
                    previous=frame["feet"][s][1]-original[i]["feet"][s][1]
                    foot[s]=max(0.,min(foot[s],FOOT_BUDGET-max(0.,previous)))
                    frame["feet"][s][1]+=foot[s]
                changes.append({"actor":actor.id,"root_displacement_m":root.tolist(),"stance_ankle_y_displacement_m":foot,"palm_proxy_height_change_m":hand,"reasons":reasons})
            steps.append({"iteration":iteration,"changes":changes})
            if max(np.linalg.norm(c["root_displacement_m"])+sum(c["stance_ankle_y_displacement_m"].values())+sum(c["palm_proxy_height_change_m"].values()) for c in changes)<.00002:break
            rows=evaluate(actors,frames)
    final=evaluate(actors,frames,record=True)
    records=[]
    for i,(actor,row) in enumerate(zip(actors,final)):
        record={"schema":"oneirifact.evaluated-geometry-kinematic-fit/v1","activity":activity,"time_s":frames[i]["time_s"],"actor":actor.id,
            "status":"BOUNDED_KINEMATIC_FIT_APPLIED" if activity in AFFECTED else "UNCHANGED_AUTHORED_INPUT",
            "baseline_authored_target":plain(baseline[i]),"baseline_choreography_sha256":BASELINE_SHA,"corrected_authored_target":plain(original[i]),"fitted_target":plain(frames[i]),"initial_observed_current_prefit":initial[i],"final_observed":row,
            "root_displacement_m":(frames[i]["hip"]-original[i]["hip"]).tolist(),
            "root_displacement_from_public_baseline_m":(frames[i]["hip"]-baseline[i]["hip"]).tolist(),
            "ankle_target_displacement_m":{s:(frames[i]["feet"][s]-original[i]["feet"][s]).tolist() for s in ("L","R")},
            "ankle_target_displacement_from_public_baseline_m":{s:(frames[i]["feet"][s]-baseline[i]["feet"][s]).tolist() for s in ("L","R")},
            "palm_proxy_height_offsets_m":frames[i].get("palm_height_offsets_m",{}),"palm_height_budget_m":PALM_HEIGHT_BUDGET,
            "steps":steps,"floor_clearance_target_m":FLOOR,"root_displacement_budget_m":ROOT_BUDGET,"stance_ankle_y_budget_m":FOOT_BUDGET,
            "iteration_budget":ITERATIONS,
            "physics":"NOT_SIMULATED","acceptance":"Residuals, introduced lift/slide and visual plausibility remain separately evaluated."}
        row["kinematic_fit"]={k:record[k] for k in ("status","root_displacement_m","ankle_target_displacement_m")};records.append(record)
    return records

def contact_episodes(rows):
    """Report lift/slide proxies without treating proximity as force/contact."""
    episodes=[]
    for side in ("L","R"):
        current=[]
        def finish():
            if not current:return
            first=current[0][1];region=min(first["source_contact_points"],key=lambda k:first["source_contact_points"][k]["point_m"][1])
            pts=np.array([r["source_contact_points"][region]["point_m"] for _,r in current]);origin=pts[0]
            episodes.append({"side":side,"start_s":current[0][0],"end_s":current[-1][0],"observations":len(current),"source_region_selected_at_episode_start":region,
                "source_vertex_id":first["source_contact_points"][region]["vertex_id"],"max_horizontal_drift_m":float(np.linalg.norm(pts[:,[0,2]]-origin[[0,2]],axis=1).max()),
                "min_height_m":float(pts[:,1].min()),"max_height_m":float(pts[:,1].max()),"status":"GEOMETRIC_SOURCE_VERTEX_PROXY_NOT_CONTACT_ACCEPTANCE"})
        for row in rows:
            c=next((c for c in row["contacts"] if c["actor_part"]=="foot."+side),None)
            if c:current.append((row["time_s"],c))
            else:finish();current=[]
        finish()
    return episodes
