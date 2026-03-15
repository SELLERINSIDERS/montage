#!/usr/bin/env python3
"""
Copy/rename Kling v4 clips to populate Remotion public/vsl/ directory.

The Remotion manifest uses a 42-scene composite numbering (master script),
while Kling v4 clips use the 88-scene flat numbering from scene_prompts_v3.

This script:
1. Maps each manifest filename to the correct Kling v4 clip
2. For scenes with multiple takes, picks the best version (latest mod time for versioned clips)
3. Copies clips to video/remotion-video/public/vsl/
4. Skips clips that already exist
5. Reports results
"""

import logging
import os
import shutil
import glob
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
V4_DIR = PROJECT_ROOT / "video/output/kling/vsl_example"  # TODO: Set your Kling output dir
DEST_DIR = PROJECT_ROOT / "video/remotion-video/public/vsl"

# ============================================================================
# MAPPING: manifest_filename -> kling_v4_base_name
#
# The manifest uses 42-scene master script IDs.
# Kling v4 uses 88-scene scene_prompts_v3 numbering.
#
# Mapping built by matching dialogue/narration between master script and
# scene prompts v3:
#
# Master Script Scene -> V3/Kling Scene (by dialogue match)
# ============================================================================

MAPPING = {
    # --- ACT 1: THE HOOK ---
    # Manifest scene_01 "In 40 BC, Cleopatra..." = V3 scene 01 "Cleopatra Portrait"
    "scene_01_cleopatra_portrait.mp4": "scene_01_cleopatra_portrait",

    # Manifest scene_02 "Not for gold. Not for land." = V3 scene 02 "Roman Warships"
    "scene_02_roman_warships.mp4": "scene_02_roman_warships",

    # Manifest scene_03 "For access to one single mineral." = Master script Scene 03 "Dead Sea Aerial"
    # BUT V3 reordered: V3 scene 03 = "Mineral Crystal Macro", V3 scene 04 = "Dead Sea Aerial Reveal"
    # The manifest scene_03 is "dead_sea_reveal" which matches V3 scene 04 "Dead Sea Aerial Reveal"
    "scene_03_dead_sea_reveal.mp4": "scene_04_dead_sea_aerial_reveal",

    # Manifest scene_04 "Cleopatra was crowned queen at eighteen." = Master Script Scene 04 "Coronation"
    # V3 scene 06 = "Coronation" (V3 inserted scenes 03-05 as crystal macro, dead sea aerial, hands on mineral)
    "scene_04_young_queen_crowned.mp4": "scene_06_coronation",

    # Manifest scene_05 "Surrounded by enemies..." = Master Script Scene 05 "Assassin Corridor"
    # V3 scene 07 = "Enemies Surround"
    "scene_05_palace_conspirators.mp4": "scene_07_enemies_surround",

    # Manifest scene_06 "...tried to have her killed. Twice." = Master Script Scene 06 "Assassination Attempt"
    # V3 scene 08 = "Assassination Attempt"
    "scene_06_twice_assassination.mp4": "scene_08_assassination_attempt",

    # Manifest scene_07 "But she didn't just survive. She discovered..." = Master Script Scene 07+08
    # V3 scene 10 = "Survival to Triumph" ("But she didn't just survive")
    "scene_07_cleopatra_triumphant.mp4": "scene_10_survival_to_triumph",

    # Manifest scene_08 "...something." = Master Script Scene 08 "Dead Sea Crystal Macro"
    # V3 scene 11 = "Discovery" ("She discovered something")
    "scene_08_dead_sea_discovery.mp4": "scene_11_discovery",

    # Manifest scene_09 "On the shores of a dead lake..." = Master Script Scene 09 "Dead Sea Wide"
    # V3 scene 12 = "Dead Sea Shore Minerals"
    "scene_09_dead_sea_wide.mp4": "scene_12_dead_sea_shore_minerals",

    # Manifest scene_10 "A mineral so valuable she went to war for it." = Master Script Scene 10 "Roman March"
    # V3 scene 13 = "Army Marching to War"
    "scene_10_military_campaign.mp4": "scene_13_army_marching_to_war",

    # Manifest scene_11 "She convinced Mark Antony..." = Master Script Scene 11 "Military Tent Strategy"
    # V3 scene 15 = "Cleopatra and Mark Antony"
    "scene_11_war_planning.mp4": "scene_15_cleopatra_and_mark_antony",

    # Manifest scene_12 "Built factories along the shores." = Master Script Scene 12 "Dead Sea Factories"
    # V3 scene 17 = "Mineral Factories"
    "scene_12_factories.mp4": "scene_17_mineral_factories",

    # Manifest scene_13 "Leased the mineral rights for 200 silver talents..." = Master Script Scene 13 "Silver Talents"
    # V3 scene 18 = "Silver Talents"
    "scene_13_silver_trade.mp4": "scene_18_silver_talents",

    # --- MONTAGE (14a-d) ---
    # Manifest scene_14a "Ruled Egypt." = V3 scene 19 "Ruled Egypt"
    "scene_14a_achievement_throne.mp4": "scene_19_ruled_egypt",

    # Manifest scene_14b "Commanded navies." = V3 scene 20 "Commanded Navies"
    "scene_14b_achievement_navy.mp4": "scene_20_commanded_navies",

    # Manifest scene_14c "Spoke nine languages." = V3 scene 21 "Spoke Nine Languages"
    "scene_14c_languages_nine_nations.mp4": "scene_21_spoke_nine_languages",

    # Manifest scene_14d "Outlasted three Roman dictators." = V3 scene 22 "Outlasted Three Roman Dictators"
    "scene_14d_achievement_outlasting.mp4": "scene_22_outlasted_three_roman_dictators",

    # --- ACT 2 continued ---
    # Manifest scene_15 "And every single night, she bathed in it." = V3 scene 23 "The Bath"
    "scene_15_mineral_bath.mp4": "scene_23_the_bath",

    # Manifest scene_16 "The most powerful woman in the ancient world." = V3 scene 24 "Queen Portrait"
    "scene_16_queen_portrait.mp4": "scene_24_queen_portrait",

    # --- ACT 3: THE PIVOT ---
    # Manifest scene_17 "But here's what history books leave out." = V3 scene 25 "History Books Explode"
    "scene_17_exploding_book.mp4": "scene_25_history_books_explode",

    # Manifest scene_18 "That mineral was magnesium." = V3 scene 26 "Magnesium Crystal Reveal"
    "scene_18_magnesium_reveal.mp4": "scene_26_magnesium_crystal_reveal",

    # Manifest scene_19 "The Dead Sea contains thirty times more magnesium..." = V3 scene 27 "Underwater Dead Sea"
    "scene_19_dead_sea_concentration.mp4": "scene_27_underwater_dead_sea",

    # Manifest scene_20 "For three thousand years, humans absorbed it daily." = V3 scene 28 "Ancient Absorption: Bathhouse"
    "scene_20_ancient_mineral_use.mp4": "scene_28_ancient_absorption_bathhouse",

    # --- TRIPLE CUT (21a-c) ---
    # Manifest scene_21a "Through water." = V3 scene 29 "Through Water"
    "scene_21a_triple_water.mp4": "scene_29_through_water",

    # Manifest scene_21b "Through soil." = V3 scene 30 "Through Soil"
    "scene_21b_triple_soil.mp4": "scene_30_through_soil",

    # Manifest scene_21c "Through food." = V3 scene 31 "Through Food"
    "scene_21c_triple_food.mp4": "scene_31_through_food",

    # --- INDUSTRIAL DECLINE ---
    # Manifest scene_22 "Then modern agriculture changed everything." = V3 scene 32 "Modern Agriculture"
    "scene_22_industrial_shift.mp4": "scene_32_modern_agriculture",

    # Manifest scene_23 "Industrial farming stripped magnesium from the soil." = V3 scene 33 "Depleted Soil"
    "scene_23_depleted_soil.mp4": "scene_33_depleted_soil",

    # Manifest scene_24 "Water treatment plants removed it..." = V3 scene 34 "Water Treatment"
    "scene_24_water_treatment.mp4": "scene_34_water_treatment",

    # Manifest scene_25 "Processed food destroyed what was left." = V3 scene 35 "Processed Food"
    "scene_25_processed_food.mp4": "scene_35_processed_food",

    # Manifest scene_26 "In just two generations..." = V3 scene 36 "Two Generations"
    "scene_26_two_generations_timeline.mp4": "scene_36_two_generations",

    # Manifest scene_27 "Today, studies show that up to 68%..." = V3 scene 38 "68% of Americans"
    # NOTE: V3 scene 37 is "Almost Never" (the end of the two-generations line), scene 38 is the 68% stat
    "scene_27_the_statistic.mp4": "scene_38_68_of_americans",

    # Manifest scene_28 "Your body uses it for over 300 essential processes..." = Multiple V3 scenes (39-45)
    # The manifest consolidates V3 scenes 39-45 into ONE scene. Best match: V3 scene 39 "Person at Desk"
    # covers "Your body uses it for over 300 essential processes"
    # BUT looking at the v4 clips more carefully:
    # scene_39_person_at_desk = "Your body uses it..."
    # scene_40_300_processes_trembling_hands = "300 essential processes"
    # scene_41_body_unable_to_relax = "When it's missing, your body can't wind down"
    # The manifest scene_28 has duration_s: 10.9 which is long - it covers the whole paragraph.
    # Best single clip for the visual: scene_39_person_at_desk (the opening shot of this sequence)
    "scene_28_body_processes.mp4": "scene_39_person_at_desk",

    # --- SLEEPLESS SEQUENCE (29a-c) ---
    # Manifest scene_29a "Lying awake at 2 AM." = V3 scene 46 "2 AM Clock"
    "scene_29a_sleepless_2am_clock.mp4": "scene_46_2_am_clock",

    # Manifest scene_29b "Racing thoughts. Tossing and turning. Exhausted but wired."
    # = V3 scene 47 "Racing Thoughts, Tossing"
    "scene_29b_sleepless_tossing.mp4": "scene_47_racing_thoughts_tossing",

    # Manifest scene_29c "Waking up more tired than when you went to bed."
    # = V3 scene 49 "Morning Exhaustion"
    "scene_29c_sleepless_dragging.mp4": "scene_49_morning_exhaustion",

    # --- REFRAME ---
    # Manifest scene_30 "It's not stress. It's not age. Your body is missing something..."
    # = V3 scene 50 "Mirror: Not Stress, Not Age" + scene 51 "Missing Something"
    # Best clip: scene_51_missing_something (the pivotal realization — Dead Sea dawn)
    "scene_30_the_reframe.mp4": "scene_51_missing_something",

    # --- ACT 4: THE SOLUTION ---
    # Manifest scene_31 "Cleopatra didn't have that problem. She absorbed more magnesium..."
    # = V3 scene 52 "Cleopatra Didn't Have That Problem"
    "scene_31_cleopatra_callback.mp4": "scene_52_cleopatra_didnt_have_that_problem",

    # Manifest scene_32 "And now, for the first time, you don't need a Dead Sea..."
    # = V3 scene 55 "You Don't Need a Dead Sea"
    "scene_32_modern_dead_sea.mp4": "scene_55_you_dont_need_a_dead_sea",

    # Manifest scene_33 "Dead Sea magnesium. The same ancient mineral source..."
    # = V3 scene 57 "Same Ancient Mineral Source"
    "scene_33_ancient_meets_modern.mp4": "scene_57_same_ancient_mineral_source",

    # Manifest scene_34 "But Brand goes further. Chelated magnesium glycinate..."
    # = V3 scene 58 "Brand Goes Further" (covers the whole paragraph)
    # This manifest scene is 10.08s long, covering scenes 58-61 in V3.
    # Best single clip: scene_58_brand_goes_further or scene_61_64_bioavailability
    # The manifest filename is "lab_science" so scene_58_brand_goes_further fits
    "scene_34_lab_science.mp4": "scene_58_brand_goes_further",

    # --- INGREDIENTS (35a-b) ---
    # Manifest scene_35a "Combined with saffron extract studied in eleven clinical trials."
    # = V3 scene 62 "Saffron Extract — 11 Clinical Trials"
    "scene_35a_saffron_field.mp4": "scene_62_saffron_extract_11_clinical_trials",

    # Manifest scene_35b "And L-Theanine." = V3 scene 63 "And L-Theanine"
    "scene_35b_ltheanine_tea.mp4": "scene_63_and_ltheanine",

    # --- TRUST ---
    # Manifest scene_36 "Third-party tested. Every batch verified. No fillers..."
    # = V3 scenes 64-66. Best clip: scene_64_thirdparty_tested
    "scene_36_trust_signals.mp4": "scene_64_thirdparty_tested",

    # --- BENEFIT CASCADE (37a-b) ---
    # Manifest scene_37a "Calm. Not groggy — calm. Your thoughts slow down..."
    # = V3 scenes 67-71. Best clip: scene_67_calm_first (opening of benefit cascade)
    "scene_37a_calm_evening.mp4": "scene_67_calm_first",

    # Manifest scene_37b "You drift off naturally. And you wake up actually rested..."
    # = V3 scenes 72-74. Best clip: scene_72_you_drift_off_naturally
    "scene_37b_peaceful_sleep.mp4": "scene_72_you_drift_off_naturally",

    # --- ACT 5: THE CLOSE ---
    # Manifest scene_38 "Cleopatra built an empire around this mineral."
    # = V3 scene 75 "Cleopatra Built an Empire Around This Mineral"
    "scene_38_empire_callback_facility.mp4": "scene_75_cleopatra_built_an_empire_around_this_mineral",

    # Manifest scene_39 "Most people can't even sleep through the night."
    # = V3 scene 76 "Most People Can't Even Sleep Through the Night"
    "scene_39_sleepless_birds_eye.mp4": "scene_76_most_people_cant_even_sleep_through_the_night",

    # Manifest scene_40 "The difference isn't willpower. It's chemistry."
    # = V3 scene 77 "The Difference Isn't Willpower" + scene 78 "It's Chemistry"
    # Best clip: scene_78_its_chemistry (the geode/chemistry visual)
    "scene_40_chemistry_golden_geode.mp4": "scene_78_its_chemistry",

    # Manifest scene_41 "Right now, Brand is offering a limited-time deal..."
    # = V3 scene 79 "Limited-Time Deal" + scene 80 "If the Link Is Still Below"
    # Best clip: scene_79_limitedtime_deal (product hero shot)
    "scene_41_product_hero.mp4": "scene_79_limitedtime_deal",

    # Manifest scene_42 "Try it for 90 nights. If you don't feel the difference..."
    # = V3 scenes 81-85. Best clip: scene_85_cleopatra_knew_that_final_frame (the closing shot)
    "scene_42_guarantee_sunset.mp4": "scene_85_cleopatra_knew_that_final_frame",
}


