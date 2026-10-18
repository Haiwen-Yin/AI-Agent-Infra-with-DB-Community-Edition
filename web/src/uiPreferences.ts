import { useEffect, useState } from "react";

type Lang = "zh" | "en";
type Theme = "light" | "dark";

declare global {
  interface Window {
    ChuanxuUI?: {
      applyLanguage: (value: Lang) => void;
      applyTheme: (value: Theme) => void;
    };
  }
}

function readPreference<T extends string>(queryKey: string, keys: string[], values: readonly T[], fallback: T): T {
  const requested = new URLSearchParams(window.location.search).get(queryKey);
  if (values.includes(requested as T)) return requested as T;
  try {
    for (const key of keys) {
      const saved = localStorage.getItem(key);
      if (values.includes(saved as T)) return saved as T;
    }
  } catch { /* Preferences remain usable when browser storage is unavailable. */ }
  return fallback;
}

export function useUIPreferences() {
  const [lang, setLang] = useState<Lang>(() => readPreference("cx_lang", ["cxLang", "cx-lang", "lang"], ["zh", "en"], "zh"));
  const [theme, setTheme] = useState<Theme>(() => readPreference("cx_theme", ["cxTheme", "cx-theme", "theme"], ["light", "dark"], "light"));

  useEffect(() => {
    const languageChanged = (event: Event) => {
      const value = (event as CustomEvent).detail?.lang;
      if (value === "zh" || value === "en") setLang(value);
    };
    const themeChanged = (event: Event) => {
      const value = (event as CustomEvent).detail?.theme;
      if (value === "light" || value === "dark") setTheme(value);
    };
    window.addEventListener("chuanxu-language-change", languageChanged);
    window.addEventListener("chuanxu-theme-change", themeChanged);
    return () => {
      window.removeEventListener("chuanxu-language-change", languageChanged);
      window.removeEventListener("chuanxu-theme-change", themeChanged);
    };
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.documentElement.dataset.lang = lang;
    try { for (const key of ["cxLang", "cx-lang", "lang"]) localStorage.setItem(key, lang); } catch { /* Optional storage. */ }
    window.ChuanxuUI?.applyLanguage(lang);
  }, [lang]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { for (const key of ["cxTheme", "cx-theme", "theme"]) localStorage.setItem(key, theme); } catch { /* Optional storage. */ }
    window.ChuanxuUI?.applyTheme(theme);
  }, [theme]);
  return { lang, setLang, theme, setTheme };
}
