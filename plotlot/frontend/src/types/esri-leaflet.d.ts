declare module "esri-leaflet" {
  import * as L from "leaflet";

  interface DynamicMapLayerOptions extends L.LayerOptions {
    url: string;
    layers?: number[];
    opacity?: number;
    f?: string;
  }

  function dynamicMapLayer(options: DynamicMapLayerOptions): L.Layer;
}
