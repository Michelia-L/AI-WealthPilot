/**
 * Minimal type declarations for plotly.js-dist-min (the package ships no types).
 * Only the surface we actually use is declared.
 */
declare module "plotly.js-dist-min" {
  export interface PlotlyHTMLElement extends HTMLElement {}

  export interface PlotlyStatic {
    react(
      root: HTMLElement,
      data: unknown[],
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>
    ): Promise<PlotlyHTMLElement>;
    purge(root: HTMLElement): void;
  }

  const Plotly: PlotlyStatic;
  export default Plotly;
}
