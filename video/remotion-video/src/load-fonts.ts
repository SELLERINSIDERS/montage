/**
 * Font loading for caption presets using @remotion/fonts.
 *
 * Replaces manual FontFace approach from load-font.ts with proper Remotion API.
 * Each caption preset references a font file in public/fonts/.
 */
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import { CAPTION_PRESETS } from "./CaptionPresets";
import type { CaptionPresetId } from "./types";

const loadedFonts = new Set<string>();

/**
 * Load the font required by a given caption preset.
 * Safe to call multiple times — fonts are loaded only once.
 */
export const loadPresetFont = async (
  presetId: CaptionPresetId,
): Promise<void> => {
  const preset = CAPTION_PRESETS[presetId];
  if (!preset) {
    throw new Error(`Unknown caption preset: ${presetId}`);
  }

  const key = `${preset.fontFamily}:${preset.fontFile}`;
  if (loadedFonts.has(key)) {
    return;
  }

  await loadFont({
    family: preset.fontFamily,
    url: staticFile(`fonts/${preset.fontFile}`),
    weight: "700",
    format: preset.fontFormat,
  });

  loadedFonts.add(key);
};
