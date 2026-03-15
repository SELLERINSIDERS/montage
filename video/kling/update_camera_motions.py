#!/usr/bin/env python3
"""
Update camera motions across the Cleopatra VSL manifest.

Problem: Too many static (54%) and dolly_in (24%) shots in scenes 33-86.
Also fixes specific issues in scenes 1-32 flagged by user review.

Changes applied to: vsl/cleopatra/vsl_cleopatra_v3_video.json
Then re-run convert_manifest.py to generate the batch-compatible version.
"""

import json
import copy

MANIFEST = "vsl/cleopatra/vsl_cleopatra_v3_video.json"

# ─── ALL CAMERA UPDATES ───────────────────────────────────────────────
# Format: scene_id -> (new_camera, new_intensity, new_video_prompt)
# Only scenes that CHANGE are listed. Unlisted scenes keep their original values.

UPDATES = {
    # ══════════════════════════════════════════════════════════════════
    # SCENES 1-32: User-flagged fixes
    # ══════════════════════════════════════════════════════════════════

    "scene_03": (
        "orbit_right", 0.3,
        "Slow orbit right around the crystal. Warm torchlight shifting across "
        "the crystal surface, causing light refractions to dance and shimmer. "
        "Subtle dust particles floating through the warm light beam above the "
        "crystal. Faint golden caustic patterns moving on the dark background. "
        "Keep crystal detail stable. Cinematic realism. 5s."
    ),

    "scene_04": (
        "zoom_out", 0.4,
        "Zoom out revealing the vast Dead Sea landscape. Heat shimmer rising "
        "from ochre desert. Turquoise water shifting with mineral density. "
        "Salt formations catching golden light along the shoreline. The scale "
        "becomes breathtaking as the view widens. Cinematic realism. 5s."
    ),

    "scene_05": (
        "tilt_up", 0.3,
        "Tilt up from the crystal, revealing the hands holding it above the "
        "water. Water droplets dripping from crystal and fingertips, catching "
        "warm light. Crystal's internal refractions shifting subtly. Ripples "
        "on water surface below hands. Cinematic realism. 5s."
    ),

    "scene_06": (
        "crane_down", 0.3,
        "Crane down following the second golden crown as it descends onto her "
        "head — she already wears one crown and this one is placed on top. "
        "The priest's hands carefully lower the ornate crown. Torchlight "
        "flickering on gold surfaces. Dust motes floating in warm light beams. "
        "Her eyes steady, unwavering as the weight settles. The double crown "
        "— symbol of unified Upper and Lower Egypt. Cinematic realism. 5s."
    ),

    "scene_14": (
        "pan_right", 0.4,
        "Pan right tracking the battle clash. Blades grinding against each "
        "other, sparks flying. Both soldiers straining, muscles trembling "
        "with effort. Dust swirling between them. Sweat drops flicking off "
        "faces with exertion. Cinematic realism. 5s."
    ),

    "scene_15": (
        "pan_right", 0.3,
        "Pan right across the map table. Candlelight flickering on their "
        "faces and the map surface. Her finger tracing a route on the "
        "parchment. His eyes following her, captivated. Smoke from candles "
        "drifting upward. Clean stone floor beneath the table — no haze, "
        "no fog. Warm torchlight only. Cinematic realism. 5s."
    ),

    "scene_19": (
        "pan_left", 0.4,
        "Pan left surveying the vast crowd and green landscape from high "
        "angle. Camera glides smoothly across the scene — the crowd stands "
        "still, banners held steady. Lush palm groves and green fields "
        "surrounding the gathering. Pyramids visible in the distance. The "
        "open space stretches in all directions. Only the camera moves — "
        "the people are motionless, frozen in reverence. Epic scale, epic "
        "power. Cinematic realism. 5s."
    ),

    "scene_20": (
        "pan_right", 0.4,
        "Pan right sweeping across the fleet formation. Sails billowing in "
        "strong wind. Waves rocking ships. Sea spray catching amber light. "
        "Silhouetted figure steady against the motion. The armada stretches "
        "across the horizon. Cinematic realism. 5s."
    ),

    "scene_26": (
        "zoom_in", 0.3,
        "Slow zoom in on the crystal surface. Cold light intensifying on "
        "crystal facets. Spectral refractions shifting subtly through the "
        "translucent structure. Microscopic dust particles floating in the "
        "light beam above. The molecular beauty reveals itself as we push "
        "closer. Cinematic realism. 5s."
    ),

    "scene_27": (
        "tilt_up", 0.3,
        "Tilt up from deep underwater toward the surface. Light rays piercing "
        "through mineral-dense water, shifting and refracting. Salt crystal "
        "formations swaying in mineral currents. Particles suspended in "
        "dense water. The camera rises toward the shimmering surface. "
        "Cinematic realism. 5s."
    ),

    "scene_30": (
        "tilt_down", 0.2,
        "Tilt down into the dark earth. Hands turning soil, fingers pressing "
        "into rich ground. Mineral flecks catching sunlight as soil is "
        "disturbed. Small earthworm moving in freshly turned earth. Warm "
        "light on hands. The camera descends into the earth's richness. "
        "Cinematic realism. 5s."
    ),

    # ══════════════════════════════════════════════════════════════════
    # SCENES 33-86: Camera diversification
    # ══════════════════════════════════════════════════════════════════

    # Scene 33: crane_up KEEP (revealing devastation — good)
    # Scene 34: dolly_in KEEP (POV inside pipe — narratively perfect)
    # Scene 35: pan_right KEEP (following conveyor belt)

    "scene_36": (
        "zoom_out", 0.3,
        "Slow zoom out from Earth in space, revealing the planet against "
        "the cosmic void. The planet rotates slowly — day/night terminator "
        "line moving. City lights appearing on the dark side. Clouds "
        "swirling in time-lapse. The thin atmosphere glowing. Time is "
        "passing at cosmic speed. Cinematic realism. 5s."
    ),

    "scene_37": (
        "tilt_down", 0.3,
        "Tilt down into the dried ancient mineral spring basin. Cracked "
        "stone visible, dried mineral deposits on walls. The empty trickle "
        "mark where water used to flow. Cold wind blowing dust across the "
        "dry basin. Dead Sea visible faintly in background. "
        "Cinematic realism. 5s."
    ),

    # Scene 38: pan_right KEEP (tracking crowd)

    "scene_39": (
        "zoom_in", 0.3,
        "Slow zoom in on the person at the desk. Pressing harder on temples. "
        "Screen light shifting. A tired exhale visible in the cold room. "
        "Shoulder muscles visibly tight. The closer we get, the more "
        "the exhaustion shows. Cinematic realism. 5s."
    ),

    "scene_40": (
        "tilt_up", 0.4,
        "Tilt up following the sequential body activation. Body systems "
        "activate from bottom to top — first muscles glow red, then "
        "nervous system lights up blue, then heart pulses golden, then "
        "bones illuminate white, then brain glows amber. Each zone "
        "activating one after another as the camera rises. All lit up "
        "simultaneously by end. Dark background. Cinematic realism. 5s."
    ),

    "scene_41": (
        "crane_down", 0.3,
        "Crane down descending toward person shifting restlessly in bed — "
        "the ghostly long-exposure effect showing multiple positions "
        "simultaneously. Sheets tangling further. Cold moonlight shifting. "
        "The surreal quality of a body that cannot find rest. The weight "
        "of the descending camera mirrors the weight of sleeplessness. "
        "Cinematic realism. 5s."
    ),

    # Scene 42: dolly_in KEEP (racing through nerves)

    "scene_43": (
        "tilt_down", 0.2,
        "Tilt down examining anatomical muscle tissue close-up. Fibers "
        "twitching slightly, pulsing with tension — contracted and unable "
        "to release. The knotted bundles shifting subtly under stress. "
        "Warm sidelight catching the red muscle surface. "
        "Cinematic realism. 5s."
    ),

    "scene_44": (
        "zoom_in", 0.3,
        "Zoom in through dark neural pathway. The golden spark flickers, "
        "dims, stutters forward — then dies completely before reaching "
        "the synapse junction. Faint blue bioluminescent traces pulse "
        "weakly along dendrites. Total darkness swallows where the signal "
        "should have connected. The void deepens. Cinematic realism. 5s."
    ),

    "scene_45": (
        "orbit_left", 0.2,
        "Slow orbit left around the tightly wound steel spring. The spring "
        "vibrates almost imperceptibly — a barely visible tremor in the "
        "coils. Cold blue light shifts subtly across the polished metal "
        "surface. The spring hums with trapped energy, unable to release. "
        "The tension is palpable from every angle. Cinematic realism. 5s."
    ),

    # Scene 46: static KEEP (2 AM stillness IS the scene)
    # Scene 47: static KEEP (surreal wave motion is the subject)

    "scene_48": (
        "pan_left", 0.3,
        "Pan left across the living room chaos. Kids moving in the "
        "background — toddler running past, older kid climbing furniture. "
        "Mother on couch, eyes closed, trying to rest. She opens her eyes "
        "wearily. Living room chaos continues around her. "
        "Keep subject identity stable. Cinematic realism. 5s."
    ),

    "scene_49": (
        "crane_down", 0.2,
        "Crane down descending toward the empty, chaotic bed in cold "
        "morning light. A sheet edge shifts slightly from a breeze through "
        "an open window. The pillow impression slowly — almost "
        "imperceptibly — rebounds, erasing the last trace of the person "
        "who was here. Cold grey light intensifies as morning grows. "
        "The bed remains empty. The night was lost. Cinematic realism. 5s."
    ),

    # Scene 50: dolly_in KEEP (approaching mirror — perfect)
    # Scene 51: pan_right KEEP (cold to warm transition)
    # Scene 52: dolly_out KEEP (revealing landscape)

    "scene_53": (
        "zoom_out", 0.3,
        "Zoom out slowly pulling higher from bird's-eye view of Cleopatra "
        "floating in the mineral bath. Her dark hair drifting slowly in "
        "the turquoise water. Mineral particles catching golden light. "
        "Her body completely still, weightless, peaceful. Water gently "
        "rippling around her. Keep subject identity stable. "
        "Cinematic realism. 5s."
    ),

    "scene_54": (
        "tilt_down", 0.2,
        "Tilt down toward kitchen counter from above. Coffee steam rising "
        "gently from the mug. Morning light shifting subtly. The tiny "
        "supplement bottle sits untouched among the clutter. A phone "
        "screen briefly illuminates then dims. The mundane stillness of "
        "inadequacy. Keep composition stable. Cinematic realism. 5s."
    ),

    "scene_55": (
        "pan_right", 0.3,
        "Pan right across the mineral shoreline of the Dead Sea. The "
        "vast turquoise expanse stretching to mountains reveals itself. "
        "Golden hour light shifts — long shadows stretching across salt "
        "formations. Mineral deposits catching light as the camera "
        "sweeps along the shore. Cinematic realism. 5s."
    ),

    # Scene 56: dolly_in KEEP (approaching product bottle)
    # Scene 57: pan_left KEEP (ancient landscape sunset)

    "scene_58": (
        "zoom_in", 0.2,
        "Slow zoom in on hands carefully lowering the product bottle into "
        "a shipping box. Gentle, deliberate placement. Tissue paper "
        "crinkling softly. Warm warehouse light. The care in every "
        "movement communicates 'this matters.' Authentic, warm "
        "fulfillment moment. Cinematic realism. 5s."
    ),

    "scene_59": (
        "tilt_up", 0.3,
        "Tilt up following the magnesium particles as they rise through "
        "the intestinal absorption scene. Golden particles drifting "
        "upward and being absorbed by villi — each one lighting up golden "
        "on contact. Blood vessels below carrying golden particles into "
        "circulation. Warm, welcoming, the body accepting the chelated "
        "form. Bio-cinematic beauty. Cinematic realism. 5s."
    ),

    # Scene 60: static KEEP (casual capsule moment)

    "scene_61": (
        "dolly_in", 0.2,
        "Gentle dolly in toward the macro shot. White capsule shell "
        "splitting open in warm water. Pinkish-white contents swirling "
        "outward in beautiful organic patterns. Warm backlight glowing "
        "through the glass. Pale pink dissolution spreading like ink in "
        "water. Cinematic realism. 5s."
    ),

    "scene_62": (
        "crane_up", 0.3,
        "Crane up rising above the woman walking through saffron fields. "
        "Purple flowers swaying at waist height, her hand brushing them "
        "gently as she passes. Golden hour light shifting. Mountains in "
        "distance revealing as camera ascends. No baskets, just a casual "
        "walk through beauty. Cinematic realism. 5s."
    ),

    # Scene 63: pan_right KEEP (tea plantation)
    # Scene 64: static KEEP (scientist precision)

    "scene_65": (
        "pan_left", 0.2,
        "Slow pan left across the kitchen counter. Woman taking capsule "
        "and sipping water from a glass. Natural swallowing motion, "
        "genuine expression — slight smile afterward. Product bottle "
        "visible on counter. Morning light shifting through kitchen "
        "window. Authentic, warm, relatable moment. "
        "Keep subject identity stable. Cinematic realism. 5s."
    ),

    # Scene 66: static KEEP (product foreground anchor)
    # Scene 67: static KEEP (calm/reading = stillness)

    "scene_68": (
        "pan_right", 0.4,
        "Pan right tracking the woman as she runs along the sunlit nature "
        "path. Hair flowing, stride confident and easy. Morning sunlight "
        "streaming through trees, golden light rays shifting. Leaves "
        "rustling. She's alive, sharp, energized — the opposite of "
        "groggy. Nature in motion around her. Cinematic realism. 5s."
    ),

    # Scene 69: static KEEP (still lake = stillness metaphor)
    # Scene 70: static KEEP (candle extinguishing — intimate)

    "scene_71": (
        "zoom_in", 0.2,
        "Slow zoom in on bio-cinematic shot. Warm golden glow slowly "
        "SPREADING through the muscle fibers — where it touches, fibers "
        "visibly soften and relax. The unclenching happens in a wave. "
        "Tiny capillaries pulsing gently. The tension dissolves as golden "
        "warmth flows through the tissue. Beautiful, warm, the body "
        "releasing. Cinematic realism. 5s."
    ),

    # Scene 72: static KEEP (sleeping face — sleep = stillness)

    "scene_73": (
        "tilt_up", 0.3,
        "Tilt up following as woman stretches luxuriously in bed and "
        "rises. Morning golden light. Genuine smile spreading across "
        "her face. She opens her eyes — clear and bright. Sits up "
        "slowly, unhurried, with the ease of someone truly rested. "
        "Sunlight catches her hair, skin glowing warm. "
        "Cinematic realism. 5s."
    ),

    "scene_74": (
        "pan_left", 0.2,
        "Pan left at bird's eye view across the dinner table. Candle "
        "flames gently swaying — warm light shifting on the wood surface. "
        "Steam from the meal barely visible. The book pages flutter "
        "imperceptibly. Everything warm, unhurried, complete. The evening "
        "routine playing out through its objects. Cinematic realism. 5s."
    ),

    # Scene 75: dolly_out KEEP (epic Cleopatra reveal)

    "scene_76": (
        "zoom_in", 0.2,
        "Slow zoom in from high angle. Person shifting positions in bed, "
        "pulling sheets tighter then pushing them away. Phone dark on "
        "nightstand. Clock reads 3:17. Cold blue light unforgiving. "
        "The body cannot find rest, tossing restlessly. "
        "Keep subject identity stable. Cinematic realism. 5s."
    ),

    # Scene 77: static KEEP (river flowing — flow IS the motion)

    "scene_78": (
        "orbit_right", 0.3,
        "Orbit right around the molecular lattice as it assembles. Golden "
        "atoms drift together and SNAP into place — each new bond sparking "
        "with warm light. Energy arcs pulse through completed connections. "
        "The lattice grows, building outward as more atoms join. Golden "
        "particles gravitate inward from the surrounding void. Chemistry "
        "in action — beautiful, precise, alive. Cinematic realism. 5s."
    ),

    # Scene 79: dolly_in KEEP (approaching product)

    "scene_80": (
        "tilt_down", 0.2,
        "Tilt down revealing the bottle on Dead Sea shore rocks below. "
        "Golden hour light warming the product label. Turquoise water "
        "lapping gently at the rocks in background. Sunset colors "
        "shifting. The product is clearly visible and recognizable — "
        "warm, inviting, premium. Cinematic realism. 5s."
    ),

    "scene_81": (
        "pan_left", 0.2,
        "Slow pan left across the night sky. The moons in the arc glow "
        "and pulse subtly — each phase illuminating in sequence, showing "
        "time passing. Stars twinkling. The warm golden window light in "
        "the distant home flickers gently. The landscape is still, "
        "peaceful. Time passes beautifully, patiently. 90 nights of "
        "cosmic patience. Cinematic realism. 5s."
    ),

    "scene_82": (
        "zoom_in", 0.2,
        "Slow zoom in on woman's genuine smile. She touches her face in "
        "mild amazement — the smile of someone who feels better than "
        "expected. Morning light warm on her features. Eyes bright, "
        "expression unforced. The authentic surprise of feeling the "
        "difference. Cinematic realism. 5s."
    ),

    # Scene 83: static KEEP ("nothing needs to move" — deliberate)

    "scene_84": (
        "crane_up", 0.2,
        "Crane up gently rising to reveal the wide evening scene. Woman "
        "turns page, dog stretches on rug, through doorway a kettle "
        "steam rises. Candle flames sway gently. Dusk light deepens "
        "outside. Life as it should be — evening restoring, not draining. "
        "Everything moves slowly, peacefully, in its own rhythm. "
        "Cinematic realism. 5s."
    ),

    # Scene 85: orbit_right KEEP (grand final Cleopatra reveal)
    # Scene 86: zoom_in KEEP (end card product hero)
}


