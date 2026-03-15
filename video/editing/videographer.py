#!/usr/bin/env python3
"""
Videographer Agent v2 — Produces a COMPLETE rendering specification (EDL) for Remotion.

The EDL is a machine-readable JSON with exact pixel positions, dimensions, colors,
font sizes, spring animation configs, and frame-accurate timing for every visual element.
Remotion components read these values directly — nothing is hardcoded.

Skill reference: .claude/commands/video-editor.md

Usage:
  python3 videographer.py <script.json> <captions.json> [output_edl.json]
"""
import json
import math
import sys
from pathlib import Path


# ── Canvas Constants (9:16 vertical) ──
CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30

# ── Grade Colors ──
GRADE_COLORS = {
    "A+": "#39E508",
    "A": "#5BEF2A",
    "B+": "#90EE90",
    "B": "#FFD700",
    "C+": "#FFA07A",
    "C": "#FF6B6B",
    "D": "#FF4444",
}


def find_word_timestamp(captions, phrase, after_ms=0):
    """Find the start timestamp when a phrase begins in the captions."""
    phrase_words = phrase.lower().split()
    if not phrase_words:
        return None
    for i, cap in enumerate(captions):
        if cap["startMs"] < after_ms:
            continue
        cap_word = cap["text"].strip().lower().rstrip(".,!?;:'\"")
        target = phrase_words[0].rstrip(".,!?;:'\"")
        if target in cap_word or cap_word in target:
            if len(phrase_words) == 1:
                return cap["startMs"]
            match = True
            for j, pw in enumerate(phrase_words[1:], 1):
                if i + j >= len(captions):
                    match = False
                    break
                next_word = captions[i + j]["text"].strip().lower().rstrip(".,!?;:'\"")
                pw_clean = pw.rstrip(".,!?;:'\"")
                if pw_clean not in next_word and next_word not in pw_clean:
                    match = False
                    break
            if match:
                return cap["startMs"]
    return None


def find_word_end_timestamp(captions, word, after_ms=0):
    """Find the end timestamp of a specific word."""
    target = word.lower().rstrip(".,!?;:'\"")
    for cap in captions:
        if cap["startMs"] < after_ms:
            continue
        cap_word = cap["text"].strip().lower().rstrip(".,!?;:'\"")
        if target in cap_word or cap_word in target:
            return cap["endMs"]
    return None


def ms_to_frame(ms):
    return round(ms / 1000 * FPS)


def find_emotional_beats(spoken_text, start_ms, captions):
    """Find words/phrases in the spoken text that deserve tight framing."""
    emphasis_phrases = [
        "flushing", "money", "drain", "red flag", "warning",
        "game changer", "winner", "best", "worst", "number one",
        "secret", "truth", "problem", "mistake", "interesting",
        "surprising", "actually", "here's", "listen", "watch",
        "important", "clinical", "proven", "studies", "research",
        "cheap", "garbage", "avoid", "skip", "don't",
    ]
    beats = []
    for phrase in emphasis_phrases:
        ts = find_word_timestamp(captions, phrase, after_ms=max(0, start_ms - 200))
        if ts is not None and ts >= start_ms:
            beats.append({"ms": ts, "frame": ms_to_frame(ts), "word": phrase})
    return beats