def find_best_clip(base_name: str) -> str | None:
    """
    Find the best clip for a given base name in the v4 directory.

    For version selection:
    - If only the original exists, use it
    - If versioned clips exist (v2, v3, etc.), compare modification times
    - Use the ORIGINAL unless a newer version has a MORE RECENT modification time
      (indicating a quality refinement)
    """
    # Find all matching clips (base + versioned)
    pattern = f"{base_name}*.mp4"
    matches = list(V4_DIR.glob(pattern))

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0].name

    # Separate original from versions
    original = None
    versions = []

    for m in matches:
        name = m.stem  # without .mp4
        # Check if it's a versioned file (ends with _v2, _v3, _v_2, etc.)
        if re.search(r'_v_?\d+$', name):
            versions.append(m)
        elif name == base_name:
            original = m
        else:
            # Edge case: might be a different scene entirely (e.g., scene_01 matching scene_010)
            # Only include exact base name matches
            if m.stem == base_name:
                original = m

    if not original and not versions:
        return None

    if not versions:
        return original.name if original else None

    if not original:
        # Only versions exist, pick the latest mod time
        best = max(versions, key=lambda p: p.stat().st_mtime)
        return best.name

    # Compare: prefer original UNLESS a version has a more recent modification time
    original_mtime = original.stat().st_mtime

    # Find the latest version
    latest_version = max(versions, key=lambda p: p.stat().st_mtime)
    latest_version_mtime = latest_version.stat().st_mtime

    if latest_version_mtime > original_mtime:
        # A newer version exists with a more recent mod time — it's a quality refinement
        return latest_version.name
    else:
        # Original is newer or same age — prefer original
        return original.name


