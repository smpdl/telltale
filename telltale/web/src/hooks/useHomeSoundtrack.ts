import React from "react";

const SOUNDTRACK_VOLUME = 0.385;

export function useHomeSoundtrack(active: boolean) {
  const [enabled, setEnabled] = React.useState(true);
  const [unlocked, setUnlocked] = React.useState(false);
  const [ready, setReady] = React.useState(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const ensureAudio = React.useCallback(() => {
    const audio = audioRef.current ?? new Audio("/dream.mp3");
    audioRef.current = audio;
    audio.loop = true;
    audio.preload = "auto";
    audio.volume = SOUNDTRACK_VOLUME;
    return audio;
  }, []);

  const stop = React.useCallback(() => {
    if (!audioRef.current) return;
    audioRef.current.pause();
  }, []);

  const start = React.useCallback(async (force = false) => {
    if ((!enabled && !force) || !active || !unlocked) return;
    const audio = ensureAudio();
    try {
      await audio.play();
      setReady(true);
    } catch {
      setReady(false);
    }
  }, [active, enabled, unlocked, ensureAudio]);

  React.useEffect(() => {
    if (!active || !enabled || !unlocked) {
      stop();
      return;
    }
    void start();
  }, [active, enabled, unlocked, start, stop]);

  React.useEffect(() => () => stop(), [stop]);

  return {
    enabled,
    ready,
    unlocked,
    unlockAndPlay: async () => {
      setUnlocked(true);
      setEnabled(true);
      const audio = ensureAudio();
      try {
        await audio.play();
        setReady(true);
      } catch {
        setReady(false);
      }
    },
    playWithoutSound: () => {
      setUnlocked(true);
      setEnabled(false);
      stop();
    },
    toggle: () => {
      setEnabled((current) => {
        if (current) {
          stop();
        } else {
          window.setTimeout(() => void start(true), 0);
        }
        return !current;
      });
    }
  };
}
