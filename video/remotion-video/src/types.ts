/**
 * EDL (Edit Decision List) schema for UniversalComposition.
 *
 * Single source of truth for the EDL JSON structure consumed by Remotion.
 * Python EDL generator must produce JSON matching this schema.
 */
import { z } from "zod";

// ── Enum types ──────────────────────────────────────────────────────

export const captionPresetIds = [
  "tiktok_bold",
  "clean_minimal",
  "cinematic_subtle",
  "wellness_soft",
] as const;
export type CaptionPresetId = (typeof captionPresetIds)[number];

export const platformTargets = [
  "tiktok",
  "instagram_reels",
  "youtube_shorts",
  "youtube",
  "generic",
] as const;
export type PlatformTarget = (typeof platformTargets)[number];

export const renderQualities = ["preview", "final"] as const;
export type RenderQuality = (typeof renderQualities)[number];

export const audioTypes = [
  "voiceover_only",
  "scene_dominant",
  "mixed",
  "silent",
] as const;

export const formatTypes = ["vsl", "ad", "ugc"] as const;

export const transitionTypes = ["hard_cut", "crossfade"] as const;

// ── Sub-schemas ─────────────────────────────────────────────────────

const ambientAudioSchema = z.object({
  src: z.string(),
  volume: z.number(),
  loop: z.boolean().default(true),
  fade_in: z.boolean().default(false),
  delay_s: z.number().default(0),
});

const sceneEntrySchema = z.object({
  id: z.string(),
  clip_src: z.string(),
  duration_s: z.number(),
  trim_start_s: z.number().default(0),
  trim_end_s: z.number(),
  audio_type: z.enum(audioTypes),
  ambient_audio: z.array(ambientAudioSchema).default([]),
  transition_in: z.enum(transitionTypes).default("hard_cut"),
  label: z.string(),
  playback_rate_override: z.number().optional(),
});

export type SceneEntry = z.infer<typeof sceneEntrySchema>;

const changelogEntrySchema = z.object({
  version: z.number(),
  date: z.string(),
  changes: z.array(z.string()),
});

const metaSchema = z.object({
  fps: z.number().default(24),
  width: z.number(),
  height: z.number(),
  title: z.string(),
  format: z.enum(formatTypes),
  caption_preset: z.enum(captionPresetIds),
  platform_target: z.enum(platformTargets),
  render_quality: z.enum(renderQualities),
  version: z.number().default(1),
});

const voiceoverSchema = z
  .object({
    src: z.string(),
    volume: z.number().min(0).max(1).default(1.0),
    whisper_data: z.string(),
  })
  .nullable();

const introSchema = z
  .object({
    type: z.enum(["logo", "brand"]),
    duration_s: z.number().default(2),
    logo_src: z.string().optional(),
    text: z.string().optional(),
    background_color: z.string().default("#000000"),
  })
  .optional();

const outroSchema = z
  .object({
    type: z.enum(["cta", "product"]),
    duration_s: z.number().default(3),
    text: z.string().optional(),
    url: z.string().optional(),
    product_image_src: z.string().optional(),
    background_color: z.string().default("#000000"),
  })
  .optional();

// ── Main EDL schema ─────────────────────────────────────────────────

export const edlSchema = z.object({
  meta: metaSchema,
  voiceover: voiceoverSchema,
  scenes: z.array(sceneEntrySchema),
  intro: introSchema,
  outro: outroSchema,
  changelog: z.array(changelogEntrySchema).default([]),
});

export type EDL = z.infer<typeof edlSchema>;