def main():
    print("=" * 70)
    print("KLING V4 -> REMOTION PUBLIC/VSL CLIP COPY")
    print("=" * 70)
    print(f"\nSource:      {V4_DIR}")
    print(f"Destination: {DEST_DIR}")
    print(f"Manifest scenes: {len(MAPPING)}")
    print()

    # Ensure destination exists
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    copied = []
    skipped = []
    missing = []
    errors = []

    for manifest_file, v4_base in MAPPING.items():
        dest_path = DEST_DIR / manifest_file

        # Skip if already exists
        if dest_path.exists():
            skipped.append(manifest_file)
            continue

        # Find best clip
        best_clip = find_best_clip(v4_base)

        if best_clip is None:
            missing.append((manifest_file, v4_base))
            continue

        src_path = V4_DIR / best_clip

        try:
            shutil.copy2(str(src_path), str(dest_path))
            size_mb = src_path.stat().st_size / (1024 * 1024)
            copied.append((manifest_file, best_clip, size_mb))
        except Exception as e:
            logger.error("Error copying %s: %s", manifest_file, e, exc_info=True)
            errors.append((manifest_file, best_clip, str(e)))

    # Report
    print("-" * 70)
    print(f"COPIED: {len(copied)} clips")
    print("-" * 70)
    for mf, v4f, size in copied:
        print(f"  {v4f}")
        print(f"    -> {mf}  ({size:.1f} MB)")

    print()
    print("-" * 70)
    print(f"SKIPPED (already exist): {len(skipped)} clips")
    print("-" * 70)
    for mf in skipped:
        print(f"  {mf}")

    if missing:
        print()
        print("-" * 70)
        print(f"MISSING (no v4 clip found): {len(missing)} clips")
        print("-" * 70)
        for mf, v4b in missing:
            print(f"  {mf}  (looked for: {v4b}*)")

    if errors:
        print()
        print("-" * 70)
        print(f"ERRORS: {len(errors)} clips")
        print("-" * 70)
        for mf, v4f, err in errors:
            print(f"  {mf} <- {v4f}: {err}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_size = sum(s for _, _, s in copied)
    print(f"  Copied:  {len(copied)} clips ({total_size:.0f} MB)")
    print(f"  Skipped: {len(skipped)} clips (already existed)")
    print(f"  Missing: {len(missing)} clips")
    print(f"  Errors:  {len(errors)} clips")
    print(f"  Total manifest scenes: {len(MAPPING)}")
    print(f"  Coverage: {len(copied) + len(skipped)}/{len(MAPPING)} ({100*(len(copied)+len(skipped))/len(MAPPING):.0f}%)")


if __name__ == "__main__":
    main()
