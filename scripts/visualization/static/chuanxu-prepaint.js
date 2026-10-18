/* Resolve explicit product preferences before the first paint. */
(function () {
  "use strict";
  var root = document.documentElement;
  var lang = "zh";
  var theme = "light";
  try {
    var query = new URLSearchParams(window.location.search);
    var queryLang = query.get("cx_lang");
    var queryTheme = query.get("cx_theme");
    var storage = window.localStorage;
    var preferenceVersion = root.getAttribute("data-cx-version") || "4.1.0";
    // An upgrade migrates aliases while preserving the user's choice.
    storage.setItem("cx-ui-preferences-version", preferenceVersion);
    var savedLang = storage.getItem("cxLang") || storage.getItem("cx-lang") || storage.getItem("lang");
    var savedTheme = storage.getItem("cxTheme") || storage.getItem("cx-theme") || storage.getItem("theme");
    if (savedLang === "en") lang = "en";
    if (savedTheme === "dark") theme = "dark";
    if (queryLang === "en" || queryLang === "zh") lang = queryLang;
    if (queryTheme === "dark" || queryTheme === "light") theme = queryTheme;
    ["cxLang", "cx-lang", "lang"].forEach(function (key) { storage.setItem(key, lang); });
    ["cxTheme", "cx-theme", "theme"].forEach(function (key) { storage.setItem(key, theme); });
  } catch (_) {}
  root.setAttribute("data-lang", lang);
  root.setAttribute("data-theme", theme);
  root.setAttribute("lang", lang === "zh" ? "zh-CN" : "en");
}());