def plan_jump_cuts(segment_timings, captions):
    """Plan content-driven jump cuts with varied framing."""
    cuts = []
    last_cut_frame = -999

    # Scale/origin presets for variety
    tight_presets = [
        (1.35, "center 30%"),
        (1.4, "center 28%"),
        (1.35, "30% 32%"),
        (1.4, "70% 30%"),
    ]
    medium_presets = [
        (1.15, "center 38%"),
        (1.2, "center 36%"),
        (1.2, "65% 36%"),
        (1.15, "35% 38%"),
    ]
    wide_presets = [
        (1.0, "center 40%"),
        (1.0, "center 42%"),
        (1.05, "center 40%"),
    ]
    extra_tight_presets = [
        (1.5, "center 28%"),
        (1.55, "center 26%"),
        (1.5, "40% 28%"),
    ]

    tight_idx = 0
    medium_idx = 0
    wide_idx = 0
    extra_tight_idx = 0

    def next_tight():
        nonlocal tight_idx
        p = tight_presets[tight_idx % len(tight_presets)]
        tight_idx += 1
        return p

    def next_medium():
        nonlocal medium_idx
        p = medium_presets[medium_idx % len(medium_presets)]
        medium_idx += 1
        return p

    def next_wide():
        nonlocal wide_idx
        p = wide_presets[wide_idx % len(wide_presets)]
        wide_idx += 1
        return p

    def next_extra_tight():
        nonlocal extra_tight_idx
        p = extra_tight_presets[extra_tight_idx % len(extra_tight_presets)]
        extra_tight_idx += 1
        return p

    def add_cut(frame, scale, origin, reason):
        nonlocal last_cut_frame
        if frame <= last_cut_frame:
            frame = last_cut_frame + 1
        cuts.append({
            "frame": frame,
            "scale": scale,
            "transform_origin": origin,
            "reason": reason,
        })
        last_cut_frame = frame

    for i, seg in enumerate(segment_timings):
        seg_type = seg.get("type", "")
        seg_id = seg.get("id", "")
        sf = seg["start_frame"]
        ef = seg["end_frame"]
        spoken = seg.get("spoken_text", "")

        if seg_type == "hook" and seg_id == "hook_1":
            # Opening hook — TIGHT to grab attention
            s, o = next_tight()
            add_cut(sf, s, o, f"TIGHT — opening hook '{spoken[:30]}...'")

            # After ~1.5 seconds, go wide for hook text overlay
            mid = sf + ms_to_frame(1500)
            if mid < ef:
                s, o = next_wide()
                add_cut(mid, s, o, "WIDE — hook title card needs space")

        elif seg_type == "product_review":
            rank = seg.get("rank", 0)
            product = seg.get("product", "")

            # Product reveal — WIDE for card overlay
            s, o = next_wide()
            add_cut(sf, s, o, f"WIDE — product #{rank} reveal ({product})")

            # Find emotional beats within this segment
            beats = find_emotional_beats(spoken, seg.get("start_ms", 0), captions)

            # Add tight cuts on emotional beats (max 2 per segment)
            beat_count = 0
            for beat in beats:
                if beat["frame"] > sf + 30 and beat["frame"] < ef - 30:
                    if beat["frame"] - last_cut_frame >= 45:  # At least 1.5s gap
                        s, o = next_tight()
                        add_cut(beat["frame"], s, o,
                                f"TIGHT — emphasis on '{beat['word']}' in #{rank}")
                        beat_count += 1
                        if beat_count >= 2:
                            break

            # If segment is long (>5s) and we haven't cut mid-segment, add a medium cut
            seg_duration_frames = ef - sf
            if seg_duration_frames > 150 and beat_count == 0:
                mid_frame = sf + seg_duration_frames // 2
                if mid_frame - last_cut_frame >= 45:
                    s, o = next_medium()
                    add_cut(mid_frame, s, o,
                            f"MEDIUM — pacing cut mid-segment #{rank}")

            # For winner (#1), use extra tight at the climax
            if rank == 1:
                climax = sf + ms_to_frame(2000)
                if climax < ef and climax - last_cut_frame >= 30:
                    s, o = next_extra_tight()
                    add_cut(climax, s, o,
                            f"EXTRA TIGHT — winner reveal emphasis #{rank}")

        elif seg_type == "hook" and seg_id == "hook_2":
            # Re-engagement — EXTRA TIGHT pattern break
            s, o = next_extra_tight()
            add_cut(sf, s, o, "EXTRA TIGHT — re-engagement hook, pattern break")

        elif seg_type == "cta":
            # CTA — MEDIUM, let the text do the work
            s, o = next_medium()
            add_cut(sf, s, o, "MEDIUM — CTA, text overlay takes focus")

    # Ensure minimum density: fill gaps >5s with a cut
    filled_cuts = list(cuts)
    for j in range(len(cuts) - 1):
        gap = cuts[j + 1]["frame"] - cuts[j]["frame"]
        if gap > 150:  # >5s at 30fps
            mid = cuts[j]["frame"] + gap // 2
            s, o = next_medium()
            filled_cuts.append({
                "frame": mid,
                "scale": s,
                "transform_origin": o,
                "reason": "MEDIUM — pacing fill (gap > 5s)",
            })

    filled_cuts.sort(key=lambda c: c["frame"])
    return filled_cuts


