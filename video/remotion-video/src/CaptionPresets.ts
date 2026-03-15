/**
 * Caption preset definitions for UniversalComposition.
 *
 * Three presets shipped initially: tiktok_bold, clean_minimal, cinematic_subtle.
 * Platform safe zones adapt caption position per delivery target.
 */
import type { CaptionPresetId, PlatformTarget } from "./types";

export interface CaptionPreset {
  id: CaptionPresetId;
  fontFamily: string;
  fontFile: string;
  fontFormat: "woff2" | "truetype";
  fontSize: { min: number; max: number };
  textTransform: "uppercase" | "lowercase" | "none";
  baseColor: string;
  activeColor: string;
  /** "bg_pill" = yellow box behind active word (true TikTok style). "text_color" = color change only. */
  highlightMode: "bg_pill" | "text_color";
  /** Background color for active word when highlightMode === "bg_pill" */
  activeBgColor?: string;
  strokeColor: string;
  strokeWidth: number;
  textShadow: string;
  enterAnimation: "scale_up" | "fade_in" | "slide_up";
  combineTokensMs: number;
}

export interface PlatformSafeZone {
  bottomMargin: number;
  topMargin: number;
}

/**
 * Three caption preset definitions.
 * Font files must exist in public/fonts/.
 */
export const CAPTION_PRESETS: Record<CaptionPresetId, CaptionPreset> = {
  tiktok_bold: {
    id: "tiktok_bold",
    fontFamily: "Montserrat",
    fontFile: "Montserrat-Bold.woff2",
    fontFormat: "woff2",
    fontSize: { min: 80, max: 110 },
    textTransform: "uppercase",
    baseColor: "#FFFFFF",
    activeColor: "#000000",
    highlightMode: "bg_pill",
    activeBgColor: "#FFFC00",
    strokeColor: "#000000",
    strokeWidth: 4,
    // 8-directional shadow outline — more reliable than WebkitTextStroke in Remotion headless Chrome
    textShadow:
      "-3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, -3px 0 0 #000, 3px 0 0 #000, 0 -3px 0 #000, 0 3px 0 #000",
    enterAnimation: "scale_up",
    combineTokensMs: 800,
  },
  clean_minimal: {
    id: "clean_minimal",
    fontFamily: "Inter",
    fontFile: "Inter-Bold.woff2",
    fontFormat: "woff2",
    fontSize: { min: 40, max: 64 },
    textTransform: "none",
    baseColor: "#F5F5F5",
    activeColor: "#FFD700",
    highlightMode: "text_color",
    strokeColor: "transparent",
    strokeWidth: 0,
    textShadow: "0 2px 8px rgba(0,0,0,0.6)",
    enterAnimation: "fade_in",
    combineTokensMs: 1200,
  },
  cinematic_subtle: {
    id: "cinematic_subtle",
    fontFamily: "TheBoldFont",
    fontFile: "theboldfont.ttf",
    fontFormat: "truetype",
    fontSize: { min: 44, max: 68 },
    textTransform: "uppercase",
    baseColor: "#E8D5A3",
    activeColor: "#FFD700",
    highlightMode: "text_color",
    strokeColor: "#1A0F00",
    strokeWidth: 2,
    textShadow: "0 0 12px rgba(255,215,0,0.3)",
    enterAnimation: "slide_up",
    combineTokensMs: 1200,
  },

  /**
   * wellness_soft — Poppins SemiBold, clean and premium.
   * Designed for supplement/wellness brands (sleep, calm, recovery).
   * Soft drop-shadow instead of hard stroke. Warm cream active highlight.
   * No background pill — minimal, elegant, not hype.
   */
  wellness_soft: {
    id: "wellness_soft",
    fontFamily: "Poppins",
    fontFile: "Poppins-SemiBold.woff2",
    fontFormat: "woff2",
    fontSize: { min: 60, max: 78 },
    textTransform: "lowercase",
    baseColor: "#FFFFFF",
    activeColor: "#F5D87E",
    highlightMode: "text_color",
    strokeColor: "transparent",
    strokeWidth: 0,
    // Multi-layer soft shadow for readability on any background — no harsh outline
    textShadow:
      "0 2px 8px rgba(0,0,0,0.9), 0 4px 20px rgba(0,0,0,0.6), 0 1px 3px rgba(0,0,0,1)",
    enterAnimation: "fade_in",
    combineTokensMs: 1000,
  },
};

/**
 * Platform safe zones — bottom/top margin in pixels for 1920h canvas.
 * Keeps captions clear of platform UI overlays (nav bars, comment buttons, etc.)
 */
export const PLATFORM_SAFE_ZONES: Record<PlatformTarget, PlatformSafeZone> = {
  tiktok: { bottomMargin: 320, topMargin: 108 },
  instagram_reels: { bottomMargin: 310, topMargin: 250 },
  youtube_shorts: { bottomMargin: 300, topMargin: 120 },
  youtube: { bottomMargin: 100, topMargin: 50 },
  generic: { bottomMargin: 200, topMargin: 100 },
};
