/**
 * CaptionLayer — word-level caption highlighting overlay for UniversalComposition.
 *
 * Loads Whisper JSON, converts to @remotion/captions format,
 * uses createTikTokStyleCaptions for word grouping and page breaks,
 * renders with selected preset styling and platform safe zone positioning.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  AbsoluteFill,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  createTikTokStyleCaptions,
  type Caption,
  type TikTokPage,
} from "@remotion/captions";
import { CAPTION_PRESETS, PLATFORM_SAFE_ZONES } from "./CaptionPresets";
import type { CaptionPreset } from "./CaptionPresets";
import { loadPresetFont } from "./load-fonts";
import type { CaptionPresetId, PlatformTarget } from "./types";

// ── Whisper JSON types ─────────────────────────────────────────────

interface WhisperWord {
  word: string;
  start: number;
  end: number;
  probability?: number;
}

interface WhisperSegment {
  start: number;
  end: number;
  text: string;
  words?: WhisperWord[];
}

interface WhisperData {
  segments: WhisperSegment[];
}

// ── Props ──────────────────────────────────────────────────────────

interface CaptionLayerProps {
  whisperDataSrc: string;
  presetId: CaptionPresetId;
  platformTarget: PlatformTarget;
}

/**
 * Convert Whisper JSON segments/words to @remotion/captions Caption[] format.
 */
function whisperToCaptions(data: WhisperData): Caption[] {
  const captions: Caption[] = [];

  for (const segment of data.segments) {
    if (segment.words && segment.words.length > 0) {
      for (const word of segment.words) {
        captions.push({
          text: word.word,
          startMs: Math.round(word.start * 1000),
          endMs: Math.round(word.end * 1000),
          timestampMs: Math.round(word.start * 1000),
          confidence: word.probability ?? null,
        });
      }
    } else {
      // Fallback: treat entire segment as one caption
      captions.push({
        text: segment.text,
        startMs: Math.round(segment.start * 1000),
        endMs: Math.round(segment.end * 1000),
        timestampMs: Math.round(segment.start * 1000),
        confidence: null,
      });
    }
  }

  return captions;
}

// ── Page renderer ──────────────────────────────────────────────────

const CaptionPage: React.FC<{
  page: TikTokPage;
  preset: CaptionPreset;
  startFrame: number;
}> = ({ page, preset, startFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Animation on page enter
  const pageFrame = frame - startFrame;
  const animDuration = 6; // frames

  let animStyle: React.CSSProperties = {};
  if (preset.enterAnimation === "scale_up") {
    const scale = interpolate(pageFrame, [0, animDuration], [0.7, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    animStyle = { transform: `scale(${scale})` };
  } else if (preset.enterAnimation === "fade_in") {
    const opacity = interpolate(pageFrame, [0, 8], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    animStyle = { opacity };
  } else if (preset.enterAnimation === "slide_up") {
    const ty = interpolate(pageFrame, [0, animDuration], [40, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    animStyle = { transform: `translateY(${ty}px)` };
  }

  // Fixed font size — always use max to keep every caption the same visual weight.
  // fitText caused short pages (1-2 words) to render larger than long pages,
  // creating inconsistent sizing. createTikTokStyleCaptions handles line breaking.
  const fontSize = preset.fontSize.max;

  // Current time in ms
  const currentMs = (frame / fps) * 1000;

  const isBgPill = preset.highlightMode === "bg_pill";

  return (
    <div style={{ textAlign: "center", lineHeight: 1.3, ...animStyle }}>
      {page.tokens.map((token, i) => {
        const isActive =
          currentMs >= token.fromMs && currentMs < token.toMs;

        const tokenText =
          preset.textTransform === "uppercase"
            ? token.text.toUpperCase()
            : preset.textTransform === "lowercase"
              ? token.text.toLowerCase()
              : token.text;

        // bg_pill mode: active word gets yellow box + black text (no stroke/shadow on active)
        // text_color mode: active word uses activeColor, all words use shadow outline
        const bgPillActive = isBgPill && isActive;

        return (
          <span
            key={i}
            style={{
              fontFamily: preset.fontFamily,
              fontWeight: 700,
              fontSize,
              display: "inline-block",
              // Text color
              color: bgPillActive
                ? preset.activeColor          // black text on yellow pill
                : isBgPill
                  ? preset.baseColor          // white for non-active in bg_pill mode
                  : isActive
                    ? preset.activeColor      // highlight color in text_color mode
                    : preset.baseColor,
              // Background pill for active word
              backgroundColor: bgPillActive ? preset.activeBgColor : "transparent",
              borderRadius: bgPillActive ? "6px" : "0px",
              padding: bgPillActive ? "2px 10px 4px" : "2px 3px 4px",
              // Shadow-based outline (more reliable than WebkitTextStroke in Remotion headless)
              // Suppressed on the active bg_pill word (black text on yellow = already readable)
              textShadow: bgPillActive
                ? "none"
                : preset.textShadow !== "none"
                  ? preset.textShadow
                  : undefined,
              marginLeft: 2,
              marginRight: 2,
            }}
          >
            {tokenText}
          </span>
        );
      })}
    </div>
  );
};

// ── Main CaptionLayer ──────────────────────────────────────────────

export const CaptionLayer: React.FC<CaptionLayerProps> = ({
  whisperDataSrc,
  presetId,
  platformTarget,
}) => {
  const [pages, setPages] = useState<TikTokPage[]>([]);
  const [handle] = useState(() => delayRender("Loading captions"));
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const preset = CAPTION_PRESETS[presetId];
  const safeZone = PLATFORM_SAFE_ZONES[platformTarget];

  const loadData = useCallback(async () => {
    try {
      // Load font for this preset
      await loadPresetFont(presetId);

      // Load Whisper JSON
      const response = await fetch(staticFile(whisperDataSrc));
      const data: WhisperData = await response.json();

      // Convert to Caption format
      const captions = whisperToCaptions(data);

      // Create TikTok-style pages with word grouping
      const result = createTikTokStyleCaptions({
        captions,
        combineTokensWithinMilliseconds: preset.combineTokensMs,
      });

      setPages(result.pages);
      continueRender(handle);
    } catch (err) {
      // If captions fail to load, continue render without them
      console.error("CaptionLayer: Failed to load whisper data:", err);
      continueRender(handle);
    }
  }, [handle, presetId, whisperDataSrc, preset.combineTokensMs]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (pages.length === 0) {
    return null;
  }

  // Find current page based on frame time
  const currentMs = (frame / fps) * 1000;
  let currentPageIndex = -1;
  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    const pageEndMs = page.startMs + page.durationMs;
    if (currentMs >= page.startMs && currentMs < pageEndMs) {
      currentPageIndex = i;
      break;
    }
  }

  if (currentPageIndex === -1) {
    return null;
  }

  const currentPage = pages[currentPageIndex];

  // Hide during post-word pauses: disappear as soon as the last word ends,
  // not when the full page durationMs expires. This prevents subtitles
  // lingering on screen during silence between phrases.
  const lastToken = currentPage.tokens[currentPage.tokens.length - 1];
  if (lastToken && currentMs > lastToken.toMs) {
    return null;
  }

  // Calculate the frame when this page started
  const pageStartFrame = Math.round((currentPage.startMs / 1000) * fps);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: safeZone.bottomMargin,
        paddingLeft: 60,
        paddingRight: 60,
        pointerEvents: "none",
      }}
    >
      <CaptionPage
        page={currentPage}
        preset={preset}
        startFrame={pageStartFrame}
      />
    </AbsoluteFill>
  );
};