def apply_updates():
    with open(MANIFEST) as f:
        data = json.load(f)

    original = copy.deepcopy(data)
    changed = []

    for scene in data["scenes"]:
        sid = scene["scene_id"]
        if sid in UPDATES:
            new_camera, new_intensity, new_prompt = UPDATES[sid]
            old_camera = scene["camera"]
            scene["camera"] = new_camera
            scene["intensity"] = new_intensity
            scene["video_prompt"] = new_prompt
            changed.append((sid, old_camera, new_camera, new_intensity))

    with open(MANIFEST, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Report
    print(f"Updated {len(changed)} scenes in {MANIFEST}")
    print()
    print(f"{'Scene':<12} {'Old Camera':<14} {'New Camera':<14} {'Intensity'}")
    print("-" * 55)
    for sid, old, new, intensity in changed:
        num = sid.replace("scene_", "")
        print(f"  {num:<10} {old:<14} {new:<14} {intensity}")

    # Distribution report
    print()
    print("NEW FULL DISTRIBUTION (all 88 scenes):")
    cam_counts = {}
    for s in data["scenes"]:
        cam_counts[s["camera"]] = cam_counts.get(s["camera"], 0) + 1
    total = sum(cam_counts.values())
    for cam, count in sorted(cam_counts.items(), key=lambda x: -x[1]):
        print(f"  {cam:<15} {count:>3} ({count/total*100:.0f}%)")

    # Scenes that need regeneration (1-32 only — these have existing clips)
    regen_1_32 = [sid for sid, _, _, _ in changed
                  if int(sid.replace("scene_", "")) <= 32]
    if regen_1_32:
        print()
        print(f"Scenes 1-32 needing clip regeneration ({len(regen_1_32)}):")
        for sid in regen_1_32:
            print(f"  {sid}")


if __name__ == "__main__":
    apply_updates()
