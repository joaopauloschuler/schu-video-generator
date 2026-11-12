// Written by vidgen, not part of chart.js: an ES module for the package's UMD build.
// Importing ./chart.umd.min.js (chart.js 4.6.1, unmodified) runs it, which sets globalThis.Chart;
// this module exports that object as the default and each of its names.
import './chart.umd.min.js';

const lib = globalThis.Chart;
export default lib;
export const {
  Animation, Animations, ArcElement, BarController, BarElement, BasePlatform, BasicPlatform, BubbleController,
  CategoryScale, Chart, Colors, DatasetController, Decimation, DomPlatform, DoughnutController, Element, Filler,
  Interaction, Legend, LineController, LineElement, LinearScale, LogarithmicScale, PieController, PointElement,
  PolarAreaController, RadarController, RadialLinearScale, Scale, ScatterController, SubTitle, Ticks, TimeScale,
  TimeSeriesScale, Title, Tooltip, _adapters, _detectPlatform, animator, controllers, defaults, elements, getChart,
  helpers, instances, layouts, overrides, platforms, registry, version,
} = lib;