def build_product_card_layer(seg, seg_index):
    """Build a complete product card layer specification."""
    rank = seg.get("rank", 0)
    grade = seg.get("grade", "")
    product = seg.get("product", "")
    product_image = seg.get("product_image", "")
    grade_color = GRADE_COLORS.get(grade, "#FFFFFF")
    is_winner = grade == "A+" or rank == 1

    # Convert avif to png for Remotion
    if product_image and product_image.endswith(".avif"):
        product_image = product_image.replace(".avif", ".png")

    # Card dimensions — ~65% of frame width, centered
    card_width = 700
    card_x = (CANVAS_W - card_width) // 2  # 190px from left
    card_y = 160

    layer = {
        "id": f"product_card_rank{rank}",
        "type": "product_card",
        "from_frame": seg["start_frame"],
        "to_frame": seg["end_frame"],
        "z_index": 10 + seg_index,

        "layout": {
            "x": card_x,
            "y": card_y,
            "width": card_width,
            "height": "auto",
            "border_radius": 28,
            "background": "rgba(0, 0, 0, 0.6)",
            "padding": {"top": 24, "right": 40, "bottom": 32, "left": 40},
        },

        "content": {
            "rank": {
                "text": f"#{rank}",
                "font_size": 44,
                "color": "#999999",
                "font_family": "TheBoldFont",
                "letter_spacing": 4,
                "text_transform": "uppercase",
            },
            "product_image": {
                "src": f"products/{product_image}" if product_image else None,
                "width": 320,
                "height": 320,
                "border_radius": 20,
                "border": f"3px solid {grade_color}44",
                "background": "#1A1A1A",
                "object_fit": "contain",
            },
            "product_name": {
                "text": product,
                "font_size": 36,
                "color": "#FFFFFF",
                "font_family": "TheBoldFont",
                "text_align": "center",
                "max_width": 620,
            },
            "grade_badge": {
                "text": grade,
                "font_size": 72,
                "color": grade_color,
                "font_family": "TheBoldFont",
                "glow": f"0 0 30px {grade_color}66, 0 0 60px {grade_color}33",
                "line_height": 1,
            },
        },

        "enter_animation": {
            "property": "transform+opacity",
            "from": {"translateY": -80, "scale": 0.85, "opacity": 0},
            "to": {"translateY": 0, "scale": 1.0, "opacity": 1},
            "spring": {"damping": 14, "stiffness": 200},
            "duration_frames": 15,
        },

        "exit_animation": {
            "property": "transform+opacity",
            "from": {"scale": 1.0, "opacity": 1},
            "to": {"scale": 0.3, "opacity": 0},
            "spring": {"damping": 20, "stiffness": 180},
            "duration_frames": 10,
            "offset_from_end": 10,
        },

        "winner_pulse": {
            "enabled": is_winner,
            "amplitude": 0.05,
            "frequency": 0.15,
            "glow_intensity": 1.5,
        } if is_winner else None,
    }

    return layer


def build_hook_layer(seg, hook_type):
    """Build a hook/title card layer."""
    if hook_type == "hook_1":
        return {
            "id": "hook_1_title",
            "type": "title_card",
            "from_frame": seg["start_frame"],
            "to_frame": seg["end_frame"],
            "z_index": 10,

            "layout": {
                "x": "center",
                "y": 300,
                "width": 900,
                "height": "auto",
                "border_radius": 28,
                "background": "rgba(0, 0, 0, 0.6)",
                "padding": {"top": 28, "right": 48, "bottom": 28, "left": 48},
            },

            "content": {
                "title": {
                    "text": "TOP 5 MAGNESIUM FOR SLEEP",
                    "font_size": 72,
                    "color": "#FFFFFF",
                    "font_family": "TheBoldFont",
                    "text_transform": "uppercase",
                    "stroke": "3px black",
                    "line_height": 1.1,
                    "max_width": 800,
                    "text_align": "center",
                },
                "subtext": {
                    "text": "RANKED",
                    "font_size": 48,
                    "color": "#39E508",
                    "font_family": "TheBoldFont",
                    "text_transform": "uppercase",
                    "letter_spacing": 8,
                },
            },

            "enter_animation": {
                "property": "transform+opacity",
                "from": {"scale": 0.7, "opacity": 0},
                "to": {"scale": 1.0, "opacity": 1},
                "spring": {"damping": 12, "stiffness": 180},
                "duration_frames": 12,
            },

            "exit_animation": {
                "property": "transform+opacity",
                "from": {"scale": 1.0, "opacity": 1},
                "to": {"scale": 0.8, "opacity": 0},
                "spring": {"damping": 20, "stiffness": 200},
                "duration_frames": 8,
                "offset_from_end": 8,
            },

            "winner_pulse": None,
        }

    elif hook_type == "hook_2":
        return {
            "id": "hook_2_reengagement",
            "type": "reengagement",
            "from_frame": seg["start_frame"],
            "to_frame": seg["end_frame"],
            "z_index": 15,

            "layout": {
                "x": "center",
                "y": 400,
                "width": "auto",
                "height": "auto",
                "border_radius": 0,
                "background": "transparent",
                "padding": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            },

            "content": {
                "emoji": {
                    "text": "\ud83d\udc40",
                    "font_size": 120,
                },
            },

            "enter_animation": {
                "property": "transform+opacity",
                "from": {"scale": 0.3, "opacity": 0},
                "to": {"scale": 1.0, "opacity": 1},
                "spring": {"damping": 10, "stiffness": 160},
                "duration_frames": 12,
            },

            "exit_animation": {
                "property": "transform+opacity",
                "from": {"scale": 1.0, "opacity": 1},
                "to": {"scale": 1.5, "opacity": 0},
                "spring": {"damping": 18, "stiffness": 200},
                "duration_frames": 10,
                "offset_from_end": 10,
            },

            "winner_pulse": None,
        }

    return None


