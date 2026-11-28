"""Data figure of source-measured anchors and desired targets, never a pose render."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BG = (246, 248, 251)
TEXT = (30, 42, 59)
BLUE = (36, 112, 185)
ORANGE = (216, 117, 30)


def font(size):
    try: return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError: return ImageFont.load_default(size=size)


def dashed(draw, a, b, color, width=3):
    length = math.dist(a, b)
    if length == 0: return
    for t in range(0, int(length), 12):
        u, v = t/length, min(1., (t+7)/length)
        draw.line([(a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u), (a[0]+(b[0]-a[0])*v, a[1]+(b[1]-a[1])*v)], fill=color, width=width)


def render_case(folder):
    inputs = json.loads((folder/"aquatic-inputs.json").read_text())
    image = Image.new("RGB", (1680, 1010), BG)
    draw = ImageDraw.Draw(image)
    draw.text((32, 22), "R246 · Aquatic target intent — source-measured proportions", font=font(30), fill=TEXT)
    draw.text((32, 66), inputs["morphology"]["id"]+" · barefoot · side projection · root-tracking view for swimming", font=font(20), fill=TEXT)
    for row, (activity, title) in enumerate((("swimming_front_crawl", "Front crawl: alternating pull/recovery, flutter kick and head-turn intent"),
                                              ("bathing_seated_wash", "Tub-seated chest washing: stationary seat, sole and rim targets"))):
        clip = json.loads((folder/(activity+"-clip.json")).read_text())
        period = clip["loop"]["period_s"]
        context = clip["instance"]["context"]
        top = 115+row*410
        draw.text((32, top), title, font=font(22), fill=TEXT)
        frames = [min(clip["frames"], key=lambda f: abs(f["source_time_s"]-period*p)) for p in (0., .25, .5, .75)]
        for col, frame in enumerate(frames):
            panel = Image.new("RGB", (396, 350), "white")
            pd = ImageDraw.Draw(panel)
            hip = frame["hip_center_m"]
            offset_z = hip[2] if row == 0 else 0.
            pts = [frame["body_anchors"][k][s] for k in ("hips_m", "shoulders_m") for s in ("L", "R")]
            pts += list(frame["hands_m"].values()) + [frame["body_anchors"]["head_m"]]
            pts += [frame["feet"][s][k] for s in ("L", "R") for k in ("ankle_m", "heel_m", "forefoot_m", "toe_m")]
            if row == 0:
                pts += [[0., context["surface_y_m"], offset_z-1.0], [0., context["surface_y_m"], offset_z+1.0]]
            else:
                z = context["center_xz_m"][1]
                pts += [[0., context["floor_y_m"], z-context["interior_length_m"]/2], [0., context["rim_y_m"], z+context["interior_length_m"]/2]]
            min_z, max_z = min(p[2]-offset_z for p in pts), max(p[2]-offset_z for p in pts)
            min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
            scale = min(330/(max_z-min_z+.1), 250/(max_y-min_y+.1))
            cz, cy = (min_z+max_z)/2, (min_y+max_y)/2
            project = lambda p: (198+(p[2]-offset_z-cz)*scale, 184-(p[1]-cy)*scale)
            pd.text((14, 12), f"Phase {frame['phase']:.2f} · {frame['source_time_s']:.2f} s", font=font(18), fill=TEXT)
            if row == 0:
                y = project([0., context["surface_y_m"], offset_z])[1]
                pd.rectangle((0, y, 395, 349), fill=(229, 243, 249))
                pd.line((0, y, 395, y), fill=(87, 153, 183), width=2)
                pd.text((12, 328), "Water plane; no support contact", font=font(14), fill=TEXT)
            else:
                x, z = context["center_xz_m"]
                ends = [z-context["interior_length_m"]/2, z+context["interior_length_m"]/2]
                floor = [project([x, context["floor_y_m"], zz]) for zz in ends]
                rims = [project([x, context["rim_y_m"], zz]) for zz in ends]
                pd.line([rims[0], floor[0], floor[1], rims[1]], fill=(111, 141, 159), width=6)
                seat = context["seat_center_m"]
                pd.line([project([seat[0], seat[1], seat[2]-context["seat_depth_m"]/2]), project([seat[0], seat[1], seat[2]+context["seat_depth_m"]/2])], fill=(111, 141, 159), width=8)
                pd.text((12, 328), "Tub supports are authored intent", font=font(14), fill=TEXT)
            shoulders = frame["body_anchors"]["shoulders_m"]
            center = [(shoulders["L"][i]+shoulders["R"][i])/2 for i in range(3)]
            pd.line([project(hip), project(center), project(frame["body_anchors"]["head_m"])], fill=(82, 93, 109), width=8)
            hx, hy = project(frame["body_anchors"]["head_m"])
            pd.ellipse((hx-10, hy-10, hx+10, hy+10), outline=(82, 93, 109), width=3)
            for s, color in (("L", BLUE), ("R", ORANGE)):
                foot = frame["feet"][s]
                dashed(pd, project(frame["body_anchors"]["hips_m"][s]), project(foot["ankle_m"]), color)
                dashed(pd, project(shoulders[s]), project(frame["hands_m"][s]), color)
                pd.line([project(foot[k]) for k in ("heel_m", "forefoot_m", "toe_m")], fill=color, width=4)
                for point in (frame["hands_m"][s], foot["ankle_m"], shoulders[s], frame["body_anchors"]["hips_m"][s]):
                    px, py = project(point)
                    pd.ellipse((px-4, py-4, px+4, py+4), fill=color)
            if row == 1:
                sponge = next(p for p in frame["props"] if p["id"] == "sponge")
                sx, sy = project(sponge["position_m"])
                pd.ellipse((sx-7, sy-7, sx+7, sy+7), fill=(224, 188, 42), outline=TEXT)
            # Each panel is an independent raster: no opposite-side drawing can
            # escape its own panel or overwrite its neighbor.
            image.paste(panel, (30+col*414, top+38))
    draw.text((32, 950), "Blue: left. Orange: right. Dashed lines are reach chords, not solved limb geometry.", font=font(18), fill=TEXT)
    draw.text((32, 978), "Native FK and contacts: NOT RUN here. Airway clearance, realism and physics: NOT QUALIFIED.", font=font(18), fill=TEXT)
    image.save(folder/"aquatic-target-intent.png")


if __name__ == "__main__":
    import sys
    for p in sorted(Path(sys.argv[1]).glob("*/aquatic-inputs.json")): render_case(p.parent)
