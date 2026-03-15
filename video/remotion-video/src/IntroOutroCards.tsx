/**
 * Optional intro and outro card components for UniversalComposition.
 *
 * Rendered when EDL defines intro/outro sections.
 * Both use simple fade animations with Remotion's interpolate().
 */
import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// ── Intro Card ─────────────────────────────────────────────────────

interface IntroCardProps {
  type: "logo" | "brand";
  durationS: number;
  logoSrc?: string;
  text?: string;
  backgroundColor: string;
}

export const IntroCard: React.FC<IntroCardProps> = ({
  type,
  durationS,
  logoSrc,
  text,
  backgroundColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const totalFrames = Math.round(durationS * fps);

  const fadeInEnd = Math.round(0.5 * fps);
  const fadeOutStart = totalFrames - Math.round(0.5 * fps);

  const fadeIn = interpolate(frame, [0, fadeInEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const fadeOut = interpolate(frame, [fadeOutStart, totalFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      {logoSrc && (
        <Img
          src={staticFile(logoSrc)}
          style={{
            maxWidth: "60%",
            maxHeight: "40%",
            objectFit: "contain",
          }}
        />
      )}
      {text && (
        <div
          style={{
            color: "#FFFFFF",
            fontSize: type === "brand" ? 64 : 48,
            fontWeight: 700,
            textAlign: "center",
            padding: "0 60px",
            marginTop: logoSrc ? 40 : 0,
          }}
        >
          {text}
        </div>
      )}
    </AbsoluteFill>
  );
};

// ── Outro Card ─────────────────────────────────────────────────────

interface OutroCardProps {
  type: "cta" | "product";
  durationS: number;
  text?: string;
  url?: string;
  productImageSrc?: string;
  backgroundColor: string;
}

export const OutroCard: React.FC<OutroCardProps> = ({
  type,
  durationS,
  text,
  url,
  productImageSrc,
  backgroundColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const totalFrames = Math.round(durationS * fps);

  // Fade in from bottom over 0.5s
  const fadeInEnd = Math.round(0.5 * fps);
  const fadeIn = interpolate(frame, [0, fadeInEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const translateY = interpolate(frame, [0, fadeInEnd], [60, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Product image slides in from right
  const imageSlideIn = interpolate(
    frame,
    [Math.round(0.3 * fps), Math.round(0.8 * fps)],
    [200, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const imageOpacity = interpolate(
    frame,
    [Math.round(0.3 * fps), Math.round(0.8 * fps)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Gentle pulse on CTA text after initial animation
  const pulseStart = Math.round(1.0 * fps);
  const pulseCycle = (frame - pulseStart) / fps;
  const pulseScale =
    frame >= pulseStart ? 1 + 0.02 * Math.sin(pulseCycle * Math.PI * 2) : 1;

  // Fade out at end
  const fadeOutStart = totalFrames - Math.round(0.5 * fps);
  const fadeOut = interpolate(frame, [fadeOutStart, totalFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const masterOpacity = Math.min(fadeIn, fadeOut);

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        justifyContent: "center",
        alignItems: "center",
        opacity: masterOpacity,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 40,
        }}
      >
        {productImageSrc && (
          <Img
            src={staticFile(productImageSrc)}
            style={{
              maxWidth: "50%",
              maxHeight: "35%",
              objectFit: "contain",
              transform: `translateX(${imageSlideIn}px)`,
              opacity: imageOpacity,
            }}
          />
        )}
        {text && (
          <div
            style={{
              color: "#FFFFFF",
              fontSize: type === "cta" ? 56 : 48,
              fontWeight: 700,
              textAlign: "center",
              padding: "0 60px",
              transform: `translateY(${translateY}px) scale(${pulseScale})`,
            }}
          >
            {text}
          </div>
        )}
        {url && (
          <div
            style={{
              color: "rgba(255,255,255,0.7)",
              fontSize: 32,
              textAlign: "center",
              transform: `translateY(${translateY}px)`,
            }}
          >
            {url}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
