/* MathJax 3 + pymdownx.arithmatex 的标准接线（Material 官方写法）：
   只处理 arithmatex 标注的元素，页面切换（instant navigation）后重排版。 */
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex"
  }
};

document$.subscribe(() => {
  // CDN 加载失败/滞后时 window.MathJax 仍是上面的配置对象，无 startup——跳过即可，
  // 首次加载成功时 MathJax 会自行完成排版（未启用 instant navigation，无需重排）。
  if (!window.MathJax.startup) return;
  MathJax.startup.output.clearCache();
  MathJax.typesetClear();
  MathJax.texReset();
  MathJax.typesetPromise();
});
