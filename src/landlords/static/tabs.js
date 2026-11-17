// On a phone the tabs are one line that scrolls sideways (styles.css). If the current page's tab starts out of sight
// at the end of that line, scroll the line, and only the line, so that it shows.
"use strict";
(function () {
  const nav = document.querySelector("nav.tabs");
  const tab = nav && nav.querySelector("[aria-current=page]");
  if (!tab || nav.scrollWidth <= nav.clientWidth) return;
  const pad = parseFloat(getComputedStyle(nav).scrollPaddingInlineEnd) || 0;
  const over = tab.getBoundingClientRect().right + pad - nav.getBoundingClientRect().right;
  if (over > 0) nav.scrollLeft += over;
})();