def build_cta_layer(seg):
    """Build the CTA layer."""
    return {
        "id": "cta_card",
        "type": "cta_card",
        "from_frame": seg["start_frame"],
        "to_frame": seg["end_frame"],
        "z_index": 15,

        "layout": {
            "x": "center",
            "y": 300,
            "width": 800,
            "height": "auto",
            "border_radius": 28,
            "background": "rgba(0, 0, 0, 0.65)",
            "padding": {"top": 32, "right": 60, "bottom": 32, "left": 60},
        },

        "content": {
            "title": {
                "text": "CLICK THE LINK",
                "font_size": 64,
                "color": "#FFFFFF",
                "font_family": "TheBoldFont",
                "text_transform": "uppercase",
                "text_align": "center",
            },
            "arrow": {
                "text": "\u2193",
                "font_size": 80,
                "bounce_amplitude": 10,
                "bounce_frequency": 0.2,
            },
        },

        "enter_animation": {
            "property": "transform+opacity",
            "from": {"scale": 0.7, "opacity": 0},
            "to": {"scale": 1.0, "opacity": 1},
            "spring": {"damping": 12, "stiffness": 180},
            "duration_frames": 12,
        },

        "exit_animation": None,
        "winner_pulse": None,
    }


def produce_edl(script_path, captions_path):
    """Analyze script + captions and produce a complete rendering specification."""
    with open(script_path) as f:
        script = json.load(f)
    with open(captions_path) as f:
        captions = json.load(f)

    meta = script.get("meta", {})
    segments = script.get("segments", [])
    style = script.get("style_config", {})

    total_duration_ms = captions[-1]["endMs"] if captions else 0
    total_frames = ms_to_frame(total_duration_ms)

    # ── Step 1: Map segments to exact timestamps from captions ──
    segment_timings = []
    last_end_ms = 0

    for seg in segments:
        spoken = seg.get("spoken_text", "")
        first_words = " ".join(spoken.split()[:3])
        last_word = spoken.split()[-1].rstrip(".,!?;:'\"") if spoken.split() else ""

        start_ms = find_word_timestamp(
            captions, first_words, after_ms=max(0, last_end_ms - 500)
        )
        end_ms = find_word_end_timestamp(
            captions, last_word, after_ms=(start_ms or last_end_ms)
        )

        if start_ms is None:
            start_ms = last_end_ms
        if end_ms is None:
            end_ms = start_ms + 5000

        segment_timings.append({
            **seg,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start_frame": ms_to_frame(start_ms),
            "end_frame": ms_to_frame(end_ms),
        })
        last_end_ms = end_ms

    # ── Step 2: Plan jump cuts (content-driven) ──
    jump_cuts = plan_jump_cuts(segment_timings, captions)

    # ── Step 3: Build layers (overlays with exact specs) ──
    layers = []
    shelf_products = []

    for i, seg in enumerate(segment_timings):
        seg_type = seg.get("type", "")
        seg_id = seg.get("id", "")

        if seg_type == "hook" and seg_id == "hook_1":
            layer = build_hook_layer(seg, "hook_1")
            if layer:
                layers.append(layer)

        elif seg_type == "product_review":
            layer = build_product_card_layer(seg, i)
            layers.append(layer)

            # Add to shelf
            grade = seg.get("grade", "")
            shelf_products.append({
                "rank": seg.get("rank"),
                "grade": grade,
                "grade_color": GRADE_COLORS.get(grade, "#FFFFFF"),
                "product": seg.get("product", ""),
                "product_image": f"products/{seg.get('product_image', '').replace('.avif', '.png')}",
                "reveal_frame": seg["start_frame"],
            })

        elif seg_type == "hook" and seg_id == "hook_2":
            layer = build_hook_layer(seg, "hook_2")
            if layer:
                layers.append(layer)

        elif seg_type == "cta":
            layers.append(build_cta_layer(seg))

    # ── Step 4: Build shelf track ──
    shelf_track = {
        "y": 50,
        "x": "center",
        "thumbnail_size": 100,
        "gap": 12,
        "background": "rgba(0, 0, 0, 0.45)",
        "background_padding": {"top": 8, "right": 16, "bottom": 8, "left": 16},
        "background_border_radius": 16,
        "grade_font_size": 24,
        "grade_font_family": "TheBoldFont",
        "image_border_radius": 12,
        "image_border": "2px solid rgba(255,255,255,0.15)",
        "products": sorted(shelf_products, key=lambda p: -(p.get("rank") or 0)),
    }

    # ── Step 5: Caption track config ──
    caption_track = {
        "position_y_from_bottom": 220,
        "max_height": 150,
        "font_size": 100,
        "font_family": "TheBoldFont",
        "text_transform": "uppercase",
        "text_color": "#FFFFFF",
        "highlight_color": style.get("caption_highlight_color", "#39E508"),
        "stroke_width": 20,
        "stroke_color": "#000000",
        "combine_within_ms": 1200,
    }

    # ── Step 6: Assemble EDL ──
    edl = {
        "meta": {
            "fps": FPS,
            "total_duration_ms": total_duration_ms,
            "total_frames": total_frames,
            "resolution": meta.get("resolution", {"width": CANVAS_W, "height": CANVAS_H}),
            "canvas": {"width": CANVAS_W, "height": CANVAS_H},
            "generated_by": "videographer_agent_v2",
        },
        "avatar_track": {
            "object_fit": "cover",
            "object_position": "center top",
            "vignette": "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)",
            "jump_cuts": jump_cuts,
        },
        "layers": layers,
        "shelf_track": shelf_track,
        "caption_track": caption_track,
        "segment_timings": [
            {
                "id": s.get("id"),
                "type": s.get("type"),
                "start_ms": s["start_ms"],
                "end_ms": s["end_ms"],
                "start_frame": s["start_frame"],
                "end_frame": s["end_frame"],
            }
            for s in segment_timings
        ],
    }

    return edl


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 videographer.py <script.json> <captions.json> [output.json]")
        sys.exit(1)

    script_path = sys.argv[1]
    captions_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) >= 4 else str(
        Path(script_path).parent / (Path(script_path).stem + "_edl.json")
    )

    print(f"Videographer v2 analyzing:", flush=True)
    print(f"  Script: {script_path}", flush=True)
    print(f"  Captions: {captions_path}", flush=True)

    edl = produce_edl(script_path, captions_path)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(edl, f, indent=2)

    # Print summary
    print(f"\nEDL v2 produced:", flush=True)
    print(f"  Output: {output_path}", flush=True)
    print(f"  Total frames: {edl['meta']['total_frames']}", flush=True)
    print(f"  Jump cuts: {len(edl['avatar_track']['jump_cuts'])}", flush=True)
    print(f"  Layers: {len(edl['layers'])}", flush=True)
    print(f"  Shelf products: {len(edl['shelf_track']['products'])}", flush=True)

    print(f"\nJump cuts ({len(edl['avatar_track']['jump_cuts'])}):", flush=True)
    for jc in edl["avatar_track"]["jump_cuts"]:
        print(
            f"  frame {jc['frame']:4d}  scale {jc['scale']:.2f}  "
            f"origin {jc['transform_origin']:16s}  {jc['reason']}",
            flush=True,
        )

    print(f"\nLayers ({len(edl['layers'])}):", flush=True)
    for layer in edl["layers"]:
        layout = layer.get("layout", {})
        print(
            f"  {layer['id']:30s}  frames {layer['from_frame']:4d}-{layer['to_frame']:4d}  "
            f"y={layout.get('y', '?'):>4}  w={layout.get('width', '?'):>4}  "
            f"type={layer['type']}",
            flush=True,
        )

    print(f"\nSegment timings:", flush=True)
    for seg in edl["segment_timings"]:
        print(
            f"  {seg['id']:15s}  {seg['start_ms']:6d}-{seg['end_ms']:6d}ms  "
            f"(frames {seg['start_frame']:4d}-{seg['end_frame']:4d})  "
            f"{seg['type']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
